from project_paths import OUTPUT_DIR, WORK_DIR
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4


SRC_DIR = Path(__file__).resolve().parent

CASES = [
    {
        "id": "partial_failure",
        "script": "run_partial_failure.py",
    },
    {
        "id": "empty_month",
        "script": "run_empty_month.py",
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只检查文件和配置，不调用模型",
    )
    args = parser.parse_args()

    missing = [
        case["script"]
        for case in CASES
        if not (SRC_DIR / case["script"]).is_file()
    ]

    if missing:
        print("缺少脚本：", ", ".join(missing))
        return 1

    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("当前终端没有设置 DEEPSEEK_API_KEY。")
        return 1

    print("场景脚本与 API Key 存在性检查通过。")

    if args.check_only:
        print("未调用模型。")
        return 0

    run_id = (
        datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid4().hex[:8]
    )

    log_dir = WORK_DIR / f"injected_suite_{run_id}"
    log_dir.mkdir(parents=True, exist_ok=False)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    for case in CASES:
        print(f"\n正在运行：{case['id']}")

        completed = subprocess.run(
            [
                sys.executable,
                str(SRC_DIR / case["script"]),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
            },
        )

        output = completed.stdout + completed.stderr
        log_path = log_dir / f"{case['id']}.txt"
        log_path.write_text(output, encoding="utf-8")

        crashed = (
            "Traceback (most recent call last)" in output
            or completed.returncode not in (0, 1)
        )

        if crashed:
            status = "error"
        elif completed.returncode == 0:
            status = "passed"
        else:
            status = "not_passed"

        results.append({
            "case_id": case["id"],
            "status": status,
            "exit_code": completed.returncode,
            "log_path": str(log_path),
        })

        print("结果：", status)
        print("详细日志：", log_path)

        if status != "passed":
            print(output)

    passed = sum(
        item["status"] == "passed"
        for item in results
    )

    report_path = OUTPUT_DIR / f"injected_summary_{run_id}.json"
    report_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "model_mode": "real_api",
                "tool_mode": "injected_results",
                "total_cases": len(results),
                "passed_cases": passed,
                "results": results,
                "limitations": [
                    "每个场景仅运行一次。",
                    "调用失败与评分失败仍需查看详细日志区分。",
                    "本入口复用现有场景脚本，尚未抽取公共评分逻辑。",
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n汇总：{passed}/{len(results)} 场景通过")
    print("报告：", report_path)

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
