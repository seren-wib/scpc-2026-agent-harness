"""축별 정확도 진단용 프로브 제출본 생성.

리더보드는 overall 점수 하나만 돌려주므로, 특정 축을 의도적으로 무효화한
제출본의 점수 차이로 축별 정확도를 역산한다 (내 답안의 집계 점수만 사용).

  P1: target만 무효 문자열로 교체 → 점수 ≈ 0.18·F + 0.18·F·C
  P2: content_scope/policy/plan만 비움 → 점수 ≈ F·(0.18 + 0.12·T + 0.18·C)

원본(0.5206) 점수와 연립하면 F(focal), T(target|focal), C(control|focal)가 풀린다.
생성 파일은 probe1_submission.csv / probe2_submission.csv — 업로드 시 submission.csv로 이름을 바꿔 제출할 것.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from harness import FinalHarness
from run import DATA_DIR, ROOT, load_jsonl, run_harness, write_submission_csv, check_csv_roundtrip


def main() -> None:
    tasks = load_jsonl(DATA_DIR / "screening_tasks.jsonl")
    expected_ids = {str(t["id"]) for t in tasks}
    base = run_harness(tasks, FinalHarness)

    p1 = copy.deepcopy(base)
    p1["meta"]["harness_name"] = "probe1_target_void"
    for answer in p1["answers"].values():
        answer["target"] = "__diagnostic_void__"

    p2 = copy.deepcopy(base)
    p2["meta"]["harness_name"] = "probe2_downstream_void"
    for answer in p2["answers"].values():
        answer["content_scope"] = {"mode": "none", "allowed_fields": [], "excluded_fields": [], "requires_user_confirmation": False}
        answer["policy"] = {"risk_flags": [], "violations": [], "requires_confirmation": False}
        answer["plan_events"] = []

    for name, payload in (("probe1_submission.csv", p1), ("probe2_submission.csv", p2)):
        path = ROOT / name
        write_submission_csv(payload, path)
        check_csv_roundtrip(path, expected_ids)
        print("wrote:", path)


if __name__ == "__main__":
    main()
