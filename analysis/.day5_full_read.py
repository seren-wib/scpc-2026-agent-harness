"""strict 비-sel ask 13건 전문 덤프 — gold 클래스 표기, 전체 history·records·pm 포함 (dev 합법)."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl, run_harness
from harness import record_map, records_of, history_in_turn_order

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json"))
answers = run_harness(tasks)["answers"]
by_id = {str(t["id"]): t for t in tasks}
gold_answers = gold.get("answers", gold)

want = {  # suffix: gold class
    "f29ff8": "RED", "1a4b36": "RED", "e62a0a": "RED", "5fdaf8": "RED", "3d4e90": "RED", "8d199e": "RED",
    "84342b": "SUM", "d2cdd2": "SUM", "41dd5a": "SUM", "5801a4": "SUM", "c36edb": "SUM", "5077e8": "SUM", "c0b84d": "SUM",
}
for tid, t in by_id.items():
    sfx = tid[-6:]
    if sfx not in want:
        continue
    g = gold_answers[tid]
    print(f"\n{'='*90}\n[{want[sfx]}] {sfx}  session={t.get('session_id')} turn_index={t.get('turn_index')}")
    print(f"gold: target={g.get('target')} scope={json.dumps(g.get('content_scope'), ensure_ascii=False)}")
    print(f"PROMPT: {t.get('prompt')}")
    for h in history_in_turn_order(t):
        print(f"  H t{(h or {}).get('turn')}: {(h or {}).get('summary')}")
    for m in (t.get("personal_memory") or []):
        print(f"  PM: {m.get('text')}")
    for r in records_of(t):
        print(f"  R {r.get('type')}: {json.dumps(r.get('value'), ensure_ascii=False)[:120]}")
    for o in ((t.get("device_state") or {}).get("objects") or []):
        print(f"  O {o.get('id')} {o.get('type')} {json.dumps(o.get('attrs'), ensure_ascii=False)[:140]}")
