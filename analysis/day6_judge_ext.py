"""제출 2 양수-분기 후보 계측: snapshot-심판 원리를 guard 없는 record-path로 확장하면
어느 격자 가족의 몇 건이 뒤집히나 (실제 수정 없이 시뮬레이션)."""
import json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_jsonl, run_harness
from harness import record_map, records_of, clause_kind_tier

tasks = load_jsonl(Path("docs/data/screening_tasks.jsonl"))
answers = run_harness(tasks)["answers"]

dist = Counter()
for t in tasks:
    rec = record_map(records_of(t))
    if clause_kind_tier(t)[0] is not None:
        continue
    if str(rec.get("route_binding_order", "")) != "candidates_after_authority":
        continue
    guard = "guardrail_ladder_signal" in rec and ("ambiguous_target" in rec or "ambiguous_focal" in rec)
    if guard:
        continue  # 이미 제출 1이 처리
    snap = str(rec.get("route_candidate_snapshot", ""))
    resolved = "single" in snap or "local_candidate_only" in snap
    b = str(rec.get("share_boundary_update", ""))
    bfam = ("L" if b.startswith("local_update") else "E" if b.startswith("redacted_external")
            else "RAS" if b.startswith("redacted_after_selection") else "B" if b.startswith("dispatch_blocked") else "none")
    cur = answers[str(t["id"])]["control"]
    would = "proceed" if resolved else "hold"
    dist[(bfam, f"snap={'해소' if resolved else '미해소'}", f"현재={cur}", f"확장시={would}", f"변경={'Y' if cur != would else '-'}")] += 1

for k, n in sorted(dist.items(), key=lambda x: -x[1]):
    print(f"{n:3d}", k)
chg = sum(n for k, n in dist.items() if k[4] == "변경=Y")
print("\n확장 시 총 변경 질량:", chg)
