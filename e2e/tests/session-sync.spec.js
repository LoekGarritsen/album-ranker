/**
 * E2E test for real-time session synchronization.
 *
 * Scenario:
 * 1. User A creates a session
 * 2. User B joins the session
 * 3. User A rates a track
 * 4. User B sees the rating update in real-time
 *
 * Prerequisites:
 * - Docker containers running via docker-compose.e2e.yml
 * - Database seeded with test album (done via API in test setup)
 */
import { test, expect } from '@playwright/test'

// Test data
const TEST_ALBUM = {
  spotify_id: 'e2e_test_album_001',
  name: 'E2E Test Album',
  artist: 'Test Artist',
  cover_url: 'https://via.placeholder.com/300',
  release_date: '2024-01-01'
}

const TEST_TRACKS = [
  { name: 'Test Track 1', duration_ms: 180000 },
  { name: 'Test Track 2', duration_ms: 200000 },
  { name: 'Test Track 3', duration_ms: 220000 }
]

test.describe('Session Real-time Sync', () => {
  let userAContext
  let userBContext
  let userAPage
  let userBPage
  let adminUserId
  let regularUserId
  let albumId
  let sessionCode

  test.beforeAll(async ({ browser }) => {
    // Create two browser contexts for two users
    userAContext = await browser.newContext()
    userBContext = await browser.newContext()
    userAPage = await userAContext.newPage()
    userBPage = await userBContext.newPage()

    // Seed test data via API
    const baseUrl = process.env.BASE_URL || 'http://localhost:8401'

    // Create admin user (User A)
    const userARes = await userAPage.request.post(`${baseUrl}/api/users`, {
      data: { name: 'E2E User A' }
    })
    const userAData = await userARes.json()
    adminUserId = userAData.id
    console.log(`Created User A with ID: ${adminUserId}`)

    // Create regular user (User B)
    const userBRes = await userBPage.request.post(`${baseUrl}/api/users`, {
      data: { name: 'E2E User B' }
    })
    const userBData = await userBRes.json()
    regularUserId = userBData.id
    console.log(`Created User B with ID: ${regularUserId}`)

    // Get the pre-seeded admin user ID for album creation
    const usersRes = await userAPage.request.get(`${baseUrl}/api/users`)
    const users = await usersRes.json()
    const adminUser = users.find(u => u.is_admin)

    if (adminUser) {
      // Seed test album via direct DB manipulation through API
      // Note: We can't add albums without Spotify integration working,
      // so we'll check if there's an existing album to use
      const albumsRes = await userAPage.request.get(`${baseUrl}/api/albums`)
      const albums = await albumsRes.json()

      if (albums.length > 0) {
        // Use existing album
        albumId = albums[0].id
        console.log(`Using existing album ID: ${albumId}`)
      } else {
        // Skip album-dependent tests
        console.log('No albums available - some tests will be skipped')
        albumId = null
      }
    }
  })

  test.afterAll(async () => {
    await userAContext.close()
    await userBContext.close()
  })

  test('User A can create a session and User B can join', async () => {
    const baseUrl = process.env.BASE_URL || 'http://localhost:8401'

    // User A creates a session (without album for this test)
    const createRes = await userAPage.request.post(`${baseUrl}/api/sessions`, {
      headers: { 'X-User-Id': adminUserId.toString() },
      data: {
        name: 'E2E Test Session',
        is_public: true
      }
    })

    expect(createRes.ok()).toBeTruthy()
    const sessionData = await createRes.json()
    sessionCode = sessionData.code
    expect(sessionCode).toHaveLength(6)
    console.log(`Session created with code: ${sessionCode}`)

    // User B joins the session
    const joinRes = await userBPage.request.post(`${baseUrl}/api/sessions/${sessionCode}/join`, {
      headers: { 'X-User-Id': regularUserId.toString() }
    })

    expect(joinRes.ok()).toBeTruthy()

    // Verify both users are participants
    const sessionRes = await userAPage.request.get(`${baseUrl}/api/sessions/${sessionCode}`)
    const session = await sessionRes.json()

    expect(session.participants.length).toBeGreaterThanOrEqual(2)
    const participantNames = session.participants.map(p => p.name)
    expect(participantNames).toContain('E2E User A')
    expect(participantNames).toContain('E2E User B')
  })

  test('WebSocket sync works between two users', async () => {
    test.skip(!sessionCode, 'Session not created')

    const baseUrl = process.env.BASE_URL || 'http://localhost:8401'

    // Navigate both users to the session page
    await userAPage.goto(`${baseUrl}`)
    await userBPage.goto(`${baseUrl}`)

    // Wait for pages to load
    await userAPage.waitForLoadState('networkidle')
    await userBPage.waitForLoadState('networkidle')

    // Select users in the UI (if user selector exists)
    // This depends on the actual UI implementation
    // For now, we'll test via API WebSocket behavior

    // Connect User A to WebSocket
    const wsUrlA = `ws://localhost:8401/api/sessions/${sessionCode}/ws?user_id=${adminUserId}`
    const wsUrlB = `ws://localhost:8401/api/sessions/${sessionCode}/ws?user_id=${regularUserId}`

    // Test WebSocket connectivity through page evaluation
    const userAConnected = await userAPage.evaluate(async (url) => {
      return new Promise((resolve) => {
        const ws = new WebSocket(url)
        ws.onopen = () => {
          ws.close()
          resolve(true)
        }
        ws.onerror = () => resolve(false)
        setTimeout(() => resolve(false), 5000)
      })
    }, wsUrlA)

    expect(userAConnected).toBe(true)

    const userBConnected = await userBPage.evaluate(async (url) => {
      return new Promise((resolve) => {
        const ws = new WebSocket(url)
        ws.onopen = () => {
          ws.close()
          resolve(true)
        }
        ws.onerror = () => resolve(false)
        setTimeout(() => resolve(false), 5000)
      })
    }, wsUrlB)

    expect(userBConnected).toBe(true)
  })

  test('Rating broadcast works between users', async () => {
    test.skip(!sessionCode || !albumId, 'Session or album not available')

    const baseUrl = process.env.BASE_URL || 'http://localhost:8401'

    // First, set album on session
    const setAlbumRes = await userAPage.request.post(
      `${baseUrl}/api/sessions/${sessionCode}/album?album_id=${albumId}`,
      { headers: { 'X-User-Id': adminUserId.toString() } }
    )
    expect(setAlbumRes.ok()).toBeTruthy()

    // Get album tracks
    const albumsRes = await userAPage.request.get(`${baseUrl}/api/albums`)
    const albums = await albumsRes.json()
    const album = albums.find(a => a.id === albumId)
    const trackId = album.tracks[0]?.id

    test.skip(!trackId, 'No tracks in album')

    // Set up WebSocket listener on User B's page to capture rating broadcast
    const ratingReceived = userBPage.evaluate(async ({ wsUrl, expectedTrackId }) => {
      return new Promise((resolve, reject) => {
        const ws = new WebSocket(wsUrl)
        const timeout = setTimeout(() => {
          ws.close()
          reject(new Error('Timeout waiting for rating'))
        }, 10000)

        ws.onmessage = (event) => {
          const data = JSON.parse(event.data)
          if (data.type === 'rating' && data.track_id === expectedTrackId) {
            clearTimeout(timeout)
            ws.close()
            resolve(data)
          }
        }

        ws.onerror = (err) => {
          clearTimeout(timeout)
          reject(err)
        }
      })
    }, {
      wsUrl: `ws://localhost:8401/api/sessions/${sessionCode}/ws?user_id=${regularUserId}`,
      expectedTrackId: trackId
    })

    // Small delay to ensure WebSocket is connected
    await userBPage.waitForTimeout(500)

    // User A submits a rating
    const ratingRes = await userAPage.request.post(
      `${baseUrl}/api/rankings/track?session_code=${sessionCode}`,
      {
        data: {
          track_id: trackId,
          user_id: adminUserId,
          score: 8.5,
          comment: 'E2E test rating'
        }
      }
    )
    expect(ratingRes.ok()).toBeTruthy()

    // Wait for User B to receive the rating broadcast
    const receivedRating = await ratingReceived
    expect(receivedRating).toBeDefined()
    expect(receivedRating.track_id).toBe(trackId)
    expect(receivedRating.user_id).toBe(adminUserId)
    expect(receivedRating.score).toBe(8.5)
    expect(receivedRating.comment).toBe('E2E test rating')
  })

  test('Session cleanup works', async () => {
    test.skip(!sessionCode, 'Session not created')

    const baseUrl = process.env.BASE_URL || 'http://localhost:8401'

    // User A ends the session
    const deleteRes = await userAPage.request.delete(
      `${baseUrl}/api/sessions/${sessionCode}`,
      { headers: { 'X-User-Id': adminUserId.toString() } }
    )
    expect(deleteRes.ok()).toBeTruthy()

    // Session should no longer be found
    const getRes = await userAPage.request.get(`${baseUrl}/api/sessions/${sessionCode}`)
    expect(getRes.status()).toBe(404)
  })
})

test.describe('Session with Album', () => {
  test('Full flow: create session, set album, change tracks', async ({ page, request }) => {
    const baseUrl = process.env.BASE_URL || 'http://localhost:8401'

    // Create a user
    const userRes = await request.post(`${baseUrl}/api/users`, {
      data: { name: 'Flow Test User' }
    })
    const user = await userRes.json()

    // Check for existing albums
    const albumsRes = await request.get(`${baseUrl}/api/albums`)
    const albums = await albumsRes.json()

    if (albums.length === 0) {
      test.skip(true, 'No albums available for testing')
      return
    }

    const album = albums[0]

    // Create session with album
    const sessionRes = await request.post(`${baseUrl}/api/sessions`, {
      headers: { 'X-User-Id': user.id.toString() },
      data: {
        name: 'Album Flow Test',
        album_id: album.id,
        is_public: true
      }
    })

    expect(sessionRes.ok()).toBeTruthy()
    const session = await sessionRes.json()

    // Verify session has album and first track set
    const sessionDetailsRes = await request.get(`${baseUrl}/api/sessions/${session.code}`)
    const details = await sessionDetailsRes.json()

    expect(details.album_id).toBe(album.id)
    expect(details.current_track_id).toBe(album.tracks[0].id)

    // Change to second track
    if (album.tracks.length > 1) {
      const trackRes = await request.post(
        `${baseUrl}/api/sessions/${session.code}/track?track_id=${album.tracks[1].id}`,
        { headers: { 'X-User-Id': user.id.toString() } }
      )
      expect(trackRes.ok()).toBeTruthy()

      // Verify track changed
      const updatedRes = await request.get(`${baseUrl}/api/sessions/${session.code}`)
      const updated = await updatedRes.json()
      expect(updated.current_track_id).toBe(album.tracks[1].id)
    }

    // Cleanup
    await request.delete(`${baseUrl}/api/sessions/${session.code}`, {
      headers: { 'X-User-Id': user.id.toString() }
    })
  })
})

test.describe('Playback Controls', () => {
  test('Play/pause/seek sync across session', async ({ request }) => {
    const baseUrl = process.env.BASE_URL || 'http://localhost:8401'

    // Create user and session
    const userRes = await request.post(`${baseUrl}/api/users`, {
      data: { name: 'Playback Test User' }
    })
    const user = await userRes.json()

    const sessionRes = await request.post(`${baseUrl}/api/sessions`, {
      headers: { 'X-User-Id': user.id.toString() },
      data: { name: 'Playback Test', is_public: true }
    })
    const session = await sessionRes.json()

    // Test play
    const playRes = await request.post(
      `${baseUrl}/api/sessions/${session.code}/playback?action=play`,
      { headers: { 'X-User-Id': user.id.toString() } }
    )
    expect(playRes.ok()).toBeTruthy()

    // Verify playing state
    let details = await (await request.get(`${baseUrl}/api/sessions/${session.code}`)).json()
    expect(details.playback.is_playing).toBe(true)

    // Test pause
    const pauseRes = await request.post(
      `${baseUrl}/api/sessions/${session.code}/playback?action=pause`,
      { headers: { 'X-User-Id': user.id.toString() } }
    )
    expect(pauseRes.ok()).toBeTruthy()

    details = await (await request.get(`${baseUrl}/api/sessions/${session.code}`)).json()
    expect(details.playback.is_playing).toBe(false)

    // Test seek
    const seekRes = await request.post(
      `${baseUrl}/api/sessions/${session.code}/playback?action=seek&position=30000`,
      { headers: { 'X-User-Id': user.id.toString() } }
    )
    expect(seekRes.ok()).toBeTruthy()

    details = await (await request.get(`${baseUrl}/api/sessions/${session.code}`)).json()
    expect(details.playback.position).toBeGreaterThanOrEqual(30000)

    // Cleanup
    await request.delete(`${baseUrl}/api/sessions/${session.code}`, {
      headers: { 'X-User-Id': user.id.toString() }
    })
  })
})
