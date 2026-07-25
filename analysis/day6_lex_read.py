"""lex층 절 템플릿 전수 열람: dev 사전에 걸린 screening 절이 실제 그 의미인지 해석."""
import re, sys
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
    if tier != "lex":
        continue
    c = re.sub(r"[A-Z]{2,4}-\d{3,6}", "<CODE>", final_clause(t)).strip()
    fam[c] += 1
    kinds[c] = kind

print(f"lex층 총 {sum(fam.values())}건 / 템플릿 {len(fam)}종\n")
for c, n in fam.most_common():
    print(f"[{n:3d}] ({kinds[c]}) {c}")
