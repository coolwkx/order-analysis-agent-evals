import json
from unittest.mock import patch

import agent_demo


def model_response(message):
    return {
        "message": message,
        "usage": {},
        "model": "scripted-test",
    }


def tool_call(call_id, arguments):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "query_user_monthly_orders",
                    "arguments": arguments,
                },
            }
        ],
    }


def main():
    trace = []

    # 第一次查询九月；第二次用不同的参数顺序重复查询。
    # 调用 ID 不同，避免触发另一项“重复 ID”检查。
    responses = [
        model_response(
            tool_call(
                "call_test_1",
                '{"year":2026,"month":9}',
            )
        ),
        model_response(
            tool_call(
                "call_test_2",
                '{"month":9,"year":2026}',
            )
        ),
        model_response({
            "role": "assistant",
            "content": json.dumps({
                "task_status": "completed",
                "rows": [],
                "largest_decline_user_id": None,
                "reason": None,
            }),
        }),
    ]

    fake_result = {
        "ok": True,
        "data": [],
        "error": None,
    }

    # 替换模型请求和工具执行器。
    # 不访问真实模型，不连接数据库。
    with (
        patch.object(
            agent_demo,
            "request_model",
            side_effect=responses,
        ) as mocked_model,
        patch.object(
            agent_demo,
            "execute_tool",
            return_value=fake_result,
        ) as mocked_executor,
    ):
        result = agent_demo.run_agent(
            "重复调用保护集成测试",
            trace,
        )

        tool_events = [
            event for event in trace
            if event.get("event") == "tool_result"
        ]

        events_valid = len(tool_events) == 2

        first_allowed = (
            events_valid
            and tool_events[0].get("duplicate_blocked") is False
            and tool_events[0]["result"]["ok"] is True
        )

        second_blocked = (
            events_valid
            and tool_events[1].get("duplicate_blocked") is True
            and tool_events[1]["result"]["ok"] is False
            and tool_events[1]["result"]["error"]["code"]
            == "DUPLICATE_TOOL_CALL"
        )

        # 检查第三轮模型看到的对话中，
        # 是否包含第二次调用的拦截结果。
        third_messages = (
            mocked_model.call_args_list[2].args[0]
            if mocked_model.call_count == 3
            else []
        )

        duplicate_feedback = [
            message
            for message in third_messages
            if message.get("role") == "tool"
            and message.get("tool_call_id") == "call_test_2"
        ]

        feedback_valid = (
            len(duplicate_feedback) == 1
            and json.loads(
                duplicate_feedback[0]["content"]
            )["error"]["code"] == "DUPLICATE_TOOL_CALL"
        )

        checks = [
            (
                "完整循环正常结束",
                result["status"] == "finished",
            ),
            (
                "模型请求共三轮",
                mocked_model.call_count == 3,
            ),
            (
                "真实执行入口只被调用一次",
                mocked_executor.call_count == 1,
            ),
            (
                "首次调用执行，重复调用被拦截",
                first_allowed and second_blocked,
            ),
            (
                "拦截结果正确反馈给模型",
                feedback_valid,
            ),
            (
                "重复请求仍计入调用预算",
                result["tool_call_count"] == 2,
            ),
        ]

    passed = 0

    for name, valid in checks:
        print(f"{'通过' if valid else '失败'}：{name}")
        passed += int(valid)

    print(f"\n集成测试：{passed}/{len(checks)} 通过")
    print("本测试验证控制流程，不评价模拟回答的业务正确性。")

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
