"""dev 앵커 확인: doctor_note_forbidden + 무절 task의 gold control 분포."""
import json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl
from harness import record_map, records_of, clause_kind_tier

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json"))
gold_answers = gold.get("answers", gold)

dist = Counter()
for t in tasks:
    rec = record_map(records_of(t))
    forbid = str(rec.get("external_share_policy", "")) + str(rec.get("health_share_policy", ""))
    if "doctor_note" not in forbid and "health" not in forbid:
        continue
    g = gold_answers[str(t["id"])]
    kind = clause_kind_tier(t)[0]
    gs = g.get("content_scope", {})
    dist[(f"clause={kind}", g["control"], gs.get("mode"), tuple(gs.get("excluded_fields") or []), g.get("target"))] += 1
for k, n in dist.most_common():
    print(n, k)
