/**
 * Tests for useSession composable.
 *
 * Tests WebSocket handling, state updates, and reconnection logic.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'

// Mock useSpotifyPlayer before importing useSession
vi.mock('../composables/useSpotifyPlayer', () => ({
  useSpotifyPlayer: () => ({
    isReady: { value: false },
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn().mockResolvedValue(undefined),
    resume: vi.fn().mockResolvedValue(undefined),
    seek: vi.fn().mockResolvedValue(undefined)
  })
}))

// Track WebSocket instances
let wsInstances = []

// Mock WebSocket class
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  constructor(url) {
    this.url = url
    this.readyState = MockWebSocket.OPEN // Start open for simplicity
    this.onopen = null
    this.onmessage = null
    this.onclose = null
    this.onerror = null
    this._messageQueue = []
    wsInstances.push(this)

    // Call onopen synchronously
    queueMicrotask(() => {
      if (this.onopen) this.onopen({ target: this })
    })
  }

  send(data) {
    this._messageQueue.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose({ target: this, code: 1000, reason: '' })
    }
  }

  _receiveMessage(data) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) })
    }
  }
}

global.WebSocket = MockWebSocket

// Helper to create mock fetch responses
function mockFetch(responses = {}) {
  return vi.fn((url) => {
    const path = url.replace(/\?.*$/, '')
    const response = responses[path] || { ok: true, data: {} }

    return Promise.resolve({
      ok: response.ok !== false,
      status: response.status || 200,
      json: async () => response.data || {}
    })
  })
}

// Import after mocking
import { useSession } from '../composables/useSession'

describe('useSession', () => {
  let session

  beforeEach(() => {
    wsInstances = []
    session = useSession()
    session.leaveSession()
    vi.clearAllMocks()
  })

  afterEach(() => {
    session.leaveSession()
  })

  describe('joinSession', () => {
    it('should fetch session data and connect WebSocket', async () => {
      const mockSessionData = {
        code: 'ABC123',
        name: 'Test Room',
        album_id: 1,
        current_track_id: 1,
        current_track_duration: 180000,
        playback: { is_playing: false, position: 0 },
        participants: []
      }

      const mockAlbums = [{
        id: 1,
        name: 'Test Album',
        tracks: [
          { id: 1, name: 'Track 1', duration_ms: 180000 },
          { id: 2, name: 'Track 2', duration_ms: 200000 }
        ]
      }]

      global.fetch = mockFetch({
        '/api/sessions/ABC123': { data: mockSessionData },
        '/api/albums': { data: mockAlbums }
      })

      const result = await session.joinSession('ABC123', { id: 1, name: 'TestUser' })

      expect(result).toBe(true)
      expect(session.session.value).toBeTruthy()
      expect(session.session.value.code).toBe('ABC123')
      expect(session.isInSession.value).toBe(true)
      expect(wsInstances.length).toBeGreaterThan(0)
    })

    it('should return false if session fetch fails', async () => {
      global.fetch = mockFetch({
        '/api/sessions/INVALID': { ok: false, status: 404 }
      })

      const result = await session.joinSession('INVALID', { id: 1 })

      expect(result).toBe(false)
      expect(session.session.value).toBeNull()
    })
  })

  describe('WebSocket message handling', () => {
    let ws

    beforeEach(async () => {
      const mockSessionData = {
        code: 'ABC123',
        album_id: 1,
        current_track_id: 1,
        current_track_duration: 180000,
        playback: { is_playing: false, position: 0 },
        participants: []
      }

      const mockAlbums = [{
        id: 1,
        tracks: [
          { id: 1, name: 'Track 1', duration_ms: 180000, rankings: [] },
          { id: 2, name: 'Track 2', duration_ms: 200000, rankings: [] }
        ]
      }]

      global.fetch = mockFetch({
        '/api/sessions/ABC123': { data: mockSessionData },
        '/api/albums': { data: mockAlbums }
      })

      await session.joinSession('ABC123', { id: 1, name: 'TestUser' })
      ws = wsInstances[wsInstances.length - 1]
    })

    it('should handle sync message', async () => {
      ws._receiveMessage({
        type: 'sync',
        track_id: 1,
        is_playing: true,
        position: 30000,
        listeners: [{ user_id: 1, user_name: 'TestUser' }]
      })

      await nextTick()

      expect(session.isPlaying.value).toBe(true)
      expect(session.playbackPosition.value).toBe(30000)
      expect(session.listeners.value).toHaveLength(1)
    })

    it('should handle track_change message', async () => {
      ws._receiveMessage({
        type: 'track_change',
        track_id: 2,
        duration: 200000,
        position: 0,
        is_playing: false,
        changed_by: 2,
        changed_by_name: 'OtherUser'
      })

      await nextTick()

      expect(session.session.value.current_track_id).toBe(2)
      expect(session.currentTrackDuration.value).toBe(200000)
      expect(session.playbackPosition.value).toBe(0)
    })

    it('should handle playback play message', async () => {
      ws._receiveMessage({
        type: 'playback',
        action: 'play',
        position: 5000
      })

      await nextTick()

      expect(session.isPlaying.value).toBe(true)
      expect(session.playbackPosition.value).toBe(5000)
    })

    it('should handle playback pause message', async () => {
      session.isPlaying.value = true

      ws._receiveMessage({
        type: 'playback',
        action: 'pause',
        position: 60000
      })

      await nextTick()

      expect(session.isPlaying.value).toBe(false)
      expect(session.playbackPosition.value).toBe(60000)
    })

    it('should handle user_joined message', async () => {
      ws._receiveMessage({
        type: 'user_joined',
        user_id: 2,
        user_name: 'NewUser',
        active_count: 2
      })

      await nextTick()

      expect(session.listeners.value).toContainEqual({
        user_id: 2,
        user_name: 'NewUser'
      })
    })

    it('should handle user_left message', async () => {
      session.listeners.value = [
        { user_id: 1, user_name: 'TestUser' },
        { user_id: 2, user_name: 'LeavingUser' }
      ]

      ws._receiveMessage({
        type: 'user_left',
        user_id: 2,
        user_name: 'LeavingUser',
        active_count: 1
      })

      await nextTick()

      expect(session.listeners.value).toHaveLength(1)
      expect(session.listeners.value[0].user_id).toBe(1)
    })

    it('should handle rating message and update track rankings', async () => {
      ws._receiveMessage({
        type: 'rating',
        track_id: 1,
        user_id: 2,
        user_name: 'OtherUser',
        score: 8.5,
        comment: 'Great track!'
      })

      await nextTick()

      const track = session.album.value.tracks.find(t => t.id === 1)
      expect(track.rankings).toContainEqual({
        user_id: 2,
        user_name: 'OtherUser',
        score: 8.5,
        comment: 'Great track!'
      })
    })

    it('should handle session_ended message', async () => {
      ws._receiveMessage({
        type: 'session_ended',
        message: 'Room closed'
      })

      await nextTick()

      expect(session.session.value).toBeNull()
      expect(session.album.value).toBeNull()
      expect(session.isInSession.value).toBe(false)
    })

    it('should correct drift > 500ms on pong', async () => {
      session.playbackPosition.value = 10000

      ws._receiveMessage({
        type: 'pong',
        position: 11000,
        is_playing: true
      })

      await nextTick()

      expect(session.playbackPosition.value).toBe(11000)
    })

    it('should ignore pong drift < 500ms', async () => {
      session.playbackPosition.value = 10000

      ws._receiveMessage({
        type: 'pong',
        position: 10300,
        is_playing: true
      })

      await nextTick()

      expect(session.playbackPosition.value).toBe(10000)
    })
  })

  describe('leaveSession', () => {
    it('should clean up all state', async () => {
      const mockSessionData = {
        code: 'ABC123',
        album_id: 1,
        current_track_id: 1,
        current_track_duration: 180000,
        playback: { is_playing: true, position: 50000 },
        participants: [{ id: 1, name: 'User', is_online: true }]
      }

      global.fetch = mockFetch({
        '/api/sessions/ABC123': { data: mockSessionData },
        '/api/albums': { data: [{ id: 1, tracks: [] }] }
      })

      await session.joinSession('ABC123', { id: 1 })

      session.isPlaying.value = true
      session.playbackPosition.value = 50000
      session.listeners.value = [{ user_id: 1, user_name: 'User' }]

      session.leaveSession()

      expect(session.session.value).toBeNull()
      expect(session.album.value).toBeNull()
      expect(session.isPlaying.value).toBe(false)
      expect(session.playbackPosition.value).toBe(0)
      expect(session.currentTrackDuration.value).toBe(0)
      expect(session.listeners.value).toHaveLength(0)
      expect(session.isInSession.value).toBe(false)
    })
  })

  describe('progress tracking', () => {
    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
      session.stopProgressInterval()
    })

    it('should increment position when playing', () => {
      session.isPlaying.value = true
      session.currentTrackDuration.value = 180000
      session.playbackPosition.value = 0

      session.startProgressInterval()

      vi.advanceTimersByTime(1000)

      expect(session.playbackPosition.value).toBeGreaterThanOrEqual(1000)

      session.stopProgressInterval()
    })

    it('should stop at track end', () => {
      session.isPlaying.value = true
      session.currentTrackDuration.value = 500
      session.playbackPosition.value = 400

      session.startProgressInterval()

      vi.advanceTimersByTime(200)

      expect(session.playbackPosition.value).toBe(500)

      session.stopProgressInterval()
    })
  })

  describe('syncWithServer', () => {
    it('should fetch and apply server state', async () => {
      session.session.value = { code: 'ABC123', current_track_id: 1 }
      session.album.value = { tracks: [{ id: 1, duration_ms: 180000 }] }
      session.playbackPosition.value = 10000
      session.isPlaying.value = false

      global.fetch = mockFetch({
        '/api/sessions/ABC123': {
          data: {
            current_track_id: 1,
            playback: { is_playing: true, position: 60000 }
          }
        }
      })

      const result = await session.syncWithServer()

      expect(result).toBe(true)
      expect(session.playbackPosition.value).toBe(60000)
      expect(session.isPlaying.value).toBe(true)
    })

    it('should return false on failure', async () => {
      session.session.value = { code: 'ABC123' }

      global.fetch = mockFetch({
        '/api/sessions/ABC123': { ok: false, status: 500 }
      })

      const result = await session.syncWithServer()

      expect(result).toBe(false)
    })
  })

  describe('formatDuration', () => {
    it('should format milliseconds to mm:ss', () => {
      expect(session.formatDuration(0)).toBe('0:00')
      expect(session.formatDuration(30000)).toBe('0:30')
      expect(session.formatDuration(60000)).toBe('1:00')
      expect(session.formatDuration(90000)).toBe('1:30')
      expect(session.formatDuration(180000)).toBe('3:00')
      expect(session.formatDuration(3661000)).toBe('61:01')
    })

    it('should handle null/undefined', () => {
      expect(session.formatDuration(null)).toBe('0:00')
      expect(session.formatDuration(undefined)).toBe('0:00')
    })
  })

  describe('computed properties', () => {
    it('isInSession should reflect session state', () => {
      expect(session.isInSession.value).toBe(false)

      session.session.value = { code: 'ABC123' }
      expect(session.isInSession.value).toBe(true)

      session.session.value = null
      expect(session.isInSession.value).toBe(false)
    })

    it('hasAlbum should reflect album state', () => {
      expect(session.hasAlbum.value).toBe(false)

      session.session.value = { album_id: 1 }
      session.album.value = { id: 1, tracks: [] }
      expect(session.hasAlbum.value).toBe(true)

      session.album.value = null
      expect(session.hasAlbum.value).toBe(false)
    })

    it('currentTrack should find track by id', () => {
      session.session.value = { current_track_id: 2 }
      session.album.value = {
        tracks: [
          { id: 1, name: 'Track 1' },
          { id: 2, name: 'Track 2' }
        ]
      }

      expect(session.currentTrack.value).toEqual({ id: 2, name: 'Track 2' })
    })

    it('progressPercent should calculate percentage', () => {
      session.playbackPosition.value = 30000
      session.currentTrackDuration.value = 180000

      // 30000 / 180000 = 0.1667 = 16.67%
      expect(session.progressPercent.value).toBeCloseTo(16.67, 1)
    })
  })
})
