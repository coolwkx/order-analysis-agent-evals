from project_paths import OUTPUT_DIR, WORK_DIR
import subprocess
import argparse
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import agent_demo
from db_tools import failure
from evaluate_answer import parse_answer


PROJECT_DIR = Path(__file__).resolve().parent.parent

TASK = (
    "查询2026年9月和10月各用户的消费额，"
    "计算10月相对9月的变化金额，"
    "找出下降金额最大的用户。"
)


def load_cases():
    path = PROJECT_DIR / "cases" / "comparison_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8-sig"))

    if not isinstance(cases, list) or not cases:
        raise ValueError("配置必须是非空列表")

    ids = set()

    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("每个任务必须是对象")

        case_id = case["id"]

        if not isinstance(case_id, str) or case_id in ids:
            raise ValueError("任务ID必须是唯一字符串")

        ids.add(case_id)

        if set(case["months"]) != {"9", "10"}:
            raise ValueError("months必须包含9和10")

        if not all(
            isinstance(rows, list)
            for rows in case["months"].values()
        ):
            raise ValueError("月份数据必须是列表")

        if not isinstance(case["expected_rows"], list):
            raise ValueError("expected_rows必须是列表")

        decline_user = case["expected_decline_user"]

        if decline_user is not None and type(decline_user) is not int:
            raise ValueError("下降用户必须是整数或null")

    return cases


def make_query(case):
    def query(year, month):
        if (
            type(year) is not int
            or type(month) is not int
            or year != 2026
            or month not in (9, 10)
        ):
            return failure(
                "INVALID_ARGUMENT",
                "本实验仅支持2026年9月和10月。",
            )

        return {
            "ok": True,
            "data": copy.deepcopy(case["months"][str(month)]),
            "error": None,
        }

    return query


def score(case, result, trace):
    answer = parse_answer(result.get("answer"))

    events = [
        event for event in trace
        if event.get("event") == "tool_result"
    ]

    observed = []
    tools_valid = len(events) == 2

    for event in events:
        arguments = json.loads(event["arguments"])

        if (
            event.get("tool") != "query_user_monthly_orders"
            or not isinstance(arguments, dict)
            or set(arguments) != {"year", "month"}
            or type(arguments["year"]) is not int
            or type(arguments["month"]) is not int
        ):
            tools_valid = False
            continue

        year = arguments["year"]
        month = arguments["month"]
        observed.append((year, month))

        if year != 2026 or month not in (9, 10):
            tools_valid = False
            continue

        expected_result = {
            "ok": True,
            "data": case["months"][str(month)],
            "error": None,
        }

        if event["result"] != expected_result:
            tools_valid = False

    tools_valid = (
        tools_valid
        and sorted(observed) == [(2026, 9), (2026, 10)]
    )

    rows = answer.get("rows")
    rows_valid = (
        isinstance(rows, list)
        and rows == case["expected_rows"]
        and all(
            isinstance(row, dict)
            and type(row.get("user_id")) is int
            for row in rows
        )
    )

    actual_user = answer.get("largest_decline_user_id")
    expected_user = case["expected_decline_user"]

    if expected_user is None:
        user_valid = actual_user is None
    else:
        user_valid = (
            type(actual_user) is int
            and actual_user == expected_user
        )

    return {
        "agent_finished": result.get("status") == "finished",
        "tool_results_correct": tools_valid,
        "answer_fields_correct": set(answer) == {
            "task_status",
            "rows",
            "largest_decline_user_id",
            "reason",
        },
        "business_completed": answer.get("task_status") == "completed",
        "rows_correct": rows_valid,
        "decline_user_correct": user_valid,
        "no_failure_reason": answer.get("reason") is None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    try:
        cases = load_cases()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("配置读取失败：", exc)
        return 1

    print("任务配置加载成功，共", len(cases), "个场景。")
	
    validation = subprocess.run(
        [
            sys.executable,
            str(
                PROJECT_DIR
                / "src"
                / "validate_case_answers.py"
            ),
        ],
        check=False,
    )

    if validation.returncode != 0:
        print("参考答案校验未通过，停止实验。")
        return 1

    if args.check_only:
        print("未调用模型。")
        return 0

    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("缺少 DEEPSEEK_API_KEY。")
        return 1

    run_id = (
        datetime.now().strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid4().hex[:8]
    )

    run_dir = WORK_DIR / f"comparison_cases_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    summaries = []

    for index, case in enumerate(cases, start=1):
        print(f"\n=== 场景：{case['id']} ===")
        trace = []

        try:
            with patch.object(
                agent_demo,
                "query_user_monthly_orders",
                side_effect=make_query(case),
            ):
                result = agent_demo.run_agent(TASK, trace)

        except Exception as exc:
            result = {
                "status": "failed",
                "answer": None,
                "error_type": type(exc).__name__,
            }

        trace_path = run_dir / f"case_{index:02d}.json"
        trace_path.write_text(
            json.dumps(
                {
                    "case_id": case["id"],
                    "task": TASK,
                    "tool_mode": "injected_results",
                    "result": result,
                    "trace": trace,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        try:
            checks = score(case, result, trace)
            passed = all(checks.values())
            details = checks
        except (
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
        ) as exc:
            passed = False
            details = {"scoring_error": str(exc)}

        print("最终回答：", result.get("answer"))
        print("检查结果：", details)
        print("场景通过：", passed)

        summaries.append({
            "case_id": case["id"],
            "passed": passed,
            "checks": details,
            "trace_path": str(trace_path),
        })

    passed_count = sum(item["passed"] for item in summaries)

    report_path = OUTPUT_DIR / f"comparison_summary_{run_id}.json"
    report_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "model_mode": "real_api",
                "tool_mode": "injected_results",
                "case_configuration": cases,
                "passed_cases": passed_count,
                "total_cases": len(cases),
                "results": summaries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n汇总：{passed_count}/{len(cases)} 场景通过")
    print("报告：", report_path)

    return 0 if passed_count == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
