"""Day 5 발 1 diff 계측: 기준선(HEAD 0.7634) vs fb:local 외향 42 플립.

diff 질량과 키워드 귀속(⚠ 프로브 버그 전력 — 귀속 확인 전에 질량을 믿지 말 것),
control/target 전환 내역을 집계한다. screening 개별 원문은 읽지 않는다(프로그램적 집계만).
"""
import csv, json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import clause_kind_tier, effective_clause_kind, record_map, records_of

csv.field_size_limit(sys.maxsize)

def load_payload(p):
    rows = list(csv.reader(open(p, encoding="utf-8", newline="")))
    return json.loads(rows[1][0])["answers"]

base = load_payload(".day5_baseline_head.csv")
new = load_payload("submission.csv")

tasks = {}
for line in open("docs/data/screening_tasks.jsonl", encoding="utf-8"):
    if line.strip():
        t = json.loads(line)
        tasks[str(t["id"])] = t

diff_ids = [k for k in base if json.dumps(base[k], sort_keys=True) != json.dumps(new[k], sort_keys=True)]
print("diff mass:", len(diff_ids))

# 귀속: diff난 task 전부가 (fb:local 절) & (외향 경계 record)인지 확인
attrib = Counter()
trans = Counter()
for k in diff_ids:
    t = tasks[k]
    kind, tier = clause_kind_tier(t)
    eff = effective_clause_kind(t)
    boundary = str(record_map(records_of(t)).get("share_boundary_update", ""))
    bkey = "redacted" if boundary.startswith("redacted") else ("blocked" if boundary.startswith("dispatch_blocked") else "OTHER:" + boundary[:20])
    attrib[(kind, tier, eff is None, bkey)] += 1
    trans[(base[k]["control"], new[k]["control"], base[k]["target"] == new[k]["target"])] += 1

print("attribution (kind, tier, flipped, boundary):")
for key, n in attrib.most_common():
    print(" ", key, n)
print("control transitions (old, new, target_same):")
for key, n in trans.most_common():
    print(" ", key, n)

# 전체 700 중 플립 조건 해당 수 (diff와 일치해야 정상)
flip_all = Counter()
for k, t in tasks.items():
    kind, tier = clause_kind_tier(t)
    if kind == "local" and tier == "fb" and effective_clause_kind(t) is None:
        boundary = str(record_map(records_of(t)).get("share_boundary_update", ""))
        flip_all["redacted" if boundary.startswith("redacted") else "blocked"] += 1
print("flip-eligible in 700:", dict(flip_all), "total", sum(flip_all.values()))
