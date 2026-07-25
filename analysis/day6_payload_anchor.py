"""dev 앵커: scope 절 task의 절 문장 vs gold excluded_fields 대응 확인."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl
from harness import final_clause, clause_kind_tier

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json")).get("answers")

for t in tasks:
    kind, tier = clause_kind_tier(t)
    if kind not in ("scope",):
        continue
    g = gold[str(t["id"])]
    gs = g.get("content_scope", {})
    print(f"--- {str(t['id'])[-6:]} gold ctl={g['control']} excl={sorted(gs.get('excluded_fields') or [])}")
    print(f"    절: {final_clause(t)[:120]}")
