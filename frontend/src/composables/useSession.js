import { ref, computed } from 'vue'

// Global session state (singleton)
const session = ref(null)
const album = ref(null)
const isPlaying = ref(false)
const playbackPosition = ref(0)
const currentTrackDuration = ref(0)
const listeners = ref([])
const ws = ref(null)
const toasts = ref([])

let progressInterval = null
let pingInterval = null
let toastId = 0

// Track if we're actively in a session
const isInSession = computed(() => !!session.value?.code)

const currentTrack = computed(() => {
  if (!album.value?.tracks || !session.value?.current_track_id) return null
  return album.value.tracks.find(t => t.id === session.value.current_track_id)
})

const progressPercent = computed(() => {
  if (!currentTrackDuration.value) return 0
  return Math.min(100, (playbackPosition.value / currentTrackDuration.value) * 100)
})

export function useSession() {
  function showToast(message, type = 'info') {
    const id = ++toastId
    toasts.value.push({ id, message, type })
    setTimeout(() => {
      toasts.value = toasts.value.filter(t => t.id !== id)
    }, 3000)
  }

  function formatDuration(ms) {
    if (!ms) return '0:00'
    const mins = Math.floor(ms / 60000)
    const secs = Math.floor((ms % 60000) / 1000)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  function startProgressInterval() {
    stopProgressInterval()
    progressInterval = setInterval(() => {
      if (isPlaying.value && currentTrackDuration.value > 0) {
        const newPosition = playbackPosition.value + 100
        if (newPosition >= currentTrackDuration.value) {
          playbackPosition.value = currentTrackDuration.value
          stopProgressInterval()
        } else {
          playbackPosition.value = newPosition
        }
      }
    }, 100)
  }

  function stopProgressInterval() {
    if (progressInterval) {
      clearInterval(progressInterval)
      progressInterval = null
    }
  }

  function connectWebSocket(code, userId, currentUser, onMessage) {
    // Clear any existing connection
    if (ws.value) {
      ws.value.close()
    }
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/sessions/${code}/ws?user_id=${userId}`

    ws.value = new WebSocket(wsUrl)

    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      handleWebSocketMessage(data, currentUser, onMessage)
    }

    ws.value.onopen = () => {
      pingInterval = setInterval(() => {
        if (ws.value?.readyState === WebSocket.OPEN) {
          ws.value.send(JSON.stringify({ type: 'ping' }))
        }
      }, 30000)
    }

    ws.value.onclose = () => {
      if (pingInterval) {
        clearInterval(pingInterval)
        pingInterval = null
      }
      // Attempt to reconnect if still in session
      setTimeout(() => {
        if (session.value?.is_active && session.value?.code === code) {
          connectWebSocket(code, userId, currentUser, onMessage)
        }
      }, 3000)
    }
  }

  function handleWebSocketMessage(data, currentUser, onMessage) {
    switch (data.type) {
      case 'sync':
        if (session.value) {
          session.value.current_track_id = data.track_id
        }
        isPlaying.value = data.is_playing
        playbackPosition.value = data.position
        listeners.value = data.listeners || []

        if (data.is_playing) {
          startProgressInterval()
        }
        break

      case 'track_change':
        stopProgressInterval()
        if (session.value) {
          session.value.current_track_id = data.track_id
        }
        currentTrackDuration.value = data.duration || 0
        playbackPosition.value = data.position || 0
        isPlaying.value = data.is_playing || false

        if (data.changed_by && data.changed_by !== currentUser?.id) {
          const trackName = album.value?.tracks?.find(t => t.id === data.track_id)?.name
          showToast(`${data.changed_by_name || 'Someone'} selected "${trackName || 'a track'}"`)
        }

        if (isPlaying.value) {
          startProgressInterval()
        }
        break

      case 'playback':
        if (data.action === 'play') {
          isPlaying.value = true
          playbackPosition.value = data.position
          startProgressInterval()
        } else if (data.action === 'pause') {
          isPlaying.value = false
          playbackPosition.value = data.position
          stopProgressInterval()
        } else if (data.action === 'seek') {
          playbackPosition.value = data.position
        }
        break

      case 'user_joined':
        if (!listeners.value.find(l => l.user_id === data.user_id)) {
          listeners.value.push({ user_id: data.user_id, user_name: data.user_name })
          if (data.user_id !== currentUser?.id) {
            showToast(`${data.user_name} joined the session`, 'success')
          }
        }
        break

      case 'user_left': {
        const leftUser = listeners.value.find(l => l.user_id === data.user_id)
        listeners.value = listeners.value.filter(l => l.user_id !== data.user_id)
        if (leftUser && data.user_id !== currentUser?.id) {
          showToast(`${leftUser.user_name || data.user_name} left the session`)
        }
        break
      }

      case 'rating':
        if (album.value?.tracks) {
          const track = album.value.tracks.find(t => t.id === data.track_id)
          if (track) {
            const existingIdx = track.rankings?.findIndex(r => r.user_id === data.user_id)
            const newRanking = {
              user_id: data.user_id,
              user_name: data.user_name,
              score: data.score,
              comment: data.comment
            }
            if (existingIdx >= 0) {
              track.rankings[existingIdx] = newRanking
            } else {
              if (!track.rankings) track.rankings = []
              track.rankings.push(newRanking)
            }
            if (data.user_id !== currentUser?.id) {
              showToast(`${data.user_name} rated "${track.name}" ${data.score.toFixed(1)}`, 'success')
            }
          }
        }
        break
    }

    // Forward to component handler if provided
    if (onMessage) {
      onMessage(data)
    }
  }

  async function joinSession(code, currentUser) {
    try {
      const res = await fetch(`/api/sessions/${code}`)
      if (!res.ok) return false

      session.value = await res.json()
      currentTrackDuration.value = session.value.current_track_duration || 0
      isPlaying.value = session.value.playback?.is_playing || false
      playbackPosition.value = session.value.playback?.position || 0
      listeners.value = session.value.participants?.filter(p => p.is_online) || []

      // Load album
      const albumRes = await fetch('/api/albums')
      if (albumRes.ok) {
        const albums = await albumRes.json()
        album.value = albums.find(a => a.id === session.value.album_id)
        if (currentTrack.value) {
          currentTrackDuration.value = currentTrack.value.duration_ms
        }
      }

      // Connect WebSocket
      connectWebSocket(code, currentUser?.id, currentUser)

      if (isPlaying.value) {
        startProgressInterval()
      }

      return true
    } catch (e) {
      console.error('Failed to join session:', e)
      return false
    }
  }

  async function leaveSession() {
    stopProgressInterval()
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
    }
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    session.value = null
    album.value = null
    isPlaying.value = false
    playbackPosition.value = 0
    currentTrackDuration.value = 0
    listeners.value = []
  }

  async function selectTrack(trackId, currentUser) {
    if (!session.value?.code) return

    try {
      const headers = {}
      if (currentUser?.id) {
        headers['X-User-Id'] = currentUser.id.toString()
      }
      await fetch(`/api/sessions/${session.value.code}/track?track_id=${trackId}`, {
        method: 'POST',
        headers
      })
      session.value.current_track_id = trackId
      const track = album.value?.tracks?.find(t => t.id === trackId)
      if (track) {
        currentTrackDuration.value = track.duration_ms
      }
      playbackPosition.value = 0
      isPlaying.value = false
      stopProgressInterval()

      // Auto-play
      await new Promise(resolve => setTimeout(resolve, 100))
      await togglePlayback(currentUser)
    } catch (e) {
      console.error('Failed to select track:', e)
    }
  }

  async function togglePlayback(currentUser) {
    if (!session.value?.code) return

    const action = isPlaying.value ? 'pause' : 'play'

    try {
      const headers = {}
      if (currentUser?.id) {
        headers['X-User-Id'] = currentUser.id.toString()
      }
      await fetch(`/api/sessions/${session.value.code}/playback?action=${action}`, {
        method: 'POST',
        headers
      })
    } catch (e) {
      console.error('Failed to toggle playback:', e)
    }
  }

  async function seekTo(percent, currentUser) {
    if (!session.value?.code) return

    const position = Math.floor((percent / 100) * currentTrackDuration.value)
    playbackPosition.value = position

    try {
      const headers = {}
      if (currentUser?.id) {
        headers['X-User-Id'] = currentUser.id.toString()
      }
      await fetch(`/api/sessions/${session.value.code}/playback?action=seek&position=${position}`, {
        method: 'POST',
        headers
      })
    } catch (e) {
      console.error('Failed to seek:', e)
    }
  }

  function skipPrevious(currentUser) {
    const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
    if (trackIdx > 0) {
      selectTrack(album.value.tracks[trackIdx - 1].id, currentUser)
    }
  }

  function skipNext(currentUser) {
    const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
    if (trackIdx !== undefined && trackIdx < album.value.tracks.length - 1) {
      selectTrack(album.value.tracks[trackIdx + 1].id, currentUser)
    }
  }

  return {
    // State
    session,
    album,
    isPlaying,
    playbackPosition,
    currentTrackDuration,
    listeners,
    toasts,
    isInSession,
    currentTrack,
    progressPercent,

    // Methods
    joinSession,
    leaveSession,
    selectTrack,
    togglePlayback,
    seekTo,
    skipPrevious,
    skipNext,
    showToast,
    formatDuration,
    startProgressInterval,
    stopProgressInterval,
    connectWebSocket
  }
}
