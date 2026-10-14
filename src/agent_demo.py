from project_paths import WORK_DIR
from tool_guard import ToolCallGuard
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from db_tools import failure, query_user_monthly_orders


MAX_ROUNDS = 6
MAX_TOOL_CALLS = 4



SYSTEM_PROMPT = """
你是订单数据分析助手。

规则：
1. 涉及实际订单数据时，必须使用工具取得数据，不得编造。
2. 缺少必要的年份或月份时，向用户澄清。
3. 工具失败不代表没有订单，不能把失败当成零。
4. 跨月比较时，比较两个月用户集合的并集。
5. 两个月查询均成功且数据完整时，
   某用户当月未出现在结果中，消费额按零计算。
6. 变化金额等于后一个月消费额减去前一个月消费额。
7. 数据足够后结束，不要重复查询相同月份。

最终回答必须是一个 JSON 对象。
不要输出 Markdown 代码块或 JSON 以外的文字。

成功完成分析时，格式为：
{
  "task_status": "completed",
  "rows": [
    {
      "user_id": 整数用户编号,
      "previous_amount": "前一个月金额",
      "current_amount": "后一个月金额",
      "change_amount": "后一个月减前一个月"
    }
  ],
  "largest_decline_user_id": 下降金额最大的用户编号或null,
  "reason": null
}

金额必须是保留两位小数的字符串。
rows 按 user_id 升序排列。
没有用户下降时，largest_decline_user_id 为 null。
若最大下降金额相同，选择 user_id 最小的用户。

因工具失败无法完成分析时，格式为：
{
  "task_status": "unable_to_complete",
  "rows": [],
  "largest_decline_user_id": null,
  "reason": "具体失败原因"
}

需要用户补充必要信息时，格式为：
{
  "task_status": "needs_clarification",
  "rows": [],
  "largest_decline_user_id": null,
  "reason": "需要用户补充的信息"
}

不得在失败时输出未经验证的用户金额或下降结论。
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_user_monthly_orders",
            "description": (
                "查询指定月份各用户的订单数与总消费额。"
                "仅返回该月有订单的用户。"
                "金额为十进制字符串。"
                "成功但没有订单时返回空列表；失败返回错误。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "minimum": 2000,
                        "maximum": 2100,
                        "description": "查询年份",
                    },
                    "month": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 12,
                        "description": "查询月份",
                    },
                },
                "required": ["year", "month"],
                "additionalProperties": False,
            },
        },
    }
]


def request_model(messages):
    """发送一次模型请求，返回模型消息及使用统计。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY。")

    base_url = os.environ.get(
        "DEEPSEEK_BASE_URL",
        "https://api.deepseek.com",
    ).rstrip("/")

    model = os.environ.get(
        "DEEPSEEK_MODEL",
        "deepseek-flash",
    )

    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
        "thinking": {"type": "disabled"},
        "max_tokens": 2048,
    }

    request = Request(
        url=f"{base_url}/chat/completions",
        data=json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=120) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as exc:
        raise RuntimeError(
            f"模型请求失败，HTTP 状态码：{exc.code}"
        ) from None

    except URLError:
        raise RuntimeError(
            "模型网络连接失败，请检查网络和接口地址。"
        ) from None

    except TimeoutError:
        raise RuntimeError("模型请求超时。") from None

    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RuntimeError("模型响应不是有效 JSON。") from None

    choices = result.get("choices")

    if not isinstance(choices, list) or not choices:
        raise RuntimeError("模型响应中没有 choices。")

    choice = choices[0]

    if choice.get("finish_reason") == "length":
        raise RuntimeError("模型输出被截断，本次停止执行。")

    message = choice.get("message")

    if not isinstance(message, dict):
        raise RuntimeError("模型响应中没有有效 message。")

    if message.get("role") != "assistant":
        raise RuntimeError("模型返回的消息角色异常。")

    return {
        "message": message,
        "usage": result.get("usage", {}),
        "model": result.get("model"),
    }


def execute_tool(call):
    """通过白名单分派工具，并检查参数结构。"""
    function = call.get("function")

    if call.get("type") != "function" or not isinstance(
        function, dict
    ):
        return failure(
            "INVALID_TOOL_CALL",
            "工具调用格式不正确。",
        )

    name = function.get("name")

    if name != "query_user_monthly_orders":
        return failure(
            "UNKNOWN_TOOL",
            "该工具未注册，不允许执行。",
        )

    try:
        arguments = json.loads(
            function.get("arguments", "")
        )
    except (json.JSONDecodeError, TypeError):
        return failure(
            "INVALID_ARGUMENT",
            "工具参数必须是有效 JSON。",
        )

    if not isinstance(arguments, dict):
        return failure(
            "INVALID_ARGUMENT",
            "工具参数必须是 JSON 对象。",
        )

    if set(arguments) != {"year", "month"}:
        return failure(
            "INVALID_ARGUMENT",
            "参数必须且只能包含 year 和 month。",
        )

    # 函数内部继续校验整数类型、年份和月份范围。
    return query_user_monthly_orders(
        year=arguments["year"],
        month=arguments["month"],
    )


def run_agent(task, trace):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    call_count = 0
    seen_call_ids = set()
    tool_guard = ToolCallGuard()

    for round_number in range(1, MAX_ROUNDS + 1):
        print(f"\n=== 第 {round_number} 轮模型请求 ===")

        started_at = time.perf_counter()
        response = request_model(messages)
        elapsed = time.perf_counter() - started_at

        message = response["message"]

        # 保存模型消息，保留工具调用的关联信息。
        messages.append(message)

        trace.append({
            "event": "model_response",
            "round": round_number,
            "elapsed_seconds": round(elapsed, 3),
            "model": response["model"],
            "usage": response["usage"],
            "message": message,
        })

        calls = message.get("tool_calls") or []

        if not isinstance(calls, list):
            raise RuntimeError("tool_calls 格式异常。")

        # 没有工具调用：模型结束本轮任务。
        if not calls:
            answer = message.get("content")

            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("模型没有返回有效最终回答。")

            return {
                "status": "finished",
                "answer": answer,
                "tool_call_count": call_count,
            }

        # 执行前检查本轮是否超出调用预算。
        if call_count + len(calls) > MAX_TOOL_CALLS:
            return {
                "status": "stopped",
                "reason": "TOOL_CALL_LIMIT",
                "answer": None,
                "tool_call_count": call_count,
            }

        # 先验证整批调用 ID，避免执行一半才发现格式问题。
        batch_ids = set()

        for call in calls:
            if not isinstance(call, dict):
                raise RuntimeError("工具调用条目格式异常。")

            call_id = call.get("id")

            if (
                not isinstance(call_id, str)
                or not call_id
                or call_id in batch_ids
                or call_id in seen_call_ids
            ):
                raise RuntimeError("工具调用 ID 缺失或重复。")

            batch_ids.add(call_id)

        seen_call_ids.update(batch_ids)

        # 第一版按顺序执行，即使模型一次提出多个调用。
        for call in calls:
            call_count += 1
            function = call.get("function") or {}

            print("模型选择工具：", function.get("name"))
            print("模型提供参数：", function.get("arguments"))

            started_at = time.perf_counter()
            result, duplicate_blocked = tool_guard.execute(
                call,
                execute_tool,
            )
            tool_elapsed = time.perf_counter() - started_at

            print("工具返回：")
            print(json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            ))

            trace.append({
                "event": "tool_result",
                "duplicate_blocked": duplicate_blocked,
                "round": round_number,
                "call_id": call["id"],
                "tool": function.get("name"),
                "arguments": function.get("arguments"),
                "elapsed_seconds": round(tool_elapsed, 3),
                "result": result,
            })

            # 每个结果必须关联对应的模型调用 ID。
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(
                    result,
                    ensure_ascii=False,
                ),
            })

    return {
        "status": "stopped",
        "reason": "ROUND_LIMIT",
        "answer": None,
        "tool_call_count": call_count,
    }


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="运行订单分析 Agent"
    )

    parser.add_argument(
        "--task",
        default=(
            "查询2026年9月和10月各用户的消费额，"
            "计算10月相对9月的变化金额，"
            "找出下降金额最大的用户。"
        ),
        help="交给 Agent 的任务",
    )

    args = parser.parse_args()
    task = args.task

    trace = []
    print("用户任务：", task)

    try:
        result = run_agent(task, trace)

    except RuntimeError as exc:
        result = {
            "status": "failed",
            "reason": str(exc),
            "answer": None,
        }

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    file_name = (
        "agent_run_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid4().hex[:8]
        + ".json"
    )

    trace_path = WORK_DIR / file_name

    trace_path.write_text(
        json.dumps(
            {
                "task": task,
                "result": result,
                "trace": trace,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== 执行结果 ===")
    print("状态：", result["status"])

    if result["status"] == "finished":
        print("\n最终回答：")
        print(result["answer"])
        print("\n注意：执行结束，答案正确性仍需核验。")
    else:
        print("停止或失败原因：", result.get("reason"))

    print("\n执行记录：", trace_path)

    return 0 if result["status"] == "finished" else 1


if __name__ == "__main__":
    sys.exit(main())
