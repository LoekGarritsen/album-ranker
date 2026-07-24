"""
GIF search proxy (Giphy). Keeps the API key server-side; clients only ever
see media URLs. Auth is applied at include_router time in main.py.
"""
import httpx
from fastapi import APIRouter, HTTPException, Query, Request

import config
from ratelimit import limiter

router = APIRouter(prefix="/api/gifs", tags=["gifs"])

GIPHY_BASE = "https://api.giphy.com/v1/gifs"


def _slim(gif: dict) -> dict:
    """Reduce a Giphy result to what the chat UI needs."""
    images = gif.get("images", {})
    preview = images.get("fixed_width", {}) or images.get("original", {})
    full = images.get("original", {}) or preview
    return {
        "id": gif.get("id"),
        "title": gif.get("title", ""),
        "preview": preview.get("url"),
        "url": full.get("url"),
        "width": int(preview.get("width") or 0),
        "height": int(preview.get("height") or 0),
    }


@router.get("/search")
@limiter.limit("30/minute")
async def search_gifs(
    request: Request,
    q: str = Query("", max_length=100),
    limit: int = Query(24, ge=1, le=50),
):
    """Search Giphy; empty query returns trending."""
    if not config.GIPHY_API_KEY:
        raise HTTPException(503, "GIF search not configured")

    q = q.strip()
    endpoint = f"{GIPHY_BASE}/search" if q else f"{GIPHY_BASE}/trending"
    params = {"api_key": config.GIPHY_API_KEY, "limit": limit, "rating": "pg-13"}
    if q:
        params["q"] = q

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(endpoint, params=params)
    except httpx.HTTPError:
        raise HTTPException(502, "GIF search unavailable")
    if res.status_code != 200:
        raise HTTPException(502, "GIF search unavailable")

    data = res.json().get("data", [])
    gifs = [g for g in (_slim(gif) for gif in data) if g["url"] and g["preview"]]
    return {"gifs": gifs}
