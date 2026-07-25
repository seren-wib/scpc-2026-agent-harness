# 분석 스크립트

가설 검증에 쓴 일회성 스크립트 28개. 하네스 동작에는 관여하지 않으며, 어떤 근거로 어떤 규칙을 만들었는지에 대한 **감사 추적**으로 보존한다.

전부 `docs/data/`의 데이터셋을 읽는다. 데이터는 저장소에 포함돼 있지 않으므로(루트 [README](../README.md) 참고) 그대로는 실행되지 않는다.

## diff 계측 — 제출 전 변경 질량과 원인 귀속

제출 후보가 **정확히 의도한 건수만, 의도한 이유로** 바뀌는지 확인한다. 키워드 오탐으로 가짜 개선 56건을 만들 뻔한 사고 이후 필수 절차가 됐다.

| 스크립트 | 대상 |
|---|---|
| `day5_diff_probe.py` | 기준선 0.7634 대비 절-경계 충돌 재분류 42건 |
| `day5_diff2.py` | 기준선 0.7634 대비 scope 수리 2종 |
| `day5_diff3.py` | 기준선 0.7636 대비 절 재분류 70건 |

## dev 채굴 — 오답의 원인 분해

정답이 공개된 120개에서 축별 오답을 전수 분해하고, 판별 신호가 실재하는지 확인한다.

| 스크립트 | 대상 |
|---|---|
| `day5_scope_mine.py` | scope 오답 채굴 (리스트는 set 비교) |
| `day5_scope_mine2.py` | scope 오답 22건의 입력 패턴 대조 |
| `day5_scope_table.py` | (control × 판별 신호) 조합별 gold scope 분포 |
| `day5_ask_split.py` | ask 26건의 gold scope 클래스별 후보 신호 |
| `day5_ask_text.py` | ask 26건 prompt + 최신 history 덤프 |
| `day5_hint_table.py` | 힌트 문장 템플릿 × gold scope 교차표 |
| `day5_session_scope.py` | 같은 세션 이전 턴이 scope를 계승하는지 |
| `day6_plan_mine.py` | plan 오답의 이벤트별 유사도 분해 |
| `day6_plan_key.py` | ask plan args의 실제 결정 키 |
| `day6_marker_gap.py` | history 호명 문장 vs 하네스 focal 선택 대조 |
| `day6_payload_anchor.py` | scope 절 문장 vs gold excluded_fields |
| `day6_doctor_anchor.py` | 절 없는 민감 기록 task의 gold control |

`day5_ask_split.py`~`day5_session_scope.py`는 전부 **판별자 부재**로 끝났다. 입력 시그니처가 완전히 동일한 두 task의 정답이 다르다는 사실이 여기서 나왔다.

## 입력 구조 집계 — 가족 단위 인벤토리

개별 문항이 아니라 필드 어휘·구조 분포를 집계해 규칙의 적용 질량과 미관측 값을 파악한다.

| 스크립트 | 대상 |
|---|---|
| `day5_key_census.py` | task JSON 최상위 키 센서스 (dev vs 채점 대상) |
| `day5_vocab_sweep.py` | 문자열 매칭 대상 필드의 어휘 전수 대조 |
| `day6_record_census.py` | record 구조 센서스 (키, 중복 type, 현재 상태) |
| `day5_snapshot_probe.py` | 미관측 snapshot 어휘의 도달 질량 |
| `day6_target_mass.py` | 약신호 계열에서 target 전환 후보 질량 |
| `day6_judge_ext.py` | 판정 원리를 다른 경로로 확장했을 때의 질량 |

## 템플릿 열람 — 가족 단위 원문 검토

문항 단위가 아니라 템플릿(가족) 단위로 중복 제거해 읽고, 사전이 실제 의미를 담고 있는지 대조한다. 어휘 사각지대 70건이 여기서 발견됐다.

| 스크립트 | 대상 |
|---|---|
| `day5_clause_read.py` | 약신호 절 템플릿 전수 |
| `day6_lex_read.py` | 사전에 걸린 절이 실제 그 의미인지 |
| `day6_fallback_read.py` | 절도 격자도 발화하지 않는 폴백 경로 |
| `day6_guard_read.py` | guardrail 가족 (죽은 분기 확인 포함) |
| `day6_ras_read.py` | redacted 접두사 가족의 무절 서브셋 |
| `day6_payload_audit.py` | 절이 제외 필드를 명시하는 가족의 payload |
| `day5_full_read.py` | 판별자 탐색용 전문 덤프 |
