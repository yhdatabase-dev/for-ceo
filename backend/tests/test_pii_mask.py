"""PII 비식별 게이트 테스트 — 외부 LLM 전송 직전 마스킹의 보증.

RFP SFR-003(비식별 후 외부 전달)의 코드 측 안전망. 패턴이 하나라도
풀리면 여기서 즉시 깨진다.
"""
from __future__ import annotations

from app.core import pii_mask


def test_rrn_masked():
    out = pii_mask.mask_pii("주민등록번호 901231-1234567 입니다")
    assert "901231-1234567" not in out.masked
    assert out.counts.get("rrn") == 1


def test_phone_masked_keeps_prefix():
    out = pii_mask.mask_pii("연락처 010-1234-5678")
    assert "1234-5678" not in out.masked
    assert "010-****-****" in out.masked


def test_biz_no_masked():
    out = pii_mask.mask_pii("사업자번호 123-45-67890")
    assert "123-45-67890" not in out.masked
    assert out.counts.get("biz_no") == 1


def test_email_masked():
    out = pii_mask.mask_pii("이메일 hong@example.com 으로")
    assert "hong@example.com" not in out.masked


def test_labeled_name_masked_keeps_first_char():
    out = pii_mask.mask_pii("성명: 홍길동 / 부서: 총무")
    assert "홍길동" not in out.masked
    assert "홍○○" in out.masked


def test_labeled_account_masked():
    out = pii_mask.mask_pii("계좌번호: 110-1234-567890")
    assert "110-1234-567890" not in out.masked
    assert out.counts.get("account") == 1


def test_card_number_masked():
    out = pii_mask.mask_pii("카드 1234-5678-9012-3456")
    assert "5678-9012" not in out.masked


def test_unlabeled_plain_text_untouched():
    """라벨 없는 일반 한글(직급·항목명 등)은 건드리지 않는다 — 오탐 방지."""
    text = "기본급 2,090,000원과 연장근로수당을 지급한다"
    assert pii_mask.mask_pii_text(text) == text


def test_payload_recursive_masking():
    payload = {
        "근로자": {"성명": "성명: 김철수", "메모": ["전화 010-9999-8888"]},
        "금액": 1000,
    }
    out = pii_mask.mask_pii_in_payload(payload)
    assert "김철수" not in str(out)
    assert "9999-8888" not in str(out)
    assert out["금액"] == 1000  # 비문자열은 그대로


def test_deterministic():
    text = "성명: 홍길동 / 주민 901231-1234567 / 010-1234-5678"
    assert pii_mask.mask_pii_text(text) == pii_mask.mask_pii_text(text)
