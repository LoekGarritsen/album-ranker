"""
Album Ranker API - Main application entry point.

This module configures the FastAPI application and includes all routers.
Route implementations are organized in the routers/ package.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from database import init_db
from routers import users, spotify_routes, albums, rankings, analytics, sessions

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    yield


app = FastAPI(title="Album Ranker API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8401",
        "http://127.0.0.1:8401",
        "https://albums.garritsen.online",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(users.router)
app.include_router(spotify_routes.router)
app.include_router(albums.router)
app.include_router(rankings.router)
app.include_router(analytics.router)
app.include_router(sessions.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8400)
