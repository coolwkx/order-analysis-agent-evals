from project_paths import OUTPUT_DIR
import json
import sys
from collections import defaultdict
from pathlib import Path




def main():
    paths = sorted(
        OUTPUT_DIR.glob("live_summary_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:3]

    if len(paths) != 3:
        print("需要至少三份 live_summary 报告。")
        return 1

    try:
        reports = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in paths
        ]

        baseline = reports[0]

        versions_match = all(
            report["source_hashes"] == baseline["source_hashes"]
            and report["requested_model"]
            == baseline["requested_model"]
            and report["source_unchanged_during_run"] is True
            for report in reports
        )

        expected_ids = {
            "normal",
            "clarification",
            "invalid_month",
        }

        cases_match = all(
            len(report["cases"]) == 3
            and {
                case["case_id"] for case in report["cases"]
            } == expected_ids
            for report in reports
        )

        if not versions_match or not cases_match:
            print("三份报告的代码版本、模型配置或场景不一致。")
            print("先检查报告，不要混在一起统计。")
            return 1

        tasks = {}
        grouped = defaultdict(list)

        for report in reports:
            for case in report["cases"]:
                case_id = case["case_id"]
                task = case["task"]

                if case_id in tasks and tasks[case_id] != task:
                    print("相同场景的任务文本发生变化：", case_id)
                    return 1

                tasks[case_id] = task
                grouped[case_id].append(case)

        summary = []

        for case_id in sorted(grouped):
            cases = grouped[case_id]
            passed = sum(
                case["evaluation_status"] == "passed"
                for case in cases
            )

            calls = [
                case["metrics"]["recorded_tool_requests"]
                for case in cases
            ]
            elapsed = [
                case["metrics"]["elapsed_seconds"]
                for case in cases
            ]

            item = {
                "case_id": case_id,
                "runs": len(cases),
                "passed": passed,
                "tool_requests_each_run": calls,
                "elapsed_seconds_each_run": elapsed,
                "reported_tokens_each_run": [
                    case["metrics"]["reported_total_tokens"]
                    for case in cases
                ],
            }
            summary.append(item)

            print(f"\n场景：{case_id}")
            print(f"自动检查通过：{passed}/{len(cases)}")
            print("各次工具请求数：", calls)
            print("各次耗时（秒）：", elapsed)

        summary_path = OUTPUT_DIR / (
            f"stability_summary_{baseline['run_id']}.json"
        )

        summary_path.write_text(
            json.dumps(
                {
                    "source_reports": [
                        str(path) for path in paths
                    ],
                    "cases": summary,
                    "limitations": [
                        "每个任务仅运行三次。",
                        "没有新增独立测试任务。",
                        "未校验数据库快照与全部运行配置一致性。",
                        "不能据此推断生产环境成功率。",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("报告读取或统计失败：", exc)
        return 1

    print("\n使用的报告：")
    for path in paths:
        print(path)

    print("\n汇总文件：", summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
