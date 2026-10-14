from project_paths import OUTPUT_DIR, WORK_DIR
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from agent_demo import run_agent


SRC_DIR = Path(__file__).resolve().parent


CASES = [
    {
        "id": "normal",
        "task": (
            "查询2026年9月和10月各用户的消费额，"
            "计算10月相对9月的变化金额，"
            "找出下降金额最大的用户。"
        ),
        "evaluator": "evaluate_answer.py",
        "arguments": ["--scenario", "normal"],
    },
    {
        "id": "clarification",
        "task": (
            "比较两个具体月份的用户消费变化，"
            "但年份和月份尚未提供。请先向我确认时间范围。"
        ),
        "evaluator": "evaluate_clarification.py",
        "arguments": [],
    },
    {
        "id": "invalid_month",
        "task": (
            "比较2026年13月和2026年10月各用户的消费额变化，"
            "并找出下降金额最大的用户。"
        ),
        "evaluator": "evaluate_invalid_month.py",
        "arguments": [],
    },
]


def source_hashes():
    names = [
        "agent_demo.py",
        "db_tools.py",
        "tool_guard.py",
        "evaluate_trace.py",
        "evaluate_answer.py",
        "evaluate_clarification.py",
        "evaluate_invalid_month.py",
    ]

    return {
        name: hashlib.sha256(
            (SRC_DIR / name).read_bytes()
        ).hexdigest()
        for name in names
    }


def preflight():
    required_variables = [
        "DEEPSEEK_API_KEY",
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_DATABASE",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
    ]

    missing_variables = [
        name for name in required_variables
        if not os.environ.get(name, "").strip()
    ]

    required_files = [
        "agent_demo.py",
        "db_tools.py",
        "tool_guard.py",
        "evaluate_trace.py",
        "evaluate_answer.py",
        "evaluate_clarification.py",
        "evaluate_invalid_month.py",
    ]

    missing_files = [
        name for name in required_files
        if not (SRC_DIR / name).is_file()
    ]

    if missing_variables or missing_files:
        if missing_variables:
            print("缺少环境变量：", ", ".join(missing_variables))
        if missing_files:
            print("缺少文件：", ", ".join(missing_files))
        return False

    return True


def evaluate_case(case, trace_path):
    command = [
        sys.executable,
        str(SRC_DIR / case["evaluator"]),
        *case["arguments"],
        "--trace",
        str(trace_path),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
            },
            timeout=30,
        )

    except (OSError, subprocess.TimeoutExpired) as exc:
        return "error", str(exc)

    output = completed.stdout + completed.stderr

    if (
        completed.returncode not in (0, 1)
        or "Traceback (most recent call last)" in output
    ):
        return "error", output

    if completed.returncode == 0:
        return "passed", output

    return "failed", output


def metrics(trace, elapsed):
    model_events = [
        event for event in trace
        if event.get("event") == "model_response"
    ]
    tool_events = [
        event for event in trace
        if event.get("event") == "tool_result"
    ]

    total_tokens = 0
    usage_complete = bool(model_events)

    for event in model_events:
        usage = event.get("usage") or {}
        value = usage.get("total_tokens")

        if type(value) is int:
            total_tokens += value
        else:
            usage_complete = False

    blocked = sum(
        event.get("duplicate_blocked") is True
        for event in tool_events
    )

    return {
        "elapsed_seconds": round(elapsed, 3),
        "received_model_responses": len(model_events),
        "recorded_tool_requests": len(tool_events),
        "duplicate_blocked_count": blocked,
        "reported_total_tokens": total_tokens,
        "usage_complete": usage_complete,
    }


def main():
    if not preflight():
        return 1

    run_id = (
        datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid4().hex[:8]
    )

    run_dir = WORK_DIR / f"live_suite_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    hashes_before = source_hashes()
    summaries = []

    for case in CASES:
        print(f"\n========== 场景：{case['id']} ==========")
        print("任务：", case["task"])

        trace = []
        started_at = time.perf_counter()

        try:
            result = run_agent(case["task"], trace)

        except Exception as exc:
            # 保留异常类型，不将未处理异常当成任务成功。
            # 不保存可能包含敏感配置的异常全文。
            result = {
                "status": "failed",
                "reason": "UNHANDLED_OR_REQUEST_ERROR",
                "error_type": type(exc).__name__,
                "answer": None,
            }

        elapsed = time.perf_counter() - started_at
        trace_path = run_dir / f"{case['id']}.json"

        trace_path.write_text(
            json.dumps(
                {
                    "task": case["task"],
                    "result": result,
                    "trace": trace,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        if result.get("status") == "finished":
            evaluation_status, details = evaluate_case(
                case,
                trace_path,
            )
        else:
            evaluation_status = "error"
            details = (
                "Agent 未正常结束："
                + str(result.get("reason", result.get("status")))
            )

        summary = {
            "case_id": case["id"],
            "task": case["task"],
            "agent_status": result.get("status"),
            "evaluation_status": evaluation_status,
            "trace_path": str(trace_path),
            "metrics": metrics(trace, elapsed),
            "evaluation_details": details.strip(),
        }
        summaries.append(summary)

        print("\n评测结果：", evaluation_status)
        print(details.strip())
        print("记录：", trace_path)

    hashes_after = source_hashes()
    source_unchanged = hashes_before == hashes_after

    passed = sum(
        item["evaluation_status"] == "passed"
        for item in summaries
    )

    report = {
        "run_id": run_id,
        "evaluation_type": "fresh_agent_runs",
        "requested_model": os.environ.get(
            "DEEPSEEK_MODEL",
            "deepseek-flash",
        ),
        "source_hashes": hashes_before,
        "source_unchanged_during_run": source_unchanged,
        "total_cases": len(summaries),
        "passed_cases": passed,
        "cases": summaries,
        "limitations": [
            "每个场景只运行一次，不能证明稳定成功率。",
            "澄清问题和失败解释仍需要人工检查。",
            "Token统计只包含已收到并记录的响应。",
            "本次尚未包含数据库故障场景。",
        ],
    }

    report_path = OUTPUT_DIR / f"live_summary_{run_id}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n总结果：{passed}/{len(summaries)} 场景通过")
    print("运行期间代码未改变：", source_unchanged)
    print("报告位置：", report_path)

    return 0 if passed == len(summaries) and source_unchanged else 1


if __name__ == "__main__":
    sys.exit(main())
