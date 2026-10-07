"""API 스모크 테스트 — 앱 기동·인증 게이트·헬스.

LLM 을 호출하지 않는 경로만 검증한다:
  - 앱이 import·기동되는가 (라우터 7개 등록 포함)
  - 보호 엔드포인트가 키 없이는 401 인가 (인증 게이트 보증)
  - 제외한 관리자·ws·sc 엔드포인트가 등록되지 않았는가
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # conftest 가 CGR_API_KEY/CGR_DATA_DIR(임시)/가짜 LLM 을 이미 설정한 상태에서 import
    from app.main import app
    with TestClient(app) as c:  # with: startup 이벤트(보관기간 정리 — 임시 디렉터리) 실행
        yield c


API = "/api/cgr"
KEY = {"X-API-Key": os.environ["CGR_API_KEY"]}


def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_warmup_no_auth(client):
    r = client.get(f"{API}/warmup")
    assert r.status_code == 200
    assert r.json() == {"status": "warm"}


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_protected_route_requires_key(client):
    assert client.get(f"{API}/history/entries").status_code == 401
    assert client.get(f"{API}/history/entries", headers={"X-API-Key": "wrong"}).status_code == 401


def test_protected_route_with_key(client):
    r = client.get(f"{API}/history/entries", headers=KEY)
    assert r.status_code == 200


@pytest.mark.parametrize(
    "path",
    ["/admin/analytics", "/slots", "/master-db/articles", "/ws/catalog", "/sc/extract/start"],
)
def test_removed_routes_absent(client, path):
    """관리자·임금명세서(ws)·노무제공자(sc) 기능 제외 — 라우트가 등록되지 않아야 한다."""
    r = client.get(f"{API}{path}", headers=KEY)
    assert r.status_code in (404, 405)


def test_upload_rejects_disguised_file(client):
    """추출 엔드포인트가 위장 파일(.png 인데 exe 바이트)을 400 으로 거부."""
    r = client.post(
        f"{API}/ec/extractions",
        headers=KEY,
        files={"file": ("fake.png", b"MZ\x90\x00" + b"\x00" * 32, "image/png")},
    )
    assert r.status_code == 400
