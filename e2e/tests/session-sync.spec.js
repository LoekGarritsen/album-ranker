// E2E test for real-time session sync. Auth is magic-link, so helpers/db.js
// mints Bearer session tokens directly in the backend container's SQLite.
import { test, expect } from '@playwright/test'
import { mintUser, seedAlbum, bearer } from '../helpers/db.js'

const baseUrl = process.env.BASE_URL || 'http://localhost:8401'
const wsBase = baseUrl.replace(/^http/, 'ws')

let userA // room creator
let userB // second participant
let album // seeded album with 3 tracks

test.beforeAll(async () => {
  userA = mintUser('E2E User A')
  userB = mintUser('E2E User B')
  album = seedAlbum({
    spotifyId: 'e2e_test_album_001',
    name: 'E2E Test Album',
    artist: 'Test Artist',
    tracks: [
      { name: 'Test Track 1', duration_ms: 180000 },
      { name: 'Test Track 2', duration_ms: 200000 },
      { name: 'Test Track 3', duration_ms: 220000 },
    ],
  })
})

// Open a WS in the page and resolve with the first message matching `matcher`
function waitForWsMessage(page, { url, matcher, timeoutMs = 10000 }) {
  return page.evaluate(({ url, matcherSrc, timeoutMs }) => {
    const matches = new Function(`return (${matcherSrc})`)()
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url)
      const timeout = setTimeout(() => {
        ws.close()
        reject(new Error('Timeout waiting for WS message'))
      }, timeoutMs)
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (matches(data)) {
          clearTimeout(timeout)
          ws.close()
          resolve(data)
        }
      }
      ws.onerror = () => {
        clearTimeout(timeout)
        reject(new Error('WS error'))
      }
    })
  }, { url, matcherSrc: matcher.toString(), timeoutMs })
}

test.describe('Session Real-time Sync', () => {
  let sessionCode

  test('User A can create a session and User B can join', async ({ request }) => {
    const createRes = await request.post(`${baseUrl}/api/sessions`, {
      headers: bearer(userA),
      data: { name: 'E2E Test Session', is_public: true },
    })
    expect(createRes.ok()).toBeTruthy()
    sessionCode = (await createRes.json()).code
    expect(sessionCode).toHaveLength(6)

    const joinRes = await request.post(`${baseUrl}/api/sessions/${sessionCode}/join`, {
      headers: bearer(userB),
    })
    expect(joinRes.ok()).toBeTruthy()

    const session = await (await request.get(`${baseUrl}/api/sessions/${sessionCode}`)).json()
    const participantNames = session.participants.map(p => p.name)
    expect(participantNames).toContain('E2E User A')
    expect(participantNames).toContain('E2E User B')
  })

  test('WebSocket sync works for authed users and guests', async ({ page }) => {
    test.skip(!sessionCode, 'Session not created')
    await page.goto(baseUrl)

    // Authed connection (token in query string) receives the initial sync
    const syncMsg = await waitForWsMessage(page, {
      url: `${wsBase}/api/sessions/${sessionCode}/ws?token=${userA.token}`,
      matcher: (d) => d.type === 'sync',
    })
    expect(syncMsg.is_playing).toBe(false)
    expect(Array.isArray(syncMsg.queue)).toBe(true)

    // Anonymous guest can still connect and gets the same sync
    const guestSync = await waitForWsMessage(page, {
      url: `${wsBase}/api/sessions/${sessionCode}/ws`,
      matcher: (d) => d.type === 'sync',
    })
    expect(guestSync.type).toBe('sync')
  })

  test('Rating broadcast works between users', async ({ page, request }) => {
    test.skip(!sessionCode, 'Session not created')

    const setAlbumRes = await request.post(
      `${baseUrl}/api/sessions/${sessionCode}/album?album_id=${album.id}`,
      { headers: bearer(userA) },
    )
    expect(setAlbumRes.ok()).toBeTruthy()
    const trackId = album.trackIds[0]

    await page.goto(baseUrl)
    const ratingReceived = waitForWsMessage(page, {
      url: `${wsBase}/api/sessions/${sessionCode}/ws?token=${userB.token}`,
      matcher: (d) => d.type === 'rating',
    })
    await page.waitForTimeout(500) // let the WS connect before rating

    const ratingRes = await request.post(
      `${baseUrl}/api/rankings/track?session_code=${sessionCode}`,
      {
        headers: bearer(userA),
        data: { track_id: trackId, score: 8.5, comment: 'E2E test rating' },
      },
    )
    expect(ratingRes.ok()).toBeTruthy()

    const received = await ratingReceived
    expect(received.track_id).toBe(trackId)
    expect(received.user_id).toBe(userA.id)
    expect(received.score).toBe(8.5)
  })

  test('Chat message persists and is broadcast', async ({ page, request }) => {
    test.skip(!sessionCode, 'Session not created')
    await page.goto(baseUrl)

    // Send a chat message over an authed WS and await its own broadcast echo
    const echoed = await page.evaluate(({ url, text }) => {
      return new Promise((resolve, reject) => {
        const ws = new WebSocket(url)
        const timeout = setTimeout(() => reject(new Error('chat timeout')), 10000)
        ws.onmessage = (event) => {
          const data = JSON.parse(event.data)
          if (data.type === 'sync') {
            ws.send(JSON.stringify({ type: 'chat', content: text, client_id: 'e2e-1' }))
          } else if (data.type === 'chat_message' && data.content === text) {
            clearTimeout(timeout)
            ws.close()
            resolve(data)
          }
        }
        ws.onerror = () => reject(new Error('WS error'))
      })
    }, { url: `${wsBase}/api/sessions/${sessionCode}/ws?token=${userA.token}`, text: 'hello from e2e' })

    expect(echoed.user_id).toBe(userA.id)
    expect(echoed.kind).toBe('text')

    // Persisted and readable through history
    const history = await (await request.get(`${baseUrl}/api/sessions/${sessionCode}/messages`)).json()
    expect(history.messages.some(m => m.content === 'hello from e2e')).toBe(true)
  })

  test('Session cleanup works', async ({ request }) => {
    test.skip(!sessionCode, 'Session not created')

    const deleteRes = await request.delete(`${baseUrl}/api/sessions/${sessionCode}`, {
      headers: bearer(userA),
    })
    expect(deleteRes.ok()).toBeTruthy()

    const getRes = await request.get(`${baseUrl}/api/sessions/${sessionCode}`)
    expect(getRes.status()).toBe(404)
  })
})

test.describe('Session with Album', () => {
  test('Full flow: create session, set album, change tracks', async ({ request }) => {
    const user = mintUser('Flow Test User')

    const sessionRes = await request.post(`${baseUrl}/api/sessions`, {
      headers: bearer(user),
      data: { name: 'Album Flow Test', album_id: album.id, is_public: true },
    })
    expect(sessionRes.ok()).toBeTruthy()
    const session = await sessionRes.json()

    const details = await (await request.get(`${baseUrl}/api/sessions/${session.code}`)).json()
    expect(details.album_id).toBe(album.id)
    expect(details.current_track_id).toBe(album.trackIds[0])

    const trackRes = await request.post(
      `${baseUrl}/api/sessions/${session.code}/track?track_id=${album.trackIds[1]}`,
      { headers: bearer(user) },
    )
    expect(trackRes.ok()).toBeTruthy()

    const updated = await (await request.get(`${baseUrl}/api/sessions/${session.code}`)).json()
    expect(updated.current_track_id).toBe(album.trackIds[1])

    await request.delete(`${baseUrl}/api/sessions/${session.code}`, { headers: bearer(user) })
  })
})

test.describe('Playback Controls', () => {
  test('Play/pause/seek sync across session', async ({ request }) => {
    const user = mintUser('Playback Test User')

    const sessionRes = await request.post(`${baseUrl}/api/sessions`, {
      headers: bearer(user),
      data: { name: 'Playback Test', is_public: true },
    })
    const session = await sessionRes.json()

    const playRes = await request.post(
      `${baseUrl}/api/sessions/${session.code}/playback?action=play`,
      { headers: bearer(user) },
    )
    expect(playRes.ok()).toBeTruthy()

    let details = await (await request.get(`${baseUrl}/api/sessions/${session.code}`)).json()
    expect(details.playback.is_playing).toBe(true)

    const pauseRes = await request.post(
      `${baseUrl}/api/sessions/${session.code}/playback?action=pause`,
      { headers: bearer(user) },
    )
    expect(pauseRes.ok()).toBeTruthy()

    details = await (await request.get(`${baseUrl}/api/sessions/${session.code}`)).json()
    expect(details.playback.is_playing).toBe(false)

    const seekRes = await request.post(
      `${baseUrl}/api/sessions/${session.code}/playback?action=seek&position=30000`,
      { headers: bearer(user) },
    )
    expect(seekRes.ok()).toBeTruthy()

    details = await (await request.get(`${baseUrl}/api/sessions/${session.code}`)).json()
    expect(details.playback.position).toBeGreaterThanOrEqual(30000)

    await request.delete(`${baseUrl}/api/sessions/${session.code}`, { headers: bearer(user) })
  })
})
