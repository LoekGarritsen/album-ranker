# Album Ranker E2E Tests

End-to-end tests using Playwright to verify real-time session synchronization.

## Test Scenarios

1. **Session Creation & Joining**
   - User A creates a session
   - User B joins the session
   - Both users appear as participants

2. **WebSocket Sync**
   - Both users can connect via WebSocket
   - Messages are received in real-time

3. **Rating Broadcast**
   - User A rates a track
   - User B receives the rating update via WebSocket

4. **Session Lifecycle**
   - Full flow: create, set album, change tracks
   - Playback controls: play, pause, seek
   - Session cleanup

## Prerequisites

- Docker and Docker Compose
- Node.js 18+

## Setup

```bash
# From the e2e directory
cd e2e
npm install
npx playwright install chromium
```

## Running Tests

### Option 1: Automatic (Playwright manages containers)

```bash
npm test
```

This will:
1. Start Docker containers via `docker-compose.e2e.yml`
2. Wait for services to be healthy
3. Run all tests
4. Leave containers running for debugging

### Option 2: Manual container management

```bash
# Terminal 1: Start containers
cd /path/to/album-ranker
docker-compose -f docker-compose.e2e.yml up --build

# Terminal 2: Run tests
cd e2e
SKIP_WEBSERVER=true npm test
```

### Option 3: Against existing deployment

```bash
BASE_URL=https://albums.garritsen.online SKIP_WEBSERVER=true npm test
```

## Test Options

```bash
# Run in headed mode (see browser)
npm run test:headed

# Debug mode (step through tests)
npm run test:debug

# Interactive UI mode
npm run test:ui
```

## Cleanup

```bash
# Stop and remove containers
docker-compose -f docker-compose.e2e.yml down -v
```

## Test Structure

```
e2e/
├── package.json          # Dependencies
├── playwright.config.js  # Playwright configuration
├── README.md            # This file
└── tests/
    └── session-sync.spec.js  # Main test file
```

## Notes

- Tests use a fresh database (ephemeral volume)
- Spotify integration is disabled (dummy credentials)
- Tests create their own users and sessions
- Album-dependent tests may be skipped if no albums exist
- WebSocket tests use two browser contexts to simulate multiple users

## Troubleshooting

**Tests timeout waiting for services:**
```bash
# Check container health
docker-compose -f docker-compose.e2e.yml ps
docker-compose -f docker-compose.e2e.yml logs backend
```

**WebSocket connection fails:**
- Ensure nginx is properly proxying WebSocket connections
- Check that port 8401 is accessible

**No albums available:**
- The E2E environment doesn't have real Spotify integration
- Pre-seed albums manually or skip album-dependent tests
