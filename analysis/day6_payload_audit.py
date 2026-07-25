"""scope-절이 제외 필드를 명시하는 가족의 payload 감사.

절 문장이 원문(raw_quote)·위치(location)·수치(numeric_value)를 직접 호명하는
템플릿의 task에서, 현재 excluded_fields 출력과의 차이 질량을 잰다.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_jsonl, run_harness
from harness import final_clause, clause_kind_tier

tasks = load_jsonl(Path("docs/data/screening_tasks.jsonl"))
answers = run_harness(tasks)["answers"]

TRIO = ("raw_quote", "location", "numeric_value")
dist = Counter()
for t in tasks:
    kind, tier = clause_kind_tier(t)
    if kind != "scope":
        continue
    c = final_clause(t)
    names_trio = (("원문" in c or "raw" in c) and ("위치" in c or "장소" in c)
                  and ("수치" in c or "숫자" in c))
    a = answers[str(t["id"])]
    cur = tuple(sorted(a["content_scope"]["excluded_fields"]))
    dist[(f"명시={'trio' if names_trio else '-'}", f"tier={tier}", f"ctl={a['control']}",
          f"현재excl={cur}", f"모드={a['content_scope']['mode']}")] += 1

for k, n in sorted(dist.items(), key=lambda x: -x[1]):
    print(f"{n:3d}", k)
trio_mismatch = sum(n for k, n in dist.items()
                    if k[0] == "명시=trio" and k[3] != f"현재excl={tuple(sorted(TRIO))}")
print("\n절이 trio 명시 & 현재 출력 불일치:", trio_mismatch)
