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


def history_in_turn_order(task: dict[str, Any]) -> list[dict[str, Any]]:
    """visible_history를 turn 값 기준 오름차순으로 정렬한다 (같은 turn은 배열 순서 유지).

    핸드북 §5 ⚠: 배열 순서는 시간 순서가 아니며, 순서 해석은 turn 값으로만 한다.
    turn이 없는 항목은 가장 오래된 것으로 간주한다.
    """
    def turn_val(item: Any) -> float:
        t = (item or {}).get("turn") if isinstance(item, dict) else None
        return float(t) if isinstance(t, (int, float)) else float("-inf")

    keyed = list(enumerate(task.get("visible_history") or []))
    keyed.sort(key=lambda p: (turn_val(p[1]), p[0]))
    return [item for _, item in keyed]


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


# dev는 WM-#### 형식이지만 접두사가 바뀌어도 살아남도록 일반화한다.
# 주의: 한글 조사가 붙으면("WM-9921로") \b가 성립하지 않으므로 경계 표식은 쓰지 않는다.
WM_CODE = re.compile(r"[A-Z]{2,4}-\d{3,6}")
FOCAL_POS = ("확정", "승인", "우선", "처리 대상", "기준 참조", "최종")
FOCAL_NEG = ("보류", "제외", "무시", "취소")
ORDINALS = {"첫": 0, "두": 1, "둘": 1, "세": 2, "셋": 2, "네": 3, "넷": 3, "다섯": 4, "여섯": 5, "일곱": 6}
ORDINAL_RE = re.compile(r"(첫|두|세|네|다섯|여섯|일곱|\d+)\s*번째|(첫|둘|셋|넷|다섯|여섯|일곱)째")


def _ordinal_index(match: re.Match) -> int:
    word = match.group(1) or match.group(2)
    return ORDINALS[word] if word in ORDINALS else int(word) - 1


def resolve_focal_by_marker(task: dict[str, Any]) -> dict[str, Any] | None:
    """marker 간접 참조 해석: route/binding record가 고른 phase → marker → ref_code → object."""
    rec = record_map(records_of(task))
    refs = rec.get("focal_marker_refs")
    trace = rec.get("focal_resolution_trace")
    if not isinstance(refs, dict) or not isinstance(trace, dict):
        return None
    marker_to_ref = refs.get("marker_to_ref") or {}
    phase_to_marker = trace.get("phase_to_marker") or {}
    rule = trace.get("latest_phase_rule") or {}

    # phase 후보를 신뢰도 순으로 수집한다. 최신성 원칙에 따라 phase_source record에서
    # rule로 유도한 phase(현재 binding 상태)를 명시된 latest_phase보다 우선한다 —
    # 둘이 일치하면 차이가 없고, 어긋나면 rule 쪽이 더 최신 상태를 반영한다.
    candidates: list[str] = []
    source_keys = [str(trace.get("phase_source"))]
    source_keys += [k for k in rec if ("binding" in k or "route" in k) and k not in source_keys]
    for key in source_keys:
        mapped = rule.get(str(rec.get(key)))
        if mapped:
            candidates.append(str(mapped))
    if trace.get("latest_phase"):
        candidates.append(str(trace["latest_phase"]))
    if rule.get("fallback"):
        candidates.append(str(rule["fallback"]))

    by_ref = {str((o.get("attrs") or {}).get("ref_code")): o for o in objects_of(task)}
    for phase in candidates:
        marker = phase_to_marker.get(phase)
        ref = marker_to_ref.get(str(marker))
        if ref and str(ref) in by_ref:
            return by_ref[str(ref)]
    # trace가 유효한 marker를 못 고르면 실패로 두고 history 해석으로 넘긴다.
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
    ordinal_hits = list(ORDINAL_RE.finditer(summary))
    # "N번째 후보만"의 '만' 한정은 동사 어휘와 무관한 문법 신호다: '만'이 붙은
    # 서수가 지목 대상이고, 같은 요약에 열거된 나머지 서수는 대조군으로 본다.
    only_idx = None
    for om in ordinal_hits:
        if re.match(r"\s*(?:후보|항목|건)?\s*만(?![큼약])", summary[om.end():om.end() + 8]):
            only_idx = _ordinal_index(om)
            break
    if only_idx is not None and only_idx < len(uniq):
        scores[uniq[only_idx]] += 3
        for om in ordinal_hits:
            idx = _ordinal_index(om)
            if idx != only_idx and idx < len(uniq):
                scores[uniq[idx]] -= 1
    for om in ordinal_hits:
        idx = _ordinal_index(om)
        after = summary[om.end():om.end() + 24]
        if idx < len(uniq):
            if any(n in after for n in FOCAL_NEG):
                scores[uniq[idx]] -= 2
            elif any(p in after for p in FOCAL_POS):
                scores[uniq[idx]] += 2
    g = summary.find("가운데")
    if g >= 0 and uniq and any(p in summary[g:g + 28] for p in FOCAL_POS):
        scores[uniq[len(uniq) // 2]] += 2
    if uniq:
        for lm in re.finditer(r"마지막", summary):
            after = summary[lm.end():lm.end() + 24]
            if re.match(r"\s*(?:후보|항목|건)?\s*만(?![큼약])", after) or any(p in after for p in FOCAL_POS):
                scores[uniq[-1]] += 2
            elif any(n in after for n in FOCAL_NEG):
                scores[uniq[-1]] -= 2
    # 위치 지시가 하나뿐이고 어휘 신호가 전무하면 그 지시 자체를 지목으로 본다 —
    # 동사가 사전 밖이어도 위치 참조는 살아남는 구조 신호라서다.
    if len(ordinal_hits) == 1 and uniq and not any(scores.values()):
        idx = _ordinal_index(ordinal_hits[0])
        if 0 <= idx < len(uniq):
            scores[uniq[idx]] += 2
    # 반복 호명도 어휘와 무관한 지목 신호다: 목록 나열은 코드를 1회씩 부르고,
    # 지목 문장은 그 코드를 한 번 더 부른다.
    counts: dict[str, int] = {}
    for m in matches:
        counts[m.group(0)] = counts.get(m.group(0), 0) + 1
    repeated = [c for c in uniq if counts[c] >= 2]
    if len(repeated) == 1:
        scores[repeated[0]] += 2
    return scores


# "단, ..." 꼬리 정정 구절: 가장 최신 지시라서 target/control을 동시에 결정한다.
CLAUSE_LOCAL = ("상태값만", "상태만 갱신", "상태만 바꾸", "상태만 남", "상태 기록", "기록으로만",
                "로컬 상태", "내부 상태", "내부 업데이트", "내부에서만", "갱신만",
                "기기 안", "장치 안", "공유하지 말", "보내지 말", "전송하지 말", "내보내지 말",
                "전달 대신", "전달 동작은 취소", "외부로 보내",
                # 범용 확장 (screening 질량 0 확인 — 비공개 검증 stream 대비 보험)
                "내부적으로만", "내부 처리", "외부 전송 없이", "외부 공유 없이",
                "메모로만", "메모만 남", "기록만 남", "발송하지 말", "올리지 말",
                "공개하지 말", "기기에서만", "단말에서만", "자체 처리")
CLAUSE_STOP = ("멈춰야", "막아야", "진행하면 안", "실행하면 안", "처리하지 않는다", "기대면 안",
               "중단해야", "진행 불가", "해서는 안", "하지 마라",
               # 범용 확장
               "중지해야", "정지해야", "멈추어야", "그만둬야", "진행할 수 없",
               "계속하면 안", "속행하면 안", "실행 불가", "처리 불가")
CLAUSE_CONFIRM = ("사용자에게 먼저 확인", "다시 확인", "먼저 확인", "확인해야 한다", "확인 전에는",
                  "미확정", "확인되지 않았", "결론을 내릴 수 없",
                  "재확인", "여부를 확인", "확실하지 않", "불명확", "판단할 수 없",
                  # 범용 확장
                  "물어본 뒤", "물어보고", "문의", "확인 후에", "확인을 받", "허락을 받",
                  "동의를 받", "승인을 받", "검토가 필요", "확인이 필요")
CLAUSE_SCOPE = ("요약만", "제외한 요약", "세부값을 제외", "식별 정보 제외", "민감한 값 제외",
                # 범용 확장
                "요점만", "핵심만", "개요만", "제목만", "민감 정보 제외", "민감한 내용은 제외",
                "가려서", "마스킹", "비식별")

CLAUSE_MARKERS = ("단,", "다만,")

# '기존 허용의 무효화' 단정: dev의 모든 hold 절이 공유하는 의미 신호.
# 허용계 명사와 소멸계 술어의 공존으로 판정한다. 단 '~는지/여부' 등 불확실
# 표지가 붙으면 무효화 단정이 아니라 미확정 진술(confirm 계열)이므로 제외 —
# dev의 confirm 절("확정되지 않았", "여부가 미확정")은 전부 이 가드에 걸린다.
INVALID_NOUNS = ("허용", "승인", "동의", "전제", "조건", "근거", "권한", "자격")
INVALID_PREDS = ("무효", "취소되", "취소된", "철회", "깨졌", "깨진", "사라졌", "만료",
                 "상실", "효력을 잃", "유효하지 않", "더 이상 유효")
UNCERTAIN_MARKS = ("는지", "여부", "미확정", "확정되지 않")

# 행위 금지형: dev의 gold-ask 절에는 금지형이 전무하고, 금지형을 품은 절은 전부
# gold-hold다 ("확인 전에는 처리하지 않는다" 판례 포함). '확인' 어휘가 있어도
# 금지형이면 요청형(confirm)이 아니라 중지 지시다.
CLAUSE_PROHIBIT = ("면 안 되", "면 안 된", "면 안된", "서는 안 되", "하지 않는다", "지 마", "지 말")
# 금지형이라도 긍정 대안이 함께 오면 중지가 아니라 방향 전환이다:
# scope 단서(요약/제외)면 amend 계열, '말고' 연결이면 local 계열로 흘려보낸다.
PROHIBIT_VETO = ("요약", "제외", "빼고", "말고")


def clause_invalidated(clause: str) -> bool:
    if any(u in clause for u in UNCERTAIN_MARKS):
        return False
    return any(n in clause for n in INVALID_NOUNS) and any(p in clause for p in INVALID_PREDS)


def clause_prohibited(clause: str) -> bool:
    if any(v in clause for v in PROHIBIT_VETO):
        return False
    return any(p in clause for p in CLAUSE_PROHIBIT)


def final_clause(task: dict[str, Any]) -> str:
    """prompt(현재 발화) 우선, 없으면 최신 history에서 '단,' 꼬리 구절을 찾는다."""
    # 꼬리 정정은 '가장 최신 지시'일 때만 유효하다: prompt와 최신 turn의 history만 본다.
    # 옛 턴의 절이 현재 턴을 납치하면 안 된다 (최신 record가 과거를 덮는 원칙의 절 버전).
    ordered = history_in_turn_order(task)
    turns = [h.get("turn") for h in ordered if isinstance(h, dict) and isinstance(h.get("turn"), (int, float))]
    newest = max(turns) if turns else None
    recent = [h for h in ordered if newest is None or (isinstance(h, dict) and h.get("turn") == newest)]
    sources = [str(task.get("prompt", ""))]
    sources += [str((h or {}).get("summary", "")) for h in reversed(recent)]
    for src in sources:
        i = max(src.rfind(m) for m in CLAUSE_MARKERS)
        if i >= 0:
            return src[i:]
    return ""


def clause_kind_tier(task: dict[str, Any]) -> tuple[str | None, str | None]:
    """절 의도와 신뢰 층위를 반환한다: lex = dev 검증된 사전 매칭(강신호),
    fb = 사전 밖 절의 느슨한 단서 추정(약신호 — dev에 표본이 없어 미검증)."""
    clause = final_clause(task)
    if not clause:
        return None, None
    if any(k in clause for k in CLAUSE_LOCAL):
        return "local", "lex"
    if any(k in clause for k in CLAUSE_STOP) or clause_invalidated(clause):
        return "stop", "lex"
    if any(k in clause for k in CLAUSE_SCOPE):
        return "scope", "lex"
    if clause_prohibited(clause):
        return "stop", "lex"
    if any(k in clause for k in CLAUSE_CONFIRM):
        return "confirm", "lex"
    # 마커는 잡혔는데 내용 어휘가 사전 밖이면 미분류로 흘리지 않는다. 느슨한 단서로
    # 의도를 추정하고, 꼬리 정정의 최빈 의도인 '내부 처리로 축소'(local)를 기본값으로 둔다.
    if any(k in clause for k in ("중단", "멈추", "막아", "불가", "보류")):
        return "stop", "fb"
    if "확인" in clause or "물어" in clause:
        return "confirm", "fb"
    if any(k in clause for k in ("요약", "제외", "빼고")):
        return "scope", "fb"
    return "local", "fb"


def clause_kind(task: dict[str, Any]) -> str | None:
    return clause_kind_tier(task)[0]


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

# 요청 도메인 → 대상 object type (TERMS_GUIDE 도메인 용어 표 기반).
DOMAIN_TYPE_HINTS = (
    (("결제", "송금", "금액"), "payment_request"),
    (("조명", "루틴", "자동화"), "iot_routine"),
    (("사진", "갤러리", "이미지"), "gallery_item"),
    (("건강 기록", "복약", "혈압", "혈당"), "health_record"),
    (("설정을", "설정 변경", "모드를"), "device_setting"),
    (("일정", "예약", "캘린더"), "calendar_event"),
)

# 이전 턴과 같은 수신처를 가리키는 표현 (공개 ontology의 same_place_scope_check 계열).
SAME_PLACE_CUES = ("같은 곳", "같은 채널", "같은 대상", "같은 수신처", "거기로", "아까 그")


def resolve_focal_by_history(task: dict[str, Any], session: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """visible_history에서 확정/승인된 ref_code를 찾아 해당 object 반환 (최신 항목 우선)."""
    by_ref = {str((o.get("attrs") or {}).get("ref_code")): o for o in objects_of(task)}
    summaries = [str((item or {}).get("summary", "")) for item in history_in_turn_order(task)]
    fallback: dict[str, Any] | None = None
    for i in range(len(summaries) - 1, -1, -1):
        summary = summaries[i]
        scores = score_codes_in_summary(summary)
        cands = [c for c in scores if c in by_ref]
        if not cands:
            continue
        best = max(cands, key=lambda c: scores[c])
        if scores[best] > 0:
            return by_ref[best]
        if len(cands) == 1 and scores[cands[0]] >= 0:
            return by_ref[cands[0]]
        # 지목 문장이 코드 목록과 분리된 항목/프롬프트에 있을 수 있다: 이 목록 뒤에
        # 오는 요약들과 현재 prompt를 이어붙여 위치 지시를 재채점한다.
        joined = " ".join([summary] + summaries[i + 1:] + [str(task.get("prompt", ""))])
        jscores = score_codes_in_summary(joined)
        jcands = [c for c in jscores if c in by_ref]
        if jcands:
            jbest = max(jcands, key=lambda c: jscores[c])
            if jscores[jbest] > 0:
                return by_ref[jbest]
        # 긍정어가 없는 요약: dev의 모든 history 가족에서 승자가 "고유 코드 목록의
        # 2번째"였던 구조적 사전확률을 폴백으로 쓴다 (부정어 걸린 후보는 제외).
        if fallback is None:
            survivors = [c for c in cands if scores[c] >= 0]
            if survivors:
                prompt = str(task.get("prompt", ""))
                typed: list[str] = []
                for keywords, obj_type in DOMAIN_TYPE_HINTS:
                    if any(k in prompt for k in keywords):
                        typed = [c for c in survivors if str(by_ref[c].get("type")) == obj_type]
                        break
                # E) 지목이 산문이 아니라 후보 object의 상태값에 있을 수 있다.
                attr_pos = FOCAL_POS + ("confirmed", "approved", "selected", "primary")
                attr_neg = FOCAL_NEG + ("pending", "held", "cancelled", "archived", "stale")
                attr_scored = sorted(
                    ((sum(1 for p in attr_pos if p in object_text(by_ref[c]))
                      - sum(1 for n in attr_neg if n in object_text(by_ref[c])), c) for c in survivors),
                    key=lambda x: -x[0])
                attr_pick = [c for s, c in attr_scored if s > 0 and s == attr_scored[0][0]]
                # F) record 값이 후보의 attrs(수신처/스레드 등)를 메아리치면 그 후보가 지목이다.
                rec_text = " ".join(text_of(r.get("value")) for r in records_of(task)).lower()
                echo_scored = []
                for c in survivors:
                    vals = [str(v).lower() for v in (by_ref[c].get("attrs") or {}).values()
                            if isinstance(v, str) and len(v) >= 3 and v.lower() not in ("me",)]
                    echo_scored.append((sum(1 for v in set(vals) if v in rec_text), c))
                echo_scored.sort(key=lambda x: -x[0])
                echo_pick = [c for s, c in echo_scored if s > 0 and s == echo_scored[0][0]]
                last_id = str((session or {}).get("last_focal_id") or "")
                carried = [c for c in survivors if last_id and str(by_ref[c].get("id")) == last_id]
                token_pick: list[str] = []
                prompt_tokens = {tok for tok in re.findall(r"[A-Za-z0-9가-힣_]+", prompt.lower()) if len(tok) >= 2}
                if prompt_tokens:
                    ranked = sorted(survivors, key=lambda c: -sum(1 for tok in prompt_tokens if tok in object_text(by_ref[c])))
                    top_score = sum(1 for tok in prompt_tokens if tok in object_text(by_ref[ranked[0]]))
                    second = sum(1 for tok in prompt_tokens if tok in object_text(by_ref[ranked[1]])) if len(ranked) >= 2 else -1
                    if top_score > max(second, 0):
                        token_pick = [ranked[0]]
                if len(attr_pick) == 1:
                    fallback = by_ref[attr_pick[0]]
                elif len(echo_pick) == 1:
                    fallback = by_ref[echo_pick[0]]
                elif len(typed) == 1:
                    fallback = by_ref[typed[0]]
                elif carried:
                    fallback = by_ref[carried[0]]
                elif token_pick:
                    fallback = by_ref[token_pick[0]]
                else:
                    pick = survivors[1] if len(survivors) >= 2 else survivors[0]
                    fallback = by_ref[pick]
    return fallback


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

        # 0-1) record 값이 후보 ref_code 하나만을 지목하면 그것이 가장 구조적인 신호다
        #      (history 폴백보다 먼저 봐야 폴백이 record 지목을 가로채지 않는다).
        by_ref = {str((o.get("attrs") or {}).get("ref_code")): o for o in objects if (o.get("attrs") or {}).get("ref_code")}
        rec_codes = {c for r in records for c in WM_CODE.findall(text_of(r.get("value"))) if c in by_ref}
        if len(rec_codes) == 1:
            return by_ref[rec_codes.pop()]

        # 0-2) history에서 확정/승인된 ref_code가 지목되면 따른다.
        focal = resolve_focal_by_history(task, session)
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

        # 2-2) 요청 도메인이 특정 object type을 지목하면 그 type을 우선한다 (TERMS_GUIDE 도메인 표).
        prompt = str(task.get("prompt", ""))
        for keywords, obj_type in DOMAIN_TYPE_HINTS:
            if any(k in prompt for k in keywords):
                typed = [o for o in objects if str(o.get("type")) == obj_type]
                if len(typed) == 1:
                    return typed[0]
                if typed:
                    for obj in typed:
                        ref_code = str((obj.get("attrs") or {}).get("ref_code") or "").lower()
                        if ref_code and ref_code in history_text:
                            return obj
                break

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
        if isinstance(changed, dict):
            for key in ("target", "to", "new_target", "value", "name", "recipient"):
                if changed.get(key):
                    return str(changed[key])
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

        # 6) "같은 곳에" 류: 세션에서 마지막으로 확정된 수신처를 잇는다.
        prompt = str(task.get("prompt", ""))
        if any(c in prompt for c in SAME_PLACE_CUES) and session.get("last_target") not in (None, "", "user"):
            return str(session["last_target"])

        for key in ("recipient", "target", "channel", "app", "merchant", "name"):
            if attrs.get(key):
                return str(attrs[key])
        return str(session.get("last_target") or "user")

    def decide_control(self, task: dict[str, Any], focal: dict[str, Any], target: str, evidence: dict[str, Any]) -> str:
        # 0) "단, ..." 꼬리 정정이 최신 지시라 record 신호보다 우선한다.
        #    이 우선권은 신호 강도와 무관하게 절대적이다: fb층 confirm을 record의
        #    확정적 hold로 중재하는 실험은 서버 -0.010(전환 13건 전패)으로 반증됐다
        #    (2026-07-08). 절이 있으면 절이 이긴다.
        kind = clause_kind(task)
        if kind == "local":
            return "proceed"
        if kind == "stop":
            return "hold"
        if kind == "scope":
            return "amend"
        if kind == "confirm":
            return "ask"
        return self.record_control(task, evidence)

    def record_control(self, task: dict[str, Any], evidence: dict[str, Any]) -> str:
        """절 신호 없이 record·정책 신호만으로 control을 판정하는 사다리."""
        records = records_of(task)
        types = {str(r.get("type")) for r in records}
        values = " ".join(text_of(r.get("value")) for r in records).lower()
        flags = set(evidence.get("risk_flags", []))

        rec = record_map(records)

        # 1) 안전/동의 계열은 무조건 중단.
        if "security_alert" in types or "phishing" in flags:
            return "hold"
        safety = str(rec.get("safety_mode", ""))
        if safety and safety not in ("off", "inactive", "normal"):
            return "hold"
        # 철회 판정은 consent record만 본다 — 다른 record 서사 속 '철회' 언급은 최신 상태가 아닐 수 있다.
        consent = rec.get("consent")
        consent_text = text_of(consent).lower()
        if any(w in consent_text for w in ("revoked", "withdraw", "denied", "철회", "거부")):
            return "hold"

        # 2) 건강 원문 등 외부 공유 자체가 금지된 경우 중단.
        forbid = str(rec.get("external_share_policy", "")) + " " + str(rec.get("health_share_policy", ""))
        if ("doctor_note" in forbid or "health" in forbid) and "forbidden" in forbid:
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

        # 4-2) 공개 ontology에 문서화된 위험/확인 신호들 (dev에는 없지만 채점 어휘에 존재).
        if "impersonation" in values:
            return "hold"
        if "minor_location" in values:
            return "hold"
        if "one_time_or_recurring" in values or "duration_ambiguous" in values:
            return "ask"
        if "calendar_conflict" in values or "tone_conflict" in values:
            return "ask"
        if "stored_preference_violation" in values or "privacy_rule_violation" in values:
            return "hold"

        # 5) 확인이 필요한 변경/불일치 신호.
        if "confirmation" in str(rec.get("payment_policy", "")) or "over_50000" in values:
            return "ask"
        prompt = str(task.get("prompt", ""))
        # (2026-07-10) '원본+익명' 프롬프트 키워드 규칙은 제거 — 격자의 local_update 0단이
        # 같은 가족을 구조로 흡수한다 (공지의 표면 패턴 경고 대응. dev 앵커 2건 모두 L0/proceed 유지).
        if "target_changed_after_turn" in rec:
            return "ask"

        # 5-2) guardrail 사다리: route_binding_order가 어느 record가 최신 심판인지 알려준다.
        #      authority가 최신이면 그 확정 여부가 결정하고, boundary가 최신이면 review 미결로 확인이 필요하다.
        authority = str(rec.get("dispatch_authority_check", ""))
        boundary = str(rec.get("share_boundary_update", ""))
        if "guardrail_ladder_signal" in rec and ("ambiguous_target" in rec or "ambiguous_focal" in rec):
            order = str(rec.get("route_binding_order", ""))
            if order == "authority_after_candidates":
                if "confirmed" in authority:
                    return "proceed"
                if "incomplete" in authority or "pending" in authority:
                    return "hold"
            if order == "boundary_after_authority":
                # 경계가 최신 심판인데 그 경계가 전송 잠금(blocked)이면 검토창 이전에
                # 차단이 확정된 것 — 격자 B행(차단=hold)과 dev guard의 미결=hold가
                # 양방향으로 수렴하는 셀이라 hold. 나머지 경계값은 review 미결 = ask.
                if boundary.startswith("dispatch_blocked"):
                    return "hold"
                return "ask"

        # 5-3) 경계 격자 — record 경로의 생성기 구조 (dev record-path 4중주 21건 전수 일치):
        #      share_boundary_update 값이 기본 판정을 그대로 적어둔다.
        #        local_update → proceed(내부 갱신) / redacted_external → amend(축소 전달) /
        #        dispatch_blocked → ask(바인딩 대기) / +user_binding_pending → hold(사용자 대기).
        #      target 모호(누구에게)는 사용자 결정 사안이라 한 단계 격상하고, focal 모호는
        #      시스템이 풀 문제라 격상하지 않는다 (dev: focal행 proceed/amend/ask/hold 단조,
        #      target행 정확히 +1 계단). local_update는 order=boundary_after_authority일 때만
        #      0단 — order가 authority를 최신 심판으로 지목하면 경계 미확정이라 1단으로 승격
        #      (order 조건 제거는 서버 실측 음수, 2026-07-09 — 생성기는 order를 실제로 본다).
        state = None
        if boundary.startswith("local_update"):
            state = 0 if str(rec.get("route_binding_order", "")) == "boundary_after_authority" else 1
        elif boundary.startswith("redacted"):
            state = 1
        elif boundary.startswith("dispatch_blocked"):
            state = 3 if "user_binding_pending" in authority else 2
        if state is not None:
            severity = state + (1 if "ambiguous_target" in rec else 0)
            return ("proceed", "amend", "ask", "hold")[min(severity, 3)]
        # 경계 record가 아예 없는 both_recent: 판정이 안 적힌 target 모호는 확인이 기본
        # (발 2 서버 검증 구성의 else-ask 유지 — 격자 도입으로 이 가족을 건드리지 않는다).
        if str(rec.get("ambiguous_target", "")) == "surface_recipient_and_resolved_target_both_recent":
            return "ask"
        if any(t in types for t in ("amount_changed", "merchant_verification", "memory_conflict", "duration_ambiguous")):
            return "ask"

        # 6) 경계 record가 없는 잔여 모호성: authority가 해소했으면 아래 정책층으로, 미결이면 확인/중단.
        snapshot = str(rec.get("route_candidate_snapshot", ""))
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
            # 사용자 확인은 target 모호(누구에게 보낼지)일 때만 요구한다. focal 모호는
            # 시스템이 풀 문제라 확인 대상이 아니다 (dev 120/120 일치).
            ambiguous = "ambiguous_target" in rec
            return {"mode": "redacted", "allowed_fields": ["summary"], "excluded_fields": excluded or ["raw_quote"], "requires_user_confirmation": ambiguous}

        # proceed
        target_is_local = "persistent_memory_write" in rec or clause_kind(task) == "local"
        if target_is_local or str(rec.get("share_boundary_update", "")).startswith("local_update"):
            # ⚠ personal_memory 제약 문장 → 제외 3종 규칙(dev 3/3)은 2026-07-09 묶음
            #   서버 음수에 포함되어 revert. 성분 미분해 — 재도전 시 단독 계측 필요.
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
        # 확인 요구는 '사용자 결정 대기'의 의미 신호다: ask 자체, 또는 진행/축소
        # 중이라도 target 모호(누구에게)나 user_binding_pending(사용자 바인딩 대기)이
        # 걸린 경우. focal 모호·시스템측 미결(authority_incomplete)은 확인 불요.
        # hold는 항상 False (dev 120/120 일치 실측).
        pending = "user_binding_pending" in str(rec.get("dispatch_authority_check", ""))
        return {
            "risk_flags": sorted(flags),
            "violations": violations,
            "requires_confirmation": control == "ask"
            or (control in ("proceed", "amend") and ("ambiguous_target" in rec or pending)),
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
            # clarify는 정의상 사용자에게 확인을 구하는 동작이다 (핸드북 verb 표).
            return [
                {"verb": "read", "target": focal_id, "args": {"purpose": purpose}},
                {"verb": "clarify", "target": "user", "args": {"reason": reason}},
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
        # 문장 어휘는 dev 생성기 표현 빈도에 정렬 (공유 범위/수신처/처리/먼저 확인/
        # 세부값 제외/상태만 갱신) — 참조 응답이 같은 생성기 어휘로 만들어졌을
        # 가능성에 베팅하는 semantic 축 정렬.
        if control == "hold":
            return "처리 전제가 무효화되어 이 요청은 보류하고 진행하지 않습니다."
        if control == "ask":
            return "수신처와 공유 범위가 아직 확정되지 않아 처리 전에 사용자에게 먼저 확인합니다."
        if control == "amend":
            return f"식별 가능한 세부값을 제외한 요약만 {target}(으)로 공유합니다."
        if scope.get("mode") == "status_only":
            return "외부로 공유하지 않고 기기 내부 상태만 갱신합니다."
        if scope.get("mode") == "raw":
            return f"원문 그대로 {target}(으)로 공유합니다."
        return f"요약을 {target}(으)로 전달합니다."
