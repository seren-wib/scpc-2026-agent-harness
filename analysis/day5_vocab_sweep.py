"""문자열 매칭 대상 필드 전수 어휘 대조: dev vs screening (프로그램적 집계만, 합법).

우리 harness가 값을 문자열로 판정하는 모든 record type에 대해
screening에만 존재하는 값과 그 질량, 현재 라우팅 결과를 찍는다.
"""
import json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_jsonl, run_harness
from harness import record_map, records_of

dev = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
scr = load_jsonl(Path("docs/data/screening_tasks.jsonl"))
answers = run_harness(scr)["answers"]

# harness가 값 문자열을 보고 분기하는 필드 전부
FIELDS = [
    "safety_mode", "consent", "payment_policy",
    "external_share_policy", "health_share_policy", "session_share_policy",
    "dispatch_authority_check", "route_binding_order", "share_boundary_update",
    "route_candidate_snapshot", "ambiguous_target", "ambiguous_focal",
    "guardrail_ladder_signal",
]

def val_str(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else str(v)

dev_vals = {f: set() for f in FIELDS}
for t in dev:
    rec = record_map(records_of(t))
    for f in FIELDS:
        if f in rec:
            dev_vals[f].add(val_str(rec[f]))

scr_vals = {f: Counter() for f in FIELDS}
routing = {}
for t in scr:
    rec = record_map(records_of(t))
    ctl = answers[str(t["id"])]["control"]
    for f in FIELDS:
        if f in rec:
            v = val_str(rec[f])
            scr_vals[f][v] += 1
            routing.setdefault((f, v), Counter())[ctl] += 1

for f in FIELDS:
    novel = {v: n for v, n in scr_vals[f].items() if v not in dev_vals[f]}
    known = sum(n for v, n in scr_vals[f].items() if v in dev_vals[f])
    print(f"\n### {f}  (dev 어휘 {len(dev_vals[f])}종 / screening 총 {sum(scr_vals[f].values())}건, dev-어휘 {known}건)")
    if dev_vals[f]:
        print(f"  dev: {sorted(dev_vals[f])[:6]}")
    for v, n in sorted(novel.items(), key=lambda x: -x[1]):
        print(f"  ★NOVEL {n:4d}건  {v[:70]}  → 현재 라우팅 {dict(routing[(f, v)])}")

# 세션 구조도 겸사 확인
sess = Counter()
for t in scr:
    sess[str(t.get("session_id", ""))] += 1
sizes = Counter(sess.values())
print(f"\n### screening 세션 구조: 세션 수 {len(sess)}, 크기 분포 {dict(sorted(sizes.items()))}")
