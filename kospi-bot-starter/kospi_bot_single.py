import os
import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Set, Optional, Literal, Dict, Any

import httpx
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from pydantic import BaseModel, AnyHttpUrl, Field
from dotenv import load_dotenv


# --- Utilities ---------------------------------------------------------------

def utcnow_iso() -> datetime:
    return datetime.now(timezone.utc)

def make_hash(*parts: str) -> str:
    joined = "||".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()

def is_kospi_stock_code(code: str) -> bool:
    return code is not None and len(code) == 6 and code.isdigit()


# --- DART service -----------------------------------------------------------

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"

async def fetch_dart_list(api_key: str, bgn_de: str, end_de: str, page_no: int = 1, page_count: int = 100):
    params = {
        "crtfc_key": api_key,
        "corp_cls": "Y",
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_no": page_no,
        "page_count": page_count,
    }
    async with httpx.AsyncClient(timeout=15) as s:
        r = await s.get(DART_LIST_URL, params=params)
        r.raise_for_status()
        return r.json()

def normalize_dart_items(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = []
    for it in raw.get("list", []) or []:
        title = it.get("rpt_nm") or "무제"
        dt = it.get("rcept_dt")
        published = datetime.strptime(dt, "%Y%m%d").isoformat() + "Z" if dt else datetime.utcnow().isoformat() + "Z"
        url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it.get('rcp_no')}"
        symbol = it.get("stock_code")
        tags = []
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
            "symbol": symbol if symbol else None,
            "title": title,
            "url": url,
            "published_at": published,
            "tags": tags,
            "score": score,
            "_dedupe": make_hash("DART", title, url),
        })
    return items


# --- News service -----------------------------------------------------------

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
        try:
            published_at = datetime.strptime(it["pubDate"], "%a, %d %b %Y %H:%M:%S %z").astimezone(timezone.utc).isoformat()
        except Exception:
            published_at = datetime.utcnow().isoformat() + "Z"
        tags = []
        t = title
        if "단독" in t:
            tags.append("단독")
        if "속보" in t:
            tags.append("속보")
        if "공시" in t or "IR" in t:
            tags.append("공시/IR")
        score = 0.1
        if "속보" in t:
            score += 0.3
        if "단독" in t:
            score += 0.2
        items.append({
            "type": "NEWS",
            "symbol": None,
            "title": title,
            "url": link,
            "published_at": published_at,
            "tags": tags,
            "score": score,
            "_dedupe": make_hash("NEWS", title, link),
        })
    return items


# --- Models -----------------------------------------------------------------

ItemType = Literal["DART", "NEWS"]

class UpdateItem(BaseModel):
    type: ItemType
    symbol: Optional[str] = None
    title: str
    url: AnyHttpUrl
    published_at: datetime
    tags: List[str] = Field(default_factory=list)
    score: float = 0.0

class UpdatesResponse(BaseModel):
    items: List[UpdateItem]


# --- Application ------------------------------------------------------------

load_dotenv()
API_KEY = os.getenv("API_KEY")
DART_API_KEY = os.getenv("DART_API_KEY")
NAVER_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_SECRET = os.getenv("NAVER_CLIENT_SECRET")

app = FastAPI(title="Korea Market Updates API", version="1.0.0")

def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    if API_KEY is None or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/updates", response_model=UpdatesResponse)
async def get_updates(
    auth: bool = Depends(verify_api_key),
    since: str | None = Query(None, description="ISO8601 UTC"),
    symbols: str | None = Query(None, description="comma separated 6-digit codes"),
    limit: int = Query(50, ge=1, le=200),
    market: str = Query("KOSPI", pattern="^(KOSPI|KOSDAQ|KONEX|ALL)$")
):
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z","+00:00"))
        except Exception:
            raise HTTPException(400, detail="Invalid 'since' format. Use ISO8601.")
    else:
        since_dt = datetime.now(timezone.utc) - timedelta(hours=3)

    symbol_set: Set[str] = set()
    if symbols:
        symbol_set = {s.strip() for s in symbols.split(",") if s.strip()}

    items: List[UpdateItem] = []

    if not DART_API_KEY:
        raise HTTPException(500, detail="DART_API_KEY not set")
    bgn = since_dt.astimezone(timezone.utc).strftime("%Y%m%d")
    end = datetime.now(timezone.utc).strftime("%Y%m%d")
    page_no = 1
    seen_hash: Set[str] = set()

    while True:
        try:
            raw = await fetch_dart_list(DART_API_KEY, bgn, end, page_no=page_no)
        except Exception:
            break
        part = normalize_dart_items(raw)
        if not part:
            break
        for p in part:
            if p["_dedupe"] in seen_hash:
                continue
            seen_hash.add(p["_dedupe"])
            try:
                pub = datetime.fromisoformat(p["published_at"].replace("Z","+00:00"))
            except Exception:
                continue
            if pub < since_dt:
                continue
            if symbol_set and (p.get("symbol") not in symbol_set):
                continue
            items.append(UpdateItem(**{k: v for k, v in p.items() if k in UpdateItem.model_fields}))

        if len(part) < 100 or page_no >= 10:
            break
        page_no += 1

    if NAVER_ID and NAVER_SECRET:
        queries = [
            "공시 OR IR 코스피",
            "유상증자 OR 전환사채 코스피",
            "거래정지 OR 단독 OR 속보 코스피",
        ]
        for q in queries:
            try:
                rawn = await fetch_news(NAVER_ID, NAVER_SECRET, q, display=30, sort="date")
            except Exception:
                continue
            partn = normalize_news(rawn)
            for p in partn:
                if p["_dedupe"] in seen_hash:
                    continue
                seen_hash.add(p["_dedupe"])
                try:
                    pub = datetime.fromisoformat(p["published_at"].replace("Z","+00:00"))
                except Exception:
                    continue
                if pub < since_dt:
                    continue
                items.append(UpdateItem(**{k: v for k, v in p.items() if k in UpdateItem.model_fields}))

    items.sort(key=lambda x: (x.score, x.published_at), reverse=True)
    items = items[:limit]
    return {"items": items}

