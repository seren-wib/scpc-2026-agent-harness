"""guardrail 가족 열람: order=candidates_after_authority(죽은 분기)로 5-2를 통과 못 하는 51건.

템플릿 dedupe: (prompt 골격, history 힌트 문장 집합, record 조합, 현재 control)별로 묶어 열람.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_jsonl, run_harness
from harness import record_map, records_of, history_in_turn_order, clause_kind_tier

tasks = load_jsonl(Path("docs/data/screening_tasks.jsonl"))
answers = run_harness(tasks)["answers"]

def norm(s):
    s = re.sub(r"[A-Z]{2,4}-\d{3,6}", "<C>", str(s))
    s = re.sub(r"marker_\w+", "<M>", s)
    return s.strip()

fams = {}
for t in tasks:
    rec = record_map(records_of(t))
    if "guardrail_ladder_signal" not in rec:
        continue
    if clause_kind_tier(t)[0] is not None:
        continue  # 절 경로는 절이 결정 — 열람 대상 아님
    order = str(rec.get("route_binding_order", ""))
    if order != "candidates_after_authority":
        continue
    tid = str(t["id"])
    hints = tuple(sorted({norm((h or {}).get("summary", ""))[:60] for h in history_in_turn_order(t)}))
    key = (
        norm(t.get("prompt", ""))[:100],
        f"amb_t={rec.get('ambiguous_target','-')[:28]}|amb_f={'Y' if 'ambiguous_focal' in rec else '-'}",
        f"auth={rec.get('dispatch_authority_check','')[:26]} snap={rec.get('route_candidate_snapshot','')[:24]}",
        f"bnd={rec.get('share_boundary_update','')[:26]} strict={rec.get('session_share_policy')}",
        f"guard={rec.get('guardrail_ladder_signal','')[:52]}",
        answers[tid]["control"],
    )
    fams.setdefault(key, []).append((tid, hints))

print(f"guardrail(candidates_after_authority, 무절) 총 {sum(len(v) for v in fams.values())}건 / 가족 {len(fams)}종\n")
for key, members in sorted(fams.items(), key=lambda x: -len(x[1])):
    print(f"--- {len(members)}건  현재={key[5]}")
    for part in key[:5]:
        print(f"    {part}")
    for h in members[0][1]:
        print(f"    H: {h}")
