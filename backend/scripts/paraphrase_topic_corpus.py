"""topicCorpus.json 의 섹션 본문을 LLM 으로 친근한 톤으로 paraphrase.

목적
  사용자가 호버에서 보는 본문이 노무사회 원문 그대로라 법률 용어 무거움.
  일반 사장님·근로자가 한 호흡에 이해할 수 있는 톤으로 다시 씀.

규칙
  - 1~2 문장으로 압축
  - 법률 용어는 풀어쓰되 정확한 법령명·조문 번호는 유지
  - "~해요" / "~합니다" 톤 통일
  - 핵심 결론 먼저, 부연 뒤
  - 법조문·판례 인용은 본문 끝에 "관련 법령: ..." 한 줄로 정리

캐싱
  - llm_cache 활용 — 같은 본문 두 번 호출 안 함
  - 결과는 frontend/src/data/topicCorpus.json 에 in-place `body_friendly` 키로 저장
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# mvp 패키지 경로 추가
ROOT_MVP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_MVP))

from openai import OpenAI  # noqa: E402

from app.integrations.llm import cache as llm_cache  # noqa: E402
from app.core.config import get_api_key, get_llm_model  # noqa: E402

WORKSPACE = Path(r"C:\Users\Jini\Desktop\1. 영세사업장 자율점검")
CORPUS_PATH = (
    WORKSPACE / "3. 취업규칙" / "frontend" / "src" / "data" / "topicCorpus.json"
)

SYSTEM_PROMPT = """\
당신은 노동법 본문을 사장님·근로자가 한 호흡에 이해할 수 있도록 풀어쓰는 전문가입니다.

[규칙]
1. **2~3문장**으로 압축. 너무 짧지도 너무 길지도 않게.
2. 법률 용어는 일상어로 풀되, 법령명·조문 번호는 정확히 유지.
3. 톤은 "~해요" / "~합니다" 친근하지만 단정하게. 광고 톤·이모지 금지.
4. 핵심 결론 먼저, 부연이나 예외는 뒤로.
5. 본문 마지막 줄에 인용 법령·판례를 한 줄로 정리:
   "관련 법령: 근로기준법 제N조" 또는 "관련 법령: ..., 판례: ..." 같은 형식.
6. 답변은 정제된 본문만 출력. 설명·머리말·인사말 없이.
"""


def paraphrase_one(client: OpenAI, model: str, title: str, body: str) -> str:
    """단일 섹션 본문을 친근한 톤으로 paraphrase. 캐시 활용."""
    user = f"제목: {title}\n\n본문:\n{body}\n\n위 내용을 [규칙]대로 친근하게 풀어 써 주세요."
    cache_key = llm_cache.make_key(
        system=SYSTEM_PROMPT,
        user=user,
        schema={"kind": "topic_paraphrase_v1"},
        model=model,
    )
    cached = llm_cache.get(cache_key)
    if cached and isinstance(cached.get("text"), str):
        return cached["text"]

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0,
        top_p=1,
    )
    text = (resp.choices[0].message.content or "").strip()
    if text:
        llm_cache.put(cache_key, {"text": text})
    return text


def main():
    if not CORPUS_PATH.exists():
        raise SystemExit(f"corpus not found: {CORPUS_PATH}")
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

    client = OpenAI(api_key=get_api_key(), timeout=120.0)
    model = get_llm_model()

    # PoC — 각 주제당 최대 N 개 섹션만 paraphrase. 자주 호버에 잡힐 가능성 큰 §1, §2.x, §3.x.
    per_topic = int(os.environ.get("PER_TOPIC", "8"))

    targets: list[tuple[str, str, str, str]] = []  # (db, sec, title, body)
    for db, sections in corpus.items():
        keys = list(sections.keys())
        # 첫 N 개 (대개 §1, §2, §2.1, §2.1.1, §2.2 …)
        for sec in keys[:per_topic]:
            entry = sections[sec]
            if not entry.get("body"):
                continue
            if entry.get("body_friendly"):
                continue  # 이미 변환됨
            targets.append((db, sec, entry.get("title", ""), entry["body"]))

    print(f"target sections: {len(targets)} (per_topic={per_topic})")
    if not targets:
        print("nothing to do.")
        return

    t0 = time.time()
    done = 0
    failed = 0
    for db, sec, title, body in targets:
        try:
            friendly = paraphrase_one(client, model, title, body)
            corpus[db][sec]["body_friendly"] = friendly
            done += 1
        except Exception as e:
            failed += 1
            print(f"  fail {db}|{sec}: {e}")
        if done % 20 == 0:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (len(targets) - done) / rate if rate > 0 else 0
            print(
                f"  progress {done}/{len(targets)} "
                f"({rate:.1f}/s, ETA {eta:.0f}s)"
            )
            # 중간 저장 — 큰 작업 중단 시 손실 최소화
            CORPUS_PATH.write_text(
                json.dumps(corpus, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    CORPUS_PATH.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    elapsed = time.time() - t0
    print(
        f"\ndone. {done} ok / {failed} fail / {elapsed:.1f}s "
        f"({done / elapsed:.2f}/s)"
    )
    print(f"size: {CORPUS_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
