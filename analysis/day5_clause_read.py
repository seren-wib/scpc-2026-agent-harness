"""fb층 절 템플릿 전수 열람 (가족 단위 열람 — 사용자 승인 2026-07-11).

screening에서 lex 사전 밖(fb tier)으로 떨어지는 절 원문을 템플릿별로 dedupe해
현재 추정 kind와 함께 나열한다. WM코드/이름류만 마스킹.
"""
import json, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_jsonl
from harness import clause_kind_tier, final_clause

tasks = load_jsonl(Path("docs/data/screening_tasks.jsonl"))

fam = Counter()
kinds = {}
for t in tasks:
    kind, tier = clause_kind_tier(t)
    if tier != "fb":
        continue
    c = final_clause(t)
    c = re.sub(r"[A-Z]{2,4}-\d{3,6}", "<CODE>", c).strip()
    fam[c] += 1
    kinds[c] = kind

print(f"fb층 총 {sum(fam.values())}건 / 고유 템플릿 {len(fam)}종\n")
for c, n in fam.most_common():
    print(f"[{n:3d}] (현재={kinds[c]}) {c}")
