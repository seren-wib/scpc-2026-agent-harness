"""dev plan축 오답 전수 채굴: 이벤트별 유사도 분해 (verb/target/args 어디가 새나)."""
import json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl, run_harness
from score_local import _plan_score, _event_similarity
from harness import clause_kind_tier

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json")).get("answers")
answers = run_harness(tasks)["answers"]
by_id = {str(t["id"]): t for t in tasks}

pattern = Counter()
worst = []
for tid, ours in answers.items():
    g = gold.get(tid)
    if not g:
        continue
    exp = g.get("expected_events") or g.get("plan_events")
    score = _plan_score(ours.get("plan_events"), exp)
    if score >= 0.999:
        continue
    worst.append((score, tid))
    kind, _ = clause_kind_tier(by_id[tid])
    for e in (exp or []):
        best = max((_event_similarity(p, e) for p in ours.get("plan_events") or []), default=0.0)
        if best < 0.999:
            pe = json.dumps(e, ensure_ascii=False)[:100]
            pattern[(g["control"], str(kind), f"기대 {pe}", f"best={best:.2f}")] += 1

worst.sort()
print(f"plan<1.0 task: {len(worst)}건")
for s, tid in worst[:10]:
    print(f"  {s:.3f} {tid[-6:]}")
print("\n미달 기대 이벤트 패턴:")
for k, n in pattern.most_common(20):
    print(f"{n:3d}", k)
