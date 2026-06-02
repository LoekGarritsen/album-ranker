# 🎵 Album Ranker

Collaborative music rating app with **real-time listening sessions**. Search albums via Spotify, rate albums and individual tracks on a 1–10 scale, compare ratings across friends, and listen together in WebSocket-synced sessions.

![Vue](https://img.shields.io/badge/Vue_3-4FC08D?style=flat-square&logo=vuedotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![Spotify](https://img.shields.io/badge/Spotify_API-1DB954?style=flat-square&logo=spotify&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)

## Features

- 🔍 **Spotify search** — find any album via the Spotify Web API
- ⭐ **Granular ratings** — score whole albums *and* individual tracks (1–10)
- 👥 **Compare** — see how your ratings stack up against other users
- 🎧 **Listen together** — synchronized playback in shared rooms over WebSocket
- 🔒 **Rooms** — public or password-protected, with admin PIN controls

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Vue 3 (Composition API) + Vite + Tailwind CSS |
| Backend | FastAPI + SQLite |
| Real-time | WebSocket (`/api/sessions/{code}/ws`) |
| Auth | Spotify OAuth (auto-refreshing tokens) |
| Deploy | Docker Compose + Nginx |

```
Frontend (Vue 3 + Vite)  ──┐
      :8401                │  Docker Compose
Backend (FastAPI + SQLite) ┘
      :8400  ──→  SQLite (./data/)
```

## Quick start

```bash
# 1. Spotify credentials — https://developer.spotify.com/dashboard
cp .env.example backend/.env   # then fill in client id/secret

# 2. Run it
docker compose up --build
#  Frontend → http://localhost:8401
#  Backend  → http://localhost:8400
```

### Local dev (without Docker)

```bash
# backend
cd backend && pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8400 --reload

# frontend
cd frontend && npm install && npm run dev
```

## Configuration

| Variable | Description |
|----------|-------------|
| `SPOTIFY_CLIENT_ID` | From the Spotify Developer Dashboard |
| `SPOTIFY_CLIENT_SECRET` | From the Spotify Developer Dashboard |
| `SPOTIFY_REDIRECT_URI` | Must match the redirect configured in your Spotify app |

## License

[MIT](LICENSE) © Loek Garritsen
