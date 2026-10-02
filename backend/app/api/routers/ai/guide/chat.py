"""노무 가이드 챗봇."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.security import require_api_key
from app.schemas.guide.chat import GuideChatIn, GuideChatOut
from app.services.ai.guide.chat import (
    _GUIDE_CHAT_SYSTEM,
    _detect_related_forms,
    _extract_followups,
    _sanitize_sanctions,
    _search_guide_context,
)

router = APIRouter(tags=["guide"])


@router.post(
    "/chat",
    response_model=GuideChatOut,
    summary="노무 가이드 챗봇 — 가이드 DB 컨텍스트 + LLM",
    dependencies=[Depends(require_api_key)],
)
def post_guide_chat(body: GuideChatIn, request: Request) -> GuideChatOut:
    msg = body.message.strip()
    if not msg:
        raise HTTPException(status_code=422, detail="질문이 비어있어요.")

    # 가이드 DB 검색 → LLM 컨텍스트 (제재 표현 정제 후 주입 — LLM이 '전과' 등을 echo 못 하게)
    ctx_text, sources = _search_guide_context(msg)
    ctx_text = _sanitize_sanctions(ctx_text)

    # 이전 대화 (최근 6턴)
    hist_lines: list[str] = []
    if body.history:
        for h in body.history[-6:]:
            role = h.role if h.role in ("user", "assistant") else "user"
            hist_lines.append(f"- {role}: {h.content[:600]}")

    user_prompt_parts: list[str] = []
    if ctx_text:
        user_prompt_parts.append("[가이드 DB 컨텍스트 — 1차 근거로 사용]\n" + ctx_text)
    else:
        user_prompt_parts.append(
            "[가이드 DB 컨텍스트] (사용자 질문과 직접 매칭되는 자료가 없음 — 일반 노동법 상식으로 답하되 마지막에 '관할 고용센터 상담 권장' 안내)"
        )
    if hist_lines:
        user_prompt_parts.append("[이전 대화]\n" + "\n".join(hist_lines))
    user_prompt_parts.append(f"[사용자 질문] {msg}")
    user_prompt = "\n\n".join(user_prompt_parts)

    # LLM 호출 — cgr.ec.services.chat 와 동일 패턴 (캐시 + 재시도)
    import time

    from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

    from app.core.config import get_api_key, get_llm_model
    from app.integrations.llm import cache as llm_cache

    model_name = get_llm_model()
    from app.core.upload import anon_visitor
    from app.repositories.shared import analytics as _an
    from app.repositories.shared import prompt as prompt_store

    # 관리자 override 가 있으면 그 프롬프트, 없으면 코드 기본값 (즉시 적용)
    system_prompt = prompt_store.get_or_default("guide_chat", _GUIDE_CHAT_SYSTEM)
    _visitor = anon_visitor(request)
    cache_key = llm_cache.make_key(
        system=system_prompt,
        user=user_prompt,
        schema={"kind": "guide_chat"},
        model=model_name,
    )
    cached = llm_cache.get(cache_key)
    if cached and isinstance(cached.get("text"), str):
        body, fups = _extract_followups(cached["text"])
        body = _sanitize_sanctions(body)
        _an.log_interaction(kind="챗봇", model=model_name, input_text=msg, output_text=body, visitor=_visitor)
        rel_forms, clarify = _detect_related_forms(msg, body)
        return GuideChatOut(
            answer=body,
            matched_sources=sources,
            follow_ups=fups,
            related_forms=rel_forms,
            clarify=clarify,
        )

    client = OpenAI(api_key=get_api_key(), timeout=60.0)
    last_err: Exception | None = None
    backoff = (2.0, 5.0, 10.0)
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                top_p=1,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise RuntimeError("chat 응답이 비어 있습니다.")
            llm_cache.put(cache_key, {"text": text})
            body, fups = _extract_followups(text)
            body = _sanitize_sanctions(body)
            _an.log_interaction(kind="챗봇", model=model_name, input_text=msg, output_text=body, visitor=_visitor)
            rel_forms, clarify = _detect_related_forms(msg, body)
            return GuideChatOut(
                answer=body,
                matched_sources=sources,
                follow_ups=fups,
                related_forms=rel_forms,
                clarify=clarify,
            )
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_err = e
            if attempt < 2:
                time.sleep(backoff[attempt])
                continue
            raise HTTPException(status_code=502, detail=f"LLM 호출 실패: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"chat 처리 실패: {e}")
    raise HTTPException(status_code=500, detail=f"chat 실패: {last_err}")
