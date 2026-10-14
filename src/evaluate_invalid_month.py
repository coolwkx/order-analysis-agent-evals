import argparse
import json
import sys
from pathlib import Path

from evaluate_answer import parse_answer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True)
    args = parser.parse_args()

    try:
        record = json.loads(
            Path(args.trace).read_text(encoding="utf-8")
        )

        if not isinstance(record, dict):
            raise ValueError("记录必须是 JSON 对象")

        result = record.get("result")
        trace = record.get("trace")

        if not isinstance(result, dict):
            raise ValueError("result 必须是对象")

        if not isinstance(trace, list):
            raise ValueError("trace 必须是列表")

        if any(not isinstance(event, dict) for event in trace):
            raise ValueError("trace 条目必须是对象")

        answer = parse_answer(result.get("answer"))

        tool_events = [
            event for event in trace
            if event.get("event") == "tool_result"
        ]

        allowed_calls = True
        invalid_month_rejected = True
        invalid_month_calls = 0

        for event in tool_events:
            if event.get("tool") != "query_user_monthly_orders":
                allowed_calls = False
                continue

            arguments = json.loads(
                event.get("arguments", "")
            )

            if (
                not isinstance(arguments, dict)
                or set(arguments) != {"year", "month"}
                or type(arguments["year"]) is not int
                or type(arguments["month"]) is not int
            ):
                allowed_calls = False
                continue

            year = arguments["year"]
            month = arguments["month"]

            # 不允许模型擅自替换成其他年月。
            if year != 2026 or month not in (10, 13):
                allowed_calls = False

            if month == 13:
                invalid_month_calls += 1

                tool_result = event.get("result")

                if not isinstance(tool_result, dict):
                    invalid_month_rejected = False
                    continue

                error = tool_result.get("error") or {}

                if not isinstance(error, dict):
                    invalid_month_rejected = False
                    continue

                invalid_month_rejected = (
                    invalid_month_rejected
                    and tool_result.get("ok") is False
                    and tool_result.get("data") is None
                    and error.get("code") == "INVALID_ARGUMENT"
                )

        reason = answer.get("reason")

        checks = [
            (
                "程序正常结束",
                result.get("status") == "finished",
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
                "要求用户澄清",
                answer.get("task_status")
                == "needs_clarification",
            ),
            (
                "没有输出金额或下降结论",
                answer.get("rows") == []
                and answer.get("largest_decline_user_id") is None,
            ),
            (
                "澄清原因非空",
                isinstance(reason, str) and bool(reason.strip()),
            ),
            (
                "已执行的调用没有擅自替换年月或工具",
                allowed_calls,
            ),
            (
                "如调用13月，工具必须拒绝",
                invalid_month_rejected,
            ),
        ]

    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
    ) as exc:
        print("评测失败：", exc)
        return 1

    passed = 0

    for name, valid in checks:
        print(f"{'通过' if valid else '失败'}：{name}")
        passed += int(valid)

    print(f"\n汇总：{passed}/{len(checks)} 通过")
    print("实际工具调用次数：", len(tool_events))
    print("13月参数调用次数：", invalid_month_calls)

    if not tool_events:
        print("模型直接发现非法月份，没有执行工具。")
    elif invalid_month_calls:
        print("检查模型是否根据参数错误进行了有效恢复。")

    print("人工检查：是否明确指出13月无效并请求修正。")

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
