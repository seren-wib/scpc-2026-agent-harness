"""SCPC 2026 실행 스크립트.

사용법:
    python3 run.py dev        # dev 120개 실행 + 로컬 채점 리포트
    python3 run.py screening  # screening 700개 실행 + submission.csv 생성/재검증

runner 구조는 baseline 노트북 셀 3/9/16과 동일. 검증 환경과 같게
session_id → turn_index 순으로 task를 정렬해 FinalHarness.answer_task(task, session)를 호출한다.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

from harness import FIXED_SLM_ID, SUBMISSION_SCHEMA, FinalHarness
from score_local import score_dev_submission, validate_payload

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "docs" / "data"
HARNESS_NAME = "valery_harness"

# 채점 힌트성 key는 참가자 뷰에서 제거 (노트북 셀 9와 동일)
REMOVED_SCORING_KEYS = ("expected_events", "answer")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def participant_task_view(task: dict[str, Any]) -> dict[str, Any]:
    view = json.loads(json.dumps(task, ensure_ascii=False))
    for key in list(view):
        if (
            key in REMOVED_SCORING_KEYS
            or key.startswith("expected_")
            or key.endswith("_brief")
            or key.endswith("_notes")
            or key.endswith("_rubric")
            or key.endswith("_keywords")
            or key.endswith("_tags")
        ):
            view.pop(key, None)
    return view


def run_harness(tasks: list[dict[str, Any]], harness_cls: type = FinalHarness, *, harness_name: str = HARNESS_NAME) -> dict[str, Any]:
    ordered = sorted(tasks, key=lambda t: (str(t.get("session_id", "")), int(t.get("turn_index", 0)), str(t.get("id", ""))))
    harness = harness_cls()
    prepare = getattr(harness, "prepare", None)
    if callable(prepare):
        prepare([])

    sessions: dict[str, dict[str, Any]] = {}
    answers: dict[str, dict[str, Any]] = {}
    for task in ordered:
        sid = str(task.get("session_id", ""))
        session = sessions.setdefault(sid, {})
        answers[str(task["id"])] = harness.answer_task(participant_task_view(task), session)

    return {
        "schema": SUBMISSION_SCHEMA,
        "meta": {
            "harness_name": harness_name,
            "uses_external_api": False,
            "fixed_slm_policy": "local_fixed_slm_only",
            "model_id": FIXED_SLM_ID,
            "temperature": 0.0,
            "seed": 42,
        },
        "answers": answers,
    }


def write_submission_csv(payload: dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["submission"])
        writer.writerow([json.dumps(payload, ensure_ascii=False, separators=(",", ":"))])


def check_csv_roundtrip(path: Path, expected_ids: set[str]) -> None:
    """DACON 서버가 하듯 CSV → JSON 복원이 되는지 확인."""
    csv.field_size_limit(sys.maxsize)  # 답안 700개가 셀 하나라 기본 128KB 제한을 넘는다
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) != 2 or rows[0] != ["submission"] or len(rows[1]) != 1:
        raise ValueError("CSV 구조가 submission 1컬럼/1행이 아님")
    payload = json.loads(rows[1][0])
    validate_payload(payload, expected_ids)


def cmd_dev() -> None:
    dev_tasks = load_jsonl(DATA_DIR / "dev_tasks.jsonl")
    dev_answers = load_json(DATA_DIR / "dev_answers.json")
    payload = run_harness(dev_tasks)
    validate_payload(payload, {str(t["id"]) for t in dev_tasks})
    report = score_dev_submission(payload, dev_answers)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_screening() -> None:
    screening_tasks = load_jsonl(DATA_DIR / "screening_tasks.jsonl")
    expected_ids = {str(t["id"]) for t in screening_tasks}
    payload = run_harness(screening_tasks)
    validate_payload(payload, expected_ids)
    out_path = ROOT / "submission.csv"
    write_submission_csv(payload, out_path)
    check_csv_roundtrip(out_path, expected_ids)
    print("wrote:", out_path)
    print("answers:", len(payload["answers"]))
    print("roundtrip check: OK")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "dev":
        cmd_dev()
    elif mode == "screening":
        cmd_screening()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
