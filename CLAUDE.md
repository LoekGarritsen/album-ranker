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
SPOTIFY_REDIRECT_URI=https://albums.garritsen.online/api/spotify/callback
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

## Production URL

https://albums.garritsen.online (proxied through Nginx Proxy Manager on helios)

## Deployment

Production runs on **hermes** (192.168.2.211) at `/docker/album-ranker/`.

### Deploy via Git (preferred)
```bash
ssh hermes "cd /docker/album-ranker && git pull && docker compose up -d --build"
```

### Git Setup on Hermes
- Deploy key: `~/.ssh/album-ranker-deploy` (read-only access to this repo)
- SSH config uses host alias `github.com-album-ranker` for this key
- Remote: `git@github.com-album-ranker:LoekGarritsen/album-ranker.git`

### Manual Deploy (if git unavailable)
```bash
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='__pycache__' --exclude='.env' --exclude='data' ./ hermes:/docker/album-ranker/
ssh hermes "cd /docker/album-ranker && docker compose up -d --build"
```

### Important Paths on Hermes
- App directory: `/docker/album-ranker/`
- Database: `/docker/album-ranker/data/albums.db`
- Environment: `/docker/album-ranker/.env` (not in git)
