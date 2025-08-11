import httpx
from datetime import datetime
from typing import List, Dict, Any
from .utils import make_hash, is_kospi_stock_code

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"

async def fetch_dart_list(api_key: str, bgn_de: str, end_de: str, page_no: int = 1, page_count: int = 100):
    params = {
        "crtfc_key": api_key,
        "corp_cls": "Y",      # KOSPI만
        "bgn_de": bgn_de,     # YYYYMMDD
        "end_de": end_de,     # YYYYMMDD
        "page_no": page_no,
        "page_count": page_count,
        # 필요 시 pblntf_ty, pblntf_detail_ty로 세분화 가능
    }
    async with httpx.AsyncClient(timeout=15) as s:
        r = await s.get(DART_LIST_URL, params=params)
        r.raise_for_status()
        return r.json()

def normalize_dart_items(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = []
    for it in raw.get("list", []) or []:
        title = it.get("rpt_nm") or "무제"
        # DART에는 정확한 발표시각이 초 단위로 안 올 수 있음 -> rcept_dt(YYYYMMDD)로 대체
        dt = it.get("rcept_dt")
        published = datetime.strptime(dt, "%Y%m%d").isoformat() + "Z" if dt else datetime.utcnow().isoformat() + "Z"
        url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it.get('rcp_no')}"
        symbol = it.get("stock_code")
        # DART의 stock_code가 6자리 숫자가 아닐 수 있으므로 검증
        if not is_kospi_stock_code(symbol):
            symbol = None
        tags = []
        # 간단 태깅 예시
        if "유상증자" in title or "증자" in title or "발행" in title:
            tags.append("자금조달")
        if "정정" in title:
            tags.append("정정")
        if "합병" in title:
            tags.append("M&A")
        score = 0.0
        if "증자" in title or "전환사채" in title:
            score += 0.6
        if "정정" in title:
            score += 0.3

        items.append({
            "type": "DART",
            "symbol": symbol,
            "title": title,
            "url": url,
            "published_at": published,
            "tags": tags,
            "score": score,
            "_dedupe": make_hash("DART", title, url),
        })
    return items
