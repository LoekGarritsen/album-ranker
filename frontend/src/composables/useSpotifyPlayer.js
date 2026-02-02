import { ref, onMounted, onUnmounted } from 'vue'

// Singleton state
const player = ref(null)
const deviceId = ref(null)
const isReady = ref(false)
const isConnected = ref(false)
const currentTrack = ref(null)
const isPaused = ref(true)
const position = ref(0)
const duration = ref(0)
const volume = ref(50)
const error = ref(null)
const currentUserId = ref(null)
const trackEnded = ref(false) // Fires when a track naturally finishes

let sdkLoaded = false
let previousState = null // Track previous state for end detection
let sdkLoadPromise = null
let positionInterval = null

// Load Spotify SDK script
function loadSpotifySDK() {
  if (sdkLoadPromise) return sdkLoadPromise

  sdkLoadPromise = new Promise((resolve) => {
    if (window.Spotify) {
      sdkLoaded = true
      resolve()
      return
    }

    window.onSpotifyWebPlaybackSDKReady = () => {
      sdkLoaded = true
      resolve()
    }

    const script = document.createElement('script')
    script.src = 'https://sdk.scdn.co/spotify-player.js'
    script.async = true
    document.body.appendChild(script)
  })

  return sdkLoadPromise
}

export function useSpotifyPlayer() {
  function setUserId(userId) {
    currentUserId.value = userId
  }

  function getHeaders() {
    const headers = {}
    if (currentUserId.value) {
      headers['X-User-Id'] = currentUserId.value.toString()
    }
    return headers
  }

  async function checkConnection() {
    if (!currentUserId.value) {
      isConnected.value = false
      return false
    }
    try {
      const res = await fetch('/api/spotify/status', { headers: getHeaders() })
      const data = await res.json()
      isConnected.value = data.connected
      return data.connected
    } catch (e) {
      isConnected.value = false
      return false
    }
  }

  async function connect() {
    if (!currentUserId.value) {
      error.value = 'Please select a user first'
      return
    }
    try {
      const res = await fetch('/api/spotify/auth', { headers: getHeaders() })
      const data = await res.json()
      // Redirect to Spotify auth
      window.location.href = data.auth_url
    } catch (e) {
      error.value = 'Failed to start Spotify connection'
    }
  }

  async function disconnect() {
    if (!currentUserId.value) return
    try {
      await fetch('/api/spotify/disconnect', {
        method: 'DELETE',
        headers: getHeaders()
      })
      isConnected.value = false
      if (player.value) {
        player.value.disconnect()
        player.value = null
      }
      deviceId.value = null
      isReady.value = false
    } catch (e) {
      error.value = 'Failed to disconnect Spotify'
    }
  }

  async function getAccessToken() {
    if (!currentUserId.value) return null
    try {
      const res = await fetch('/api/spotify/token', { headers: getHeaders() })
      if (!res.ok) {
        if (res.status === 404) {
          isConnected.value = false
          return null
        }
        throw new Error('Token fetch failed')
      }
      const data = await res.json()
      return data.access_token
    } catch (e) {
      error.value = 'Failed to get Spotify token'
      return null
    }
  }

  async function initPlayer() {
    const connected = await checkConnection()
    if (!connected) return false

    await loadSpotifySDK()

    const token = await getAccessToken()
    if (!token) return false

    return new Promise((resolve) => {
      player.value = new window.Spotify.Player({
        name: 'Album Ranker',
        getOAuthToken: async (cb) => {
          const freshToken = await getAccessToken()
          cb(freshToken)
        },
        volume: volume.value / 100
      })

      player.value.addListener('ready', ({ device_id }) => {
        deviceId.value = device_id
        isReady.value = true
        error.value = null
        resolve(true)
      })

      player.value.addListener('not_ready', () => {
        isReady.value = false
        deviceId.value = null
      })

      player.value.addListener('player_state_changed', (state) => {
        if (!state) return

        currentTrack.value = state.track_window.current_track
        isPaused.value = state.paused
        position.value = state.position
        duration.value = state.duration

        // Detect natural track end using multiple signals
        // See: https://github.com/spotify/web-playback-sdk/issues/35
        // See: https://github.com/spotify/web-playback-sdk/issues/85
        // When a track ends naturally:
        // - First event: paused=true, position near duration
        // - Second event: paused=true, position=0
        // Current track may also appear in previous_tracks
        const currentTrackId = state.track_window.current_track?.id
        const inPreviousTracks = state.track_window.previous_tracks?.some(
          t => t.id === currentTrackId
        )
        const nearEnd = state.duration > 0 && state.position >= state.duration - 2000

        if (previousState && !previousState.paused && state.paused) {
          // Transition from playing to paused
          // Track ended if position is near end OR track moved to previous_tracks
          if (nearEnd || inPreviousTracks) {
            trackEnded.value = true
          }
        }

        // Reset when playback resumes
        if (!state.paused) {
          trackEnded.value = false
        }

        // Store state for next comparison
        previousState = {
          paused: state.paused,
          position: state.position,
          track_id: currentTrackId
        }
      })

      player.value.addListener('initialization_error', ({ message }) => {
        error.value = `Init error: ${message}`
        resolve(false)
      })

      player.value.addListener('authentication_error', ({ message }) => {
        error.value = `Auth error: ${message}`
        isConnected.value = false
        resolve(false)
      })

      player.value.addListener('account_error', ({ message }) => {
        error.value = `Account error: ${message}. Spotify Premium required.`
        resolve(false)
      })

      player.value.connect()

      // Timeout after 10 seconds
      setTimeout(() => {
        if (!isReady.value) {
          error.value = 'Failed to connect to Spotify'
          resolve(false)
        }
      }, 10000)
    })
  }

  async function transferPlayback() {
    if (!deviceId.value) return false

    const token = await getAccessToken()
    if (!token) return false

    try {
      // Transfer playback to this device
      const res = await fetch('https://api.spotify.com/v1/me/player', {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          device_ids: [deviceId.value],
          play: false
        })
      })

      if (!res.ok && res.status !== 204) {
        console.error('Transfer playback failed:', res.status)
        return false
      }

      return true
    } catch (e) {
      console.error('Transfer playback error:', e)
      return false
    }
  }

  async function play(spotifyUri, positionMs = 0) {
    if (!isReady.value || !deviceId.value) {
      error.value = 'Player not ready'
      return false
    }

    const token = await getAccessToken()
    if (!token) return false

    try {
      // First, ensure this device is active
      await transferPlayback()

      // Small delay to let transfer complete
      await new Promise(resolve => setTimeout(resolve, 200))

      // Now start playback
      const res = await fetch(`https://api.spotify.com/v1/me/player/play?device_id=${deviceId.value}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          uris: [spotifyUri],
          position_ms: positionMs
        })
      })

      if (!res.ok && res.status !== 204) {
        const data = await res.json().catch(() => ({}))
        const reason = data.error?.reason || data.error?.message || `Status ${res.status}`
        console.error('Spotify play error:', data)

        // Handle specific errors
        if (res.status === 403) {
          if (reason.includes('PREMIUM_REQUIRED')) {
            throw new Error('Spotify Premium required for playback')
          }
          throw new Error(`Playback forbidden: ${reason}. Try disconnecting and reconnecting Spotify.`)
        }
        throw new Error(reason)
      }

      isPaused.value = false
      return true
    } catch (e) {
      error.value = `Play failed: ${e.message}`
      console.error('Spotify playback failed:', e.message)
      return false
    }
  }

  async function pause() {
    if (player.value) {
      await player.value.pause()
      isPaused.value = true
    }
  }

  async function resume() {
    if (player.value) {
      await player.value.resume()
      isPaused.value = false
    }
  }

  async function seek(positionMs) {
    if (player.value) {
      await player.value.seek(positionMs)
      position.value = positionMs
    }
  }

  async function setVolume(vol) {
    volume.value = vol
    if (player.value) {
      await player.value.setVolume(vol / 100)
    }
  }

  function startPositionTracking() {
    stopPositionTracking()
    positionInterval = setInterval(async () => {
      if (player.value && !isPaused.value) {
        const state = await player.value.getCurrentState()
        if (state) {
          position.value = state.position
        }
      }
    }, 1000)
  }

  function stopPositionTracking() {
    if (positionInterval) {
      clearInterval(positionInterval)
      positionInterval = null
    }
  }

  function cleanup() {
    stopPositionTracking()
    if (player.value) {
      player.value.disconnect()
    }
  }

  return {
    // State
    player,
    deviceId,
    isReady,
    isConnected,
    currentTrack,
    isPaused,
    position,
    duration,
    volume,
    error,
    trackEnded,

    // Methods
    setUserId,
    checkConnection,
    connect,
    disconnect,
    initPlayer,
    play,
    pause,
    resume,
    seek,
    setVolume,
    startPositionTracking,
    stopPositionTracking,
    cleanup,
    getAccessToken
  }
}
