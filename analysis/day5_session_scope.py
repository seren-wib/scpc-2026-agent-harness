"""세션 메모리 가설: dev ask의 gold scope가 같은 세션 이전 턴의 gold에서 계승되는가."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import load_json, load_jsonl

tasks = load_jsonl(Path("docs/data/dev_tasks.jsonl"))
gold = load_json(Path("docs/data/dev_answers.json"))
gold_answers = gold.get("answers", gold)

by_session = {}
for t in tasks:
    by_session.setdefault(str(t.get("session_id", "")), []).append(t)
for s in by_session.values():
    s.sort(key=lambda t: int(t.get("turn_index", 0)))

def cls(g):
    gs = g.get("content_scope", {})
    return f"{g['control']}:{gs.get('mode')}/{','.join(sorted(map(str, gs.get('excluded_fields') or [])))}"

hit = miss = 0
for sid, seq in sorted(by_session.items()):
    golds = [gold_answers.get(str(t["id"])) for t in seq]
    for i, (t, g) in enumerate(zip(seq, golds)):
        if not g or g["control"] != "ask":
            continue
        prev = [f"t{p.get('turn_index')}={cls(pg)}" for p, pg in zip(seq[:i], golds[:i]) if pg]
        mode = g.get("content_scope", {}).get("mode")
        # 계승 가설: 이전 턴 중 마지막으로 mode가 있는 턴(none 제외)의 mode와 비교
        prev_modes = [pg.get("content_scope", {}).get("mode") for pg in golds[:i] if pg]
        prev_modes = [m for m in prev_modes if m and m != "none"]
        inherit = prev_modes[-1] if prev_modes else None
        mark = "HIT " if inherit == mode else ("....") if inherit is None else "MISS"
        if inherit is not None:
            hit += inherit == mode
            miss += inherit != mode
        print(f"{mark} {sid[-8:]}/t{t.get('turn_index')} ask gold={cls(g)}  prev=[{' | '.join(prev) or '없음'}]")
print(f"\ninherit hit={hit} miss={miss}")
