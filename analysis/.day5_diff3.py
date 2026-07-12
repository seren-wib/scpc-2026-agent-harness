"""발 3 diff 계측: 0.7636 기준선(발 2) 대비 fb 절 재분류 70건. 귀속 확인."""
import csv, json, sys, re, subprocess
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import clause_kind_tier, final_clause

csv.field_size_limit(sys.maxsize)

def load_payload(p):
    rows = list(csv.reader(open(p, encoding="utf-8", newline="")))
    return json.loads(rows[1][0])["answers"]

# 발 2(0.7636) 기준선: HEAD~5 즈음이 아니라 커밋 6c66806 시점 = 현재 코드에서 어휘 확장만 빼면 됨.
# 간단히: git stash로 복원하는 대신, 저장해 둔 발 2 산출물이 없으므로 커밋에서 재생성.
subprocess.run(["git", "stash"], check=True, capture_output=True)
subprocess.run(["python3", "run.py", "screening"], check=True, capture_output=True)
base = load_payload("submission.csv")
subprocess.run(["git", "stash", "pop"], check=True, capture_output=True)
subprocess.run(["python3", "run.py", "screening"], check=True, capture_output=True)
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
    kind, tier = clause_kind_tier(t)
    c = re.sub(r"[A-Z]{2,4}-\d{3,6}", "<CODE>", final_clause(t))[:34]
    attrib[(c, f"{base[k]['control']}->{new[k]['control']}", f"tier={tier}", f"tgt:{base[k]['target']}->{new[k]['target']}")] += 1
for key, n in attrib.most_common():
    print(f"{n:3d}", key)
