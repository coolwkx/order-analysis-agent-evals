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

        model_events = [
            event for event in trace
            if event.get("event") == "model_response"
        ]

        tool_events = [
            event for event in trace
            if event.get("event") == "tool_result"
        ]

        no_tool_requests = bool(model_events) and all(
            isinstance(event.get("message"), dict)
            and not event["message"].get("tool_calls")
            for event in model_events
        )

        reason = answer.get("reason")

        checks = [
            (
                "程序正常结束",
                result.get("status") == "finished",
            ),
            (
                "没有提出或执行工具调用",
                no_tool_requests and len(tool_events) == 0,
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
                "业务状态为需要澄清",
                answer.get("task_status")
                == "needs_clarification",
            ),
            (
                "没有输出金额或下降结论",
                answer.get("rows") == []
                and answer.get("largest_decline_user_id") is None,
            ),
            (
                "澄清信息非空",
                isinstance(reason, str) and bool(reason.strip()),
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
    print("人工检查：是否明确请求补充两个具体年月。")

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
