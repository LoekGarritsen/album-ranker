import { ref, computed } from 'vue'
import { useSpotifyPlayer } from './useSpotifyPlayer'

// Global session state (singleton)
const session = ref(null)
const album = ref(null)
const isPlaying = ref(false)
const playbackPosition = ref(0)
const currentTrackDuration = ref(0)
const listeners = ref([])
const ws = ref(null)
const toasts = ref([])
const sessionUser = ref(null) // Store current user for auto-advance

let progressInterval = null
let pingInterval = null
let toastId = 0

// Track if we're actively in a session
const isInSession = computed(() => !!session.value?.code)

// Track if session has an album selected
const hasAlbum = computed(() => !!session.value?.album_id && !!album.value)

const currentTrack = computed(() => {
  if (!album.value?.tracks || !session.value?.current_track_id) return null
  return album.value.tracks.find(t => t.id === session.value.current_track_id)
})

const progressPercent = computed(() => {
  if (!currentTrackDuration.value) return 0
  return Math.min(100, (playbackPosition.value / currentTrackDuration.value) * 100)
})

export function useSession() {
  // Get Spotify player (singleton)
  const {
    isReady: spotifyReady,
    play: spotifyPlay,
    pause: spotifyPause,
    resume: spotifyResume,
    seek: spotifySeek
  } = useSpotifyPlayer()
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
          // Auto-advance to next track
          autoAdvanceToNext()
        } else {
          playbackPosition.value = newPosition
        }
      }
    }, 100)
  }

  function autoAdvanceToNext() {
    // Advance to next track when current track ends
    // This is the fallback for all users - Spotify users may get early advance from Session.vue watcher
    const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
    if (trackIdx >= 0 && trackIdx < album.value.tracks.length - 1) {
      // There's a next track, advance to it
      selectTrack(album.value.tracks[trackIdx + 1].id, sessionUser.value)
    } else {
      // Last track ended, stop playback
      isPlaying.value = false
      stopProgressInterval()
    }
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
      try {
        const data = JSON.parse(event.data)
        handleWebSocketMessage(data, currentUser, onMessage)
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e, event.data)
      }
    }

    ws.value.onopen = () => {
      // Ping every 10 seconds for more responsive sync (room is source of truth)
      pingInterval = setInterval(() => {
        if (ws.value?.readyState === WebSocket.OPEN) {
          ws.value.send(JSON.stringify({ type: 'ping' }))
        }
      }, 10000)
    }

    ws.value.onclose = () => {
      if (pingInterval) {
        clearInterval(pingInterval)
        pingInterval = null
      }
      // Attempt to reconnect if still in session
      setTimeout(() => {
        if (session.value?.code === code) {
          connectWebSocket(code, userId, currentUser, onMessage)
        }
      }, 3000)
    }

    ws.value.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  }

  function handleWebSocketMessage(data, currentUser, onMessage) {
    switch (data.type) {
      case 'sync':
        // Stop any existing interval first
        stopProgressInterval()

        if (session.value) {
          session.value.current_track_id = data.track_id
        }
        playbackPosition.value = data.position || 0
        isPlaying.value = data.is_playing || false
        listeners.value = data.listeners || []

        // Only start interval if actually playing
        if (isPlaying.value) {
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
        stopProgressInterval()
        playbackPosition.value = data.position || 0

        if (data.action === 'play') {
          isPlaying.value = true
          startProgressInterval()
        } else if (data.action === 'pause') {
          isPlaying.value = false
        } else if (data.action === 'seek') {
          // Keep current playing state, just update position
          if (isPlaying.value) {
            startProgressInterval()
          }
        }
        break

      case 'pong':
        // Sync position from server on every pong (every 30s)
        // Room is source of truth - sync all users including Spotify users
        if (data.position !== undefined) {
          const drift = Math.abs(playbackPosition.value - data.position)
          // Only correct if drift is more than 500ms
          if (drift > 500) {
            playbackPosition.value = data.position
          }
        }
        // Also sync play/pause state from server
        if (data.is_playing !== undefined && data.is_playing !== isPlaying.value) {
          isPlaying.value = data.is_playing
          if (isPlaying.value) {
            startProgressInterval()
          } else {
            stopProgressInterval()
          }
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

      case 'album_change':
        // Album was changed by someone - need to reload album data
        if (session.value) {
          session.value.album_id = data.album_id
          session.value.album_name = data.album_name
          session.value.cover_url = data.cover_url
          session.value.current_track_id = data.track_id
        }
        currentTrackDuration.value = data.track_duration || 0
        playbackPosition.value = 0
        isPlaying.value = false
        stopProgressInterval()

        // Reload the full album data
        loadAlbumData(data.album_id)

        if (data.changed_by !== currentUser?.id) {
          showToast(`${data.changed_by_name || 'Someone'} selected album "${data.album_name}"`)
        }
        break

      case 'session_ended':
        // Room was closed/deleted
        showToast(data.message || 'This room has been closed', 'error')
        // Clear session state - the WebSocket will close automatically
        session.value = null
        album.value = null
        sessionUser.value = null
        isPlaying.value = false
        playbackPosition.value = 0
        currentTrackDuration.value = 0
        listeners.value = []
        stopProgressInterval()
        break
    }

    // Forward to component handler if provided
    if (onMessage) {
      onMessage(data)
    }
  }

  async function loadAlbumData(albumId) {
    if (!albumId) {
      album.value = null
      return
    }

    try {
      const albumRes = await fetch('/api/albums')
      if (albumRes.ok) {
        const albums = await albumRes.json()
        album.value = albums.find(a => a.id === albumId)
        if (currentTrack.value) {
          currentTrackDuration.value = currentTrack.value.duration_ms
        }
      }
    } catch (e) {
      console.error('Failed to load album data:', e)
    }
  }

  async function joinSession(code, currentUser) {
    try {
      const res = await fetch(`/api/sessions/${code}`)
      if (!res.ok) return false

      session.value = await res.json()
      sessionUser.value = currentUser // Store for auto-advance
      currentTrackDuration.value = session.value.current_track_duration || 0
      isPlaying.value = session.value.playback?.is_playing || false
      playbackPosition.value = session.value.playback?.position || 0
      listeners.value = session.value.participants?.filter(p => p.is_online) || []

      // Load album only if session has one
      if (session.value.album_id) {
        await loadAlbumData(session.value.album_id)
      } else {
        album.value = null
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

  async function setAlbum(albumId, currentUser) {
    if (!session.value?.code) return false

    try {
      const headers = {}
      if (currentUser?.id) {
        headers['X-User-Id'] = currentUser.id.toString()
      }
      const res = await fetch(`/api/sessions/${session.value.code}/album?album_id=${albumId}`, {
        method: 'POST',
        headers
      })

      if (res.ok) {
        // Album data will be updated via WebSocket album_change message
        return true
      }
      return false
    } catch (e) {
      console.error('Failed to set album:', e)
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
    sessionUser.value = null
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

      // Auto-play from beginning
      await new Promise(resolve => setTimeout(resolve, 100))
      await startPlaybackFromBeginning(currentUser, track)
    } catch (e) {
      console.error('Failed to select track:', e)
    }
  }

  async function startPlaybackFromBeginning(currentUser, track) {
    if (!session.value?.code) return

    try {
      const headers = {}
      if (currentUser?.id) {
        headers['X-User-Id'] = currentUser.id.toString()
      }

      // Send play action with position 0
      await fetch(`/api/sessions/${session.value.code}/playback?action=seek&position=0`, {
        method: 'POST',
        headers
      })
      await fetch(`/api/sessions/${session.value.code}/playback?action=play`, {
        method: 'POST',
        headers
      })

      // Control Spotify if connected
      if (spotifyReady.value && track?.spotify_id) {
        await spotifyPlay(`spotify:track:${track.spotify_id}`, 0)
      }

      playbackPosition.value = 0
      isPlaying.value = true
      startProgressInterval()
    } catch (e) {
      console.error('Failed to start playback:', e)
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
      // State will be updated via WebSocket broadcast
      // Spotify will be synced via the isPlaying watcher in Session.vue
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

      // Seek on Spotify if connected
      if (spotifyReady.value) {
        await spotifySeek(position)
      }
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
    if (trackIdx >= 0 && trackIdx < album.value.tracks.length - 1) {
      selectTrack(album.value.tracks[trackIdx + 1].id, currentUser)
    }
  }

  async function syncWithServer() {
    if (!session.value?.code) return false

    try {
      // Stop interval first to prevent race conditions
      stopProgressInterval()

      const res = await fetch(`/api/sessions/${session.value.code}`)
      if (!res.ok) {
        showToast('Sync failed: server error', 'error')
        return false
      }

      const data = await res.json()

      // Update local state with server state
      if (data.playback) {
        const serverPos = data.playback.position || 0
        const serverIsPlaying = data.playback.is_playing || false

        // Set position from server
        playbackPosition.value = serverPos
        isPlaying.value = serverIsPlaying
      }

      // Update track if different
      if (data.current_track_id && data.current_track_id !== session.value.current_track_id) {
        session.value.current_track_id = data.current_track_id
        const track = album.value?.tracks?.find(t => t.id === data.current_track_id)
        if (track) {
          currentTrackDuration.value = track.duration_ms
        }
      }

      // Sync Spotify player if connected
      if (spotifyReady.value) {
        const track = currentTrack.value
        if (track?.spotify_id) {
          if (isPlaying.value) {
            await spotifyPlay(`spotify:track:${track.spotify_id}`, playbackPosition.value)
          } else {
            await spotifyPause()
            // Only seek if we have a valid position
            if (playbackPosition.value > 0) {
              await spotifySeek(playbackPosition.value)
            }
          }
        }
      }

      // Restart interval only if playing
      if (isPlaying.value) {
        startProgressInterval()
      }

      showToast(`Synced: ${formatDuration(playbackPosition.value)}`, 'success')
      return true
    } catch (e) {
      console.error('Failed to sync with server:', e)
      showToast('Sync failed', 'error')
      return false
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
    hasAlbum,
    currentTrack,
    progressPercent,

    // Methods
    joinSession,
    leaveSession,
    selectTrack,
    setAlbum,
    loadAlbumData,
    togglePlayback,
    seekTo,
    skipPrevious,
    skipNext,
    showToast,
    formatDuration,
    startProgressInterval,
    stopProgressInterval,
    connectWebSocket,
    syncWithServer
  }
}
