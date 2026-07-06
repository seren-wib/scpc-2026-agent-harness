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
        policy = self.build_policy(task, focal, control, evidence)
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
        if kind == "confirm":
            return "ask"

        # TODO: 단일 record label만 보지 말고 prompt, focal object, session 상태를 함께 보강하세요.
        if "security_alert" in types or "phishing" in flags or "safety_mode" in types or "privacy_guard" in types:
            return "hold"
        if "consent" in types and any(word in values for word in ["revoked", "withdraw", "denied", "철회", "거부"]):
            return "hold"
        if evidence.get("requires_confirmation") or any(t in types for t in ["ambiguous_target", "ambiguous_focal", "duration_ambiguous", "memory_conflict", "amount_changed", "merchant_verification", "routine_scope"]):
            return "ask"
        if evidence.get("requires_redaction") or any(t in types for t in ["external_share_policy", "share_scope", "payment_policy", "enterprise_policy_recall"]):
            return "amend"
        return "proceed"

    def build_content_scope(self, task: dict[str, Any], focal: dict[str, Any], control: str, evidence: dict[str, Any]) -> dict[str, Any]:
        attrs = focal.get("attrs") or {}
        contains = {str(x) for x in attrs.get("contains", [])} if isinstance(attrs.get("contains"), list) else set()

        if control == "hold":
            return {"mode": "none", "allowed_fields": [], "excluded_fields": [], "requires_user_confirmation": False}
        if control == "ask":
            return {"mode": "summary", "allowed_fields": ["status"], "excluded_fields": sorted(contains & {"raw_quote", "rrn", "location", "numeric_value", "doctor_note", "card_number"}), "requires_user_confirmation": True}
        if control == "amend" or evidence.get("requires_redaction"):
            excluded = sorted(contains & {"raw_quote", "rrn", "location", "numeric_value", "doctor_note", "card_number", "name"})
            return {"mode": "redacted", "allowed_fields": ["summary", "title", "status"], "excluded_fields": excluded or ["raw_quote"], "requires_user_confirmation": False}
        return {"mode": "summary", "allowed_fields": ["summary", "title", "status"], "excluded_fields": ["raw_quote"], "requires_user_confirmation": False}

    def build_policy(self, task: dict[str, Any], focal: dict[str, Any], control: str, evidence: dict[str, Any]) -> dict[str, Any]:
        flags = set(evidence.get("risk_flags", []))
        violations: set[str] = set()
        values = " ".join(text_of(r.get("value")) for r in records_of(task)).lower()
        if "revoked" in values or "철회" in values:
            violations.add("consent_revoked")
        if "phishing" in values or "피싱" in values:
            violations.add("security_alert_ignored")
        return {
            "risk_flags": sorted(flags),
            "violations": sorted(violations),
            "requires_confirmation": control == "ask",
        }

    def build_plan_events(self, task: dict[str, Any], focal_id: str, target: str, control: str, scope: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
        events = [{"verb": "read", "target": focal_id, "args": {"purpose": "inspect_task_context"}}]
        if control == "hold":
            reason = policy.get("violations", ["safety_or_policy"])[0] if policy.get("violations") else "safety_or_policy"
            events.append({"verb": "guard", "target": focal_id, "args": {"reason": reason}})
        elif control == "ask":
            events.append({"verb": "clarify", "target": "user", "args": {"reason": "confirmation_required"}})
        else:
            if scope.get("mode") == "redacted":
                events.append({"verb": "redact", "target": focal_id, "args": {"remove": "sensitive_fields"}})
            elif scope.get("mode") in {"summary", "status_only"}:
                events.append({"verb": "summarize", "target": focal_id, "args": {"mode": scope.get("mode")}})
            events.append({"verb": "dispatch", "target": target, "args": {"scope": scope.get("mode")}})
        return events

    def user_response(self, control: str, target: str, scope: dict[str, Any], policy: dict[str, Any]) -> str:
        if control == "hold":
            return "보안, 동의 또는 정책 조건 때문에 진행하지 않겠습니다."
        if control == "ask":
            return "대상이나 허용 범위를 한 번 더 확인해야 합니다."
        if control == "amend":
            return f"민감 정보를 제외하고 {target}(으)로 진행하겠습니다."
        return f"요청한 범위로 {target}(으)로 진행하겠습니다."
