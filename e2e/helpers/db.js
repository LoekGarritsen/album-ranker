// E2E DB helpers. Magic-link auth can't be clicked from E2E, so we mint users
// and session tokens directly in the container's SQLite — same rows the real
// flow creates, no auth backdoor in application code.
import { execSync } from 'child_process'

const CONTAINER = process.env.E2E_BACKEND_CONTAINER || 'album-ranker-e2e-backend'

function pyExec(script) {
  const out = execSync(`docker exec -i ${CONTAINER} python -c "import sys; exec(sys.stdin.read())"`, {
    input: script,
    encoding: 'utf8',
  })
  return out.trim()
}

/**
 * Create (or reuse) a user and mint a valid Bearer session token for it.
 * Returns { id, name, token }.
 */
export function mintUser(name, { admin = false } = {}) {
  const out = pyExec(`
import sqlite3, secrets, hashlib
from datetime import datetime, timedelta
conn = sqlite3.connect('/app/data/album_ranker.db')
conn.execute('PRAGMA foreign_keys = ON')
name = ${JSON.stringify(name)}
email = name.lower().replace(' ', '.') + '@e2e.test'
row = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
if row:
    uid = row[0]
else:
    uid = conn.execute(
        'INSERT INTO users (name, email, is_admin) VALUES (?, ?, ?)',
        (name, email, ${admin ? 1 : 0}),
    ).lastrowid
raw = secrets.token_urlsafe(32)
th = hashlib.sha256(raw.encode()).hexdigest()
exp = (datetime.utcnow() + timedelta(days=1)).isoformat()
conn.execute('INSERT INTO auth_sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)', (uid, th, exp))
conn.commit()
print(f'{uid}|{raw}')
`)
  const [id, token] = out.split('|')
  return { id: Number(id), name, token }
}

// Seed an album with tracks (Spotify is stubbed in E2E, so the API can't add
// albums). Idempotent per spotify_id. Returns { id, trackIds }.
export function seedAlbum({ spotifyId, name, artist, tracks }) {
  const out = pyExec(`
import sqlite3, json
conn = sqlite3.connect('/app/data/album_ranker.db')
conn.execute('PRAGMA foreign_keys = ON')
sid = ${JSON.stringify(spotifyId)}
row = conn.execute('SELECT id FROM albums WHERE spotify_id = ?', (sid,)).fetchone()
if row:
    aid = row[0]
else:
    aid = conn.execute(
        'INSERT INTO albums (spotify_id, name, artist, cover_url) VALUES (?, ?, ?, ?)',
        (sid, ${JSON.stringify(name)}, ${JSON.stringify(artist)}, 'https://via.placeholder.com/300'),
    ).lastrowid
    for i, t in enumerate(json.loads(${JSON.stringify(JSON.stringify(tracks))})):
        conn.execute(
            'INSERT INTO tracks (album_id, spotify_id, name, artist, disc_number, track_number, duration_ms) VALUES (?, ?, ?, ?, 1, ?, ?)',
            (aid, f'{sid}_t{i+1}', t['name'], ${JSON.stringify(artist)}, i + 1, t['duration_ms']),
        )
conn.commit()
ids = [r[0] for r in conn.execute('SELECT id FROM tracks WHERE album_id = ? ORDER BY track_number', (aid,))]
print(json.dumps({'id': aid, 'trackIds': ids}))
`)
  return JSON.parse(out)
}

export function bearer(user) {
  return { Authorization: `Bearer ${user.token}` }
}
