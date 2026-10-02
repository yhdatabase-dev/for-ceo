"""노무 가이드 콘텐츠 조회·서식 다운로드·엑셀 내보내기."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)

from app.core.security import require_api_key
from app.repositories.guide.content import _FORMS_DIR, _query_all

router = APIRouter(tags=["guide"])


# ─────────────────────────────────────────────
# 1) GET /api/v1/guide/items — FAQ 항목
# ─────────────────────────────────────────────
@router.get(
    "/items",
    summary="가이드 FAQ 항목 (1·2·3 시트 통합)",
    description=(
        "audience: employer / worker / both. 기본 사업주 + 공통.\n"
        "category 로 필터 가능 (임금 검증 / 의무 경계 / 취업규칙 등)."
    ),
    dependencies=[Depends(require_api_key)],
)
def get_guide_items(
    audience: str | None = Query(
        default=None, description="필터 — employer / worker / both"
    ),
    category: str | None = Query(default=None, description="카테고리 부분 일치"),
):
    sql = (
        "SELECT code, audience, category, title, worker_reason, employer_reason, "
        "       key_points, related_laws, priority, applies_under_5, note "
        "FROM guide_item WHERE excluded_from_service = 0 "
    )
    params: list[Any] = []
    if audience:
        sql += "AND audience = ? "
        params.append(audience)
    else:
        # 기본 — 사업주 + 공통
        sql += "AND audience IN ('employer', 'both') "
    if category:
        sql += "AND category LIKE ? "
        params.append(f"%{category}%")
    sql += "ORDER BY priority, code"
    return {"items": _query_all(sql, tuple(params))}

@router.get(
    "/items/{code}",
    summary="가이드 항목 단건",
    dependencies=[Depends(require_api_key)],
)
def get_guide_item(code: str):
    rows = _query_all(
        "SELECT * FROM guide_item WHERE code = ? AND excluded_from_service = 0",
        (code,),
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return rows[0]

# ─────────────────────────────────────────────
# 2) GET /api/v1/guide/glossary — 용어 사전
# ─────────────────────────────────────────────
@router.get(
    "/glossary",
    summary="용어 사전 (통상임금 vs 평균임금 등)",
    dependencies=[Depends(require_api_key)],
)
def get_glossary():
    return {
        "items": _query_all(
            "SELECT code, term, short_def, full_def, confusable_with, legal_basis "
            "FROM guide_glossary ORDER BY code"
        )
    }

# ─────────────────────────────────────────────
# 3) GET /api/v1/guide/by-size/{min_size} — 규모별 의무
# ─────────────────────────────────────────────
@router.get(
    "/by-size/{min_size}",
    summary="사업장 규모별 의무 — 홈 페이지에서 prefetch",
    description="min_size 예: '1인 이상', '5인 이상', '10인 이상', '30인 이상', '50인 이상'",
    dependencies=[Depends(require_api_key)],
)
def get_duties_by_size(min_size: str):
    # 정확 일치 + 누적 (예: 10인 이상은 1·5·10 모두 적용)
    SIZE_RANK = {
        "1인 이상": 1,
        "5인 이상": 5,
        "10인 이상": 10,
        "30인 이상": 30,
        "50인 이상": 50,
    }
    target_rank = SIZE_RANK.get(min_size, 0)
    if not target_rank:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"min_size must be one of {list(SIZE_RANK.keys())}",
        )
    rows = _query_all(
        "SELECT code, min_size, duty, description, related_docs, legal_basis "
        "FROM size_threshold_duty ORDER BY code"
    )
    # 본인 규모 이하 + 일치 모두 노출 (1인+ 의무는 5인+ 사업장에도 해당)
    applicable = [
        r for r in rows if SIZE_RANK.get(r["min_size"], 999) <= target_rank
    ]
    return {"size": min_size, "rank": target_rank, "duties": applicable}

# ─────────────────────────────────────────────
# 4) GET /api/v1/guide/by-stage/{stage} — 시기별 의무
# ─────────────────────────────────────────────
@router.get(
    "/by-stage/{stage}",
    summary="시기별 의무 (사업개시·채용·근로중·종료)",
    dependencies=[Depends(require_api_key)],
)
def get_duties_by_stage(stage: str):
    rows = _query_all(
        "SELECT code, stage, duty, description, deadline, legal_basis, priority, penalty "
        "FROM obligation_timeline "
        "WHERE excluded_from_service = 0 AND stage LIKE ? "
        "ORDER BY priority, code",
        (f"%{stage}%",),
    )
    return {"stage": stage, "duties": rows}

# ─────────────────────────────────────────────
# 4-b) GET /api/v1/guide/timeline — 전체 단계별 의무 (28개)
# ─────────────────────────────────────────────
@router.get(
    "/timeline",
    summary="전체 단계별 의무 (8단계 × 28항목)",
    description="사업 흐름(개시→채용→임금→…→종료) 순서대로 기한·우선순위·과태료 포함.",
    dependencies=[Depends(require_api_key)],
)
def get_timeline_all():
    rows = _query_all(
        "SELECT code, stage, duty, description, deadline, legal_basis, priority, penalty "
        "FROM obligation_timeline "
        "WHERE excluded_from_service = 0 "
        "ORDER BY stage, priority, code",
    )
    return {"items": rows}

# ─────────────────────────────────────────────
# 5) GET /api/v1/guide/forms — 신청 서식 (사업주용만)
# ─────────────────────────────────────────────
@router.get(
    "/forms",
    summary="신청 서식 카탈로그 (사업주 작성·제출용)",
    description="진정·구제 신청서 등은 시드에서 제외됨.",
    dependencies=[Depends(require_api_key)],
)
def get_forms(
    category: str | None = Query(default=None),
    audience: str | None = Query(default=None, description="명시 시 그 audience 만"),
):
    """양식 카탈로그 — 분쟁 양식은 시드에서 제외(EXCLUDED_FORM_CODES)되었고,
    남은 양식은 모두 정상 노무행정 양식이라 사업주가 모두 알아둬야 한다:

      - 근로자가 신청하는 출산·육아·산재 급여 → 사업주 확인서·협조 의무
      - 사업주가 발급하는 이직확인서·임금명세서
      - 사업주가 작성·신고하는 근로계약서·취업규칙

    그래서 default 는 audience 무관 — `excluded_from_service = 0` 만.
    """
    sql = (
        "SELECT code, category, form_name, purpose, submitter, submit_to, "
        "       submit_method, deadline, legal_basis, download_url, audience, "
        "       local_filename, local_mime, local_size, fetched_at "
        "FROM form_template WHERE excluded_from_service = 0 "
    )
    params: list[Any] = []
    if audience:
        sql += "AND audience = ? "
        params.append(audience)
    if category:
        sql += "AND category LIKE ? "
        params.append(f"%{category}%")
    sql += "ORDER BY code"
    items = _query_all(sql, tuple(params))
    # 클라이언트가 "직접 다운로드 가능" 한지 즉시 알 수 있도록 has_local 플래그 추가.
    # local_filename 이 있고 실제 파일도 있어야 true — 시드만 되고 파일 빠진 경우 false.
    for it in items:
        fn = it.get("local_filename")
        it["has_local"] = bool(fn and (_FORMS_DIR / fn).is_file())
    return {"items": items}

# ─────────────────────────────────────────────
# 5-b) GET /api/v1/guide/forms/{code}/download — 양식 파일 직접 다운로드
# ─────────────────────────────────────────────
@router.get(
    "/forms/{code}/download",
    summary="양식 파일 다운로드 — 로컬 파일이 있으면 스트림, 없으면 외부 URL 로 302",
    description=(
        "1) `local_filename` 컬럼이 채워져 있고 `backend/data/forms/<filename>` 파일이 "
        "실재하면 FileResponse 로 stream (정확한 MIME + Content-Disposition).\n"
        "2) 둘 다 없으면 `download_url` (고용노동부 자료실 등) 로 302 redirect — "
        "사용자가 외부 사이트에서라도 양식을 찾을 수 있게 폴백."
    ),
    dependencies=[Depends(require_api_key)],
)
def download_form(code: str):
    rows = _query_all(
        "SELECT code, form_name, local_filename, local_mime, download_url, "
        "excluded_from_service "
        "FROM form_template WHERE code = ?",
        (code,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"양식 코드 {code} 를 찾을 수 없습니다.")
    row = rows[0]
    if row["excluded_from_service"]:
        raise HTTPException(
            status_code=410,
            detail="이 양식은 자율점검 범위에서 제외됐습니다(분쟁·구제 신청서).",
        )

    local_filename = row["local_filename"]
    if local_filename:
        # 경로조작 방어(국정원 8대/KISA '경로 조작 및 자원 삽입') — DB 값이라도
        # ../ 등으로 _FORMS_DIR 밖을 가리키지 못하게 basename + 컨테인먼트 이중 확인.
        safe_name = Path(local_filename).name
        path = (_FORMS_DIR / safe_name).resolve()
        forms_root = _FORMS_DIR.resolve()
        if forms_root in path.parents and path.is_file():
            # Content-Disposition 헤더 — starlette/HTTP 표준이 latin-1 강제하므로
            # 한국어 파일명을 그대로 넣으면 UnicodeEncodeError. 해결:
            #   1) ASCII fallback (코드 기반) — 모든 브라우저가 인식
            #   2) RFC 5987 `filename*=UTF-8''<percent-encoded>` — 한국어 그대로 노출
            # 최신 브라우저는 filename* 우선 → 한국어 파일명으로 저장됨.
            # `quote` 가 ASCII 외 문자만 percent-encode 하므로 영문 파일명은 그대로.
            ext = Path(safe_name).suffix or ".bin"
            ascii_fallback = f"{row['code']}{ext}"
            cd = (
                f"attachment; filename=\"{ascii_fallback}\"; "
                f"filename*=UTF-8''{quote(safe_name)}"
            )
            return FileResponse(
                path,
                media_type=row["local_mime"] or "application/octet-stream",
                # FileResponse 의 filename= 인자도 latin-1 강제하므로 ASCII 만.
                # 진짜 파일명은 위 cd 헤더의 filename* 로 전달.
                filename=ascii_fallback,
                headers={"Content-Disposition": cd},
            )
        # local_filename 설정됐지만 실제 파일 없음 — 로깅용 경고는 운영자 몫
    # 폴백 — 외부 정부 사이트 URL
    if row["download_url"]:
        return RedirectResponse(url=row["download_url"], status_code=302)
    raise HTTPException(
        status_code=404,
        detail="이 양식의 다운로드 파일도, 외부 URL 도 등록돼 있지 않습니다.",
    )

# ─────────────────────────────────────────────
# 6) GET /api/v1/guide/wage-calc — 계산 공식 (V003~V006 연계)
# ─────────────────────────────────────────────
@router.get(
    "/wage-calc",
    summary="임금·수당 계산 공식 카탈로그",
    description=(
        "결과 페이지에서 V003 연장근로수당 finding 옆에 'CAL001 공식 보기' 같이 활용."
    ),
    dependencies=[Depends(require_api_key)],
)
def get_wage_calc(
    violation_code: str | None = Query(default=None),
):
    sql = (
        "SELECT code, category, calc_name, formula, conditions, limits, "
        "       legal_basis, note, related_violation_code "
        "FROM wage_calc_formula "
    )
    params: list[Any] = []
    if violation_code:
        sql += "WHERE related_violation_code = ? "
        params.append(violation_code)
    sql += "ORDER BY code"
    return {"items": _query_all(sql, tuple(params))}

# ─────────────────────────────────────────────
# 7) GET /api/v1/guide/orgs — 관할 기관 (분쟁 기관 제외)
# ─────────────────────────────────────────────
@router.get(
    "/orgs",
    summary="관할 기관 (사업주 이용 채널만)",
    dependencies=[Depends(require_api_key)],
)
def get_orgs():
    return {
        "items": _query_all(
            "SELECT code, org_class, org_name, duties, common_cases, phone, "
            "       online_channel, jurisdiction, note "
            "FROM gov_org WHERE excluded_from_service = 0 ORDER BY code"
        )
    }

# ─────────────────────────────────────────────
# 8) GET /api/v1/guide/audit — 근로감독 가이드
# ─────────────────────────────────────────────
@router.get(
    "/audit",
    summary="근로감독 종류·진행 절차",
    dependencies=[Depends(require_api_key)],
)
def get_audit_guide():
    return {
        "types": _query_all(
            "SELECT code, name, description, period_covered, legal_basis "
            "FROM audit_guide WHERE kind = 'type' ORDER BY code"
        ),
        "procedure": _query_all(
            "SELECT code, name, step_no, timing, description, legal_basis "
            "FROM audit_guide WHERE kind = 'procedure' "
            "ORDER BY step_no, code"
        ),
    }

# ─────────────────────────────────────────────
# 9) GET /api/v1/guide/required-docs — 비치 서류
# ─────────────────────────────────────────────
@router.get(
    "/required-docs",
    summary="법령상 의무 비치 서류",
    dependencies=[Depends(require_api_key)],
)
def get_required_docs():
    return {
        "items": _query_all(
            "SELECT code, classification, doc_name, description, "
            "       prep_time, retention_period, legal_basis, penalty "
            "FROM required_document ORDER BY classification, code"
        )
    }

# ─────────────────────────────────────────────
# 10) GET /api/v1/guide/lifecycle — 채용~종료 라이프사이클
# ─────────────────────────────────────────────
@router.get(
    "/lifecycle",
    summary="채용부터 종료까지 종합 가이드",
    dependencies=[Depends(require_api_key)],
)
def get_lifecycle():
    return {
        "items": _query_all(
            "SELECT code, phase, sub_topic, requirement, related_docs, "
            "       timing, legal_basis, note "
            "FROM employment_lifecycle ORDER BY code"
        )
    }

# ─────────────────────────────────────────────
# 11) GET /api/v1/guide/recruit — 채용 절차 준수사항
# ─────────────────────────────────────────────
@router.get(
    "/recruit",
    summary="채용 절차 준수사항 (채용공고~합격통지)",
    dependencies=[Depends(require_api_key)],
)
def get_recruit():
    return {
        "items": _query_all(
            "SELECT code, stage, duty, description, violation_examples, "
            "       penalty, applies_to, legal_basis, checkpoint "
            "FROM recruit_compliance ORDER BY code"
        )
    }

# ─────────────────────────────────────────────
# 12) GET /api/v1/guide/overview — 대시보드 한 화면 요약
# ─────────────────────────────────────────────
@router.get(
    "/overview",
    summary="가이드 전체 한 줄 요약 (사업주 대시보드용)",
    dependencies=[Depends(require_api_key)],
)
def get_overview():
    """프론트 /guide 페이지의 첫 진입 시 카운트만 빠르게."""
    return JSONResponse(
        {
            "guide_items": _query_all(
                "SELECT COUNT(*) AS n FROM guide_item "
                "WHERE excluded_from_service = 0 AND audience IN ('employer', 'both')"
            )[0]["n"],
            "obligations": _query_all(
                "SELECT COUNT(*) AS n FROM obligation_timeline WHERE excluded_from_service = 0"
            )[0]["n"],
            "wage_formulas": _query_all(
                "SELECT COUNT(*) AS n FROM wage_calc_formula"
            )[0]["n"],
            "glossary": _query_all("SELECT COUNT(*) AS n FROM guide_glossary")[0]["n"],
            "forms": _query_all(
                "SELECT COUNT(*) AS n FROM form_template "
                "WHERE excluded_from_service = 0 AND audience IN ('employer', 'both')"
            )[0]["n"],
            "orgs": _query_all(
                "SELECT COUNT(*) AS n FROM gov_org WHERE excluded_from_service = 0"
            )[0]["n"],
            "required_docs": _query_all(
                "SELECT COUNT(*) AS n FROM required_document"
            )[0]["n"],
            "lifecycle_steps": _query_all(
                "SELECT COUNT(*) AS n FROM employment_lifecycle"
            )[0]["n"],
        }
    )

# ═══════════════════════════════════════════════════════════════
# 14) GET /api/v1/guide/export.xlsx — 가이드 데이터 통합 Excel 다운로드
#
# 6개 시트: 시기별 의무 / 규모별 의무 / 용어 사전 / 정부 기관 / 비치 서류 /
#           고용 생애주기 / 채용 컴플라이언스
# 사장님이 오프라인에서도 참고할 수 있도록 정리된 자료를 한 파일로.
# ═══════════════════════════════════════════════════════════════
@router.get(
    "/export.xlsx",
    summary="가이드 데이터 통합 Excel 다운로드",
    dependencies=[Depends(require_api_key)],
)
def export_guide_xlsx():
    """openpyxl 로 다중 시트 xlsx 생성 후 스트림."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        raise HTTPException(status_code=503, detail="openpyxl 미설치 — pip install openpyxl")

    wb = Workbook()
    # 헤더 스타일 — 옅은 브랜드 배경 + 굵은 글씨
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="0B3D91")
    header_align = Alignment(vertical="center", horizontal="center")

    def _add_sheet(title: str, headers: list[str], rows: list[dict], col_widths: list[int]):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
        for r in rows:
            ws.append([r.get(k, "") or "" for k in r.keys()])
        for i, w in enumerate(col_widths, start=1):
            ws.column_dimensions[chr(64 + i)].width = w
        ws.row_dimensions[1].height = 28
        # 본문 줄 wrap
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    # 기본 첫 시트 제거 후 순서대로 추가
    wb.remove(wb.active)

    # 1) 시기별 의무
    _add_sheet(
        "시기별 의무",
        ["코드", "단계", "의무", "설명", "기한", "근거 법령", "벌칙", "우선순위"],
        [
            {
                "code": r["code"],
                "stage": r["stage"],
                "duty": r["duty"],
                "description": r["description"],
                "deadline": r["deadline"],
                "legal_basis": r["legal_basis"],
                "penalty": r["penalty"],
                "priority": r["priority"],
            }
            for r in _query_all(
                "SELECT code, stage, duty, description, deadline, legal_basis, penalty, priority "
                "FROM obligation_timeline WHERE excluded_from_service = 0 "
                "ORDER BY stage, code"
            )
        ],
        [10, 12, 28, 50, 18, 28, 32, 10],
    )

    # 2) 규모별 의무
    _add_sheet(
        "규모별 의무",
        ["코드", "최소 규모", "의무", "설명", "관련 서류", "근거 법령"],
        [
            {
                "code": r["code"],
                "min_size": r["min_size"],
                "duty": r["duty"],
                "description": r["description"],
                "related_docs": r["related_docs"],
                "legal_basis": r["legal_basis"],
            }
            for r in _query_all(
                "SELECT code, min_size, duty, description, related_docs, legal_basis "
                "FROM size_threshold_duty ORDER BY "
                "CASE min_size WHEN '1인 이상' THEN 1 WHEN '5인 이상' THEN 5 "
                "  WHEN '10인 이상' THEN 10 WHEN '30인 이상' THEN 30 "
                "  WHEN '50인 이상' THEN 50 ELSE 999 END, code"
            )
        ],
        [10, 12, 30, 50, 25, 28],
    )

    # 3) 용어 사전
    _add_sheet(
        "용어 사전",
        ["코드", "용어", "짧은 정의", "상세 정의", "헷갈리는 용어", "근거"],
        [
            {
                "code": r["code"],
                "term": r["term"],
                "short_def": r["short_def"],
                "full_def": r["full_def"],
                "confusable_with": r["confusable_with"],
                "legal_basis": r["legal_basis"],
            }
            for r in _query_all(
                "SELECT code, term, short_def, full_def, confusable_with, legal_basis "
                "FROM guide_glossary ORDER BY code"
            )
        ],
        [10, 22, 50, 70, 30, 22],
    )

    # 4) 정부 기관
    _add_sheet(
        "정부 기관",
        ["코드", "기관 분류", "기관명", "담당 업무", "흔한 활용 사례", "전화", "온라인 채널", "관할"],
        [
            {
                "code": r["code"],
                "org_class": r["org_class"],
                "org_name": r["org_name"],
                "duties": r["duties"],
                "common_cases": r["common_cases"],
                "phone": r["phone"],
                "online_channel": r["online_channel"],
                "jurisdiction": r["jurisdiction"],
            }
            for r in _query_all(
                "SELECT code, org_class, org_name, duties, common_cases, phone, "
                "       online_channel, jurisdiction "
                "FROM gov_org WHERE excluded_from_service = 0 ORDER BY org_class, code"
            )
        ],
        [10, 18, 26, 40, 40, 14, 36, 22],
    )

    # 5) 비치 서류
    _add_sheet(
        "비치 서류",
        ["코드", "분류", "서류명", "설명", "작성 시기", "보존 기간", "근거 법령", "벌칙"],
        [
            {
                "code": r["code"],
                "classification": r["classification"],
                "doc_name": r["doc_name"],
                "description": r["description"],
                "prep_time": r["prep_time"],
                "retention_period": r["retention_period"],
                "legal_basis": r["legal_basis"],
                "penalty": r["penalty"],
            }
            for r in _query_all(
                "SELECT code, classification, doc_name, description, prep_time, "
                "       retention_period, legal_basis, penalty "
                "FROM required_document ORDER BY classification, code"
            )
        ],
        [10, 14, 30, 50, 18, 18, 28, 22],
    )

    # 6) 고용 생애주기
    _add_sheet(
        "고용 생애주기",
        ["코드", "단계", "세부 주제", "요건", "관련 서류", "시기", "근거"],
        [
            {
                "code": r["code"],
                "phase": r["phase"],
                "sub_topic": r["sub_topic"],
                "requirement": r["requirement"],
                "related_docs": r["related_docs"],
                "timing": r["timing"],
                "legal_basis": r["legal_basis"],
            }
            for r in _query_all(
                "SELECT code, phase, sub_topic, requirement, related_docs, timing, legal_basis "
                "FROM employment_lifecycle ORDER BY phase, code"
            )
        ],
        [10, 14, 22, 50, 22, 16, 24],
    )

    # 7) 채용 컴플라이언스
    _add_sheet(
        "채용 컴플라이언스",
        ["코드", "단계", "의무", "설명", "위반 사례", "벌칙", "적용 대상", "근거", "점검 포인트"],
        [
            {
                "code": r["code"],
                "stage": r["stage"],
                "duty": r["duty"],
                "description": r["description"],
                "violation_examples": r["violation_examples"],
                "penalty": r["penalty"],
                "applies_to": r["applies_to"],
                "legal_basis": r["legal_basis"],
                "checkpoint": r["checkpoint"],
            }
            for r in _query_all(
                "SELECT code, stage, duty, description, violation_examples, penalty, "
                "       applies_to, legal_basis, checkpoint "
                "FROM recruit_compliance ORDER BY stage, code"
            )
        ],
        [10, 14, 26, 45, 36, 22, 18, 22, 30],
    )

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    fname = "영세사업장_노무_가이드.xlsx"
    ascii_fallback = "labor-guide.xlsx"
    cd = (
        f"attachment; filename=\"{ascii_fallback}\"; "
        f"filename*=UTF-8''{quote(fname)}"
    )
    return StreamingResponse(
        buf,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": cd},
    )
