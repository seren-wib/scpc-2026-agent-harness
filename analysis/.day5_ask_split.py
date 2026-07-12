"""dev ask 26건 전수: gold scope 클래스별로 모든 후보 신호를 나란히 — 판별자 사냥."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl, run_harness
from harness import clause_kind_tier, record_map, records_of

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json"))
answers = run_harness(tasks)["answers"]
by_id = {str(t["id"]): t for t in tasks}
gold_answers = gold.get("answers", gold)

rows = []
for tid, ours in answers.items():
    g = gold_answers.get(tid)
    if not g or g["control"] != "ask":
        continue
    t = by_id[tid]
    rec = record_map(records_of(t))
    gs = g.get("content_scope", {})
    cls = f"{gs.get('mode')}/{','.join(sorted(map(str, gs.get('excluded_fields') or [])))}"
    focal = next((o for o in ((t.get("device_state") or {}).get("objects") or [])
                  if str(o.get("id")) == str(g.get("focal_id"))), {})
    contains = sorted(map(str, ((focal.get("attrs") or {}).get("contains") or [])))
    prompt = str(t.get("prompt", ""))
    rows.append((cls, {
        "id": tid[-6:],
        "strict": str(rec.get("session_share_policy", "")) == "strict",
        "sel": "원본" in prompt and "사진" in prompt,
        "amb_t": "ambiguous_target" in rec,
        "amb_f": "ambiguous_focal" in rec,
        "bnd": str(rec.get("share_boundary_update", ""))[:14],
        "auth": str(rec.get("dispatch_authority_check", ""))[:18],
        "snap": str(rec.get("route_candidate_snapshot", ""))[:18],
        "guard": "guardrail_ladder_signal" in rec,
        "tchg": "target_changed_after_turn" in rec,
        "pm": len(t.get("personal_memory") or []),
        "contains": ",".join(contains)[:40],
        "clause": str(clause_kind_tier(t)[0]),
        "sens": bool(set(contains) & {"raw_quote", "rrn", "name", "amount", "location", "numeric_value"}),
    }))

rows.sort(key=lambda r: r[0])
cur = None
for cls, r in rows:
    if cls != cur:
        print(f"\n===== gold {cls}")
        cur = cls
    print("  " + " ".join(f"{k}={v}" for k, v in r.items()))
