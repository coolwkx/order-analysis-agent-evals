import argparse
import json
import sys
from pathlib import Path


def evaluate(record, scenario):
    checks = []

    def add_check(name, passed):
        checks.append({
            "name": name,
            "passed": bool(passed),
        })

    trace = record.get("trace", [])
    result = record.get("result", {})

    tool_events = [
        event
        for event in trace
        if event.get("event") == "tool_result"
    ]

    # 验证调用了指定工具，参数对应两个目标月份。
    valid_calls = True
    queried_months = []
    tool_results = []

    for event in tool_events:
        if event.get("tool") != "query_user_monthly_orders":
            valid_calls = False

        try:
            arguments = json.loads(event.get("arguments", ""))

            if (
                not isinstance(arguments, dict)
                or set(arguments) != {"year", "month"}
                or type(arguments["year"]) is not int
                or type(arguments["month"]) is not int
            ):
                valid_calls = False
                continue

            queried_months.append(
                (arguments["year"], arguments["month"])
            )
            tool_results.append(
                (arguments["month"], event.get("result", {}))
            )

        except (json.JSONDecodeError, TypeError):
            valid_calls = False

    add_check("模型正常结束", result.get("status") == "finished")

    answer = result.get("answer")
    add_check(
        "最终回答非空",
        isinstance(answer, str) and bool(answer.strip()),
    )

    add_check("工具名称与参数结构正确", valid_calls)

    add_check(
        "九月和十月各查询一次，没有额外调用",
        len(tool_events) == 2
        and sorted(queried_months) == [
            (2026, 9),
            (2026, 10),
        ],
    )

    if scenario == "normal":
        expected = {
            9: [
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
            10: [
                {
                    "user_id": 102,
                    "order_count": 1,
                    "total_amount": "999.00",
                },
            ],
        }

        correct_results = len(tool_results) == 2

        for month, tool_result in tool_results:
            correct_results = correct_results and (
                month in expected
                and tool_result.get("ok") is True
                and tool_result.get("error") is None
                and tool_result.get("data") == expected.get(month)
            )

        add_check("两个月工具数据符合预期", correct_results)

    else:
        failure_results = len(tool_results) == 2

        for _, tool_result in tool_results:
            error = tool_result.get("error") or {}

            failure_results = failure_results and (
                tool_result.get("ok") is False
                and tool_result.get("data") is None
                and error.get("code") == "DATABASE_ERROR"
            )

        add_check(
            "两次查询均明确返回数据库失败",
            failure_results,
        )

    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        required=True,
        choices=["normal", "database_failure"],
    )
    parser.add_argument("--trace", required=True)
    args = parser.parse_args()

    path = Path(args.trace)

    try:
        record = json.loads(path.read_text(encoding="utf-8"))

        if not isinstance(record, dict):
            raise ValueError("记录根节点必须是 JSON 对象")

        checks = evaluate(record, args.scenario)

    except (OSError, ValueError, TypeError, AttributeError) as exc:
        print("评测记录读取或结构检查失败：", exc)
        return 1

    passed = sum(check["passed"] for check in checks)

    for check in checks:
        label = "通过" if check["passed"] else "失败"
        print(f"{label}：{check['name']}")

    print(f"\n自动检查：{passed}/{len(checks)} 通过")
    print("注意：本脚本没有自动判断最终回答的语义正确性。")

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
