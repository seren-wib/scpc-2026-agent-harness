"""배수진 후보 계측: fb층 confirm/stop 가족에서 target을 user 대신
record 경로(resolved_target/target_changed)로 바꿀 수 있는 질량."""
import json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl, run_harness
from harness import clause_kind_tier, record_map, records_of

scr = load_jsonl(Path("docs/data/screening_tasks.jsonl"))
answers = run_harness(scr)["answers"]

dist = Counter()
for t in scr:
    kind, tier = clause_kind_tier(t)
    if kind not in ("confirm", "stop"):
        continue
    rec = record_map(records_of(t))
    changed = rec.get("target_changed_after_turn")
    resolved = rec.get("resolved_target")
    alt = None
    if isinstance(changed, str) and changed:
        alt = changed
    elif isinstance(resolved, str) and resolved:
        alt = resolved
    cur = answers[str(t["id"])]["target"]
    dist[(kind, tier, f"현재={cur}", f"대체={'있음' if alt else '없음'}")] += 1

for k, n in sorted(dist.items(), key=lambda x: -x[1]):
    print(f"{n:4d}", k)
flip = sum(n for k, n in dist.items() if k[3] == "대체=있음" and k[2] == "현재=user")
print("\ntarget 플립 가능 질량(user→record):", flip)

# dev 앵커 재확인: lex confirm/stop task의 gold target 분포
dev = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json")).get("answers")
gd = Counter()
for t in dev:
    kind, tier = clause_kind_tier(t)
    if kind in ("confirm", "stop"):
        g = gold[str(t["id"])]
        gd[(kind, f"gold_target={g.get('target')}")] += 1
print("\ndev lex confirm/stop gold target:")
for k, n in gd.most_common():
    print(f"{n:3d}", k)
