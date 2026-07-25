"""dev scope 오답 22건의 prompt/personal_memory/최신 history를 패턴별로 덤프 (dev 자유 분석 합법)."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl, run_harness
from harness import clause_kind_tier, record_map, records_of, history_in_turn_order

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json"))
answers = run_harness(tasks)["answers"]
by_id = {str(t["id"]): t for t in tasks}
gold_answers = gold.get("answers", gold)

def norm(v):
    return sorted(map(str, v)) if isinstance(v, list) else v

groups = {}
for tid, ours in answers.items():
    g = gold_answers.get(tid)
    if not g:
        continue
    gs, os_ = g.get("content_scope", {}), ours.get("content_scope", {})
    diffs = {k for k in set(gs) | set(os_) if norm(gs.get(k)) != norm(os_.get(k))}
    if not diffs:
        continue
    key = (g["control"], gs.get("mode"), tuple(norm(gs.get("excluded_fields") or [])))
    groups.setdefault(key, []).append(tid)

for key in sorted(groups, key=str):
    print(f"\n===== gold control={key[0]} mode={key[1]} excluded={key[2]} ({len(groups[key])}건)")
    for tid in groups[key]:
        t = by_id[tid]
        rec = record_map(records_of(t))
        hist = history_in_turn_order(t)
        last = str((hist[-1] or {}).get("summary", ""))[:110] if hist else ""
        print(f"  {tid}")
        print(f"    prompt: {str(t.get('prompt',''))[:160]}")
        for m in (t.get("personal_memory") or []):
            print(f"    pm: {str(m.get('text',''))[:120]}")
        print(f"    last_hist: {last}")
        print(f"    strict={rec.get('session_share_policy')} boundary={rec.get('share_boundary_update')} clause={clause_kind_tier(t)}")
