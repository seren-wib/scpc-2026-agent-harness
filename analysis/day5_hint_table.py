"""dev ask 26건: 전체 history의 힌트 문장 템플릿 × gold scope 클래스 교차표."""
import json, re, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl, run_harness
from harness import history_in_turn_order

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json"))
answers = run_harness(tasks)["answers"]
by_id = {str(t["id"]): t for t in tasks}
gold_answers = gold.get("answers", gold)

def norm(s):
    s = re.sub(r"[A-Z]{2,4}-\d{3,6}", "<CODE>", s)
    s = re.sub(r"marker_\w+", "<MARK>", s)
    return s.strip()

table = Counter()
ids = {}
for tid, ours in answers.items():
    g = gold_answers.get(tid)
    if not g or g["control"] != "ask":
        continue
    t = by_id[tid]
    gs = g.get("content_scope", {})
    cls = f"{gs.get('mode')}/{','.join(sorted(map(str, gs.get('excluded_fields') or [])))}"
    seen = {norm(str((h or {}).get("summary", ""))) for h in history_in_turn_order(t)}
    for s in seen:
        if s:
            table[(s[:60], cls)] += 1
            ids.setdefault((s[:60], cls), []).append(tid[-6:])

# 문장별로 클래스 분포 출력
by_sent = {}
for (s, cls), n in table.items():
    by_sent.setdefault(s, {})[cls] = n
for s in sorted(by_sent, key=lambda x: -sum(by_sent[x].values())):
    dist = by_sent[s]
    pure = "PURE" if len(dist) == 1 else ""
    print(f"[{sum(dist.values()):2d}] {pure:4s} {s}")
    for cls, n in sorted(dist.items()):
        print(f"        {cls}: {n} {ids.get((s, cls), [])[:8]}")
