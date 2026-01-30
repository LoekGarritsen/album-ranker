<script setup>
import { ref, onMounted, onUnmounted, inject, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Play, Pause, Users, Copy, Check, Star, ChevronLeft, Radio, SkipBack, SkipForward, Volume2, Music, Unplug, RefreshCw } from 'lucide-vue-next'
import RatingModal from '../components/RatingModal.vue'
import { useSpotifyPlayer } from '../composables/useSpotifyPlayer'

const route = useRoute()
const router = useRouter()
const currentUser = inject('currentUser')

// Spotify player
const {
  isReady: spotifyReady,
  isConnected: spotifyConnected,
  isPaused: spotifyPaused,
  position: spotifyPosition,
  error: spotifyError,
  setUserId: setSpotifyUserId,
  checkConnection: checkSpotifyConnection,
  connect: connectSpotify,
  disconnect: disconnectSpotify,
  initPlayer: initSpotifyPlayer,
  play: spotifyPlay,
  pause: spotifyPause,
  resume: spotifyResume,
  seek: spotifySeek,
  startPositionTracking,
  stopPositionTracking,
  cleanup: cleanupSpotify
} = useSpotifyPlayer()

const session = ref(null)
const album = ref(null)
const loading = ref(true)
const copied = ref(false)
const ws = ref(null)

// Playback state
const isPlaying = ref(false)
const playbackPosition = ref(0)
const currentTrackDuration = ref(0)
const listeners = ref([])

// Playback interval for progress updates
let progressInterval = null
let pingInterval = null

// Sync state
const isSyncing = ref(false)
const isAutoAdvancing = ref(false)

// Rating modal state
const ratingModal = ref({ show: false, type: null, item: null, album: null })

const sessionCode = computed(() => route.params.code)

const currentTrack = computed(() => {
  if (!album.value?.tracks || !session.value?.current_track_id) return null
  return album.value.tracks.find(t => t.id === session.value.current_track_id)
})

const progressPercent = computed(() => {
  if (!currentTrackDuration.value) return 0
  return Math.min(100, (playbackPosition.value / currentTrackDuration.value) * 100)
})

async function loadSession() {
  if (!sessionCode.value) return

  loading.value = true
  try {
    const res = await fetch(`/api/sessions/${sessionCode.value}`)
    if (res.ok) {
      session.value = await res.json()
      currentTrackDuration.value = session.value.current_track_duration || 0
      isPlaying.value = session.value.playback?.is_playing || false
      playbackPosition.value = session.value.playback?.position || 0

      // Extract listeners from participants who are online
      listeners.value = session.value.participants?.filter(p => p.is_online) || []

      await loadAlbum()
      connectWebSocket()

      // Initialize Spotify player if connected
      setSpotifyUserId(currentUser.value?.id)
      await checkSpotifyConnection()
      if (spotifyConnected.value) {
        await initSpotifyPlayer()
        if (spotifyReady.value) {
          startPositionTracking()
        }
      }

      // Start progress interval if playing (for non-Spotify users)
      if (isPlaying.value && !spotifyReady.value) {
        startProgressInterval()
      }
    } else {
      router.push('/')
    }
  } catch (e) {
    console.error('Failed to load session:', e)
  }
  loading.value = false
}

async function loadAlbum() {
  if (!session.value?.album_id) return

  try {
    const res = await fetch('/api/albums')
    if (res.ok) {
      const albums = await res.json()
      album.value = albums.find(a => a.id === session.value.album_id)

      // Update duration if we have a current track
      if (currentTrack.value) {
        currentTrackDuration.value = currentTrack.value.duration_ms
      }
    }
  } catch (e) {
    console.error('Failed to load album:', e)
  }
}

function connectWebSocket() {
  // Clear any existing ping interval
  if (pingInterval) {
    clearInterval(pingInterval)
    pingInterval = null
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const userId = currentUser.value?.id || ''
  const wsUrl = `${protocol}//${window.location.host}/api/sessions/${sessionCode.value}/ws?user_id=${userId}`

  ws.value = new WebSocket(wsUrl)

  ws.value.onmessage = (event) => {
    const data = JSON.parse(event.data)
    handleWebSocketMessage(data)
  }

  ws.value.onopen = () => {
    // Keep connection alive with pings
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
    stopProgressInterval()
    // Attempt to reconnect after 3 seconds
    setTimeout(() => {
      if (session.value?.is_active) {
        connectWebSocket()
      }
    }, 3000)
  }
}

async function handleWebSocketMessage(data) {
  switch (data.type) {
    case 'sync':
      session.value.current_track_id = data.track_id
      isPlaying.value = data.is_playing
      playbackPosition.value = data.position
      listeners.value = data.listeners || []

      // Sync Spotify playback if ready
      if (spotifyReady.value && data.is_playing) {
        const track = album.value?.tracks?.find(t => t.id === data.track_id)
        if (track?.spotify_id) {
          await spotifyPlay(`spotify:track:${track.spotify_id}`, data.position)
        }
      }

      if (data.is_playing && !spotifyReady.value) {
        startProgressInterval()
      }
      break

    case 'track_change':
      // Stop any existing progress tracking
      stopProgressInterval()

      session.value.current_track_id = data.track_id
      currentTrackDuration.value = data.duration || 0
      playbackPosition.value = data.position || 0
      isPlaying.value = data.is_playing || false

      // Pause Spotify when track changes (user needs to press play)
      if (spotifyReady.value) {
        await spotifyPause()
      }

      // Only start progress interval for non-Spotify users when playing
      if (isPlaying.value && !spotifyReady.value) {
        startProgressInterval()
      }
      break

    case 'playback':
      if (data.action === 'play') {
        isPlaying.value = true
        playbackPosition.value = data.position

        // Start Spotify playback
        if (spotifyReady.value) {
          const track = currentTrack.value
          if (track?.spotify_id) {
            await spotifyPlay(`spotify:track:${track.spotify_id}`, data.position)
          }
        } else {
          startProgressInterval()
        }
      } else if (data.action === 'pause') {
        isPlaying.value = false
        playbackPosition.value = data.position

        if (spotifyReady.value) {
          await spotifyPause()
        }
        stopProgressInterval()
      } else if (data.action === 'seek') {
        playbackPosition.value = data.position

        if (spotifyReady.value) {
          await spotifySeek(data.position)
        }
      }
      break

    case 'user_joined':
      // Add to listeners if not already there
      if (!listeners.value.find(l => l.user_id === data.user_id)) {
        listeners.value.push({ user_id: data.user_id, user_name: data.user_name })
      }
      break

    case 'user_left':
      listeners.value = listeners.value.filter(l => l.user_id !== data.user_id)
      break
  }
}

function startProgressInterval() {
  stopProgressInterval()
  progressInterval = setInterval(() => {
    if (isPlaying.value && currentTrackDuration.value > 0 && !isAutoAdvancing.value) {
      const newPosition = playbackPosition.value + 100
      // Cap position at duration
      if (newPosition >= currentTrackDuration.value) {
        playbackPosition.value = currentTrackDuration.value
        stopProgressInterval()
        // Track ended, auto-advance to next
        autoAdvanceTrack()
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

async function selectTrack(trackId) {
  try {
    await fetch(`/api/sessions/${sessionCode.value}/track?track_id=${trackId}`, {
      method: 'POST',
      headers: { 'X-User-Id': currentUser.value?.id?.toString() || '' }
    })
    session.value.current_track_id = trackId
    const track = album.value?.tracks?.find(t => t.id === trackId)
    if (track) {
      currentTrackDuration.value = track.duration_ms

      // If Spotify is ready, pause any current playback
      if (spotifyReady.value) {
        await spotifyPause()
      }
    }
    playbackPosition.value = 0
    isPlaying.value = false
    stopProgressInterval()
  } catch (e) {
    console.error('Failed to update track:', e)
  }
}

async function togglePlayback() {
  const action = isPlaying.value ? 'pause' : 'play'

  // Handle Spotify playback
  if (spotifyReady.value) {
    if (action === 'play') {
      const track = currentTrack.value
      if (track?.spotify_id) {
        const spotifyUri = `spotify:track:${track.spotify_id}`
        const success = await spotifyPlay(spotifyUri, playbackPosition.value)
        if (!success) {
          console.error('Spotify playback failed')
        }
      }
    } else {
      await spotifyPause()
    }
  }

  // Always broadcast to sync other users
  try {
    await fetch(`/api/sessions/${sessionCode.value}/playback?action=${action}`, {
      method: 'POST',
      headers: { 'X-User-Id': currentUser.value?.id?.toString() || '' }
    })
  } catch (e) {
    console.error('Failed to toggle playback:', e)
  }
}

async function seekTo(percent) {
  const position = Math.floor((percent / 100) * currentTrackDuration.value)
  playbackPosition.value = position

  // Seek in Spotify if ready
  if (spotifyReady.value) {
    await spotifySeek(position)
  }

  try {
    await fetch(`/api/sessions/${sessionCode.value}/playback?action=seek&position=${position}`, {
      method: 'POST',
      headers: { 'X-User-Id': currentUser.value?.id?.toString() || '' }
    })
  } catch (e) {
    console.error('Failed to seek:', e)
  }
}

function handleProgressClick(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  const percent = ((event.clientX - rect.left) / rect.width) * 100
  seekTo(Math.max(0, Math.min(100, percent)))
}

function skipPrevious() {
  const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value.current_track_id)
  if (trackIdx > 0) {
    selectTrack(album.value.tracks[trackIdx - 1].id)
  }
}

function skipNext() {
  const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value.current_track_id)
  if (trackIdx !== undefined && trackIdx < album.value.tracks.length - 1) {
    selectTrack(album.value.tracks[trackIdx + 1].id)
  }
}

async function copyCode() {
  await navigator.clipboard.writeText(sessionCode.value)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

function openTrackRating(track) {
  ratingModal.value = { show: true, type: 'track', item: track, album: album.value }
}

function closeRating() {
  ratingModal.value = { show: false, type: null, item: null, album: null }
}

async function submitRating(data) {
  const res = await fetch('/api/rankings/track', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      track_id: ratingModal.value.item.id,
      user_id: currentUser.value.id,
      score: data.score,
      comment: data.comment || null
    })
  })

  if (res.ok) {
    await loadAlbum()
    closeRating()
  }
}

function getScoreColor(score) {
  if (!score) return 'text-slate-500'
  if (score >= 8) return 'text-green-400'
  if (score >= 6) return 'text-yellow-400'
  if (score >= 4) return 'text-orange-400'
  return 'text-red-400'
}

function getUserRanking(rankings) {
  return rankings?.find(r => r.user_id === currentUser.value?.id)
}

function formatDuration(ms) {
  if (!ms) return '0:00'
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

// Auto-advance to next track
async function autoAdvanceTrack() {
  if (isAutoAdvancing.value) return
  isAutoAdvancing.value = true

  try {
    const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value.current_track_id)
    if (trackIdx !== undefined && trackIdx >= 0 && trackIdx < album.value.tracks.length - 1) {
      const nextTrack = album.value.tracks[trackIdx + 1]
      await selectTrack(nextTrack.id)
      // Small delay to let state settle, then auto-play
      setTimeout(() => {
        togglePlayback()
        isAutoAdvancing.value = false
      }, 300)
    } else {
      // Last track, pause
      isPlaying.value = false
      if (spotifyReady.value) {
        await spotifyPause()
      }
      isAutoAdvancing.value = false
    }
  } catch (e) {
    console.error('Auto-advance failed:', e)
    isAutoAdvancing.value = false
  }
}

// Sync position from Spotify player and handle track end
watch(spotifyPosition, (pos) => {
  if (spotifyReady.value && !spotifyPaused.value) {
    playbackPosition.value = pos

    // Check if track has ended (within 1.5 seconds of end to account for polling delay)
    if (!isAutoAdvancing.value && currentTrackDuration.value > 0 && pos >= currentTrackDuration.value - 1500) {
      autoAdvanceTrack()
    }
  }
})

// Handle Spotify connect button
async function handleSpotifyConnect() {
  if (spotifyConnected.value) {
    await disconnectSpotify()
  } else {
    await connectSpotify()
  }
}

// Sync audio with session state
async function syncAudio() {
  if (!spotifyReady.value || !currentTrack.value?.spotify_id || isSyncing.value) return

  isSyncing.value = true
  try {
    // Fetch latest session state from server
    const res = await fetch(`/api/sessions/${sessionCode.value}`)
    if (!res.ok) return

    const sessionData = await res.json()
    const serverPosition = sessionData.playback?.position || 0
    const serverIsPlaying = sessionData.playback?.is_playing || false
    const serverTrackId = sessionData.current_track_id

    // Find the track
    const track = album.value?.tracks?.find(t => t.id === serverTrackId)
    if (!track?.spotify_id) return

    // Update local state
    playbackPosition.value = serverPosition
    isPlaying.value = serverIsPlaying
    session.value.current_track_id = serverTrackId

    // Sync Spotify player
    if (serverIsPlaying) {
      await spotifyPlay(`spotify:track:${track.spotify_id}`, serverPosition)
    } else {
      await spotifyPause()
      await spotifySeek(serverPosition)
    }
  } catch (e) {
    console.error('Failed to sync audio:', e)
  } finally {
    isSyncing.value = false
  }
}

onMounted(loadSession)

onUnmounted(() => {
  stopProgressInterval()
  stopPositionTracking()
  cleanupSpotify()
  if (pingInterval) {
    clearInterval(pingInterval)
    pingInterval = null
  }
  if (ws.value) {
    ws.value.close()
  }
})
</script>

<template>
  <div>
    <router-link to="/" class="inline-flex items-center gap-2 text-slate-400 hover:text-white mb-6 py-2 min-h-[44px]">
      <ChevronLeft class="w-4 h-4" />
      Back to Albums
    </router-link>

    <div v-if="loading" class="text-center py-12 text-slate-400">
      Loading session...
    </div>

    <div v-else-if="session && album">
      <!-- Session Header -->
      <div class="glass p-4 sm:p-6 mb-4">
        <div class="flex flex-col sm:flex-row items-center sm:items-start gap-4 sm:gap-6">
          <img
            :src="album.cover_url || '/placeholder.svg'"
            class="w-24 h-24 sm:w-32 sm:h-32 rounded-xl object-cover bg-white/10"
          />
          <div class="flex-1 text-center sm:text-left">
            <div class="flex items-center justify-center sm:justify-start gap-2 text-accent-primary text-sm mb-2">
              <Radio class="w-4 h-4 animate-pulse" />
              Listening Session
            </div>
            <h1 class="text-xl sm:text-2xl font-heading font-bold mb-1">{{ album.name }}</h1>
            <p class="text-slate-400 mb-4">{{ album.artist }}</p>

            <!-- Session Code -->
            <div class="flex items-center justify-center sm:justify-start gap-3">
              <div class="px-4 py-2 bg-white/10 rounded-lg font-mono text-base sm:text-lg tracking-wider">
                {{ sessionCode }}
              </div>
              <button
                @click="copyCode"
                class="p-2 glass glass-hover rounded-lg min-h-[44px] min-w-[44px] flex items-center justify-center"
              >
                <Check v-if="copied" class="w-5 h-5 text-green-400" />
                <Copy v-else class="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Live Listeners -->
      <div class="glass p-4 mb-4">
        <div class="flex items-center gap-3 mb-3">
          <Users class="w-5 h-5 text-accent-primary" />
          <span class="font-medium">Listening Now</span>
          <span class="text-sm text-slate-400">({{ listeners.length }})</span>
        </div>
        <div class="flex flex-wrap gap-2">
          <div
            v-for="listener in listeners"
            :key="listener.user_id"
            class="flex items-center gap-2 px-3 py-1.5 bg-white/10 rounded-full text-sm"
          >
            <span class="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
            <span>{{ listener.user_name }}</span>
          </div>
          <div v-if="listeners.length === 0" class="text-slate-500 text-sm">
            No one is listening yet
          </div>
        </div>
      </div>

      <!-- Spotify Connect Banner -->
      <div v-if="!spotifyConnected" class="glass p-4 mb-4 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-[#1DB954] rounded-full flex items-center justify-center">
            <Music class="w-5 h-5 text-black" />
          </div>
          <div>
            <p class="font-medium text-sm sm:text-base">Connect Spotify</p>
            <p class="text-xs text-slate-400">Play music in sync with others (Premium required)</p>
          </div>
        </div>
        <button
          @click="handleSpotifyConnect"
          class="px-4 py-2 bg-[#1DB954] text-black font-medium rounded-full hover:bg-[#1ed760] transition-colors text-sm min-h-[44px]"
        >
          Connect
        </button>
      </div>

      <!-- Spotify Status Banner (when connected) -->
      <div v-else-if="spotifyConnected && !spotifyReady" class="glass p-4 mb-4 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-[#1DB954] rounded-full flex items-center justify-center animate-pulse">
            <Music class="w-5 h-5 text-black" />
          </div>
          <div>
            <p class="font-medium text-sm sm:text-base">Spotify Connected</p>
            <p class="text-xs text-slate-400">{{ spotifyError || 'Initializing player...' }}</p>
          </div>
        </div>
        <button
          @click="handleSpotifyConnect"
          class="p-2 hover:bg-white/10 rounded-full transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
          title="Disconnect Spotify"
        >
          <Unplug class="w-5 h-5 text-slate-400" />
        </button>
      </div>

      <!-- Playbar -->
      <div class="glass p-4 mb-4">
        <!-- Spotify ready indicator -->
        <div v-if="spotifyReady" class="flex items-center gap-2 mb-3 text-xs text-[#1DB954]">
          <Music class="w-3 h-3" />
          <span>Playing via Spotify</span>
          <button
            @click="syncAudio"
            :disabled="isSyncing"
            class="ml-auto flex items-center gap-1 px-2 py-1 text-slate-400 hover:text-white hover:bg-white/10 rounded transition-colors disabled:opacity-50"
            title="Sync audio with session"
          >
            <RefreshCw class="w-3 h-3" :class="{ 'animate-spin': isSyncing }" />
            <span>Sync</span>
          </button>
          <button
            @click="handleSpotifyConnect"
            class="text-slate-400 hover:text-white transition-colors"
          >
            Disconnect
          </button>
        </div>

        <div class="flex items-center gap-4">
          <!-- Track info -->
          <div class="flex items-center gap-3 flex-1 min-w-0">
            <img
              :src="album.cover_url || '/placeholder.svg'"
              class="w-12 h-12 rounded object-cover bg-white/10 flex-shrink-0"
            />
            <div class="min-w-0">
              <p class="truncate font-medium text-sm sm:text-base" :class="{ 'text-accent-primary': isPlaying }">
                {{ currentTrack?.name || 'No track selected' }}
              </p>
              <p class="text-xs text-slate-500">{{ album.artist }}</p>
            </div>
          </div>

          <!-- Playback controls -->
          <div class="flex items-center gap-2">
            <button
              @click="skipPrevious"
              class="p-2 hover:bg-white/10 rounded-full transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
            >
              <SkipBack class="w-5 h-5" />
            </button>
            <button
              @click="togglePlayback"
              class="p-3 bg-accent-primary text-black rounded-full hover:bg-accent-primary/90 transition-colors min-h-[48px] min-w-[48px] flex items-center justify-center"
              :disabled="spotifyConnected && !spotifyReady"
              :class="{ 'opacity-50 cursor-not-allowed': spotifyConnected && !spotifyReady }"
            >
              <Pause v-if="isPlaying" class="w-6 h-6" />
              <Play v-else class="w-6 h-6 ml-0.5" />
            </button>
            <button
              @click="skipNext"
              class="p-2 hover:bg-white/10 rounded-full transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
            >
              <SkipForward class="w-5 h-5" />
            </button>
          </div>
        </div>

        <!-- Progress bar -->
        <div class="mt-4">
          <div
            class="relative h-2 bg-white/10 rounded-full cursor-pointer group"
            @click="handleProgressClick"
          >
            <div
              class="absolute left-0 top-0 h-full bg-accent-primary rounded-full transition-all"
              :style="{ width: progressPercent + '%' }"
            ></div>
            <div
              class="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-white rounded-full shadow-lg opacity-0 group-hover:opacity-100 transition-opacity"
              :style="{ left: progressPercent + '%', transform: 'translate(-50%, -50%)' }"
            ></div>
          </div>
          <div class="flex justify-between text-xs text-slate-500 mt-1">
            <span>{{ formatDuration(playbackPosition) }}</span>
            <span>{{ formatDuration(currentTrackDuration) }}</span>
          </div>
        </div>
      </div>

      <!-- Track List -->
      <div class="glass overflow-hidden">
        <div
          v-for="track in album.tracks"
          :key="track.id"
          @click="selectTrack(track.id)"
          class="flex items-center gap-2 sm:gap-4 px-3 sm:px-4 py-3 cursor-pointer transition-colors border-b border-white/5 last:border-0"
          :class="session.current_track_id === track.id ? 'bg-accent-primary/10' : 'hover:bg-white/5'"
        >
          <div class="w-6 sm:w-8 text-center flex-shrink-0">
            <div v-if="session.current_track_id === track.id && isPlaying" class="flex items-center justify-center gap-0.5">
              <span class="w-1 h-3 bg-accent-primary rounded-full animate-pulse"></span>
              <span class="w-1 h-4 bg-accent-primary rounded-full animate-pulse" style="animation-delay: 0.2s"></span>
              <span class="w-1 h-2 bg-accent-primary rounded-full animate-pulse" style="animation-delay: 0.4s"></span>
            </div>
            <Play
              v-else-if="session.current_track_id === track.id"
              class="w-4 h-4 text-accent-primary mx-auto"
            />
            <span v-else class="text-xs sm:text-sm text-slate-500">{{ track.track_number }}</span>
          </div>

          <div class="flex-1 min-w-0">
            <p class="truncate text-sm sm:text-base" :class="session.current_track_id === track.id ? 'text-accent-primary font-medium' : ''">
              {{ track.name }}
            </p>
            <p class="text-xs text-slate-500">{{ formatDuration(track.duration_ms) }}</p>
          </div>

          <!-- Scores - hidden on small screens -->
          <div class="hidden sm:flex items-center gap-3">
            <div v-for="ranking in track.rankings" :key="ranking.user_id" class="text-center">
              <div class="text-xs text-slate-500">{{ ranking.user_name?.split(' ')[0] }}</div>
              <div class="font-heading font-bold" :class="getScoreColor(ranking.score)">
                {{ ranking.score?.toFixed(1) || '-' }}
              </div>
            </div>
          </div>

          <!-- Rate button -->
          <button
            @click.stop="openTrackRating(track)"
            class="flex items-center gap-1 px-2 sm:px-3 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors text-sm min-h-[44px] min-w-[44px] justify-center flex-shrink-0"
          >
            <Star class="w-3 h-3" />
            <span class="hidden sm:inline">{{ getUserRanking(track.rankings)?.score?.toFixed(1) || 'Rate' }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Rating modal -->
    <RatingModal
      v-if="ratingModal.show"
      :type="ratingModal.type"
      :item="ratingModal.item"
      :album="ratingModal.album"
      :current-user="currentUser"
      @close="closeRating"
      @submit="submitRating"
    />
  </div>
</template>
