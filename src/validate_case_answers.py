import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path


CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "cases"
    / "comparison_cases.json"
)


def parse_money(value):
    if not isinstance(value, str):
        raise ValueError("金额必须是字符串")

    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ValueError("金额无法解析") from None

    if not amount.is_finite():
        raise ValueError("金额必须是有限数值")

    if value != format(amount, ".2f"):
        raise ValueError("金额必须采用两位小数的规范格式")

    return amount


def monthly_amounts(rows):
    if not isinstance(rows, list):
        raise ValueError("月份数据必须是列表")

    amounts = {}

    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("每条月份记录必须是对象")

        if set(row) != {
            "user_id",
            "order_count",
            "total_amount",
        }:
            raise ValueError("月份记录字段不符合要求")

        user_id = row["user_id"]
        order_count = row["order_count"]

        if type(user_id) is not int or user_id <= 0:
            raise ValueError("用户编号必须是正整数")

        if user_id in amounts:
            raise ValueError("同一月份出现重复用户")

        if type(order_count) is not int or order_count <= 0:
            raise ValueError("订单数必须是正整数")

        amount = parse_money(row["total_amount"])

        if amount < 0:
            raise ValueError("本练习的订单金额不能为负数")

        amounts[user_id] = amount

    return amounts


def calculate_answer(months):
    if not isinstance(months, dict):
        raise ValueError("months 必须是对象")

    if set(months) != {"9", "10"}:
        raise ValueError("months 必须且只能包含9和10")

    previous = monthly_amounts(months["9"])
    current = monthly_amounts(months["10"])

    users = sorted(set(previous) | set(current))
    rows = []
    declines = []

    for user_id in users:
        before = previous.get(user_id, Decimal("0.00"))
        after = current.get(user_id, Decimal("0.00"))
        change = after - before

        rows.append({
            "user_id": user_id,
            "previous_amount": format(before, ".2f"),
            "current_amount": format(after, ".2f"),
            "change_amount": format(change, ".2f"),
        })

        if change < 0:
            declines.append((change, user_id))

    # 变化最负的用户下降最多；
    # 变化相同时，选择编号最小的用户。
    decline_user = min(declines)[1] if declines else None

    return rows, decline_user


def validate_expected_rows(rows):
    if not isinstance(rows, list):
        raise ValueError("expected_rows 必须是列表")

    user_ids = []

    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("参考答案行必须是对象")

        if set(row) != {
            "user_id",
            "previous_amount",
            "current_amount",
            "change_amount",
        }:
            raise ValueError("参考答案行字段不符合要求")

        user_id = row["user_id"]

        if type(user_id) is not int or user_id <= 0:
            raise ValueError("参考用户编号必须是正整数")

        user_ids.append(user_id)

        for field in (
            "previous_amount",
            "current_amount",
            "change_amount",
        ):
            parse_money(row[field])

    if user_ids != sorted(set(user_ids)):
        raise ValueError("参考用户必须唯一且按编号升序排列")


def main():
    try:
        cases = json.loads(
            CONFIG_PATH.read_text(encoding="utf-8-sig")
        )

        if not isinstance(cases, list) or not cases:
            raise ValueError("配置必须是非空列表")

    except (OSError, ValueError) as exc:
        print("配置读取失败：", exc)
        return 1

    passed = 0
    seen_ids = set()

    for index, case in enumerate(cases, start=1):
        name = f"第{index}个场景"

        try:
            if not isinstance(case, dict):
                raise ValueError("场景必须是对象")

            name = case["id"]

            if not isinstance(name, str) or not name.strip():
                raise ValueError("场景ID必须是非空字符串")

            if name in seen_ids:
                raise ValueError("场景ID重复")

            seen_ids.add(name)

            calculated_rows, calculated_user = calculate_answer(
                case["months"]
            )

            validate_expected_rows(case["expected_rows"])

            expected_user = case["expected_decline_user"]

            if (
                expected_user is not None
                and type(expected_user) is not int
            ):
                raise ValueError("参考下降用户必须是整数或null")

            rows_correct = (
                case["expected_rows"] == calculated_rows
            )
            user_correct = expected_user == calculated_user
            valid = rows_correct and user_correct

            print(f"\n{'通过' if valid else '失败'}：{name}")

            if not rows_correct:
                print("参考金额或用户列表与重新计算结果不一致。")
                print("重新计算结果：")
                print(json.dumps(
                    calculated_rows,
                    ensure_ascii=False,
                    indent=2,
                ))

            if not user_correct:
                print("参考下降用户：", expected_user)
                print("重新计算下降用户：", calculated_user)

            if valid:
                passed += 1

        except (ValueError, KeyError, TypeError) as exc:
            print(f"\n失败：{name}")
            print("原因：", exc)

    print(f"\n参考答案校验：{passed}/{len(cases)} 通过")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
