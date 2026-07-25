# 문서 안내

프로젝트 개요와 실행 방법은 루트 [README](../README.md)에 있다. 이 폴더는 그보다 깊은 설명을 담는다.

| 문서 | 내용 |
|---|---|
| [harness_architecture.md](harness_architecture.md) | `harness.py` 전체 구조 — 판단 사다리, 절 파서, 경계 격자를 함수·행 단위로 서술 |
| [캠페인_회고_7일.md](캠페인_회고_7일.md) | 7일간의 기록 — 점수 여정 19회분, 주요 발견, 방법론, 규정 경계의 변화 |

읽는 순서는 루트 README → 아키텍처 → 회고를 권한다. 회고는 각 규칙이 **왜** 그 모양인지를 설명하므로, 코드를 이해한 뒤에 읽는 편이 낫다.

## 데이터

`data/`, `원본/`, 베이스라인 노트북은 **git 추적 대상이 아니다.** 대회 배포물과 주최측 저작물이라 재배포하지 않는다. 로컬에만 존재하며, 새 환경에서 실행하려면 직접 배치해야 한다. 필요한 파일 목록은 루트 README의 실행 섹션에 있다.

## 채점 구조 요약

가중치: `focal 0.18 / control 0.18 / plan 0.18 / content_scope 0.17 / policy 0.13 / target 0.12 / semantic_response 0.04`

```
focal 오답                      → 해당 과제 사실상 0점
focal 정답 + target/control 오답 → scope/policy/plan 전부 0점
셋 다 정답                       → 나머지 축 부분점수 정산
```

로컬 채점기 [score_local.py](../score_local.py)는 공식 baseline 노트북 셀 11의 추출본이며 `semantic_response`를 항상 0으로 주는 보수적 근사다. 로컬 점수의 천장은 약 0.96이다.
