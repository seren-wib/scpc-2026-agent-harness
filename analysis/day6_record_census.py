"""record 원본 구조 전수 센서스: 항목 키, 중복 type, current_request_hint 값 다양성."""
import json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_jsonl

for name in ("dev_tasks.jsonl", "screening_tasks.jsonl"):
    tasks = load_jsonl(Path("docs/data") / name)
    entry_keys = Counter()
    dup_types = Counter()
    hint_vals = Counter()
    dict_value_types = Counter()
    for t in tasks:
        recs = ((t.get("device_state") or {}).get("records") or [])
        seen = Counter(str(r.get("type")) for r in recs if isinstance(r, dict))
        for typ, n in seen.items():
            if n > 1:
                dup_types[typ] += 1
        for r in recs:
            if isinstance(r, dict):
                entry_keys[tuple(sorted(r.keys()))] += 1
                if r.get("type") == "current_request_hint":
                    hint_vals[str(r.get("value"))[:80]] += 1
                if isinstance(r.get("value"), dict):
                    dict_value_types[str(r.get("type"))] += 1
    print(f"\n### {name}")
    print("record 항목 키 조합:", dict(entry_keys))
    print("한 task 안 중복 type:", dict(dup_types) or "없음")
    print("dict형 value를 갖는 type:", dict(dict_value_types))
    print("current_request_hint 값 종류:")
    for v, n in hint_vals.most_common():
        print(f"  [{n:3d}] {v}")
