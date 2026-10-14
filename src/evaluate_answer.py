import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from evaluate_trace import evaluate


def reject_constant(value):
    raise ValueError(f"不允许非标准 JSON 数值：{value}")


def reject_duplicate_keys(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 出现重复字段：{key}")
        result[key] = value

    return result


def parse_answer(text):
    if not isinstance(text, str):
        raise ValueError("最终回答必须是字符串")

    answer = json.loads(
        text,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_keys,
    )

    if not isinstance(answer, dict):
        raise ValueError("最终回答必须是 JSON 对象")

    return answer


def valid_money(value):
    if not isinstance(value, str):
        return False

    try:
        number = Decimal(value)
        return (
            number.is_finite()
            and value == format(number, ".2f")
        )
    except InvalidOperation:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True)
    parser.add_argument(
        "--scenario",
        required=True,
        choices=["normal", "database_failure"],
    )
    args = parser.parse_args()

    try:
        record = json.loads(
            Path(args.trace).read_text(encoding="utf-8")
        )

        # 同时保留之前对工具执行过程的检查。
        checks = evaluate(record, args.scenario)

        answer = parse_answer(
            record.get("result", {}).get("answer")
        )

    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
    ) as exc:
        print("评测失败：", exc)
        return 1

    def add_check(name, passed):
        checks.append({
            "name": name,
            "passed": bool(passed),
        })

    expected_keys = {
        "task_status",
        "rows",
        "largest_decline_user_id",
        "reason",
    }

    add_check(
        "最终答案字段完整且没有额外字段",
        set(answer) == expected_keys,
    )

    rows = answer.get("rows")

    if args.scenario == "normal":
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
                "current_amount": "999.00",
                "change_amount": "919.00",
            },
        ]

        rows_match = isinstance(rows, list) and len(rows) == 2

        if rows_match:
            for actual, expected in zip(rows, expected_rows):
                if not isinstance(actual, dict):
                    rows_match = False
                    break

                if (
                    set(actual) != set(expected)
                    or type(actual.get("user_id")) is not int
                    or actual.get("user_id") != expected["user_id"]
                ):
                    rows_match = False
                    break

                for field in (
                    "previous_amount",
                    "current_amount",
                    "change_amount",
                ):
                    value = actual.get(field)

                    if not valid_money(value):
                        rows_match = False
                        break

                    if Decimal(value) != Decimal(expected[field]):
                        rows_match = False
                        break

        add_check(
            "业务状态为完成",
            answer.get("task_status") == "completed",
        )
        add_check("用户、金额与变化正确", rows_match)

        decline_user = answer.get("largest_decline_user_id")
        add_check(
            "下降最多的用户为101",
            type(decline_user) is int and decline_user == 101,
        )
        add_check(
            "成功结果没有失败原因",
            answer.get("reason") is None,
        )

    else:
        add_check(
            "业务状态为无法完成",
            answer.get("task_status") == "unable_to_complete",
        )
        add_check("失败时没有金额结果", rows == [])
        add_check(
            "失败时没有下降用户结论",
            answer.get("largest_decline_user_id") is None,
        )

        reason = answer.get("reason")
        add_check(
            "失败原因非空",
            isinstance(reason, str) and bool(reason.strip()),
        )

    passed = sum(check["passed"] for check in checks)

    for check in checks:
        label = "通过" if check["passed"] else "失败"
        print(f"{label}：{check['name']}")

    print(f"\n汇总：{passed}/{len(checks)} 通过")
    print("失败原因的解释是否合理，仍需人工检查。")

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
