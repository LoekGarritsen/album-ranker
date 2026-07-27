// E2E coverage for switching a room between listening (ranking) and hangout
// mode: switch pauses playback but loses nothing, hangout automation is
// mode-gated, and fresh sockets sync the current mode. API + WS level.
import { test, expect } from '@playwright/test'
import { mintUser, bearer, seedAlbum } from '../helpers/db.js'

const baseUrl = process.env.BASE_URL || 'http://localhost:8401'
const wsBase = baseUrl.replace(/^http/, 'ws')

const media = (n) => ({
  type: 'track',
  spotify_id: `e2e_mode_${n}`,
  name: `Mode Song ${n}`,
  artist: 'Mode Artist',
  image: null,
  duration_ms: 90000,
})

let host
let member
let album
let code

test.beforeAll(async ({ request }) => {
  host = mintUser('Mode Host')
  member = mintUser('Mode Member')
  album = seedAlbum({
    spotifyId: 'e2e_mode_album',
    name: 'Mode Album',
    artist: 'Mode Artist',
    tracks: [
      { name: 'Mode Track 1', duration_ms: 120000 },
      { name: 'Mode Track 2', duration_ms: 120000 },
    ],
  })
  const res = await request.post(`${baseUrl}/api/sessions`, {
    headers: bearer(host),
    data: { name: 'Mode E2E Room', is_public: true, mode: 'listening', album_id: album.id },
  })
  expect(res.ok()).toBeTruthy()
  code = (await res.json()).code
  await request.post(`${baseUrl}/api/sessions/${code}/join`, { headers: bearer(member) })
})

test.afterAll(async ({ request }) => {
  await request.delete(`${baseUrl}/api/sessions/${code}`, { headers: bearer(host) })
})

test('only the creator or an admin can switch modes', async ({ request }) => {
  const denied = await request.post(`${baseUrl}/api/sessions/${code}/mode?mode=hangout`, {
    headers: bearer(member),
  })
  expect(denied.status()).toBe(403)
})

test('switching to hangout pauses playback and keeps the track', async ({ page, request }) => {
  // Start ranking playback and let the room clock run a moment
  const play = await request.post(
    `${baseUrl}/api/sessions/${code}/track?track_id=${album.trackIds[0]}&play=true`,
    { headers: bearer(host) },
  )
  expect(play.ok()).toBeTruthy()
  await page.waitForTimeout(400)

  // Watch the broadcasts a connected client receives during the switch
  await page.goto(baseUrl)
  const broadcasts = page.evaluate(({ url }) => {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url)
      const received = []
      const timeout = setTimeout(() => { ws.close(); resolve(received) }, 8000)
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        received.push(data)
        if (data.type === 'mode_change') {
          clearTimeout(timeout)
          ws.close()
          resolve(received)
        }
      }
      ws.onerror = () => reject(new Error('WS error'))
    })
  }, { url: `${wsBase}/api/sessions/${code}/ws?token=${member.token}` })

  // Give the socket time to land before switching
  await page.waitForTimeout(500)
  const res = await request.post(`${baseUrl}/api/sessions/${code}/mode?mode=hangout`, {
    headers: bearer(host),
  })
  expect(res.ok()).toBeTruthy()
  expect((await res.json()).mode).toBe('hangout')

  const messages = await broadcasts
  // Pause lands before the mode change so clients stop Spotify first
  const pauseIdx = messages.findIndex(m => m.type === 'playback' && m.action === 'pause')
  const modeIdx = messages.findIndex(m => m.type === 'mode_change' && m.mode === 'hangout')
  expect(pauseIdx).toBeGreaterThan(-1)
  expect(modeIdx).toBeGreaterThan(pauseIdx)

  // Nothing lost: paused, position kept, track kept
  const details = await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()
  expect(details.mode).toBe('hangout')
  expect(details.playback.is_playing).toBe(false)
  expect(details.playback.position).toBeGreaterThan(0)
  expect(details.current_track_id).toBe(album.trackIds[0])
})

test('fresh sockets sync the current mode', async ({ page }) => {
  await page.goto(baseUrl)
  const sync = await page.evaluate(({ url }) => {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url)
      const timeout = setTimeout(() => { ws.close(); reject(new Error('no sync')) }, 8000)
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.type === 'sync') {
          clearTimeout(timeout)
          ws.close()
          resolve(data)
        }
      }
      ws.onerror = () => reject(new Error('WS error'))
    })
  }, { url: `${wsBase}/api/sessions/${code}/ws?token=${member.token}` })

  expect(sync.mode).toBe('hangout')
  expect(sync.album_id).toBe(album.id)
})

test('hangout media and queue work after the switch', async ({ request }) => {
  const set = await request.post(`${baseUrl}/api/sessions/${code}/media`, {
    headers: bearer(host),
    data: media(1),
  })
  expect(set.ok()).toBeTruthy()

  const add = await request.post(`${baseUrl}/api/sessions/${code}/queue`, {
    headers: bearer(member),
    data: media(2),
  })
  expect((await add.json()).started).toBe(false)

  const details = await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()
  expect(details.media?.spotify_id).toBe('e2e_mode_1')
  expect(details.queue).toHaveLength(1)
})

test('switching back to listening disables hangout automation but loses nothing', async ({ request }) => {
  const res = await request.post(`${baseUrl}/api/sessions/${code}/mode?mode=listening`, {
    headers: bearer(host),
  })
  expect(res.ok()).toBeTruthy()

  // Hangout endpoints are gated now
  const setMedia = await request.post(`${baseUrl}/api/sessions/${code}/media`, {
    headers: bearer(host),
    data: media(9),
  })
  expect(setMedia.status()).toBe(409)

  const seq = (await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()).media_seq
  const adv = await request.post(`${baseUrl}/api/sessions/${code}/queue/next?seq=${seq}`, {
    headers: bearer(host),
  })
  expect((await adv.json()).advanced).toBe(false)

  // Now-playing, queue, album, and track all survive the round trip
  const details = await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()
  expect(details.mode).toBe('listening')
  expect(details.media?.spotify_id).toBe('e2e_mode_1')
  expect(details.queue).toHaveLength(1)
  expect(details.album_id).toBe(album.id)
  expect(details.current_track_id).toBe(album.trackIds[0])
})

test('switching back to hangout re-enables the queue with everything intact', async ({ request }) => {
  await request.post(`${baseUrl}/api/sessions/${code}/mode?mode=hangout`, {
    headers: bearer(host),
  })
  const seq = (await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()).media_seq
  const adv = await request.post(`${baseUrl}/api/sessions/${code}/queue/next?seq=${seq}`, {
    headers: bearer(host),
  })
  expect((await adv.json()).advanced).toBe(true)

  const details = await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()
  expect(details.media?.spotify_id).toBe('e2e_mode_2')
  expect(details.queue).toHaveLength(0)
})

test('queue add in a listening room never auto-starts playback', async ({ request }) => {
  const res = await request.post(`${baseUrl}/api/sessions`, {
    headers: bearer(host),
    data: { name: 'Mode Listening Room', is_public: true, mode: 'listening' },
  })
  const listeningCode = (await res.json()).code

  const add = await request.post(`${baseUrl}/api/sessions/${listeningCode}/queue`, {
    headers: bearer(host),
    data: media(5),
  })
  const body = await add.json()
  expect(body.started).toBe(false)
  expect(body.queue).toHaveLength(1)

  const details = await (await request.get(`${baseUrl}/api/sessions/${listeningCode}`)).json()
  expect(details.media).toBeNull()

  await request.delete(`${baseUrl}/api/sessions/${listeningCode}`, { headers: bearer(host) })
})
