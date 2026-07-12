"""dev content_scope 오답 채굴 v2 — 리스트는 set 비교(채점기와 동일), 순서 허수 제거."""
import json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl, run_harness
from harness import clause_kind_tier, record_map, records_of

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json"))
answers = run_harness(tasks)["answers"]
by_id = {str(t["id"]): t for t in tasks}
gold_answers = gold.get("answers", gold)

def norm(v):
    return sorted(map(str, v)) if isinstance(v, list) else v

pattern = Counter()
mismatch = 0
for tid, ours in answers.items():
    g = gold_answers.get(tid)
    if not g:
        continue
    gs, os_ = g.get("content_scope", {}), ours.get("content_scope", {})
    diffs = {k for k in set(gs) | set(os_) if norm(gs.get(k)) != norm(os_.get(k))}
    if not diffs:
        continue
    mismatch += 1
    t = by_id[tid]
    kind, tier = clause_kind_tier(t)
    rec = record_map(records_of(t))
    focal_gold = g.get("focal_id") == ours.get("focal_id")
    ctl = f"{ours['control']}/{g['control']}"
    print(f"--- {tid} ctl(ours/gold)={ctl} focal_ok={focal_gold} clause={kind}/{tier}")
    for k in sorted(diffs):
        print(f"    {k}: ours={os_.get(k)!r} gold={gs.get(k)!r}")
    contains = ((by_id[tid].get('device_state') or {}).get('objects') or [])
    focal_obj = next((o for o in contains if str(o.get('id')) == str(g.get('focal_id'))), {})
    print(f"    gold-focal contains={((focal_obj.get('attrs') or {}).get('contains'))} "
          f"boundary={rec.get('share_boundary_update')} policy={rec.get('session_share_policy')}")
    pattern[(ctl, tuple(sorted(diffs)))] += 1

print("\ntotal true scope mismatches:", mismatch, "/", len(answers))
for k, n in pattern.most_common():
    print(" ", k, n)
