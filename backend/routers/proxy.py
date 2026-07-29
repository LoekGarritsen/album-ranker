"""
Image proxy for Spotify cover art, so canvas-based recap cards can draw
covers without CORS taint. Restricted to Spotify image hosts.
"""
import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter(prefix="/api", tags=["proxy"])

ALLOWED_PREFIXES = (
    "https://i.scdn.co/",
    "https://mosaic.scdn.co/",
    "https://image-cdn-ak.spotifycdn.com/",
    "https://image-cdn-fa.spotifycdn.com/",
)


@router.get("/image-proxy")
async def image_proxy(url: str = Query(..., max_length=500)):
    if not url.startswith(ALLOWED_PREFIXES):
        raise HTTPException(400, "Only Spotify image URLs are allowed")
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError:
            raise HTTPException(502, "Failed to fetch image")
    content_type = resp.headers.get("content-type", "image/jpeg")
    if not content_type.startswith("image/"):
        raise HTTPException(502, "Upstream did not return an image")
    return Response(
        content=resp.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
