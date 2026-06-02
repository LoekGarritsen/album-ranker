# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Album Ranker is a collaborative music rating application with real-time listening sessions. Users can search albums via Spotify, rate albums/tracks (1-10 scale), compare ratings across users, and listen together in synchronized WebSocket-based sessions.

## Architecture

```
Frontend (Vue 3 + Vite)     Backend (FastAPI + SQLite)
      :8401                        :8400
         │                            │
         └──── Docker Compose ────────┘
                    │
              SQLite (./data/)
```

- **Backend**: FastAPI with SQLite, handles Spotify OAuth and WebSocket sessions
- **Frontend**: Vue 3 Composition API with Tailwind CSS, served by Nginx in production
- **Real-time**: WebSocket at `/api/sessions/{code}/ws` for synchronized playback

## Development Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8400 --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # Vite dev server with /api proxy to :8400
npm run build    # Production build to dist/
```

### Docker (Production)
```bash
docker-compose up --build
# Frontend: http://localhost:8401
# Backend: http://localhost:8400
```

## Required Environment Variables

Create `.env` in backend directory:
```
SPOTIFY_CLIENT_ID=<client_id>
SPOTIFY_CLIENT_SECRET=<client_secret>
SPOTIFY_REDIRECT_URI=https://albums.garritsen.dev/api/spotify/callback
```

## Key Files

| File | Purpose |
|------|---------|
| `backend/main.py` | All API endpoints (38+), WebSocket handling |
| `backend/database.py` | SQLite schema, connection management |
| `backend/spotify.py` | Spotify API client, OAuth flow |
| `backend/models.py` | Pydantic request/response models |
| `frontend/src/composables/useSession.js` | Session state, WebSocket logic |
| `frontend/src/composables/useSpotifyPlayer.js` | Spotify Web Playback SDK |

## API Patterns

- User identification via `X-User-Id` header
- Admin actions require PIN verification (4-digit)
- WebSocket broadcasts rating updates to session participants
- Spotify tokens auto-refresh with 5-minute buffer before expiry

## Database

SQLite with tables: `users`, `albums`, `tracks`, `album_rankings`, `track_rankings`, `listening_sessions`, `session_participants`, `spotify_tokens`

Foreign keys are enabled. Use `get_db_connection()` context manager for transactions.

## Frontend State

Vue composables provide singleton state:
- `useSession()` - Session membership, WebSocket connection, playback sync
- `useSpotifyPlayer()` - Spotify SDK instance, playback controls

## Deployment

Built and run via Docker Compose (`docker compose up -d --build`). The backend
reads `backend/.env` (git-ignored) for Spotify credentials; SQLite lives in
`./data/`.
