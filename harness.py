"""SCPC 2026 AI Agent Harness.

baseline 노트북(docs/SCPC2026_Final_baseline.ipynb)의 FixedSLMClient(셀 5)와
FinalHarness(셀 7)를 그대로 추출한 파일. 점수는 이 파일의 판단 함수들을 개선해서 낸다.
상위권 검증 제출 대상이므로 단일 파일을 유지한다.
"""
from __future__ import annotations

import json
import re
from typing import Any

SUBMISSION_SCHEMA = "scpc.final.answer.v1"
FIXED_SLM_ID = "scpc-final-fixed-slm-local-facade"


class FixedSLMClient:
    model_id = FIXED_SLM_ID

    def summarize_task(self, task: dict[str, Any]) -> dict[str, Any]:
        text_parts: list[str] = [str(task.get("prompt", ""))]
        device_state = task.get("device_state", {}) or {}
        for rec in device_state.get("records", []) or []:
            text_parts.append(str(rec.get("type", "")))
            text_parts.append(str(rec.get("value", "")))
        for mem in task.get("personal_memory", []) or []:
            text_parts.append(str(mem.get("text", "")))
        text = " ".join(text_parts).lower()

        flags: set[str] = set()
        tags: set[str] = set()
        if "phishing" in text or "피싱" in text or "security_alert" in text:
            flags.update(["payment", "phishing"])
            tags.add("security_precedence")
        if "consent" in text or "동의" in text:
            tags.add("consent_precedence")
        if "health" in text or "건강" in text or "복약" in text or "검진" in text:
            flags.add("health")
        if "external" in text or "외부" in text:
            flags.add("external_share")
        if "privacy" in text or "개인정보" in text or "개인" in text:
            flags.add("privacy")
        if "rrn" in text or "raw_quote" in text or "실명" in text or "위치" in text:
            flags.add("sensitive_content")
        if "ambiguous" in text or "모호" in text:
            flags.add("ambiguous_reference")
            tags.add("resolved_target")

        return {
            "risk_flags": sorted(flags),
            "requires_redaction": any(k in text for k in ["raw_sensitive_forbidden", "raw_quote_forbidden", "numeric_value_forbidden", "실명", "위치", "원문"]),
            "requires_confirmation": any(k in text for k in ["ambiguous", "amount_changed", "duration_ambiguous", "missing", "확인", "모호"]),
            "audit_tags": sorted(tags),
        }


def records_of(task: dict[str, Any]) -> list[dict[str, Any]]:
    return list(((task.get("device_state") or {}).get("records") or []))


def objects_of(task: dict[str, Any]) -> list[dict[str, Any]]:
    return list(((task.get("device_state") or {}).get("objects") or []))


def record_map(records: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for record in records:
        if isinstance(record, dict):
            out[str(record.get("type"))] = record.get("value")
    return out


def text_of(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def object_text(obj: dict[str, Any]) -> str:
    attrs = obj.get("attrs") or {}
    return " ".join([
        str(obj.get("id", "")),
        str(obj.get("type", "")),
        text_of(attrs),
    ]).lower()


WM_CODE = re.compile(r"WM-\d+")
FOCAL_POS = ("확정", "승인", "우선", "처리 대상", "기준 참조", "최종")
FOCAL_NEG = ("보류", "제외", "무시", "취소")
ORDINALS = {"첫": 0, "두": 1, "세": 2, "네": 3, "다섯": 4}


def resolve_focal_by_marker(task: dict[str, Any]) -> dict[str, Any] | None:
    """marker 간접 참조 해석: route/binding record가 고른 phase → marker → ref_code → object."""
    rec = record_map(records_of(task))
    refs = rec.get("focal_marker_refs")
    trace = rec.get("focal_resolution_trace")
    if not isinstance(refs, dict) or not isinstance(trace, dict):
        return None
    marker_to_ref = refs.get("marker_to_ref") or {}
    phase = trace.get("latest_phase")
    if not phase:
        rule = trace.get("latest_phase_rule") or {}
        source_val = rec.get(str(trace.get("phase_source")))
        phase = rule.get(str(source_val)) or rule.get("fallback")
    marker = (trace.get("phase_to_marker") or {}).get(str(phase))
    ref = marker_to_ref.get(str(marker))
    if not ref:
        return None
    for obj in objects_of(task):
        if str((obj.get("attrs") or {}).get("ref_code")) == str(ref):
            return obj
    return None


def score_codes_in_summary(summary: str) -> dict[str, float]:
    """history 문장 안 WM-code마다 주변 긍정/부정 신호를 점수화.

    문맥 창은 문장 경계(.)와 이웃 코드에서 잘라 옆 후보의 신호를 훔치지 않게 하고,
    한국어는 수식어가 명사 앞에 오므로 코드 앞 문맥에 2배 가중치를 준다.
    """
    matches = list(WM_CODE.finditer(summary))
    if not matches:
        return {}
    scores: dict[str, float] = {}
    for i, m in enumerate(matches):
        code = m.group(0)
        scores.setdefault(code, 0.0)
        pre_start = summary.rfind(".", 0, m.start()) + 1
        if i > 0:
            pre_start = max(pre_start, matches[i - 1].end())
        pre = summary[max(pre_start, m.start() - 24):m.start()]
        post_end = summary.find(".", m.end())
        post_end = len(summary) if post_end < 0 else post_end
        if i + 1 < len(matches):
            post_end = min(post_end, matches[i + 1].start())
        post = summary[m.end():min(post_end, m.end() + 24)]
        if any(p in pre for p in FOCAL_POS):
            scores[code] += 2
        if any(n in pre for n in FOCAL_NEG):
            scores[code] -= 2
        if any(p in post for p in FOCAL_POS):
            scores[code] += 1
        if any(n in post for n in FOCAL_NEG):
            scores[code] -= 1
    uniq = list(dict.fromkeys(m.group(0) for m in matches))
    for om in re.finditer(r"(첫|두|세|네|다섯)\s*번째", summary):
        idx = ORDINALS[om.group(1)]
        after = summary[om.end():om.end() + 24]
        if idx < len(uniq):
            if any(n in after for n in FOCAL_NEG):
                scores[uniq[idx]] -= 2
            elif any(p in after for p in FOCAL_POS):
                scores[uniq[idx]] += 2
    g = summary.find("가운데")
    if g >= 0 and uniq and any(p in summary[g:g + 28] for p in FOCAL_POS):
        scores[uniq[len(uniq) // 2]] += 2
    return scores


# "단, ..." 꼬리 정정 구절: 가장 최신 지시라서 target/control을 동시에 결정한다.
CLAUSE_LOCAL = ("상태값만", "상태만 갱신", "상태만 바꾸", "로컬 상태", "내부 상태", "내부 업데이트",
                "기기 안", "장치 안", "공유하지 말", "보내지 말", "전달 대신", "전달 동작은 취소")
CLAUSE_STOP = ("멈춰야", "막아야", "진행하면 안", "실행하면 안", "처리하지 않는다", "기대면 안")
CLAUSE_CONFIRM = ("사용자에게 먼저 확인", "다시 확인", "먼저 확인", "확인해야 한다", "확인 전에는",
                  "추가 확인 없이", "미확정", "확인되지 않았", "결론을 내릴 수 없")
CLAUSE_SCOPE = ("요약만", "제외한 요약", "세부값을 제외")


def final_clause(task: dict[str, Any]) -> str:
    """prompt(현재 발화) 우선, 없으면 최신 history에서 '단,' 꼬리 구절을 찾는다."""
    sources = [str(task.get("prompt", ""))]
    sources += [str((h or {}).get("summary", "")) for h in reversed(task.get("visible_history") or [])]
    for src in sources:
        i = src.rfind("단,")
        if i >= 0:
            return src[i:]
    return ""


def clause_kind(task: dict[str, Any]) -> str | None:
    clause = final_clause(task)
    if not clause:
        return None
    if any(k in clause for k in CLAUSE_LOCAL):
        return "local"
    if any(k in clause for k in CLAUSE_STOP):
        return "stop"
    if any(k in clause for k in CLAUSE_SCOPE):
        return "scope"
    if any(k in clause for k in CLAUSE_CONFIRM):
        return "confirm"
    return None


def memory_field_for(task: dict[str, Any], recall: dict[str, Any]) -> str:
    """recall 상황에서 저장 프로필의 어느 필드가 수신처인지 도메인으로 정한다."""
    if recall.get("memory_class") == "prior_result":
        return "last_success_target"
    if recall.get("memory_class") == "standing_constraint":
        return "approval_channel"
    rec = record_map(records_of(task))
    if "ops_memory_recall" in rec:
        return "last_success_target"
    if "enterprise_policy_recall" in rec:
        return "approval_channel"
    prompt = str(task.get("prompt", ""))
    if any(k in prompt for k in ("조명", "공간", "조도", "불을")):
        return "dusk_room"
    if any(k in prompt for k in ("검진", "점검", "건강", "복약", "처방")):
        return "health_channel"
    if "승인" in prompt:
        return "approval_channel"
    return "preferred_channel"


# 프로필을 못 찾았을 때(스트림에 write가 없던 경우)의 도메인 기본값.
MEMORY_FIELD_DEFAULTS = {"dusk_room": "living_room", "health_channel": "caregiver"}


def resolve_focal_by_history(task: dict[str, Any]) -> dict[str, Any] | None:
    """visible_history에서 확정/승인된 ref_code를 찾아 해당 object 반환 (최신 항목 우선)."""
    by_ref = {str((o.get("attrs") or {}).get("ref_code")): o for o in objects_of(task)}
    for item in reversed(task.get("visible_history") or []):
        summary = str((item or {}).get("summary", ""))
        scores = score_codes_in_summary(summary)
        cands = [c for c in scores if c in by_ref]
        if not cands:
            continue
        best = max(cands, key=lambda c: scores[c])
        if scores[best] > 0:
            return by_ref[best]
        if len(cands) == 1:
            return by_ref[cands[0]]
    return None


class FinalHarness:
    def __init__(self) -> None:
        self.slm = FixedSLMClient()
        self.memory: dict[str, Any] = {}

    def prepare(self, tasks: list[dict[str, Any]]) -> None:
        # 운영 runner와 같은 형태를 유지하기 위한 hook입니다.
        # 전체 평가 대상 미리보기 없이, 실행 중 얻은 정보만 self.memory에 누적하는 방식으로 사용하세요.
        self.memory.clear()

    def answer_task(self, task: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
        evidence = self.slm.summarize_task(task)
        self.update_session_memory(task, session, evidence)

        focal = self.choose_focal(task, session, evidence)
        focal_id = str(focal.get("id") or "")
        target = self.infer_target(task, focal, session, evidence)
        control = self.decide_control(task, focal, target, evidence)
        content_scope = self.build_content_scope(task, focal, control, evidence)
        policy = self.build_policy(task, focal, control, evidence, target)
        plan_events = self.build_plan_events(task, focal_id, target, control, content_scope, policy)

        session["last_focal_id"] = focal_id
        session["last_target"] = target
        session["last_control"] = control

        return {
            "focal_id": focal_id,
            "target": target,
            "control": control,
            "content_scope": content_scope,
            "policy": policy,
            "plan_events": plan_events,
            "user_response": self.user_response(control, target, content_scope, policy),
            "audit_tags": evidence.get("audit_tags", []),
            "counterfactual": "최신 기록, 동의 상태, 공유 범위, 보안 신호가 바뀌면 판단이 달라질 수 있습니다.",
        }

    def update_session_memory(self, task: dict[str, Any], session: dict[str, Any], evidence: dict[str, Any]) -> None:
        # TODO: 같은 session 안에서 이후 turn이 참고해야 하는 정보를 저장하세요.
        # 예: 최근 focal, 최근 target, 사용자 선호, 이전 성공/실패 결과 등.
        for record in records_of(task):
            if record.get("type") == "persistent_memory_write" and isinstance(record.get("value"), dict):
                value = record["value"]
                # memory_key와 person 양쪽으로 저장한다. person은 최신 write가 덮는다.
                for key in (value.get("memory_key"), value.get("person")):
                    if key:
                        self.memory[str(key)] = value
        session["last_evidence"] = evidence

    def choose_focal(self, task: dict[str, Any], session: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        objects = objects_of(task)
        records = records_of(task)
        if not objects:
            return {}

        # 0) marker 간접 참조가 있으면 그 체인이 가장 명시적인 근거다.
        focal = resolve_focal_by_marker(task)
        if focal is not None:
            return focal

        # 0-2) history에서 확정/승인된 ref_code가 지목되면 따른다.
        focal = resolve_focal_by_history(task)
        if focal is not None:
            return focal

        # 1) record 값이 object id를 직접 가리키면 우선합니다.
        object_by_id = {str(o.get("id")): o for o in objects}
        for record in reversed(records):
            value = record.get("value")
            candidates: list[str] = []
            if isinstance(value, str):
                candidates.append(value)
            elif isinstance(value, dict):
                candidates.extend(str(v) for v in value.values() if isinstance(v, str))
            for candidate in candidates:
                if candidate in object_by_id:
                    return object_by_id[candidate]

        # 2) visible_history의 WM-code와 object ref_code가 맞으면 활용합니다.
        history_text = " ".join(text_of(item) for item in task.get("visible_history", [])).lower()
        for obj in objects:
            ref_code = str((obj.get("attrs") or {}).get("ref_code") or "").lower()
            if ref_code and ref_code in history_text:
                return obj

        # 3) prompt와 attrs 텍스트가 많이 겹치는 object를 고릅니다.
        prompt_tokens = {tok for tok in re.findall(r"[A-Za-z0-9가-힣_]+", str(task.get("prompt", "")).lower()) if len(tok) >= 2}
        best = objects[0]
        best_score = -1
        for obj in objects:
            obj_text = object_text(obj)
            score = sum(1 for tok in prompt_tokens if tok in obj_text)
            if score > best_score:
                best = obj
                best_score = score
        return best

    def infer_target(self, task: dict[str, Any], focal: dict[str, Any], session: dict[str, Any], evidence: dict[str, Any]) -> str:
        rec = record_map(records_of(task))
        attrs = focal.get("attrs") or {}

        # 1) "단, ..." 꼬리 정정이 가장 최신 지시: 내부 갱신 → memory_store, 확인/중지 → user.
        kind = clause_kind(task)
        if kind == "local":
            return "memory_store"
        if kind in ("stop", "confirm"):
            return "user"

        # 2) 메모리 기록 요청 자체는 저장소가 대상이다.
        if "persistent_memory_write" in rec:
            return "memory_store"

        # 3) 저장된 프로필 recall: 도메인에 맞는 필드가 수신처.
        recall = rec.get("persistent_memory_recall")
        if isinstance(recall, dict):
            field = memory_field_for(task, recall)
            profile = self.memory.get(str(recall.get("memory_key"))) or self.memory.get(str(recall.get("person")))
            if isinstance(profile, dict) and profile.get(field):
                return str(profile[field])
            if field in MEMORY_FIELD_DEFAULTS:
                return MEMORY_FIELD_DEFAULTS[field]

        # 4) 턴 이후 대상 변경이 기존 해석보다 최신이다.
        changed = rec.get("target_changed_after_turn")
        if isinstance(changed, str) and changed:
            return changed

        # 5) 문맥상 해석된 대상.
        resolved = rec.get("resolved_target")
        if isinstance(resolved, dict):
            for key in ("target", "route", "value", "name", "recipient"):
                if resolved.get(key):
                    return str(resolved[key])
        if isinstance(resolved, str) and resolved:
            return resolved

        for key in ("recipient", "target", "channel", "app", "merchant", "name"):
            if attrs.get(key):
                return str(attrs[key])
        return str(session.get("last_target") or "user")

    def decide_control(self, task: dict[str, Any], focal: dict[str, Any], target: str, evidence: dict[str, Any]) -> str:
        records = records_of(task)
        types = {str(r.get("type")) for r in records}
        values = " ".join(text_of(r.get("value")) for r in records).lower()
        flags = set(evidence.get("risk_flags", []))

        # 0) "단, ..." 꼬리 정정이 최신 지시라 record 신호보다 우선한다.
        kind = clause_kind(task)
        if kind == "local":
            return "proceed"
        if kind == "stop":
            return "hold"
        if kind == "scope":
            return "amend"
        if kind == "confirm":
            return "ask"

        rec = record_map(records)

        # 1) 안전/동의 계열은 무조건 중단.
        if "security_alert" in types or "phishing" in flags:
            return "hold"
        safety = str(rec.get("safety_mode", ""))
        if safety and safety not in ("off", "inactive", "normal"):
            return "hold"
        consent = rec.get("consent")
        consent_status = str(consent.get("status", "")) if isinstance(consent, dict) else str(consent or "")
        if any(w in consent_status for w in ("revoked", "withdraw", "denied", "철회", "거부")):
            return "hold"
        if any(w in values for w in ("revoked", "철회")):
            return "hold"

        # 2) 건강 원문 등 외부 공유 자체가 금지된 경우 중단.
        forbid = str(rec.get("external_share_policy", "")) + " " + str(rec.get("health_share_policy", ""))
        if "doctor_note" in forbid or "health" in forbid and "forbidden" in forbid:
            return "hold"

        # 3) 메모리 기록 요청은 그대로 진행.
        if "persistent_memory_write" in rec:
            return "proceed"

        # 4) 저장 프로필과의 충돌: 기피 항목 위반은 중단, 취향 반전은 확인.
        recall = rec.get("persistent_memory_recall")
        if isinstance(recall, dict):
            profile = self.memory.get(str(recall.get("memory_key"))) or self.memory.get(str(recall.get("person")))
            prompt = str(task.get("prompt", ""))
            if isinstance(profile, dict) and profile.get("avoid") and str(profile["avoid"]) in prompt:
                return "hold"
            if "반대" in prompt or "다른 말투" in prompt:
                return "ask"

        # 5) 확인이 필요한 변경/불일치 신호.
        if "confirmation" in str(rec.get("payment_policy", "")):
            return "ask"
        prompt = str(task.get("prompt", ""))
        if "원본" in prompt and "익명" in prompt and "local_update" in str(rec.get("share_boundary_update", "")):
            return "proceed"
        if "target_changed_after_turn" in rec:
            return "ask"

        # 5-2) guardrail 사다리: route_binding_order가 어느 record가 최신 심판인지 알려준다.
        #      authority가 최신이면 그 확정 여부가 결정하고, boundary가 최신이면 review 미결로 확인이 필요하다.
        if "guardrail_ladder_signal" in rec and ("ambiguous_target" in rec or "ambiguous_focal" in rec):
            order = str(rec.get("route_binding_order", ""))
            authority = str(rec.get("dispatch_authority_check", ""))
            if order == "authority_after_candidates":
                if "confirmed" in authority:
                    return "proceed"
                if "incomplete" in authority or "pending" in authority:
                    return "hold"
            if order == "boundary_after_authority":
                return "ask"

        # 5-3) 표면 수신처와 해석된 수신처가 둘 다 최신이면 사람이 골라야 한다.
        if str(rec.get("ambiguous_target", "")) == "surface_recipient_and_resolved_target_both_recent":
            return "ask"
        if any(t in types for t in ("amount_changed", "merchant_verification", "memory_conflict", "duration_ambiguous")):
            return "ask"

        # 6) 모호성: route/authority record가 해소했으면 넘어가고, 아니면 확인/중단.
        snapshot = str(rec.get("route_candidate_snapshot", ""))
        authority = str(rec.get("dispatch_authority_check", ""))
        ambiguous = "ambiguous_target" in rec or "ambiguous_focal" in rec
        resolved = "single" in snapshot or "confirmed" in authority
        if ambiguous and not resolved:
            if "blocked" in authority or "pending" in authority:
                return "hold"
            return "ask"

        # 7) 축소 진행 신호: 원문 금지, 과거 작업/규정 recall, 엄격 공유 정책.
        if "forbidden" in forbid or "summary_only" in forbid:
            return "amend"
        if "ops_memory_recall" in rec or "enterprise_policy_recall" in rec:
            return "amend"
        if str(rec.get("session_share_policy", "")) == "strict":
            return "amend"
        return "proceed"

    # focal의 contains 표기 → 답안 excluded_fields 어휘 매핑.
    SENSITIVE_FIELD_MAP = {
        "raw_quote": "raw_quote", "rrn": "rrn", "name": "name", "location": "location",
        "numeric_value": "numeric_value", "amount": "numeric_value", "doctor_note": "doctor_note",
        "card_number": "card_number",
    }

    def sensitive_fields_of(self, focal: dict[str, Any]) -> list[str]:
        attrs = focal.get("attrs") or {}
        contains = attrs.get("contains") if isinstance(attrs.get("contains"), list) else []
        return sorted({self.SENSITIVE_FIELD_MAP[str(c)] for c in contains if str(c) in self.SENSITIVE_FIELD_MAP})

    def build_content_scope(self, task: dict[str, Any], focal: dict[str, Any], control: str, evidence: dict[str, Any]) -> dict[str, Any]:
        rec = record_map(records_of(task))
        strict = str(rec.get("session_share_policy", "")) == "strict"

        if control == "hold":
            return {"mode": "none", "allowed_fields": [], "excluded_fields": [], "requires_user_confirmation": False}
        if control == "ask":
            return {"mode": "summary", "allowed_fields": ["summary"], "excluded_fields": ["raw_quote"], "requires_user_confirmation": True}
        if control == "amend":
            excluded = self.sensitive_fields_of(focal)
            ambiguous = "ambiguous_target" in rec or "ambiguous_focal" in rec
            return {"mode": "redacted", "allowed_fields": ["summary"], "excluded_fields": excluded or ["raw_quote"], "requires_user_confirmation": ambiguous}

        # proceed
        target_is_local = "persistent_memory_write" in rec or clause_kind(task) == "local"
        if target_is_local or str(rec.get("share_boundary_update", "")).startswith("local_update"):
            excluded = ["location", "numeric_value", "raw_quote"] if strict else []
            return {"mode": "status_only", "allowed_fields": ["status"], "excluded_fields": excluded, "requires_user_confirmation": False}
        if not strict:
            return {"mode": "raw", "allowed_fields": ["summary", "title"], "excluded_fields": [], "requires_user_confirmation": False}
        return {"mode": "summary", "allowed_fields": ["summary"], "excluded_fields": [], "requires_user_confirmation": False}

    def build_policy(self, task: dict[str, Any], focal: dict[str, Any], control: str, evidence: dict[str, Any], target: str = "") -> dict[str, Any]:
        rec = record_map(records_of(task))
        kind = clause_kind(task)
        flags: set[str] = set()

        if str(rec.get("session_share_policy", "")) == "strict":
            flags.add("strict_share_policy")
        if "ambiguous_target" in rec:
            flags.add("target_ambiguity")
        if "ambiguous_focal" in rec:
            flags.add("ambiguous_focal")
        if self.sensitive_fields_of(focal):
            flags.add("sensitive_content")
        # 외부 목적지로 향하는 요청이면 외부 공유 위험이 있다.
        if target and target not in ("memory_store", "user"):
            flags.add("external_share")
        # 공유 경계가 갱신된 흐름은 전제가 바뀐 것이다.
        if "share_boundary_update" in rec:
            flags.add("precondition_changed")
        # 최신 정정/경계로 로컬 처리 범위가 걸린 흐름.
        if kind in ("local", "stop", "confirm") or "persistent_memory_write" in rec \
                or str(rec.get("share_boundary_update", "")).startswith("local_update"):
            flags.add("local_only")

        if control == "hold":
            flags.update(("precondition_invalidated", "safety"))
        elif control == "ask":
            flags.add("clarification_required")
        elif control == "amend":
            flags.update(("external_share", "minimal_disclosure"))

        violations = ["precondition_changed_ignored"] if control == "hold" else []
        return {
            "risk_flags": sorted(flags),
            "violations": violations,
            "requires_confirmation": control == "ask",
        }

    def build_plan_events(self, task: dict[str, Any], focal_id: str, target: str, control: str, scope: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
        if control == "hold":
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": "invalidated_precondition"}},
                {"verb": "guard", "target": focal_id, "args": {"reason": "precondition_invalidated"}},
            ]
        if control == "ask":
            # 꼬리 정정("단, 확인") 기반이면 전제 변경 확인, record 기반이면 route 해석 확인.
            if clause_kind(task) == "confirm":
                purpose, reason = "clarify_precondition", "precondition_changed"
            else:
                purpose = reason = "route_resolution_required"
            clarify_target = "user" if target == "user" or "ambiguous_target" in record_map(records_of(task)) else target
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": purpose}},
                {"verb": "clarify", "target": clarify_target, "args": {"reason": reason}},
            ]
        if control == "amend":
            excluded = scope.get("excluded_fields") or []
            remove = "raw_quote" if excluded == ["raw_quote"] else "sensitive_fields"
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": "minimal_disclosure"}},
                {"verb": "redact", "target": focal_id, "args": {"remove": remove}},
                {"verb": "dispatch", "target": target, "args": {"scope": "redacted"}},
            ]
        # proceed: 내부 갱신 / 원문 전달 / 요약 전달.
        mode = scope.get("mode")
        if mode == "status_only":
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": "local_update"}},
                {"verb": "verify", "target": "share_boundary_update", "args": {"scope": "local_update"}},
                {"verb": "update", "target": focal_id, "args": {"state": "local_status_only"}},
            ]
        if mode == "raw":
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": "inspect_context"}},
                {"verb": "dispatch", "target": target, "args": {"scope": "raw"}},
            ]
        return [
            {"verb": "read", "target": focal_id, "args": {"purpose": "inspect_context"}},
            {"verb": "summarize", "target": focal_id, "args": {"mode": "summary"}},
            {"verb": "dispatch", "target": target, "args": {"scope": "summary"}},
        ]

    def user_response(self, control: str, target: str, scope: dict[str, Any], policy: dict[str, Any]) -> str:
        if control == "hold":
            return "최신 보안·동의·정책 신호로 처리 전제가 무효화되어 이 요청은 보류합니다."
        if control == "ask":
            return "대상 또는 허용 범위가 확정되지 않아 진행 전에 사용자 확인이 필요합니다."
        if control == "amend":
            return f"민감 정보를 제외한 요약만 {target}(으)로 전달합니다."
        if scope.get("mode") == "status_only":
            return "외부로 보내지 않고 기기 내부 상태만 업데이트합니다."
        return f"요청 범위 그대로 {target}(으)로 진행합니다."
