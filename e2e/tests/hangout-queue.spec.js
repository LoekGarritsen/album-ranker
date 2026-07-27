// E2E coverage for hangout rooms: shared queue, vote reordering, seq-guarded
// advance, and GIF chat validation. API-level against the docker stack.
import { test, expect } from '@playwright/test'
import { mintUser, bearer } from '../helpers/db.js'

const baseUrl = process.env.BASE_URL || 'http://localhost:8401'
const wsBase = baseUrl.replace(/^http/, 'ws')

const media = (n) => ({
  type: 'track',
  spotify_id: `e2e_q_${n}`,
  name: `Queue Song ${n}`,
  artist: 'Queue Artist',
  image: null,
  duration_ms: 90000,
})

let host
let guest2
let code

test.beforeAll(async ({ request }) => {
  host = mintUser('Queue Host')
  guest2 = mintUser('Queue Friend')
  const res = await request.post(`${baseUrl}/api/sessions`, {
    headers: bearer(host),
    data: { name: 'Queue E2E Room', is_public: true, mode: 'hangout' },
  })
  expect(res.ok()).toBeTruthy()
  code = (await res.json()).code
  await request.post(`${baseUrl}/api/sessions/${code}/join`, { headers: bearer(guest2) })
})

test.afterAll(async ({ request }) => {
  await request.delete(`${baseUrl}/api/sessions/${code}`, { headers: bearer(host) })
})

test('first add starts playing instead of queueing', async ({ request }) => {
  const res = await request.post(`${baseUrl}/api/sessions/${code}/queue`, {
    headers: bearer(host),
    data: media(1),
  })
  expect(res.ok()).toBeTruthy()
  const body = await res.json()
  expect(body.started).toBe(true)
  expect(body.queue).toHaveLength(0)

  const details = await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()
  expect(details.media?.spotify_id).toBe('e2e_q_1')
})

test('subsequent adds queue up FIFO and are visible to everyone', async ({ request }) => {
  for (const n of [2, 3]) {
    const res = await request.post(`${baseUrl}/api/sessions/${code}/queue`, {
      headers: bearer(n === 2 ? host : guest2),
      data: media(n),
    })
    expect((await res.json()).started).toBe(false)
  }
  const q = (await (await request.get(`${baseUrl}/api/sessions/${code}/queue`)).json()).queue
  expect(q.map(i => i.spotify_id)).toEqual(['e2e_q_2', 'e2e_q_3'])
  expect(q[1].added_by_name).toBe('Queue Friend')
})

test('votes reorder the queue and advance pops the top-voted item', async ({ request }) => {
  const q = (await (await request.get(`${baseUrl}/api/sessions/${code}/queue`)).json()).queue
  const later = q.find(i => i.spotify_id === 'e2e_q_3')

  // Both users upvote song 3 — it should now outrank song 2
  for (const u of [host, guest2]) {
    const res = await request.post(
      `${baseUrl}/api/sessions/${code}/queue/${later.id}/vote?vote=up`,
      { headers: bearer(u) },
    )
    expect(res.ok()).toBeTruthy()
  }
  const reordered = (await (await request.get(`${baseUrl}/api/sessions/${code}/queue`)).json()).queue
  expect(reordered[0].spotify_id).toBe('e2e_q_3')
  expect(reordered[0].likes).toBe(2)

  // Advance pops the top-voted item into now-playing (seq is mandatory
  // proof the caller saw the room state)
  const seq = (await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()).media_seq
  const adv = await request.post(`${baseUrl}/api/sessions/${code}/queue/next?seq=${seq}`, {
    headers: bearer(host),
  })
  const advBody = await adv.json()
  expect(advBody.advanced).toBe(true)
  const details = await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()
  expect(details.media?.spotify_id).toBe('e2e_q_3')
})

test('stale seq advance is a no-op (no double skip)', async ({ request }) => {
  // seq=0 is stale by now (several media changes bumped it)
  const res = await request.post(`${baseUrl}/api/sessions/${code}/queue/next?seq=0`, {
    headers: bearer(guest2),
  })
  const body = await res.json()
  expect(body.advanced).toBe(false)
  // Song 2 must still be waiting in the queue
  expect(body.queue.map(i => i.spotify_id)).toContain('e2e_q_2')
})

test('only the adder, creator, or admin can remove a queue item', async ({ request }) => {
  const outsider = mintUser('Queue Outsider')
  const q = (await (await request.get(`${baseUrl}/api/sessions/${code}/queue`)).json()).queue
  const item = q.find(i => i.spotify_id === 'e2e_q_2') // added by host

  const denied = await request.delete(`${baseUrl}/api/sessions/${code}/queue/${item.id}`, {
    headers: bearer(outsider),
  })
  expect(denied.status()).toBe(403)

  const allowed = await request.delete(`${baseUrl}/api/sessions/${code}/queue/${item.id}`, {
    headers: bearer(host),
  })
  expect(allowed.ok()).toBeTruthy()
})

test('anonymous guest can advance the queue (guest-only rooms must not stall)', async ({ request }) => {
  // Re-arm the queue, then advance with NO Authorization header at all
  await request.post(`${baseUrl}/api/sessions/${code}/queue`, {
    headers: bearer(host),
    data: media(4),
  })
  const seq = (await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()).media_seq
  const res = await request.post(`${baseUrl}/api/sessions/${code}/queue/next?seq=${seq}`)
  expect(res.ok()).toBeTruthy()
  expect((await res.json()).advanced).toBe(true)

  const details = await (await request.get(`${baseUrl}/api/sessions/${code}`)).json()
  expect(details.media?.spotify_id).toBe('e2e_q_4')
})

test('gif chat messages require a Giphy URL; text falls through untouched', async ({ page }) => {
  await page.goto(baseUrl)

  const results = await page.evaluate(({ url }) => {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url)
      const received = []
      const timeout = setTimeout(() => { ws.close(); resolve(received) }, 6000)
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.type === 'sync') {
          // Non-Giphy URL as gif must be dropped; Giphy URL must broadcast
          ws.send(JSON.stringify({ type: 'chat', kind: 'gif', content: 'https://evil.example/x.gif', client_id: 'g1' }))
          setTimeout(() => {
            ws.send(JSON.stringify({ type: 'chat', kind: 'gif', content: 'https://media.giphy.com/media/abc/giphy.gif', client_id: 'g2' }))
          }, 500)
        } else if (data.type === 'chat_message') {
          received.push(data)
          if (data.client_id === 'g2') {
            clearTimeout(timeout)
            ws.close()
            resolve(received)
          }
        }
      }
      ws.onerror = () => reject(new Error('WS error'))
    })
  }, { url: `${wsBase}/api/sessions/${code}/ws?token=${host.token}` })

  expect(results.some(m => m.client_id === 'g1')).toBe(false)
  expect(results.some(m => m.client_id === 'g2' && m.kind === 'gif')).toBe(true)
})
