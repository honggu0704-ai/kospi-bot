import os
from datetime import datetime, timedelta, timezone
from typing import List, Set
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from dotenv import load_dotenv
from models import UpdatesResponse, UpdateItem
from services.dart import fetch_dart_list, normalize_dart_items
from services.news import fetch_news, normalize_news

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
    # 시간 범위 기본값: 최근 3시간
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z","+00:00"))
        except Exception:
            raise HTTPException(400, detail="Invalid 'since' format. Use ISO8601.")
    else:
        since_dt = datetime.now(timezone.utc) - timedelta(hours=3)

    # 심볼 필터(옵션)
    symbol_set: Set[str] = set()
    if symbols:
        symbol_set = {s.strip() for s in symbols.split(",") if s.strip()}

    items: List[UpdateItem] = []

    # --- DART ---
    if not DART_API_KEY:
        raise HTTPException(500, detail="DART_API_KEY not set")
    bgn = since_dt.astimezone(timezone.utc).strftime("%Y%m%d")
    end = datetime.now(timezone.utc).strftime("%Y%m%d")
    page_no = 1
    seen_hash: Set[str] = set()

    while True:
        try:
            raw = await fetch_dart_list(DART_API_KEY, bgn, end, page_no=page_no)
        except Exception as e:
            break
        part = normalize_dart_items(raw)
        if not part:
            break
        for p in part:
            if p["_dedupe"] in seen_hash:
                continue
            seen_hash.add(p["_dedupe"])

            # 날짜 필터
            try:
                pub = datetime.fromisoformat(p["published_at"].replace("Z","+00:00"))
            except Exception:
                continue
            if pub < since_dt:
                continue

            # 심볼 필터
            if symbol_set and (p.get("symbol") not in symbol_set):
                continue

            items.append(UpdateItem(**{k: v for k, v in p.items() if k in UpdateItem.model_fields}))

        if len(part) < 100 or page_no >= 10:
            break
        page_no += 1

    # --- NEWS ---
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

    # 정렬: 점수->시간 역순
    items.sort(key=lambda x: (x.score, x.published_at), reverse=True)
    items = items[:limit]
    return {"items": items}
