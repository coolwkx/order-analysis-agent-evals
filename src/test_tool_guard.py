from tool_guard import ToolCallGuard


def make_call(call_id, arguments):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "query_user_monthly_orders",
            "arguments": arguments,
        },
    }


def main():
    executions = []

    def fake_executor(call):
        executions.append(call)
        return {
            "ok": True,
            "data": [],
            "error": None,
        }

    guard = ToolCallGuard()

    first_result, first_blocked = guard.execute(
        make_call("call_1", '{"year":2026,"month":9}'),
        fake_executor,
    )

    second_result, second_blocked = guard.execute(
        make_call("call_2", '{"month":9,"year":2026}'),
        fake_executor,
    )

    third_result, third_blocked = guard.execute(
        make_call("call_3", '{"year":2026,"month":10}'),
        fake_executor,
    )

    checks = [
        (
            "首次查询允许执行",
            first_result["ok"] is True
            and first_blocked is False,
        ),
        (
            "相同参数即使顺序不同也被拦截",
            second_blocked is True
            and second_result["error"]["code"]
            == "DUPLICATE_TOOL_CALL",
        ),
        (
            "不同月份允许执行",
            third_result["ok"] is True
            and third_blocked is False,
        ),
        (
            "执行器实际只执行两次",
            len(executions) == 2,
        ),
    ]

    # 新任务使用新的保护对象，不应沿用旧任务的记录。
    new_guard = ToolCallGuard()
    _, blocked = new_guard.execute(
        make_call("call_4", '{"year":2026,"month":9}'),
        fake_executor,
    )

    checks.append((
        "新任务可以重新查询相同月份",
        blocked is False and len(executions) == 3,
    ))

    passed = 0

    for name, valid in checks:
        print(f"{'通过' if valid else '失败'}：{name}")
        passed += int(valid)

    print(f"\n汇总：{passed}/{len(checks)} 通过")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
