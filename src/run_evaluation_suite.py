from project_paths import OUTPUT_DIR, WORK_DIR
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


SRC_DIR = Path(__file__).resolve().parent
TRACE_DIR = WORK_DIR


CASES = [
    {
        "name": "正常查询与计算",
        "script": "evaluate_answer.py",
        "arguments": ["--scenario", "normal"],
        "trace": "agent_run_20261014_145728_055c18ce.json",
    },
    {
        "name": "数据库连接失败",
        "script": "evaluate_answer.py",
        "arguments": ["--scenario", "database_failure"],
        "trace": "agent_run_20261014_145605_4708a5f4.json",
    },
    {
        "name": "缺少时间信息",
        "script": "evaluate_clarification.py",
        "arguments": [],
        "trace": "agent_run_20261014_150634_249c47ff.json",
    },
    {
        "name": "非法月份输入",
        "script": "evaluate_invalid_month.py",
        "arguments": [],
        "trace": "agent_run_20261014_151134_bbb2399f.json",
    },
]


def run_case(case):
    script_path = SRC_DIR / case["script"]
    trace_path = TRACE_DIR / case["trace"]

    missing = [
        str(path)
        for path in (script_path, trace_path)
        if not path.is_file()
    ]

    if missing:
        return {
            "name": case["name"],
            "status": "error",
            "trace": str(trace_path),
            "details": "文件不存在：" + ", ".join(missing),
        }

    command = [
        sys.executable,
        str(script_path),
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
        return {
            "name": case["name"],
            "status": "error",
            "trace": str(trace_path),
            "details": str(exc),
        }

    output = completed.stdout + completed.stderr

    if (
        completed.returncode not in (0, 1)
        or "Traceback (most recent call last)" in output
    ):
        status = "error"
    elif completed.returncode == 0:
        status = "passed"
    else:
        status = "failed"

    return {
        "name": case["name"],
        "status": status,
        "exit_code": completed.returncode,
        "trace": str(trace_path),
        "details": output.strip(),
    }


def main():
    results = []

    for case in CASES:
        result = run_case(case)
        results.append(result)

        labels = {
            "passed": "通过",
            "failed": "未通过",
            "error": "运行错误",
        }

        print(f"{labels[result['status']]}：{result['name']}")

        if result["status"] != "passed":
            print(result["details"])

    passed = sum(
        result["status"] == "passed"
        for result in results
    )
    failed = sum(
        result["status"] == "failed"
        for result in results
    )
    errors = sum(
        result["status"] == "error"
        for result in results
    )

    report = {
        "evaluation_type": "existing_trace_replay",
        "total_cases": len(results),
        "passed_cases": passed,
        "failed_cases": failed,
        "error_cases": errors,
        "results": results,
        "limitations": [
            "只对已有记录评分，没有重新运行 Agent。",
            "四个场景各使用一份记录，不能代表稳定成功率。",
            "澄清与失败原因的语义仍需人工检查。",
            "部分评测器尚未完成错误样本验证。",
        ],
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report_path = OUTPUT_DIR / (
        "evaluation_summary_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid4().hex[:8]
        + ".json"
    )

    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"\n场景汇总：{passed}/{len(results)} 通过，"
        f"{failed} 项未通过，{errors} 项运行错误"
    )
    print("报告位置：", report_path)

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
