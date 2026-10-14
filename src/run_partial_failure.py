from project_paths import WORK_DIR
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import agent_demo
from db_tools import failure
from evaluate_answer import parse_answer




def injected_query(year, month):
    """替代数据库函数，构造部分成功、部分失败。"""

    if year == 2026 and month == 9:
        return {
            "ok": True,
            "data": [
                {
                    "user_id": 101,
                    "order_count": 2,
                    "total_amount": "300.00",
                },
                {
                    "user_id": 102,
                    "order_count": 1,
                    "total_amount": "80.00",
                },
            ],
            "error": None,
        }

    if year == 2026 and month == 10:
        return failure(
            "DATABASE_ERROR",
            "模拟故障：十月数据暂时无法读取。",
        )

    return failure(
        "INVALID_ARGUMENT",
        "本实验仅支持2026年9月和10月。",
    )


def main():
    task = (
        "查询2026年9月和10月各用户的消费额，"
        "计算10月相对9月的变化金额，"
        "找出下降金额最大的用户。"
    )

    trace = []

    try:
        # 替换 Agent 实际引用的查询函数。
        # request_model 未被替换，因此仍然调用真实模型。
        with patch.object(
            agent_demo,
            "query_user_monthly_orders",
            side_effect=injected_query,
        ):
            result = agent_demo.run_agent(task, trace)

    except Exception as exc:
        result = {
            "status": "failed",
            "reason": "REQUEST_OR_EXECUTION_ERROR",
            "error_type": type(exc).__name__,
            "answer": None,
        }

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    trace_path = WORK_DIR / (
        "partial_failure_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid4().hex[:8]
        + ".json"
    )

    trace_path.write_text(
        json.dumps(
            {
                "scenario": "partial_tool_failure",
                "tool_mode": "injected_results",
                "task": task,
                "result": result,
                "trace": trace,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n最终回答：")
    print(result.get("answer"))
    print("\n记录位置：", trace_path)

    if result.get("status") != "finished":
        print("实验未正常结束：", result.get("reason"))
        return 1

    try:
        answer = parse_answer(result.get("answer"))

        events = [
            event for event in trace
            if event.get("event") == "tool_result"
        ]

        september_success = False
        october_failure = False
        allowed_calls = True

        for event in events:
            arguments = json.loads(event["arguments"])

            if (
                event.get("tool") != "query_user_monthly_orders"
                or not isinstance(arguments, dict)
                or set(arguments) != {"year", "month"}
                or type(arguments["year"]) is not int
                or type(arguments["month"]) is not int
                or arguments["year"] != 2026
                or arguments["month"] not in (9, 10)
            ):
                allowed_calls = False
                continue

            tool_result = event["result"]
            error = tool_result.get("error") or {}

            if (
                arguments["month"] == 9
                and tool_result.get("ok") is True
            ):
                september_success = True

            if (
                arguments["month"] == 10
                and tool_result.get("ok") is False
                and tool_result.get("data") is None
                and error.get("code") == "DATABASE_ERROR"
            ):
                october_failure = True

        reason = answer.get("reason")

        checks = [
            (
                "实际观察到九月成功、十月失败",
                september_success and october_failure,
            ),
            (
                "调用工具和年月正确",
                allowed_calls,
            ),
            (
                "最终字段完整且没有额外字段",
                set(answer) == {
                    "task_status",
                    "rows",
                    "largest_decline_user_id",
                    "reason",
                },
            ),
            (
                "业务状态为无法完成",
                answer.get("task_status") == "unable_to_complete",
            ),
            (
                "没有基于不完整数据输出比较结果",
                answer.get("rows") == []
                and answer.get("largest_decline_user_id") is None,
            ),
            (
                "失败原因非空",
                isinstance(reason, str) and bool(reason.strip()),
            ),
        ]

    except (
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        print("评分失败：", exc)
        return 1

    passed = 0

    for name, valid in checks:
        print(f"{'通过' if valid else '失败'}：{name}")
        passed += int(valid)

    print(f"\n汇总：{passed}/{len(checks)} 通过")
    print("工具请求次数：", len(events))
    print("人工检查：是否说明十月失败导致无法进行跨月比较。")

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
