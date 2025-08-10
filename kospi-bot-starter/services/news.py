import httpx
from datetime import datetime, timezone
from typing import List, Dict, Any
from .utils import make_hash

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

def _headers(naver_id: str, naver_secret: str):
    return {
        "X-Naver-Client-Id": naver_id,
        "X-Naver-Client-Secret": naver_secret,
    }

async def fetch_news(naver_id: str, naver_secret: str, query: str, display: int = 50, sort: str = "date"):
    params = {"query": query, "display": display, "sort": sort}
    async with httpx.AsyncClient(timeout=15, headers=_headers(naver_id, naver_secret)) as s:
        r = await s.get(NAVER_NEWS_URL, params=params)
        r.raise_for_status()
        return r.json()

def normalize_news(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = []
    for it in raw.get("items", []) or []:
        title = it.get("title", "").replace("<b>", "").replace("</b>", "")
        link = it.get("link")
        # Naver 뉴스 pubDate 예: 'Sun, 10 Aug 2025 14:30:00 +0900'
        try:
            published_at = datetime.strptime(it["pubDate"], "%a, %d %b %Y %H:%M:%S %z").astimezone(timezone.utc).isoformat()
        except Exception:
            published_at = datetime.utcnow().isoformat() + "Z"

        tags = []
        t = title
        if "단독" in t: tags.append("단독")
        if "속보" in t: tags.append("속보")
        if "공시" in t or "IR" in t: tags.append("공시/IR")

        score = 0.1
        if "속보" in t: score += 0.3
        if "단독" in t: score += 0.2

        items.append({
            "type": "NEWS",
            "symbol": None,  # 심볼 매핑은 확장 포인트(회사명 사전 필요)
            "title": title,
            "url": link,
            "published_at": published_at,
            "tags": tags,
            "score": score,
            "_dedupe": make_hash("NEWS", title, link),
        })
    return items
