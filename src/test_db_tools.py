import json
import logging

from db_tools import query_user_monthly_orders


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    cases = [
        {
            "name": "九月正常查询",
            "year": 2026,
            "month": 9,
            "expected_data": [
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
        },
        {
            "name": "十月正常查询",
            "year": 2026,
            "month": 10,
            "expected_data": [
                {
                    "user_id": 102,
                    "order_count": 1,
                    "total_amount": "999.00",
                },
            ],
        },
        {
            "name": "七月没有数据",
            "year": 2026,
            "month": 7,
            "expected_data": [],
        },
        {
            "name": "十二月查询冒烟检查",
            "year": 2026,
            "month": 12,
            "expected_data": [],
        },
        {
            "name": "月份越界",
            "year": 2026,
            "month": 13,
            "expected_error": "INVALID_ARGUMENT",
        },
        {
            "name": "月份类型错误",
            "year": 2026,
            "month": "9",
            "expected_error": "INVALID_ARGUMENT",
        },
        {
            "name": "拒绝布尔值",
            "year": 2026,
            "month": True,
            "expected_error": "INVALID_ARGUMENT",
        },
    ]

    passed = 0

    for case in cases:
        result = query_user_monthly_orders(
            case["year"],
            case["month"],
        )

        if "expected_error" in case:
            valid = (
                result["ok"] is False
                and result["data"] is None
                and result["error"]["code"]
                == case["expected_error"]
            )
        else:
            valid = (
                result["ok"] is True
                and result["data"] == case["expected_data"]
                and result["error"] is None
            )

        print(f"\n{'通过' if valid else '失败'}：{case['name']}")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        if valid:
            passed += 1

    print(f"\n汇总：{passed}/{len(cases)} 通过")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
