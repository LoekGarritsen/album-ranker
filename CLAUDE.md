# CLAUDE.md

Album Ranker: collaborative music rating app with real-time listening sessions. Users search
albums via Spotify, rate albums/tracks (1-10), compare ratings, run club rounds and lists,
and listen together in synchronized WebSocket sessions. **This repo is public**: never
commit secrets, emails, or `.env` contents.

## Architecture

```
Frontend (Vue 3 + Vite, Nginx in prod)   Backend (FastAPI + SQLite)
  container :8401 -> host :8201            container :8400 -> host :8200
                    └──── compose.yaml ────┘   SQLite in ./data/
```

- **Backend**: `backend/main.py` wires the app; endpoints live in `backend/routers/*.py`
  (sessions, club, lists, rankings, spotify_routes, auth, ...). Schema + migrations in
  `backend/database.py` (`get_connection()` context manager, foreign keys on).
- **Frontend**: Vue 3 Composition API + Tailwind. Singleton state in
  `frontend/src/composables/` (`useAuth`, `useSession` = WebSocket + playback sync,
  `useSpotifyPlayer` = Web Playback SDK).
- **Real-time**: WebSocket at `/api/sessions/{code}/ws`.

## Auth

Magic-link login via Resend (`backend/email_service.py`; with `RESEND_API_KEY` unset the
link is logged instead of mailed). Sign-up is limited to `ALLOWED_EMAILS`. Identity comes
from an opaque session token sent as `Authorization: Bearer <token>`, stored hashed in
`auth_sessions` (`backend/auth_deps.py`); admin routes use `require_admin` (`users.is_admin`).
Never trust a client-supplied user id. Spotify tokens auto-refresh 5 minutes before expiry.

## Commands

```bash
# Backend (http://localhost:8400)
cd backend && pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8400 --reload
cd backend && pytest                 # tests/ (pytest-asyncio, auto mode)

# Frontend (Vite dev server proxies /api to :8400)
cd frontend && npm install && npm run dev
cd frontend && npm run test:run      # vitest
npm run build                        # production build to dist/

# Full stack in Docker (frontend :8201, backend :8200)
docker compose up -d --build

# E2E (Playwright, ephemeral data, dummy Spotify creds)
docker compose -f docker-compose.e2e.yml up --build -d
cd e2e && npm test
docker compose -f docker-compose.e2e.yml down -v
```

## Environment

`compose.yaml` reads `.env` in the **repo root** (git-ignored; template `.env.example`):
`SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`
(`https://albums.garritsen.dev/api/spotify/callback`), `FRONTEND_URL`, `RESEND_API_KEY`,
`ALLOWED_EMAILS`, optional `GIPHY_API_KEY` (chat GIF search returns 503 without it).
`BACKEND_PORT`/`FRONTEND_PORT` override the 8200/8201 host ports.

## Deployment

Live at `https://albums.garritsen.dev` (NPM proxies to hermes). hermes
`/docker/album-ranker` is a git checkout of this repo with its own `.env`; there is no CI.
Deploy manually after pushing: `ssh hermes`, then in `/docker/album-ranker` run
`git pull && docker compose up -d --build`. SQLite lives in `/docker/album-ranker/data/`.
