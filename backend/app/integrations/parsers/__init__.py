#
# 파일 입력 어댑터 (docx/hwp/hwpx/pdf/평문 → plaintext).
#
# << 개정이력(Modification Information) >>
# 수정일          수정자      수정 내용
# ----------      ------      ---------------------------
# 2026.05.28      kimzion77   최초 생성
# 2026.10.02      이시영      구조 이행 (backend/cgr → backend/app)
#
# Author: kimzion77
# Since: 2026.05.28
#
"""파일 입력 어댑터 (docx/hwp/hwpx/pdf/평문 → plaintext)."""
from app.integrations.parsers.dispatcher import parse_to_text

__all__ = ["parse_to_text"]
