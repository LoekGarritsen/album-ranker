"""
Album Ranker API - Main application entry point.

This module configures the FastAPI application and includes all routers.
Route implementations are organized in the routers/ package.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

load_dotenv()

import config
from database import init_db
from ratelimit import limiter
from auth_deps import get_current_user
from fastapi import Depends
from routers import auth, users, spotify_routes, albums, rankings, analytics, sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    yield


app = FastAPI(title="Album Ranker API", lifespan=lifespan)

# Rate limiting (slowapi)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers. Auth endpoints are public; Spotify (OAuth callback) and
# sessions (WebSocket + per-route auth) manage their own access. The remaining
# data routers are gated behind a valid session token.
_auth = [Depends(get_current_user)]
app.include_router(auth.router)
app.include_router(spotify_routes.router)
app.include_router(sessions.router)
app.include_router(users.router, dependencies=_auth)
app.include_router(albums.router, dependencies=_auth)
app.include_router(rankings.router, dependencies=_auth)
app.include_router(analytics.router, dependencies=_auth)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8400)
