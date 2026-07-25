"""history가 마커/코드를 직접 호명하는 문장 vs 우리 focal 선택의 불일치 계측.

호명 패턴: '<ref>는 통과 항목' / '기준 참조는 <ref>' / 'binding은 <ref>' /
'실제 처리할 ref는 <ref>로 고정' / '승인 상태가 유지된 참조는 <ref>' 등.
ref가 marker_* 이름이면 focal_marker_refs로 WM코드로 변환해 비교.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_jsonl, run_harness, load_json
from harness import record_map, records_of, history_in_turn_order

NAME_PATTERNS = [
    re.compile(r"(marker_\w+|[A-Z]{2,4}-\d{3,6})[는은가이]?\s*통과 항목"),
    re.compile(r"기준 참조는\s*(marker_\w+|[A-Z]{2,4}-\d{3,6})"),
    re.compile(r"binding은\s*(marker_\w+|[A-Z]{2,4}-\d{3,6})"),
    re.compile(r"처리할 ref는\s*(marker_\w+|[A-Z]{2,4}-\d{3,6})"),
    re.compile(r"승인 상태가 유지된 참조는\s*(marker_\w+|[A-Z]{2,4}-\d{3,6})"),
    re.compile(r"참조 코드는\s*(marker_\w+|[A-Z]{2,4}-\d{3,6})"),
    re.compile(r"승인 표시가 남은 것은\s*(marker_\w+|[A-Z]{2,4}-\d{3,6})"),
    re.compile(r"승인 후보\s*(marker_\w+|[A-Z]{2,4}-\d{3,6})"),
]

def named_focal(task):
    rec = record_map(records_of(task))
    refs = (rec.get("focal_marker_refs") or {}).get("marker_to_ref") or {} if isinstance(rec.get("focal_marker_refs"), dict) else {}
    for h in reversed(history_in_turn_order(task)):
        s = str((h or {}).get("summary", ""))
        for pat in NAME_PATTERNS:
            m = pat.search(s)
            if m:
                ref = m.group(1)
                if ref.startswith("marker_"):
                    ref = str(refs.get(ref, ""))
                return ref, s[:70]
    return None, None

def check(split, tasks, answers):
    agree = Counter()
    examples = []
    for t in tasks:
        tid = str(t["id"])
        ref, sent = named_focal(t)
        if not ref:
            continue
        by_ref = {str((o.get("attrs") or {}).get("ref_code")): str(o.get("id")) for o in ((t.get("device_state") or {}).get("objects") or [])}
        if ref not in by_ref:
            agree["named_ref_not_in_objects"] += 1
            continue
        ours = answers[tid]["focal_id"] if isinstance(answers[tid], dict) else answers[tid]
        ok = by_ref[ref] == ours
        agree["match" if ok else "MISMATCH"] += 1
        if not ok and len(examples) < 6:
            examples.append((tid[-6:], sent))
    print(f"[{split}] {dict(agree)}")
    for e in examples:
        print("   ", e)

dev_tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json")).get("answers")
scr_tasks = load_jsonl(Path("docs/data/screening_tasks.jsonl"))
scr_answers = run_harness(scr_tasks)["answers"]
dev_answers = run_harness(dev_tasks)["answers"]

# dev는 gold와도 비교 — 호명 문장이 gold focal과 일치하는지(호명 신뢰도 검증)
gold_agree = Counter()
for t in dev_tasks:
    ref, _ = named_focal(t)
    if not ref:
        continue
    by_ref = {str((o.get("attrs") or {}).get("ref_code")): str(o.get("id")) for o in ((t.get("device_state") or {}).get("objects") or [])}
    if ref in by_ref:
        g = gold[str(t["id"])]["focal_id"]
        gold_agree["named==gold" if by_ref[ref] == g else "named!=gold"] += 1
print("[dev 호명 vs gold]", dict(gold_agree))
check("dev 호명 vs ours", dev_tasks, dev_answers)
check("screening 호명 vs ours", scr_tasks, scr_answers)
