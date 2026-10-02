"""파일 입력 어댑터 (docx/hwp/hwpx/pdf/평문 → plaintext)."""
from app.integrations.parsers.dispatcher import parse_to_text

__all__ = ["parse_to_text"]
