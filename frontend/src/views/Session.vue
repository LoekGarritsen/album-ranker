<script setup>
import { ref, onMounted, onUnmounted, inject, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Play, Pause, Users, Copy, Check, Star, ChevronLeft, Radio, SkipBack, SkipForward, Volume2, Music, Unplug, RefreshCw, Info } from 'lucide-vue-next'
import RatingModal from '../components/RatingModal.vue'
import TrackDetailModal from '../components/TrackDetailModal.vue'
import { useSpotifyPlayer } from '../composables/useSpotifyPlayer'
import { useSession } from '../composables/useSession'

const route = useRoute()
const router = useRouter()
const currentUser = inject('currentUser')

// Global session state
const {
  session,
  album,
  isPlaying,
  playbackPosition,
  currentTrackDuration,
  listeners,
  currentTrack,
  progressPercent,
  isInSession,
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
} = useSession()

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

const loading = ref(true)
const copied = ref(false)

// Sync state
const isSyncing = ref(false)
const isAutoAdvancing = ref(false)

// Rating modal state
const ratingModal = ref({ show: false, type: null, item: null, album: null })

// Track detail modal state
const trackDetailModal = ref({ show: false, trackId: null })

const sessionCode = computed(() => route.params.code)

async function loadSession() {
  if (!sessionCode.value) return

  loading.value = true
  try {
    // Check if already in this session
    if (session.value?.code === sessionCode.value) {
      // Already connected, just refresh Spotify state
      await initSpotifyIfNeeded()
      loading.value = false
      return
    }

    // Join the session using global store
    const success = await joinSession(sessionCode.value, currentUser.value)
    if (!success) {
      router.push('/')
      return
    }

    // Initialize Spotify player if connected
    await initSpotifyIfNeeded()

    // Start progress interval if playing (for non-Spotify users)
    if (isPlaying.value && !spotifyReady.value) {
      startProgressInterval()
    }
  } catch (e) {
    console.error('Failed to load session:', e)
  }
  loading.value = false
}

async function initSpotifyIfNeeded() {
  setSpotifyUserId(currentUser.value?.id)
  await checkSpotifyConnection()
  if (spotifyConnected.value) {
    await initSpotifyPlayer()
    if (spotifyReady.value) {
      startPositionTracking()
    }
  }
}

async function handleSelectTrack(trackId) {
  await selectTrack(trackId, currentUser.value)

  // Also trigger Spotify playback
  if (spotifyReady.value) {
    const track = album.value?.tracks?.find(t => t.id === trackId)
    if (track?.spotify_id) {
      await spotifyPlay(`spotify:track:${track.spotify_id}`, 0)
    }
  }
}

async function handleTogglePlayback() {
  const wasPlaying = isPlaying.value
  await togglePlayback(currentUser.value)

  // Handle Spotify playback
  if (spotifyReady.value) {
    if (!wasPlaying) {
      const track = currentTrack.value
      if (track?.spotify_id) {
        await spotifyPlay(`spotify:track:${track.spotify_id}`, playbackPosition.value)
      }
    } else {
      await spotifyPause()
    }
  }
}

async function handleSeekTo(percent) {
  await seekTo(percent, currentUser.value)

  if (spotifyReady.value) {
    const position = Math.floor((percent / 100) * currentTrackDuration.value)
    await spotifySeek(position)
  }
}

function handleProgressClick(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  const percent = ((event.clientX - rect.left) / rect.width) * 100
  handleSeekTo(Math.max(0, Math.min(100, percent)))
}

function handleSkipPrevious() {
  skipPrevious(currentUser.value)
}

function handleSkipNext() {
  skipNext(currentUser.value)
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

function openTrackDetail(track) {
  trackDetailModal.value = { show: true, trackId: track.id }
}

function closeTrackDetail() {
  trackDetailModal.value = { show: false, trackId: null }
}

function handleTrackDetailRate(track) {
  closeTrackDetail()
  openTrackRating(track)
}

async function submitRating(data) {
  const res = await fetch(`/api/rankings/track?session_code=${sessionCode.value}`, {
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

// Auto-advance to next track
async function autoAdvanceTrack() {
  if (isAutoAdvancing.value) return
  isAutoAdvancing.value = true

  try {
    const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
    if (trackIdx !== undefined && trackIdx >= 0 && trackIdx < album.value.tracks.length - 1) {
      const nextTrack = album.value.tracks[trackIdx + 1]
      await handleSelectTrack(nextTrack.id)
      isAutoAdvancing.value = false
    } else {
      // Last track, pause
      await handleTogglePlayback()
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
  // Don't cleanup session - keep it running in background
  // Only cleanup Spotify tracking for this view
  stopPositionTracking()
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
            class="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm"
            :class="listener.user_id === currentUser?.id ? 'bg-accent-primary/20 border border-accent-primary/50' : 'bg-white/10'"
          >
            <span class="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
            <span>{{ listener.user_name }}</span>
            <span v-if="listener.user_id === currentUser?.id" class="text-xs text-accent-primary">(you)</span>
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
              @click="handleSkipPrevious"
              class="p-2 hover:bg-white/10 rounded-full transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
            >
              <SkipBack class="w-5 h-5" />
            </button>
            <button
              @click="handleTogglePlayback"
              class="p-3 bg-accent-primary text-black rounded-full hover:bg-accent-primary/90 transition-colors min-h-[48px] min-w-[48px] flex items-center justify-center"
              :disabled="spotifyConnected && !spotifyReady"
              :class="{ 'opacity-50 cursor-not-allowed': spotifyConnected && !spotifyReady }"
            >
              <Pause v-if="isPlaying" class="w-6 h-6" />
              <Play v-else class="w-6 h-6 ml-0.5" />
            </button>
            <button
              @click="handleSkipNext"
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
          @click="handleSelectTrack(track.id)"
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

          <!-- Info button -->
          <button
            @click.stop="openTrackDetail(track)"
            class="p-2 hover:bg-white/10 rounded-lg transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center flex-shrink-0"
            title="Track info"
          >
            <Info class="w-4 h-4 text-slate-400" />
          </button>

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

    <!-- Track detail modal -->
    <TrackDetailModal
      v-if="trackDetailModal.show"
      :track-id="trackDetailModal.trackId"
      :current-user="currentUser"
      @close="closeTrackDetail"
      @rate="handleTrackDetailRate"
    />

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
