"""task JSON 최상위 키 센서스: dev vs screening (필드 구조 확인 — 공지로 합법 확정된 집계).

run.py의 participant_task_view가 벗겨내는 채점 힌트 키들이
공개 원본 파일에 실재하는지 확인한다. 값은 읽지 않는다 — 키 이름과 개수만.
"""
import json, sys
from collections import Counter
from pathlib import Path

for name in ("dev_tasks.jsonl", "screening_tasks.jsonl"):
    keys = Counter()
    n = 0
    for line in open(Path("docs/data") / name, encoding="utf-8"):
        if not line.strip():
            continue
        n += 1
        for k in json.loads(line):
            keys[k] += 1
    print(f"\n### {name} ({n} tasks)")
    for k, c in sorted(keys.items(), key=lambda x: -x[1]):
        strip = k in ("expected_events", "answer") or k.startswith("expected_") or \
                k.endswith(("_brief", "_notes", "_rubric", "_keywords", "_tags"))
        print(f"  {'★STRIPPED' if strip else '         '} {c:4d}  {k}")
