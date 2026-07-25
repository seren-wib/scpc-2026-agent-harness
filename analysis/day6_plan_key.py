"""dev ask 전수: gold plan args(read purpose/clarify reason)의 진짜 결정 키 탐색."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl
from harness import clause_kind_tier, final_clause, record_map, records_of

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json")).get("answers")

for t in tasks:
    tid = str(t["id"])
    g = gold.get(tid)
    if not g or g.get("control") != "ask":
        continue
    exp = g.get("expected_events") or []
    purpose = next((e.get("args", {}).get("purpose") for e in exp if e.get("verb") == "read"), None)
    reason = next((e.get("args", {}).get("reason") for e in exp if e.get("verb") == "clarify"), None)
    kind, tier = clause_kind_tier(t)
    rec = record_map(records_of(t))
    c = final_clause(t)[:56]
    tchg = "tchg" if "target_changed_after_turn" in rec else "    "
    ambt = "ambT" if "ambiguous_target" in rec else "    "
    print(f"{tid[-6:]} kind={str(kind):7s} {tchg} {ambt} read={str(purpose):26s} clarify={str(reason):26s} 절={c}")
