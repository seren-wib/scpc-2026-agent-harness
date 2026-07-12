"""dev 120 전수: (control, 판별 신호) 조합별 gold scope 분포표 — 후보 규칙 전수 검증."""
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

def sig(t):
    rec = record_map(records_of(t))
    prompt = str(t.get("prompt", ""))
    b = str(rec.get("share_boundary_update", ""))
    bp = "local" if b.startswith("local_update") else ("redact" if b.startswith("redacted") else ("blocked" if b.startswith("dispatch_blocked") else "none"))
    sel = ("원본" in prompt and "사진" in prompt)
    return {
        "strict": str(rec.get("session_share_policy", "")) == "strict",
        "boundary": bp,
        "sel_prompt": sel,
        "clause": clause_kind_tier(t)[0],
    }

rows = Counter()
for tid, ours in answers.items():
    g = gold_answers.get(tid)
    if not g:
        continue
    t = by_id[tid]
    s = sig(t)
    gs = g.get("content_scope", {})
    gold_key = (gs.get("mode"), tuple(sorted(map(str, gs.get("excluded_fields") or []))))
    ctl = g["control"]
    if ctl == "ask":
        rows[("ASK", s["strict"], s["sel_prompt"], gold_key)] += 1
    elif ctl == "proceed":
        mode = gs.get("mode")
        if mode == "status_only":
            # status_only: 제외목록과 focal contains 매핑 관계 확인
            focal = next((o for o in ((t.get("device_state") or {}).get("objects") or [])
                          if str(o.get("id")) == str(g.get("focal_id"))), {})
            contains = tuple(sorted(map(str, ((focal.get("attrs") or {}).get("contains") or []))))
            rows[("PROC-status", s["strict"], contains, gold_key[1])] += 1
        else:
            rows[("PROC-ext", s["strict"], s["boundary"], gold_key)] += 1
    elif ctl == "amend":
        rows[("AMEND", s["strict"], s["boundary"], gold_key)] += 1
    else:
        rows[("HOLD", s["strict"], s["boundary"], gold_key)] += 1

for k in sorted(rows, key=str):
    print(k, rows[k])
