"""local_candidate_only 어휘 교량 후보 계측 (프로그램적 집계만).

screening에서 route_candidate_snapshot 값별로: 현재 우리 control 출력 분포와,
'해소됨' 처리 시 rule 6을 통과해 어디로 떨어지는지를 센다.
"""
import json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_jsonl, run_harness
from harness import FinalHarness, record_map, records_of, clause_kind

tasks = load_jsonl(Path("docs/data/screening_tasks.jsonl"))
answers = run_harness(tasks)["answers"]

dist = Counter()
for t in tasks:
    tid = str(t["id"])
    rec = record_map(records_of(t))
    snap = str(rec.get("route_candidate_snapshot", ""))
    if not snap:
        continue
    ours = answers[tid]["control"]
    # rule 6 도달 조건 재현: 절 없음 + 격자/경계/앞단 규칙 미발화 + ambiguous 존재
    kind = clause_kind(t)
    ambiguous = "ambiguous_target" in rec or "ambiguous_focal" in rec
    boundary = str(rec.get("share_boundary_update", ""))
    authority = str(rec.get("dispatch_authority_check", ""))
    resolved_now = "single" in snap or "confirmed" in authority
    at_rule6 = (kind is None and ambiguous and not boundary and not resolved_now)
    strict = str(rec.get("session_share_policy", "")) == "strict"
    forbid = str(rec.get("external_share_policy", "")) + " " + str(rec.get("health_share_policy", ""))
    would = "amend" if ("forbidden" in forbid or "summary_only" in forbid or strict
                        or "ops_memory_recall" in rec or "enterprise_policy_recall" in rec) else "proceed"
    dist[(snap[:24], f"ours={ours}", f"rule6={at_rule6}", f"would={would if at_rule6 else '-'}")] += 1

for k, n in sorted(dist.items(), key=lambda x: -x[1]):
    print(f"{n:4d}", k)
