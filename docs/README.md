# SCPC 2026 문서 안내

> **작업 상태·전략·작전 계획·절대 규칙은 저장소 루트의 [CLAUDE.md](../CLAUDE.md)가 원본이다.**
> 이 폴더는 대회 스펙과 데이터만 담는다.

## 1. 폴더 지도

```
docs/
├── README.md                     ← 지금 이 파일
├── harness_architecture.md       ← harness.py 상세 구조 (판단 사다리·절 파서·템플릿)
├── SCPC2026_Final_baseline.ipynb ← 공식 baseline 노트북. 셀 11 = 로컬 채점기 원본
│                                    (score_local.py로 추출됨. PLAN_ARG 정규화 표도 여기)
├── guide/
│   ├── 핸드북.md                 ← 공식 문서 5개 통합본. 규칙·제출·채점·task/answer 구조·
│   │                                plan args ontology 전부. 스펙 질문은 여기서 먼저
│   └── 원본/                     ← 공식 문서 원문 5개 (01_문제설명 ~ 05_용어집).
│                                    규정 해석이 갈릴 때 인용할 근거
└── data/
    ├── dev_tasks.jsonl           연습 task 120개 — 정답 공개, 자유 분석 가능
    ├── dev_answers.json          위 120개의 참조 정답 (계획 필드 key가 expected_events임에 주의)
    ├── screening_tasks.jsonl     ★ 제출 대상 700개 — 내용 열람·분석 금지 (실격 조항.
    │                                하네스의 답안 생성용 읽기와 출력 diff 개수 집계만 허용)
    ├── submission_schema.json    답안 JSON 스키마
    └── sample_submission.csv     제출 CSV 형식 예시
```

## 2. 채점 구조 — 요약

가중치: `focal 0.18 / control 0.18 / plan 0.18 / content_scope 0.17 / policy 0.13 / target 0.12 / semantic_response 0.04`

```
focal_id 오답  →  해당 task 사실상 0점 (모든 축이 focal에 곱해짐)
focal 정답 + target 또는 control 오답  →  scope/policy/plan 전부 0점
셋 다 정답  →  scope·policy·plan 부분점수 정산
```

로컬 채점기(`score_local.py`)는 semantic_response를 항상 0으로 주는 보수적 근사 — 로컬 천장 ≈ 0.96.

## 3. 절대 규칙 — 요약 (원문은 핸드북 2장)

- 답안 생성은 제공된 FixedSLMClient + 자작 규칙 로직만. 외부 LLM/API 사용 = 실격
- 평가 데이터(screening) 수작업 라벨링·패턴 분석·정답 추정 = 실격
- task_id 하드코딩 = 무효. dev 문장 통암기 = 비공개 검증에서 자멸
- 제출: submission.csv 1행 1컬럼, UTF-8, 하루 5회, 최종 순위는 직접 선택한 파일 1개

## 4. 읽는 순서 (새 세션 기준)

1. 루트 `CLAUDE.md` — 현재 상태·작전·방법론 (필수)
2. `guide/핸드북.md` — 스펙 레퍼런스 (필요할 때 조회)
3. `harness_architecture.md` — 코드 구조 파악
4. baseline 노트북은 채점기 세부(정규화 alias 등)가 궁금할 때만
