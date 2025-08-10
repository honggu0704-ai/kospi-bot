import hashlib
from datetime import datetime, timezone

def utcnow_iso() -> datetime:
    return datetime.now(timezone.utc)

def make_hash(*parts: str) -> str:
    joined = "||".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()

def is_kospi_stock_code(code: str) -> bool:
    # DART stock_code: 6자리. (유가증권시장은 corp_cls=Y로 필터)
    return code is not None and len(code) == 6 and code.isdigit()
