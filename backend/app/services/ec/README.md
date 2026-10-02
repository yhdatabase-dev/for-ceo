# `cgr.ec` — 근로계약서 모듈

근로기준법 제17조 기반 필수기재사항 검토.
35 슬롯 × 7 worker_types(정규/기간제/단시간/일용/연소/외국인/외국인-농축어업) × business_size(5+/5-).

## 4단계 파이프라인

```
1. extract     OCR/파서 — 파일 → 텍스트
2. structure   LLM — 텍스트 → 8섹션 JSON
3. analyze     LLM — 33매핑 위반 분석
4. generate    LLM — 표준 계약서 본문 생성
```

추가: `chat` — 결과 후속 챗봇.

## 파일

| 파일 | 책임 |
|---|---|
| `catalog.py` | 슬롯 로더 — 마스터 DB 우선 + YAML fallback |
| `prompts.py` | 시스템 프롬프트 (33매핑 테이블 포함) |
| `topic_lookup.py` | 슬롯 → 노무사회 코퍼스 섹션 lookup |
| `verdict.py` | 결과 후처리 룰 |
| `services/structure.py` | 8섹션 구조화 |
| `services/analyze.py` | 33매핑 분석 |
| `services/chat.py` | 챗봇 |
| `services/generate.py` | 표준 계약서 생성 |

## 진입

```python
from cgr.ec.catalog import load_ec_catalog
from cgr.ec.services import analyze, structure, generate

cat = load_ec_catalog()
structured = structure.run(extracted_text)
result = analyze.run(structured, business_size='5+', worker_types=['정규직'])
contract_text = generate.run(result, user_overrides={})
```

## API

`backend/cgr/api/routes/ec.py` — 5 엔드포인트 (`/api/v1/ec/{extract,structure,analyze,chat,generate}`).
