"""발 2 후보 diff 계측: 0.7634 기준선 vs scope 2종 수리. 귀속 확인 포함."""
import csv, json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import record_map, records_of, clause_kind_tier

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

attrib = Counter()
for k in diff_ids:
    t = tasks[k]
    rec = record_map(records_of(t))
    b = str(rec.get("share_boundary_update", ""))
    strict = str(rec.get("session_share_policy", "")) == "strict"
    bmode, nmode = base[k]["content_scope"]["mode"], new[k]["content_scope"]["mode"]
    same_ctl = base[k]["control"] == new[k]["control"]
    which = "A:status_excl" if bmode == nmode == "status_only" else (
        "B:raw_flip" if (bmode, nmode) == ("summary", "raw") or (bmode, nmode) == ("raw", "raw") else f"OTHER:{bmode}->{nmode}")
    excl_delta = (tuple(sorted(base[k]["content_scope"]["excluded_fields"])), tuple(sorted(new[k]["content_scope"]["excluded_fields"])))
    attrib[(which, same_ctl, strict, b[:14], excl_delta if which.startswith("A") else None)] += 1

for key, n in attrib.most_common():
    print(" ", key, n)
