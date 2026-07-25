"""폴백층 열람: 절 없음 + 격자/guardrail 미발화로 rung 7/8에 떨어지는 task들.

가족: strict→amend / forbid(external_share_policy)→amend / else→proceed.
프롬프트·힌트 템플릿 dedupe해서 의미 해석.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_jsonl, run_harness
from harness import record_map, records_of, history_in_turn_order, clause_kind_tier

tasks = load_jsonl(Path("docs/data/screening_tasks.jsonl"))
answers = run_harness(tasks)["answers"]

def norm(s):
    s = re.sub(r"[A-Z]{2,4}-\d{3,6}", "<C>", str(s))
    s = re.sub(r"marker_\w+", "<M>", s)
    return s.strip()

fams = {}
for t in tasks:
    rec = record_map(records_of(t))
    if clause_kind_tier(t)[0] is not None:
        continue
    # 격자·guardrail·both_recent·anon 경로 제외 → 폴백층만
    if str(rec.get("share_boundary_update", "")):
        continue
    if "guardrail_ladder_signal" in rec and ("ambiguous_target" in rec or "ambiguous_focal" in rec):
        continue
    tid = str(t["id"])
    ctl = answers[tid]["control"]
    forbid = str(rec.get("external_share_policy", ""))
    strict = str(rec.get("session_share_policy", ""))
    fam = f"forbid={forbid[:24]}" if ("forbidden" in forbid or "summary_only" in forbid) else (
        "strict" if strict == "strict" else "else")
    key = (
        fam, ctl,
        norm(t.get("prompt", ""))[:110],
        f"recs={','.join(sorted(str(r.get('type')) for r in records_of(t)))[:90]}",
    )
    fams.setdefault(key, []).append(tid)

print(f"폴백층 총 {sum(len(v) for v in fams.values())}건 / 가족 {len(fams)}종\n")
for key, members in sorted(fams.items(), key=lambda x: (x[0][0], -len(x[1]))):
    print(f"--- [{key[0]}] {len(members)}건 현재={key[1]}")
    print(f"    P: {key[2]}")
    print(f"    {key[3]}")
