import json

from db_tools import failure


class ToolCallGuard:
    """在一次任务内，阻止相同工具和参数被重复执行。"""

    def __init__(self):
        self._seen = set()

    def execute(self, call, executor):
        function = call.get("function")

        if not isinstance(function, dict):
            return executor(call), False

        name = function.get("name")

        # 只保护当前注册的只读查询工具。
        if name != "query_user_monthly_orders":
            return executor(call), False

        try:
            arguments = json.loads(
                function.get("arguments", "")
            )
        except (json.JSONDecodeError, TypeError):
            return executor(call), False

        if not isinstance(arguments, dict):
            return executor(call), False

        # 参数顺序不同，但内容相同，也视为同一调用。
        key = (
            name,
            json.dumps(
                arguments,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )

        if key in self._seen:
            return failure(
                "DUPLICATE_TOOL_CALL",
                "本任务已尝试过相同查询，请使用已有结果；"
                "若已有结果失败，请停止或说明无法完成。",
            ), True

        self._seen.add(key)
        return executor(call), False
