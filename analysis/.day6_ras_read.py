"""redacted_after_selection 가족 재해석: 무절 record-path 서브셋의 템플릿 열람.

Day 4 제출 2(+0.0005 혼조)가 격자 상태1로 편입한 가족 — 어느 셀이 틀렸는지 읽는다.
"""
import re, sys
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

total = Counter()
fams = {}
for t in tasks:
    rec = record_map(records_of(t))
    if not str(rec.get("share_boundary_update", "")).startswith("redacted_after_selection"):
        continue
    kind, tier = clause_kind_tier(t)
    total[f"clause={kind}" if kind else "record-path"] += 1
    if kind is not None:
        continue
    tid = str(t["id"])
    key = (
        answers[tid]["control"],
        f"amb_t={'Y' if 'ambiguous_target' in rec else '-'} amb_f={'Y' if 'ambiguous_focal' in rec else '-'} guard={'Y' if 'guardrail_ladder_signal' in rec else '-'}",
        f"auth={rec.get('dispatch_authority_check','')[:24]} snap={rec.get('route_candidate_snapshot','')[:22]} order={rec.get('route_binding_order','')[:26]}",
        norm(t.get("prompt", ""))[:100],
    )
    fams.setdefault(key, []).append(tid)

print("경로 분해:", dict(total), "\n")
for key, members in sorted(fams.items(), key=lambda x: -len(x[1])):
    t = None
    print(f"--- {len(members)}건 현재={key[0]}")
    for part in key[1:]:
        print(f"    {part}")
