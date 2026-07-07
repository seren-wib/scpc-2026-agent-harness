# harness.py 아키텍처

> 대상 파일: `harness.py` (813 lines) · 생성일: 2026-07-07
> baseline 노트북(`docs/SCPC2026_Final_baseline.ipynb`)의 `FixedSLMClient`(셀 5)·`FinalHarness`(셀 7)를 그대로 추출한 단일 파일. 상위권 검증 제출 대상이라 파일을 분리하지 않고 유지한다.

## 0. 한눈에 보기

```
Task(JSON) + Session(dict)
        │
        ▼
FixedSLMClient.summarize_task()          ── evidence(risk_flags/tags/redaction/confirmation)
        │
        ▼
FinalHarness.answer_task()
    ├─ update_session_memory()           ── self.memory 갱신 (persistent_memory_write 반영)
    ├─ choose_focal()                    ── focal object 결정
    ├─ infer_target()                    ── 수신처(target) 결정
    ├─ decide_control()                  ── proceed/ask/hold/amend 결정
    ├─ build_content_scope()             ── 공개 범위(allowed/excluded fields) 결정
    ├─ build_policy()                    ── risk_flags/violations 재계산
    ├─ build_plan_events()               ── verb 시퀀스(read/clarify/redact/dispatch/...) 생성
    └─ user_response()                   ── 사용자향 응답 문장 생성
        │
        ▼
answer dict (SUBMISSION_SCHEMA = "scpc.final.answer.v1")
```

모듈 상수는 두 개뿐이다: `SUBMISSION_SCHEMA = "scpc.final.answer.v1"`, `FIXED_SLM_ID = "scpc-final-fixed-slm-local-facade"`.

---

## 1. `FixedSLMClient` (17–54행)

과제(SLM)를 흉내 내는 로컬 파사드. 입력 task를 텍스트로 뭉쳐서(prompt + device_state.records + personal_memory) 키워드 매칭만으로 4개 필드를 만든다.

| 출력 필드 | 판정 방식 |
|---|---|
| `risk_flags` | `phishing`(피싱/security_alert), `payment`(phishing과 동반), `health`, `external_share`, `privacy`, `sensitive_content`(rrn/raw_quote/실명/위치), `ambiguous_reference` — 키워드 존재 여부로 set에 추가 |
| `audit_tags` | `security_precedence`(피싱 동반), `consent_precedence`, `resolved_target`(ambiguous 동반) |
| `requires_redaction` | `raw_sensitive_forbidden`/`raw_quote_forbidden`/`numeric_value_forbidden`/실명/위치/원문 중 하나라도 등장 |
| `requires_confirmation` | `ambiguous`/`amount_changed`/`duration_ambiguous`/`missing`/확인/모호 중 하나라도 등장 |

순수 문자열 매칭이며 상태를 갖지 않는다. `FinalHarness`는 이 결과를 `evidence`로 받아 이후 모든 단계에 전달한다.

---

## 2. 데이터 접근 헬퍼 (57–110행)

task/JSON 구조를 다루는 저수준 유틸리티.

- `records_of(task)` / `objects_of(task)` — `device_state.records` / `device_state.objects` 배열 추출
- `record_map(records)` — `{type: value}` 딕셔너리로 평탄화 (동일 type은 나중 값이 덮음)
- `history_in_turn_order(task)` — `visible_history`를 `turn` 값으로 정렬. **배열 순서≠시간 순서**라는 핸드북 §5 경고에 따라 turn 오름차순으로 재정렬하고, turn 없는 항목은 최고참으로 취급
- `text_of(value)` / `object_text(obj)` — 임의 값을 검색 가능한 소문자 문자열로 직렬화

이 6개 함수가 이후 모든 판단 로직의 입력 파이프라인이다.

---

## 3. Focal(참조 대상) 해석 파이프라인

가장 복잡한 서브시스템. "이 지시가 가리키는 object가 무엇인가"를 다단계 사다리로 좁혀 나간다.

### 3.1 `resolve_focal_by_marker` (119–152행) — 0순위: marker 간접 참조
`focal_marker_refs`(marker→ref_code)와 `focal_resolution_trace`(phase→marker, latest_phase_rule) record가 모두 있을 때만 동작. phase 후보를 신뢰도 순으로 모은다:
1. `phase_source`가 가리키는 binding/route record → rule 매핑값 (최신 상태 반영, 최우선)
2. `trace.latest_phase` (명시된 최신 phase)
3. `rule.fallback`

이 phase로 marker→ref_code→object 체인을 완성하면 반환, 실패하면 `None`으로 하위 단계에 넘긴다.

### 3.2 `score_codes_in_summary` (155–232행) — history 문장 내 WM-code 점수화
정규식 `WM_CODE = [A-Z]{2,4}-\d{3,6}` 로 코드(WM-1234 등)를 찾고, 문장 내 위치 신호로 점수를 매긴다:

| 신호 | 규칙 |
|---|---|
| 전/후 문맥 키워드 | `FOCAL_POS`(확정/승인/우선/처리 대상/기준 참조/최종) → 앞 문맥 +2, 뒤 문맥 +1 / `FOCAL_NEG`(보류/제외/무시/취소) → 앞 -2, 뒤 -1. 한국어는 수식어가 명사 앞이라 앞 문맥에 가중치 2배 |
| 서수 한정("N번째 후보**만**") | 해당 코드 +3, 나머지 서수 코드 -1 |
| 서수 뒤 긍/부정어 | ±2 |
| "가운데" + 긍정어 | 중간 코드 +2 |
| "마지막" + 한정/긍정 | 마지막 코드 +2, 부정이면 -2 |
| 위치 지시 1개 & 어휘 신호 전무 | 그 코드 +2 (구조 신호로 인정) |
| 반복 호명(코드가 2회 이상 등장 & 유일) | +2 |

문맥 창은 문장 경계(`.`)와 이웃 코드 경계에서 잘라 옆 후보 신호를 훔치지 않게 한다.

### 3.3 `resolve_focal_by_history` (328–404행) — 1순위: history 기반 확정/승인 탐색
최신 history summary부터 역순으로 `score_codes_in_summary` 적용:
- 최고점 코드가 양수면 즉시 채택
- 후보가 1개뿐이고 0점 이상이면 채택
- 애매하면 이후 요약들 + prompt를 이어붙여 재채점(joined rescoring)
- 그래도 안 되면 **fallback 사다리**(긍정 신호 없는 첫 케이스에서 1회만 계산):
  1. object 속성 텍스트의 긍/부정 어휘 점수(`attr_pos`/`attr_neg`) 단독 최고
  2. record 값이 후보 attrs를 그대로 메아리치는 경우(echo)
  3. prompt 도메인 키워드가 가리키는 object type(`DOMAIN_TYPE_HINTS`) 매칭이 유일
  4. 세션의 `last_focal_id`를 이어받는 후보(carried)
  5. prompt 토큰 겹침 최고점이 2등보다 확실히 높은 경우(token_pick)
  6. 그래도 없으면 구조적 사전확률: 생존 후보 중 **2번째**(dev 데이터 관찰 기반 휴리스틱)

### 3.4 `FinalHarness.choose_focal` (457–524행) — 전체 우선순위 사다리

| 순서 | 조건 | 동작 |
|---|---|---|
| 0 | `resolve_focal_by_marker` 성공 | 그 object 반환 |
| 0-1 | records 값에 WM-code가 정확히 1개만 유효 ref_code로 매칭 | 그 object 반환 |
| 0-2 | `resolve_focal_by_history` 성공 | 그 object 반환 |
| 1 | record 값(문자열/dict value)이 object id를 직접 가리킴(최신 record부터) | 그 object 반환 |
| 2 | visible_history 텍스트에 ref_code가 등장 | 그 object 반환 |
| 2-2 | prompt 도메인 키워드 → `DOMAIN_TYPE_HINTS`로 object type 특정, 후보가 유일하거나 history에 ref_code 등장 | 그 object 반환 |
| 3 | 위 전부 실패 | prompt 토큰과 attrs 텍스트 겹침 점수 최고인 object (fallback, 없으면 objects[0]) |

---

## 4. "단, ..." 꼬리 절 파서 (235–287행)

핸드북 상 가장 최신 지시로 취급되는 `단,`/`다만,` 꼬리 구절 처리. **이전 버전은 이 파서가 268개 케이스에서 실패해 -0.17 손실을 냈던 지점**(마커는 잡히는데 절 내용 어휘가 사전 밖 → `clause_kind`가 `None`으로 흘러 record 미끼로 오판됨).

- `final_clause(task)`: prompt 우선, 없으면 **최신 turn**의 history summary에서만 `단,`/`다만,` 마커 검색 (옛 턴의 절이 현재 턴을 납치하지 않도록 turn 필터링)
- `clause_kind_tier(task)`: 절 텍스트를 (kind, 신뢰 층위) 쌍으로 판정. `clause_kind()`는 kind만 주는 래퍼.
  - **lex 층** (dev 검증된 강신호): `CLAUSE_LOCAL`→local, `CLAUSE_STOP` 또는 `clause_invalidated`(허용계 명사×소멸계 술어 공존, 불확실 표지 가드)→stop, `CLAUSE_SCOPE`→scope, `clause_prohibited`(행위 금지형, scope/말고 리다이렉트 거부권)→stop, `CLAUSE_CONFIRM`→confirm
  - **fb 층** (사전 밖 절의 느슨한 추정 — dev에 표본 0, screening에서만 발화): 중단어→stop, 확인/물어→confirm, 요약/제외/빼고→scope, **기본값 `"local"`** (꼬리 정정의 최빈 의도가 "내부 처리로 축소"이기 때문)
  - ⚠ 분기 귀속 실측(2026-07-07): screening 700 중 절 경로 432(61.7%), 그중 **fb층 284(40.6%)** — fb-default:local 131 / fb:confirm 81 / fb:scope 49 / fb:stop 23. dev는 전부 lex층이라 fb층 수정은 구조적으로 dev 무회귀.

이 `clause_kind` 결과는 `infer_target`/`decide_control`/`build_policy`/`build_plan_events` 전부에서 최우선 분기로 쓰인다. 단 `decide_control`에서 **fb:confirm은 약신호로 격하**되어 record 사다리(`record_control`)가 확정적 hold를 내면 그쪽이 이긴다 (screening 실측: 81건 중 13건 ask→hold 전환).

---

## 5. Target(수신처) 해석 — `infer_target` (526–577행)

| 순서 | 조건 | 결과 |
|---|---|---|
| 1 | `clause_kind == "local"` | `"memory_store"` |
| 1 | `clause_kind in ("stop","confirm")` | `"user"` |
| 2 | record에 `persistent_memory_write` 존재 | `"memory_store"` |
| 3 | `persistent_memory_recall` 존재 | `memory_field_for()`로 도메인 필드 결정 → `self.memory`에서 프로필 조회, 없으면 `MEMORY_FIELD_DEFAULTS` |
| 4 | `target_changed_after_turn` record | 그 안의 target/to/new_target/value/name/recipient 값 |
| 5 | `resolved_target` record | 그 안의 target/route/value/name/recipient 값 |
| 6 | prompt에 `SAME_PLACE_CUES`("같은 곳"/"거기로" 등) & 세션에 `last_target` 있음 | 세션의 `last_target` 이어받기 |
| 7 | focal의 attrs(recipient/target/channel/app/merchant/name) | 그 값 |
| 8 | 전부 실패 | 세션의 `last_target` 또는 `"user"` |

`memory_field_for()`(290–308행)는 recall의 `memory_class`(prior_result→last_success_target, standing_constraint→approval_channel) 또는 record 타입(ops_memory_recall/enterprise_policy_recall), 아니면 prompt 도메인 키워드(조명/건강/승인)로 저장 프로필 필드명을 정한다.

---

## 6. Control(진행 방침) 결정 — `decide_control` (579–686행)

4값 상태 머신: `proceed` / `ask` / `hold` / `amend`. 우선순위 순서대로 첫 매치가 결정된다.

| 순서 | 조건 | 결과 | 비고 |
|---|---|---|---|
| 0 | `clause_kind` 존재 | local→proceed, stop→hold, scope→amend, confirm(lex)→ask | 절이 record 신호보다 최우선. **fb:confirm만 예외** — `record_control`이 hold면 hold, 아니면 ask (약신호 절은 확정적 record 신호에 진다) |
| 1 | `security_alert`/phishing 플래그, `safety_mode` 비정상, 동의 철회(consent record만) | `hold` | 안전/동의는 무조건 중단 |
| 2 | `external_share_policy`/`health_share_policy`에 forbidden + doctor_note/health | `hold` | 건강 원문 등 공유 금지 |
| 3 | `persistent_memory_write` | `proceed` | 메모리 기록은 그대로 진행 |
| 4 | recall된 프로필의 `avoid` 항목이 prompt에 등장 | `hold` | / "반대"·"다른 말투" | `ask` |
| 4-2 | `impersonation`/`minor_location` | `hold` · `one_time_or_recurring`/`duration_ambiguous`/`calendar_conflict`/`tone_conflict` | `ask` · `stored_preference_violation`/`privacy_rule_violation` | `hold` |
| 5 | `payment_policy`=confirmation, `over_50000` | `ask` · 원본+익명+local_update 조합 | `proceed` · `target_changed_after_turn` | `ask` |
| 5-2 | `guardrail_ladder_signal` + ambiguous_target/focal → `route_binding_order`로 분기 | authority_after_candidates: confirmed→proceed, incomplete/pending→hold · boundary_after_authority→ask | |
| 5-3 | `ambiguous_target == surface_recipient_and_resolved_target_both_recent` | `ask` · amount_changed/merchant_verification/memory_conflict/duration_ambiguous 타입 | `ask` |
| 6 | ambiguous(target/focal) 미해소(`route_candidate_snapshot`/`dispatch_authority_check`로 미확정) | blocked/pending→hold, 그 외→ask | |
| 7 | 원문 금지/summary_only, ops_memory_recall/enterprise_policy_recall, session_share_policy=strict | `amend` | 기본 축소 진행 |
| — | 위 전부 미해당 | `proceed` | 기본값 |

---

## 7. 출력 조립 단계

### 7.1 `build_content_scope` (700–720행)
`control` 값에 따라 공개 범위를 결정한다.

| control | mode | allowed_fields | excluded_fields | requires_confirmation |
|---|---|---|---|---|
| hold | none | [] | [] | False |
| ask | summary | [summary] | [raw_quote] | True |
| amend | redacted | [summary] | `sensitive_fields_of(focal)` 또는 [raw_quote] | ambiguous 여부 |
| proceed(로컬: memory_write/clause=local/share_boundary_update=local_update) | status_only | [status] | strict면 [location, numeric_value, raw_quote] | False |
| proceed(비strict) | raw | [summary, title] | [] | False |
| proceed(strict) | summary | [summary] | [] | False |

`sensitive_fields_of`(695–698행)는 focal의 `attrs.contains` 목록을 `SENSITIVE_FIELD_MAP`(raw_quote/rrn/name/location/numeric_value·amount/doctor_note/card_number)으로 변환.

### 7.2 `build_policy` (722–758행)
`risk_flags`를 재구성: strict_share_policy, target_ambiguity, ambiguous_focal, sensitive_content(민감 필드 존재), external_share(target이 memory_store/user가 아님), precondition_changed(share_boundary_update 존재), local_only(clause가 local/stop/confirm 또는 memory_write/local_update). control별 추가: hold→precondition_invalidated+safety, ask→clarification_required, amend→external_share+minimal_disclosure. `violations`는 hold일 때만 `["precondition_changed_ignored"]`.

### 7.3 `build_plan_events` (760–802행)
control별 verb 시퀀스(핸드북 verb 어휘: read/clarify/guard/redact/dispatch/verify/update/summarize):

- **hold**: `read`(invalidated_precondition) → `guard`(precondition_invalidated)
- **ask**: `read`(purpose는 clause=confirm이면 clarify_precondition, 아니면 route_resolution_required) → `clarify`(target=user)
- **amend**: `read`(minimal_disclosure) → `redact`(raw_quote 또는 sensitive_fields) → `dispatch`(scope=redacted)
- **proceed & mode=status_only**: `read`(local_update) → `verify`(share_boundary_update) → `update`(local_status_only)
- **proceed & mode=raw**: `read`(inspect_context) → `dispatch`(scope=raw)
- **proceed & 기타(summary)**: `read` → `summarize` → `dispatch`(scope=summary)

### 7.4 `user_response` (804–813행)
control/scope 조합을 4가지 고정 문장 템플릿으로 매핑(hold/ask/amend/status_only/기본 진행 문구).

---

## 8. `FinalHarness` 클래스 전체 흐름 (407–443행)

```python
class FinalHarness:
    def __init__(self):
        self.slm = FixedSLMClient()
        self.memory: dict = {}          # 세션 간 영속(prepare()에서만 초기화)

    def prepare(self, tasks): self.memory.clear()

    def answer_task(self, task, session):
        evidence = self.slm.summarize_task(task)
        self.update_session_memory(task, session, evidence)   # persistent_memory_write 반영

        focal   = self.choose_focal(task, session, evidence)
        target  = self.infer_target(task, focal, session, evidence)
        control = self.decide_control(task, focal, target, evidence)
        scope   = self.build_content_scope(task, focal, control, evidence)
        policy  = self.build_policy(task, focal, control, evidence, target)
        events  = self.build_plan_events(task, focal_id, target, control, scope, policy)

        session["last_focal_id"], session["last_target"], session["last_control"] = ...
        return {focal_id, target, control, content_scope, policy,
                plan_events, user_response, audit_tags, counterfactual}
```

### 세션 상태(`session: dict`, task 간 영속)
- `last_focal_id` / `last_target` / `last_control` — 매 turn 종료 시 갱신, `infer_target`의 "같은 곳" 참조와 focal fallback의 `carried` 후보에 재사용
- `last_evidence` — `update_session_memory`에서 저장(현재 다른 곳에서 직접 참조되진 않음)

### 인스턴스 상태(`self.memory: dict`, task 실행 전체에 걸쳐 영속)
- `persistent_memory_write` record가 있으면 `memory_key`/`person` 양쪽 키로 저장(같은 키는 최신 write가 덮음)
- `infer_target`/`decide_control`의 `persistent_memory_recall` 처리에서 프로필 조회에 사용

### 최종 반환 스키마
```
{
  "focal_id": str, "target": str, "control": "proceed|ask|hold|amend",
  "content_scope": {mode, allowed_fields, excluded_fields, requires_user_confirmation},
  "policy": {risk_flags, violations, requires_confirmation},
  "plan_events": [{verb, target, args}, ...],
  "user_response": str,
  "audit_tags": [...],            # evidence에서 그대로 전달
  "counterfactual": str,          # 고정 문구
}
```

---

## 9. 설계상 특징 요약

- **최신성 원칙이 전체를 관통한다**: marker phase, "단," 절, `target_changed_after_turn`, `share_boundary_update` 등 "가장 최근 상태/지시가 이전을 덮는다"는 규칙이 focal/target/control 세 축 모두에서 반복 적용된다.
- **사다리(ladder) 패턴**: `choose_focal`(7단계), `decide_control`(9단계), `resolve_focal_by_history`의 fallback(6단계)이 모두 "구조적으로 강한 신호 → 약한 신호 → 통계적 사전확률" 순으로 내려가는 동일한 설계를 공유한다.
- **어휘 사전 폴백은 알려진 리스크 지점**: `clause_kind`의 느슨한 폴백, focal fallback의 "생존 후보 중 2번째" 휴리스티브, `MEMORY_FIELD_DEFAULTS` 하드코딩은 dev 데이터 관찰에서 나온 경험적 규칙이라 원리 기반 대체가 필요한 부채로 코드 주석에도 명시돼 있다.
