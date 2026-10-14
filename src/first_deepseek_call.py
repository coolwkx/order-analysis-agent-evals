import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    # 1. 读取当前终端提供的配置
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    base_url = os.environ.get(
        "DEEPSEEK_BASE_URL",
        "https://api.deepseek.com",
    ).rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")

    if not api_key:
        print("配置错误：没有设置 DEEPSEEK_API_KEY。")
        print("请在当前 PowerShell 中设置密钥后重新运行。")
        return 1

    # 2. 构造请求地址和请求内容
    endpoint = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是一位中文 Python 学习助手，请简洁回答。",
            },
            {
                "role": "user",
                "content": "请用三句话解释：函数、API 和工具调用有什么区别？",
            },
        ],
        "stream": False,
        "max_tokens": 1024,
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = Request(
        url=endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    print("请求地址：", endpoint)
    print("请求模型：", model)
    print("正在等待模型响应……")

    started_at = time.perf_counter()

    # 3. 发送请求并解析响应
    try:
        with urlopen(request, timeout=120) as response:
            raw_body = response.read().decode("utf-8")
            result = json.loads(raw_body)

    except HTTPError as exc:
        print(f"\n请求失败，HTTP 状态码：{exc.code}")

        hints = {
            400: "检查请求参数和模型名称。",
            401: "检查 API Key 是否有效，是否来自 DeepSeek 官方平台。",
            402: "检查账户余额。",
            404: "检查接口地址，并查看官方文档中的模型与路径。",
            429: "请求受到限制，请稍后再试。",
            500: "服务端异常，请稍后再试。",
            503: "服务暂时不可用，请稍后再试。",
        }

        print(hints.get(exc.code, "请检查接口配置与服务状态。"))
        return 1

    except URLError as exc:
        print("\n网络连接失败：", exc.reason)
        print("检查网络、代理设置，以及是否能访问官方服务。")
        return 1

    except TimeoutError:
        print("\n请求超时，本次没有自动重试。")
        return 1

    except (json.JSONDecodeError, UnicodeDecodeError):
        print("\n响应解析失败：没有收到预期的 JSON 数据。")
        return 1

    elapsed = time.perf_counter() - started_at

    # 4. 提取最终回答
    choices = result.get("choices")

    if not isinstance(choices, list) or not choices:
        print("\n响应结构异常：没有找到 choices。")
        return 1

    choice = choices[0]
    message = choice.get("message") or {}
    answer = message.get("content")
    finish_reason = choice.get("finish_reason")

    print(f"\n响应耗时：{elapsed:.2f} 秒")
    print("返回模型：", result.get("model", "未提供"))
    print("结束原因：", finish_reason)

    if not isinstance(answer, str) or not answer.strip():
        print("\n已收到响应，但没有非空的最终回答。")
        print("这次暂不计为验证通过。")
        print("如果结束原因为 length，可能是输出预算不足。")
        return 1

    print("\n=== 模型回答 ===")
    print(answer)

    print("\n=== Token 使用情况 ===")
    print(json.dumps(
        result.get("usage", {}),
        ensure_ascii=False,
        indent=2,
    ))

    if finish_reason == "length":
        print("\n回答可能被截断，本次暂不计为完整验证通过。")
        return 1

    print("\n首次调用验证通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
