# SCPC 2026 AI Agent Harness — 문서 안내

> **한 줄 요약**: 개인 기기 에이전트가 받는 요청(task JSON)을 읽고, "무엇을 · 어디로 · 진행할지/보류할지 · 어떤 범위로 · 어떤 순서로" 판단하는 **규칙 기반 Python 하네스**를 만들어, 700개 과제의 답안 JSON을 `submission.csv`로 제출하는 대회 (DACON 예선).

---

## 1. 폴더 지도

```
docs/
├── README.md                     ← 지금 이 파일. 여기서 시작
├── SCPC2026_Final_baseline.ipynb ← 공식 baseline 노트북 (여기서 실행하면 data/ 자동 인식)
├── guide/
│   └── 핸드북.md                 ← 공식 문서 5개를 하나로 통합한 완전판 레퍼런스.
│                                    규칙·제출·채점·task/answer 구조·ontology 전부 여기
├── data/
│   ├── dev_tasks.jsonl           연습용 task 120개 (정답 공개)
│   ├── dev_answers.json          위 120개의 참조 정답 → 로컬 채점에 사용
│   ├── screening_tasks.jsonl     ★ 제출 대상 700개 (정답 비공개)
│   ├── submission_schema.json    답안 JSON이 지켜야 할 스키마
│   └── sample_submission.csv     제출 CSV 형식 예시
└── _archive/                     ← 해시 검증된 100% 중복 사본 + Windows 다운로드 메타파일
                                     + 공식 문서 5개 원본(guide_원본/). 내용 확인 후 삭제 가능
```

## 2. 읽는 순서 (처음이라면)

1. 이 README 끝까지 (5분) — 큰 그림과 전략
2. `guide/핸드북.md` — 규칙·제출·데이터 구조 완전판 (필수)
3. `SCPC2026_Final_baseline.ipynb` 실행 — 전체 파이프라인 체감
4. 제출 직전에 핸드북 2~3장(절대 규칙·제출)만 다시 확인

## 3. 무엇을 만드는가

- **입력**: task 하나 = 사용자 요청(`prompt`) + 기기 상태(`device_state.objects`: 후보 객체들, `device_state.records`: 판단 신호들) + 이전 턴 요약(`visible_history`) + 장기 메모리(`personal_memory`). 같은 `session_id`의 task들은 이어지는 대화라서 **세션 메모리**가 필요함.
- **출력**: task당 답안 JSON 하나.

| 필드 | 의미 |
|---|---|
| `focal_id` | 처리할 중심 object의 id |
| `target` | 최종 수신처 (사람/채널/앱/`memory_store`/`user`) |
| `control` | `proceed` 진행 / `amend` 축소 진행 / `hold` 중단 / `ask` 사용자 확인 |
| `content_scope` | 정보 사용 범위: `raw`/`summary`/`redacted`/`status_only`/`none` + 허용·제외 필드 |
| `policy` | `risk_flags`, `violations`, `requires_confirmation` |
| `plan_events` | 실행 계획 시퀀스: `read`→`verify`→`redact`→`dispatch` 등 (verb, target, args) |

- **LLM 없음**: 제공되는 `FixedSLMClient`는 키워드 기반 보조 신호기일 뿐. 판단 로직은 전부 직접 작성. 외부 LLM API로 답안 생성 시 실격.

## 4. 채점 구조 — 전략의 핵심

로컬 채점기(노트북 셀 11) 기준, 점수는 **계층적으로 잠겨 있음**:

```
focal_id 오답  →  해당 task 사실상 0점 (모든 축이 focal에 곱해짐)
focal 정답 + target 또는 control 오답  →  scope/policy/plan 전부 0점
셋 다 정답  →  scope·policy·plan 부분점수 정산
```

가중치: `focal 0.18 / control 0.18 / plan 0.18 / content_scope 0.17 / policy 0.13 / target 0.12 / semantic_response 0.04`

따라서 우선순위는:

1. **focal_id 해석** — `visible_history`의 참조("두 번째 후보만 확정"), marker(`focal_marker_refs`의 `marker_to_ref` 매핑), record가 가리키는 object id를 정확히 풀 것
2. **control 판단** — 보안알림/동의철회 → `hold`, 모호함 → `ask`, 민감정보 축소 → `amend`, 이상 없음 → `proceed`. 항상 **최신 record가 과거를 덮음**
3. **plan_events** — verb 불일치 = 그 event 0점. args 값은 공개 ontology(약 90개 bucket: `local_update`, `consent_check`, `sensitive_fields` 등)로 정규화 채점. **ontology 밖 임의 label 남발 시 감점** (초과 event당 -0.06)

## 5. 반드시 지킬 것

- 제출: `submission.csv` 1행 1컬럼(`submission`), 셀 안에 답안 JSON 전체. UTF-8. **하루 5회 제한**
- `meta.fixed_slm_policy: "local_fixed_slm_only"`, `meta.model_id: "scpc-final-fixed-slm-local-facade"`, `uses_external_api: false` 고정
- **하드코딩 금지** (특정 task_id 정답표 등) — 상위권은 `harness.py` 제출 후 비공개 task로 재현성 검증받음
- dev 정답을 제출물에 섞지 말 것. 평가 데이터 패턴 분석해 정답 추정하는 행위 = Data Leakage로 실격

## 6. 작업 루프

```
FinalHarness 로직 수정
  → dev 120개 실행 + score_dev_submission으로 로컬 점수 확인
  → 점수 오르면 screening 700개 실행 → submission.csv 생성
  → DACON 제출 → 리더보드 확인 → 반복
```

개선 대상 함수 7개 (노트북 셀 7): `choose_focal` · `infer_target` · `decide_control` · `build_content_scope` · `build_policy` · `build_plan_events` · `update_session_memory`
