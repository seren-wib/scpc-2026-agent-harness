# harness.py 판단 사다리 전체 리뷰 (2026-07-08)

`answer_task` 파이프라인 7단계 전수 리뷰. 방법론: 코드 정독 + **dev 120 전수 실측**(rung 귀속·gold 대조) + **screening rule-path 집계**(어느 코드 분기가 발화했는지 개수만 — 내용 비접근, fb층 지도와 동일한 합법 채널). 모든 수치는 인메모리 실행 실측이며 추정치 없음.

회계 검증: 아래 잔손실 합계(scope 0.0134 + plan 0.0064 + policy 0.0041 + 게이트 오답 3건 ≈0.020) ≈ 0.042. 현 dev 0.9186과 합치면 로컬 천장 ~0.96에 도달 → **누락된 손실원 없음**.

---

## 파트 0: update_session_memory

### 판정
쓰기 경로 자체는 건전. 결정론 확보(`prepare()` 초기화 + 실행 순서가 검증 환경과 동일), dev의 write 5건은 전부 recall 14건보다 앞 세션. write는 항상 24필드 완전체 프로필 + memory_key 중복 없음이라 overwrite/merge 논쟁 무의미.

### 발견 — stale recall 오답 (sess_0107/6)
- recall 14건 중 13건 정답. 유일 오답 = **target+control 동시 오답 → scope/policy/plan 게이트 전멸** (한 task에서 0.78 가중치 손실).
- 구조: recall이 **한 번도 write된 적 없는 memory_key** + `age_hint: many_sessions_later`. person 폴백(582행)이 같은 사람의 다른 프로필을 대신 물어와 health_channel=caregiver 출력. gold는 **clinic_portal + ask**.
- clinic_portal은 task 내 어디에도 없음 — 정체는 jimin 최신 프로필의 **checkup_place**. 프롬프트가 "언제 검진을 받으러 가야 하는지"인데 `memory_field_for`가 health_channel(채널)을 고름 → **필드 선택 미스**.
- control도 gold가 ask + `precondition_changed` + `clarification_required` (저장된 checkup_time 존재 vs 캘린더 이벤트 전부 time=미정).
- person 폴백이 답을 결정한 유일한 케이스가 이 오답 (sess_0083은 앞 규칙이 가로챔). 폴백 존재 가치 실증 0, 해악 1. 단 폴백 제거만으론 DEFAULT(caregiver)로 같은 오답 — 수리하려면 필드 선택 + stale-recall→ask 규칙이 필요.

### 청소거리 (비용 0)
- `session["last_evidence"]` — 아무도 안 읽는 죽은 상태.
- 483행 TODO — baseline 잔재 (last_focal 갱신은 answer_task가 함).
- 함수명 `update_session_memory` ≠ 실제 일(인스턴스/세션 횡단 메모리 갱신).

---

## 파트 1: choose_focal

### dev 실측
- **focal 120/120 만점.** 발화 단은 marker(83)·history(37) 둘뿐. 나머지 5단(0-1 rec_code / 1 rec_id / 2 hist_ref / 2-2 domain / 3 token)은 dev 표본 0.

### screening rule-path 집계
- **700 = marker 463 + history 237. 추측층 5단은 screening에서도 질량 0 = 완전한 죽은 코드** (가족 비율 dev 69/31 ↔ screening 66/34 거의 동일).
- marker 내부: latest_phase 단독 187 / rule∧latest **일치** 276 / **불일치 0 (dev도 0)** / rule_fallback 승자 0. → "불일치 시 rule 우선" 주석(131행)은 실증 근거 없는 장식이나 불일치 자체가 없어 무해. 사실상 marker = `latest_phase → marker → ref` 단일 경로.
- history 내부: pos 115 / **single0 77 / joined_pos 2 / 폴백 피라미드 43** (attr 9, echo 1, typed 15, token 12, surv2 6, carried 0). **dev history 37은 전원 pos** → **122건(전체의 17.4%)이 dev 무표본 경로.** 절 파서 fb층(284건)과 같은 구도의 두 번째 지도.
- fb_surv2의 "2번째 사전확률"(439행 survivors[1])은 dev 긍정신호 케이스에서의 외삽 — 폴백 자체의 dev 표본 0. **CLAUDE.md "idx-1 잔재 6건" = 이 fb_surv2 6건** (Day 4 청소 주소 확정).

### 코드 소견
- rung 2(hist_ref)는 history 해석기가 "전원 부정어"로 기각한 코드를 다시 주울 수 있는 논리 모순 — 질량 0이라 실해 없음.
- rung 0-1은 record 텍스트 극성(보류/제외) 검사 없음 — 질량 0.
- resolve_focal_by_history: 옛 summary의 긍정 신호가 새 summary의 중립 폴백을 이김 — dev 37/37이 지지.
- **결론: focal 잔여 리스크는 rung 커버리지가 아니라 history 서브경로 122건의 품질.** 서버 focal 추정 0.90~0.96의 오차가 살 곳은 여기뿐. 폴백 개선은 dev 검증 불가 영역 — 신규 원리 없이 건드리지 말 것.

---

## 파트 2: infer_target

### dev 실측
- **target 119/120.** 유일 오답 = sess_0107 (파트 0 참조, r3:recall_profile 경로).
- 발화 rung: 절 50(local 33/stop 6/confirm 11) · mem_write 5 · recall 12 · changed 4 · resolved 40 · attrs_name/recipient 9 — 오답 1건 외 전부 정답.

### screening rule-path 집계
- 절 360(51.4%) / resolved 228 / attrs_recipient 81 / recall 16 / mem_write 4 / changed 3 / attrs 기타 5 / r8:last_or_user 3.
- **r6:same_place(SAME_PLACE_CUES)는 dev·screening 양쪽 질량 0 — 죽은 규칙.**
- dev 무표본 + screening 질량: attrs_merchant 2 / attrs_target 1 / r8 폴백 3 — 합계 6건 소액.
- **target 축의 실질 리스크 = 절 360건의 kind 추정** (fb-local 131 전부 memory_store행). kind 오추정 시 target+control 동시 오답 — 기존 kind 추정기 광맥과 동일 주소 재확인.
- recall 가족은 screening 16건뿐 → **파트 0 수리 기대값 +0.004~0.006으로 하향 보정. 단독 발사 금지, 합승 전용.**

---

## 파트 3: decide_control

### dev 실측
- **control 117/120.** 오답 3: both_recent 2건(ask 출력, gold amend) + sess_0107(strict→amend, gold ask).
- 절층(lex) 52건 전원 정답 — 절 최우선 설계 재확인. confirm(fb) 중재 로직은 dev 표본 0 (주석의 자인과 일치).

### screening rule-path 집계 (700)
- 절층 367: local(fb) 131 / local(lex) 92 / scope(fb) 49 / scope(lex) 23 / stop(fb) 23 / stop(lex) 15 / confirm(lex) 18. **confirm(fb) 81의 record 재판정 내역 = amend 28 / ask 30 / hold 13 / proceed 10 — CLAUDE.md fb층 지도와 정확히 일치 (귀속 방법 교차검증 성공).**
- record층 dev-빈약/screening-과밀 주머니: **both_recent 50 (bare 37 + confirm(fb) 경유 13, dev 1/3 정답)** / **guard_boundary 40 (dev 1)** / **amb_hold 30 (dev 1)** / anon_local 24 (dev 2) / health_forbid 21 (dev 2) / strict 71 (dev 11/12).

### 신규 발견 — both_recent 판별자 (Day 1 ① 설계 재료)
dev에서 both_recent record 보유 task 9건 중 절 없는 3건만 5-3 도달:
- gold **amend** 2건(0003, 0011): `share_boundary_update=local_update_boundary` + `order=boundary_after_authority`. gold target=resolved_target 값, scope=redacted.
- gold **ask** 1건(0038): `share_boundary_update=redacted_external_boundary` + `order=authority_after_candidates`. scope=summary.
- **교차 증거**: sess_0107(다른 모호성 가족)도 redacted_external + authority_after_candidates에서 gold ask.
- 가설: both_recent에서 **boundary가 local_update계 → amend(+target=resolved), redacted_external계 → ask.** n=3+교차 1. 5-2 guard 가족의 order 의미와 상충 가능성 있으니 boundary 값 기준을 우선 검토.
- 주의: 50건 전부 amend로 밀면 출력 mix에서 amend 과다(23%→30%). boundary 분기라면 일부만 이동 — 분포 정렬 나침반에도 부합.

### 코드 소견
- 5-3 both_recent가 rung 6의 해소 검사(snapshot/authority)를 우회 — boundary 분기로 흡수 가능.
- duration_ambiguous가 4-2(values)와 5-3(types)에서 중복 검사 — 무해.

---

## 파트 4: build_content_scope

### dev 실측 (게이트 열린 117건, 채점기 = mode 0.40 / allowed·excluded F1 각 0.25 / confirm 0.10)
- scope<1.0 task 24건, 총손실 9.43유닛 = **dev -0.0134 (하위축 잔손실 1위).**
- mode 혼동 14건이 주범: **summary→redacted 8** / summary→none 2 / summary↔raw 각 2.
- **summary→redacted 8건은 전원 control=ask + strict.** gold는 mode=redacted + excluded=[raw_quote] (focal에 민감 contains 있으면 sensitive 전체: 0023·0040은 [name, numeric_value, raw_quote, rrn]).
- **반례 존재**: 같은 ask+strict인 both_recent 가족(0032·0038)은 gold summary. → ask의 scope는 "무조건 summary"(753행)가 아니라 **가족별 분기** 필요. 후보 판별자: recall 가족·민감 contains → redacted / 모호성(route) 가족 → summary.
- proceed의 strict→summary / 비strict→raw 경계(764~766행) 4건 역전: 0021·0025(strict인데 gold raw), 0053·0065(normal인데 gold summary). strict 단독으론 부족한 신호 — 판별자 미발견.

---

## 파트 5: build_policy

### dev 실측
- policy<1.0 32건, 총손실 3.78유닛 = **-0.0041**. violations는 dev 전수 무결점.
- **정정 (07-08)**: 초판의 "requires_confirmation 무결점"은 별도 집계 없이 단정한 오기. 후속 실측에서 14건 불일치 확인, 발 2에서 수리됨 (803행 `control=="ask"` 단순 등식이 원인). 리뷰 방법론 교훈: 채점기 컴포넌트는 셋 다 각각 세어야 함.
- **`precondition_changed` 과잉 18건 — 전원 `share_boundary_update=dispatch_blocked_until_binding`에서 발생.** 대조군: gold가 이 플래그를 주는 boundary는 전부 redacted_external_boundary 또는 local_update_boundary.
- → **785행 "boundary 존재 = 전제 변경"을 "boundary가 local_update/redacted_external 계열일 때만"으로 좁히면 18건 전부 해소.** dev 검증 완료된 무위험 수리 (의미도 정합: dispatch_blocked는 전제 '변경'이 아니라 '미결').
- `sensitive_content` 결손 7건: focal contains에만 의존(779행) — gold는 record/scope 신호에서도 부여하는 듯. 채굴 여지.
- `target_ambiguity` 결손 2건 소액.

---

## 파트 6: build_plan_events

### dev 실측 (채점기: verb 불일치 = 이벤트 0점, 초과 이벤트 -0.06/개)
- plan<1.0 14건, 총손실 4.29유닛 = **-0.0064**.
- verb 열 불일치 4건은 전부 **scope mode 혼동과 같은 뿌리** (proceed 분기의 verbs를 mode가 결정: summary↔raw 혼동 4건 = summarize 삽입/누락 4건). **scope 수리 시 자동 동반 해소.**
- 나머지 10건은 verb 동일, target/args 차이 — args는 ontology 정준화 후 F1이라 부분점수 존재.
- ask 분기 reason: 절 confirm → clarify_precondition, record → route_resolution_required(817행). **stale-recall 수리 시 gold(0107)는 clarify_precondition + precondition_changed를 원함 → recall발 ask에도 clarify_precondition을 줘야 함.**
- verify target=share_boundary_update 고정은 소거 검증 완료 사항 — 유지.

---

## 파트 7: user_response

- 고정 문장 5종. semantic 축(0.04)은 서버 전용 — 로컬 측정 불가.
- 문장이 control·target·mode와 정합적, 구조적 결함 없음. 개선은 순수 탐사 영역(서버 델타로만 판독). 개선탄 무료 라이더 전용, 단독 발사 금지.

---

## 종합 — 실행 가능 항목 (가치순)

| # | 항목 | 근거 | dev 델타 | screening 질량 | 위험 |
|---|---|---|---|---|---|
| 1 | **both_recent를 boundary 값으로 amend/ask 분기** (decide_control 5-3) | dev 3건 완전 분리 + 0107 교차 | +2건 (control+게이트) | 50건 | n=3, 낮음 |
| 2 | **precondition_changed를 boundary 계열로 제한** (build_policy 785행) | dev 18/18 완전 분리 | +18건 부분점수 | 미측정(무해) | 사실상 0 |
| 3 | **ask의 scope 가족별 분기** (summary vs redacted) | dev 8건 vs 반례 2건 | 최대 +8건 부분점수 | ask류 ~190건 | 중간(반례 존재) |
| 4 | **stale-recall → ask + clarify_precondition + checkup 필드** (파트 0·6) | 0107 단건 + 의미론 | +1건 (이중 게이트) | recall 16건 중 일부 | n=1, 좁게 묶으면 낮음 |
| 5 | proceed의 summary/raw 경계 신호 재발굴 | dev 4건 역전 | +4건 부분점수 | 미상 | 판별자 미발견 |
| 6 | sensitive_content 부여 조건 확장 | dev 7건 결손 | +7건 부분점수 | 미상 | 채굴 필요 |

- **1+2 합승 추천** — 같은 boundary 원리의 두 얼굴 (Day 1 ①에 부합, both_recent는 기존 후보 명단에 있음). 2는 dev 무회귀가 수학적으로 보장.
- 3·5·6은 Day 1 ② scope/policy 묶음의 구체 좌표. 4는 ②에 합승.

## 청소 목록 (제출 불필요, Day 4)

- choose_focal 죽은 단 5개 (dev·screening 질량 0 실측 — 출력 불변 보장)
- SAME_PLACE_CUES (양쪽 질량 0)
- marker "rule 우선" 주석 정정 (불일치 실측 0)
- update_session_memory: last_evidence·TODO 잔재, 함수명 재고
- fb_surv2 = idx-1 잔재 6건 (기존 Day 4 항목과 동일 주소)

## 추기 — 발사 대차대조 (2026-07-08)

- #1 both_recent: **발사됨** (발 2, +0.0074 신기록 기여. 단 boundary∩order 교집합 판별 — 리뷰 원안인 boundary 단독은 dev diff 0 + screening +8건으로 별도 계측됨, 차기 합승 1순위)
- #2 precondition_changed: **발사됨** (발 3 계류, 42/42)
- #6 sensitive_content: **발사됨** (발 3, doctor_note 규칙 120/120)
- 파트 6 ask plan reason: **발사됨** (발 3, 경계변경 판별자로 26/26 — 리뷰 제안보다 강한 형태)
- #3 ask scope 분기: 미발사 — 리뷰의 후보 판별자로도 A-테이블이 안 갈림. 진짜 판별자 미발견
- #4 stale-recall / #5 proceed 경계: 미발사
- 서버 갭 산수: lawful 잔여 전부 합쳐 0.77~0.78 견고. 0.88은 fb-local 131건(이중 게이트) 도박의 적중 여부에 종속 — 이 문서의 지도 밖 광맥은 없음

## 리스크 재고 (수리 아님, 인지용)

- history 해석기 dev 무표본 경로 122건 (폴백 43 + single0 77 + joined 2) — focal 서버 추정치와 dev 만점의 간극이 살 유일한 주소. 신규 원리 없이 손대지 말 것.
- confirm(fb) 중재(618~633행)는 dev 표본 0 — screening 81건이 타고 있으나 검증 수단이 서버 델타뿐.
