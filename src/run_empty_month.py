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
        # 查询成功，但这个月没有任何订单。
        return {
            "ok": True,
            "data": [],
            "error": None,
        }

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
        "empty_month_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid4().hex[:8]
        + ".json"
    )

    trace_path.write_text(
        json.dumps(
            {
                "scenario": "successful_empty_month",
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

        tool_events = [
            event for event in trace
            if event.get("event") == "tool_result"
        ]

        observed_months = []
        tool_results_match = len(tool_events) == 2

        for event in tool_events:
            arguments = json.loads(event["arguments"])

            if (
                event.get("tool") != "query_user_monthly_orders"
                or not isinstance(arguments, dict)
                or set(arguments) != {"year", "month"}
                or type(arguments["year"]) is not int
                or type(arguments["month"]) is not int
            ):
                tool_results_match = False
                continue

            year = arguments["year"]
            month = arguments["month"]
            observed_months.append((year, month))

            if (
                year != 2026
                or month not in (9, 10)
                or event["result"] != injected_query(year, month)
            ):
                tool_results_match = False

        tool_results_match = (
            tool_results_match
            and sorted(observed_months)
            == [(2026, 9), (2026, 10)]
        )

        expected_rows = [
            {
                "user_id": 101,
                "previous_amount": "300.00",
                "current_amount": "0.00",
                "change_amount": "-300.00",
            },
            {
                "user_id": 102,
                "previous_amount": "80.00",
                "current_amount": "0.00",
                "change_amount": "-80.00",
            },
        ]

        rows = answer.get("rows")
        rows_match = (
            isinstance(rows, list)
            and rows == expected_rows
            and all(
                isinstance(row, dict)
                and type(row.get("user_id")) is int
                for row in rows
            )
        )

        decline_user = answer.get("largest_decline_user_id")

        checks = [
            (
                "两个月各查询一次，返回结果符合注入数据",
                tool_results_match,
            ),
            (
                "答案字段完整且没有额外字段",
                set(answer) == {
                    "task_status",
                    "rows",
                    "largest_decline_user_id",
                    "reason",
                },
            ),
            (
                "业务状态为完成",
                answer.get("task_status") == "completed",
            ),
            (
                "正确将成功空月份按零计算",
                rows_match,
            ),
            (
                "下降最多的用户为101",
                type(decline_user) is int and decline_user == 101,
            ),
            (
                "没有错误报告查询失败",
                answer.get("reason") is None,
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

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
