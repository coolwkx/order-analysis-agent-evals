from project_paths import WORK_DIR
import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


def load_record(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8")
    )


def change_answer(record, update):
    answer = json.loads(record["result"]["answer"])
    update(answer)

    record["result"]["answer"] = json.dumps(
        answer,
        ensure_ascii=False,
    )


def wrong_amount(record):
    def update(answer):
        answer["rows"][0]["change_amount"] = "-30.00"

    change_answer(record, update)


def wrong_user(record):
    def update(answer):
        answer["largest_decline_user_id"] = 102

    change_answer(record, update)


def missing_month(record):
    for index, event in enumerate(record["trace"]):
        if event.get("event") != "tool_result":
            continue

        arguments = json.loads(event["arguments"])

        if arguments.get("month") == 10:
            del record["trace"][index]
            return

    raise ValueError("没有找到十月工具结果")


def invalid_json(record):
    record["result"]["answer"] = "这不是 JSON"


def invented_failure_result(record):
    def update(answer):
        answer["rows"] = [
            {
                "user_id": 101,
                "previous_amount": "300.00",
                "current_amount": "0.00",
                "change_amount": "-300.00",
            }
        ]
        answer["largest_decline_user_id"] = 101

    change_answer(record, update)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--normal-trace", required=True)
    parser.add_argument("--failure-trace", required=True)
    args = parser.parse_args()

    try:
        normal = load_record(args.normal_trace)
        failure = load_record(args.failure_trace)
    except (OSError, ValueError) as exc:
        print("读取原始记录失败：", exc)
        return 1

    evaluator = Path(__file__).with_name("evaluate_answer.py")

    if not evaluator.is_file():
        print("找不到 evaluate_answer.py")
        return 1

    test_dir = (
        WORK_DIR
        / f"evaluator_checks_{uuid4().hex[:8]}"
    )
    test_dir.mkdir(parents=True, exist_ok=False)

    # expected_code:
    # 0 = 评测器应接受
    # 1 = 评测器应拒绝
    cases = [
        ("正常原始记录", normal, "normal", None, 0),
        (
            "失败原始记录",
            failure,
            "database_failure",
            None,
            0,
        ),
        ("错误变化金额", normal, "normal", wrong_amount, 1),
        ("错误下降用户", normal, "normal", wrong_user, 1),
        ("缺少十月工具结果", normal, "normal", missing_month, 1),
        ("非法JSON回答", normal, "normal", invalid_json, 1),
        (
            "失败时编造业务结果",
            failure,
            "database_failure",
            invented_failure_result,
            1,
        ),
    ]

    passed = 0

    for index, (
        name,
        source,
        scenario,
        mutation,
        expected_code,
    ) in enumerate(cases, start=1):
        record = copy.deepcopy(source)

        try:
            if mutation is not None:
                mutation(record)

        except (KeyError, IndexError, TypeError, ValueError) as exc:
            print(f"\n失败：{name}")
            print("构造测试记录失败：", exc)
            continue

        path = test_dir / f"case_{index:02d}.json"
        path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 使用同一个 Python 环境执行评测器。
        # 不使用 shell 拼接命令。
        completed = subprocess.run(
            [
                sys.executable,
                str(evaluator),
                "--scenario",
                scenario,
                "--trace",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={
                **__import__("os").environ,
                "PYTHONIOENCODING": "utf-8",
            },
        )

        output = completed.stdout + completed.stderr

        # 错误样本必须被正常拒绝，
        # 不能把评测器崩溃误认为识别成功。
        accepted = (
            completed.returncode == expected_code
            and "Traceback (most recent call last)" not in output
        )

        print(f"\n{'通过' if accepted else '失败'}：{name}")
        print(
            f"预期退出码={expected_code}，"
            f"实际退出码={completed.returncode}"
        )

        if accepted:
            passed += 1
        else:
            print(output)

    print(f"\n评测器验证：{passed}/{len(cases)} 通过")
    print("测试副本目录：", test_dir)

    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
