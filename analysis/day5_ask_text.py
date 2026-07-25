"""dev ask 26건: gold scope 클래스별 전체 prompt + 최신 2 history + pm 원문 대조 (dev 자유 분석 합법)."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl, run_harness
from harness import record_map, records_of, history_in_turn_order, clause_kind_tier

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json"))
answers = run_harness(tasks)["answers"]
by_id = {str(t["id"]): t for t in tasks}
gold_answers = gold.get("answers", gold)

groups = {}
for tid, ours in answers.items():
    g = gold_answers.get(tid)
    if not g or g["control"] != "ask":
        continue
    gs = g.get("content_scope", {})
    cls = f"{gs.get('mode')}/{','.join(sorted(map(str, gs.get('excluded_fields') or [])))}"
    groups.setdefault(cls, []).append(tid)

for cls in sorted(groups):
    print(f"\n########## gold {cls} ({len(groups[cls])}건)")
    for tid in groups[cls]:
        t = by_id[tid]
        rec = record_map(records_of(t))
        strict = "S" if str(rec.get("session_share_policy", "")) == "strict" else "n"
        print(f"--- {tid[-6:]} [{strict}] clause={clause_kind_tier(t)[0]}")
        print(f"  P: {t.get('prompt','')}")
        hist = history_in_turn_order(t)
        for h in hist[-2:]:
            print(f"  H(t{(h or {}).get('turn')}): {str((h or {}).get('summary',''))[:150]}")
        for m in (t.get("personal_memory") or []):
            print(f"  pm: {m.get('text','')}")
