"""가짜 LLM 서버 — OpenAI API 키가 없을 때(로컬·테스트) 실호출 대신 쓴다.

127.0.0.1 의 빈 포트에 OpenAI 호환 HTTP 서버를 띄우고 형식에 맞는 고정 응답을 돌려준다.
  - POST /v1/chat/completions : 시스템 프롬프트로 단계를 구분해 고정 JSON 응답.
                                함수 호출(tools) 요청은 함수 스키마대로 채운 인자를 돌려준다.
  - POST /v1/embeddings       : 글자 2-gram 해시 벡터(비슷한 문장끼리 유사도가 높게 나온다).
응답 문구에는 "[가짜 응답]" 이 붙는다. 판정 품질 확인용이 아니라 화면·API 흐름 확인용이다.

사용: app.core.config.init_llm() 이 mock 일 때 start() 를 부른다.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)

_FAKE = "[가짜 응답] 테스트 응답입니다."
_lock = threading.Lock()
_base_url: str | None = None


def _structure() -> dict[str, Any]:
    from app.services.ec.structure import empty_structure

    s = empty_structure()
    fill = {
        ("기본정보", "사업장명"): "(주)테스트", ("기본정보", "사업주성명"): "김대표",
        ("기본정보", "사업장소재지"): "서울시 강남구", ("기본정보", "근로자성명"): "홍길동",
        ("계약사항", "근무장소"): "본사 사무실", ("계약사항", "업무내용"): "영업 관리",
        ("계약사항", "수습기간"): "입사일로부터 3개월", ("계약사항", "근로계약서교부"): "1부씩 교부",
        ("근로시간", "소정근로시간"): "1일 8시간, 1주 40시간", ("근로시간", "시업시각"): "09:00",
        ("근로시간", "종업시각"): "18:00", ("근로시간", "휴게시간"): "12:00 ~ 13:00",
        ("휴일휴가", "근무일"): "월~금", ("휴일휴가", "주휴일"): "토, 일",
        ("휴일휴가", "연차유급휴가"): "근로기준법에 따름",
        ("임금", "임금총액"): "월 250만원", ("임금", "기본급"): "200만원",
        ("임금", "제수당"): "직책수당 30만원, 식대 20만원", ("임금", "임금지급일"): "매월 25일",
        ("임금", "임금지급방법"): "계좌이체",
    }
    for (sec, key), v in fill.items():
        if sec in s and key in s[sec]:
            s[sec][key]["value"] = v
    return s


def _analysis() -> dict[str, Any]:
    def item(name, ok, why, found, law, fix, cond="공통"):
        return {"항목": name, "적용조건": cond, "서면명시의무": "필수_서면교부", "적절성": ok,
                "판단이유": why, "발견내용": found, "법적근거": law, "개선권고": fix}

    return {
        "riskLevel": "중", "overallStatus": "보완필요",
        "overallOpinion": "[가짜 응답] 필수 기재사항 대부분이 있으나 일부 보완이 필요합니다.",
        "results": [
            item("사용자 정보", "적절", "상호·대표자·소재지가 기재되어 있습니다. <meta db=\"DB_임금체불\" n=\"3.1.1\" />",
                 "(주)테스트, 대표자 김대표, 서울시 강남구", "근로기준법 제17조", "-"),
            item("임금", "적절", "임금 총액과 구성항목이 기재되어 있습니다. <meta db=\"DB_임금\" n=\"3.1.1\" />",
                 "월 250만원", "근로기준법 제17조 제1항 제1호", "-"),
            item("퇴직금", "부적절", "퇴직금 관련 기재가 없습니다. <meta db=\"DB_퇴직금\" n=\"2.2.1\" />",
                 "없음", "근로자퇴직급여보장법 제4조", "퇴직금 지급 조항을 추가하세요."),
            item("연차유급휴가", "보완필요", "구체적 일수가 없습니다. <meta db=\"DB_연차유급휴가\" n=\"2.1.2\" />",
                 "근로기준법에 따름", "근로기준법 제60조", "1년 80% 이상 출근 시 15일 부여를 명시하세요.", "5인이상"),
        ],
        "finalRecommendations": "[가짜 응답] 퇴직금 조항을 추가하고 연차 일수를 명시하세요.",
    }


def _pick(system: str) -> tuple[str, dict[str, Any]]:
    """시스템 프롬프트로 단계를 구분한다."""
    if '"worker_types"' in system:
        return "classify", {"worker_types": ["정규직"], "doc_kind": "표준 근로계약서",
                            "reason": "[가짜 응답] 기간 정함이 없는 상용직 계약입니다."}
    if '"overallStatus"' in system:
        return "analyze", _analysis()
    if "기본정보" in system and "계약사항" in system:
        return "structure", _structure()
    if "적절성" in system and "작성예시" in system:
        return "validate_field", {"적절성": "적절", "이유": "[가짜 응답] 기재 내용이 충분합니다.", "작성예시": "-"}
    if "표준" in system and "근로계약서" in system and "생성" in system:
        return "generate", {"contract_text": "[가짜 응답] 표준근로계약서 본문"}
    return "other", {"answer": _FAKE, "text": _FAKE}


def _fill(schema: dict[str, Any], user: str, key: str = "") -> Any:
    """함수 스키마를 보고 형식에 맞는 값을 만든다. 규정은 모두 '없음(found/present=false)' 으로 답한다."""
    t = schema.get("type")
    if isinstance(t, list):
        if "null" in t:
            return None
        t = t[0] if t else None
    if "enum" in schema and t != "array":
        vals = [x for x in schema["enum"] if x is not None]
        return vals[0] if vals else None
    if t == "object" or "properties" in schema:
        return {k: _fill(v, user, k) for k, v in (schema.get("properties") or {}).items()}
    if t == "array":
        item = schema.get("items") or {}
        for k, v in (item.get("properties") or {}).items():  # 항목마다 다른 id 를 하나씩 배정
            ids = [x for x in (v.get("enum") or []) if x is not None]
            if k == "slot_id" and not ids:
                ids = list(dict.fromkeys(re.findall(r'"slot_id":\s*"([^"]+)"', user)))
            if ids:
                return [{**_fill(item, user), k: x} for x in ids]
        return [_fill(item, user) for _ in range(schema.get("minItems", 0))]
    if t == "boolean":
        return False
    if t == "integer":
        return schema.get("minimum", 0)
    if t == "number":
        return 0.5
    if t == "string":
        return "" if key == "quote" else _FAKE
    return None


def _embed(text: str, dim: int) -> list[float]:
    v = [0.0] * dim
    t = re.sub(r"\s+", "", text or "")
    for i in range(max(len(t) - 1, 1)):
        h = int.from_bytes(hashlib.md5(t[i:i + 2].encode("utf-8")).digest()[:4], "little")
        v[h % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _chat(body: dict[str, Any]) -> dict[str, Any]:
    msgs = body.get("messages") or []
    text = lambda role: "\n".join(  # noqa: E731
        m["content"] for m in msgs if m.get("role") == role and isinstance(m.get("content"), str))
    system, user = text("system"), text("user")
    message: dict[str, Any] = {"role": "assistant", "content": None}
    tools = body.get("tools") or []
    if tools:
        want = ((body.get("tool_choice") or {}).get("function") or {}).get("name")
        fn = next((x["function"] for x in tools if x["function"]["name"] == want), tools[0]["function"])
        kind = "tool:" + fn["name"]
        args = _fill(fn.get("parameters") or {}, user)
        message["tool_calls"] = [{"id": "call_mock", "type": "function", "function": {
            "name": fn["name"], "arguments": json.dumps(args, ensure_ascii=False)}}]
    else:
        kind, payload = _pick(system)
        json_mode = (body.get("response_format") or {}).get("type") == "json_object"
        message["content"] = (json.dumps(payload, ensure_ascii=False)
                              if json_mode or kind != "other" else payload["answer"])
    log.debug(f"mock llm: {kind}")
    return {"id": "mock", "object": "chat.completion", "created": int(time.time()),
            "model": body.get("model") or "mock",
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if tools else "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


def _embeddings(body: dict[str, Any]) -> dict[str, Any]:
    texts = body.get("input") or []
    texts = [texts] if isinstance(texts, str) else texts
    dim = int(body.get("dimensions") or 1024)
    return {"object": "list", "model": body.get("model") or "mock",
            "data": [{"object": "embedding", "index": i, "embedding": _embed(x, dim)}
                     for i, x in enumerate(texts)],
            "usage": {"prompt_tokens": 0, "total_tokens": 0}}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        path = self.path.rstrip("/")
        if path.endswith("/embeddings"):
            resp = _embeddings(body)
        elif path.endswith("/chat/completions"):
            resp = _chat(body)
        else:
            self.send_error(404)
            return
        out = json.dumps(resp, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def start() -> str:
    """가짜 LLM 서버를 1회 띄우고 OpenAI 호환 base URL(…/v1)을 돌려준다."""
    global _base_url
    with _lock:
        if _base_url:
            return _base_url
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=server.serve_forever, name="mock-llm", daemon=True).start()
        _base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"

        # 임베딩 클라이언트는 주소가 OpenAI 로 고정돼 있어 기본값만 가짜 서버로 바꾼다.
        from app.integrations.llm.embedding import Embedder

        Embedder.__init__.__kwdefaults__["endpoint"] = f"{_base_url}/embeddings"
        log.warning(f"OpenAI API 키 없음 — 가짜 LLM 으로 동작 ({_base_url})")
        return _base_url
