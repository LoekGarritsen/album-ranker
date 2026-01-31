<script setup>
import { ref, onMounted, onUnmounted, inject, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Play, Pause, Users, Copy, Check, Star, ChevronLeft, Radio, SkipBack, SkipForward, Volume2, Music, Unplug, RefreshCw, Info, Disc3, Search, X } from 'lucide-vue-next'
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
  hasAlbum,
  joinSession,
  leaveSession,
  selectTrack,
  setAlbum,
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

async function handleSyncAudio() {
  if (isSyncing.value) return
  isSyncing.value = true
  await syncWithServer()
  isSyncing.value = false
}

// Rating modal state
const ratingModal = ref({ show: false, type: null, item: null, album: null })

// Track detail modal state
const trackDetailModal = ref({ show: false, trackId: null })

// Album picker state
const showAlbumPicker = ref(false)
const allAlbums = ref([])
const albumSearch = ref('')
const loadingAlbums = ref(false)
const settingAlbum = ref(false)

const filteredAlbums = computed(() => {
  if (!albumSearch.value.trim()) return allAlbums.value
  const search = albumSearch.value.toLowerCase()
  return allAlbums.value.filter(a =>
    a.name.toLowerCase().includes(search) ||
    a.artist.toLowerCase().includes(search)
  )
})

const sessionCode = computed(() => route.params.code)

async function loadSession() {
  if (!sessionCode.value) return

  loading.value = true

  try {
    // Check if already in this session
    if (session.value?.code === sessionCode.value) {
      // Already connected, just refresh Spotify state
      loading.value = false
      initSpotifyIfNeeded()
      return
    }

    // Join the session using global store
    const success = await joinSession(sessionCode.value, currentUser.value)
    if (!success) {
      router.push('/')
      return
    }

    // Start progress interval if playing (for non-Spotify users)
    if (isPlaying.value && !spotifyReady.value) {
      startProgressInterval()
    }
  } catch (e) {
    console.error('Failed to load session:', e)
  }
  loading.value = false

  // Initialize Spotify player in background (don't block loading)
  initSpotifyIfNeeded()
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

async function openAlbumPicker() {
  showAlbumPicker.value = true
  albumSearch.value = ''
  if (allAlbums.value.length === 0) {
    await loadAllAlbums()
  }
}

function closeAlbumPicker() {
  showAlbumPicker.value = false
  albumSearch.value = ''
}

async function loadAllAlbums() {
  loadingAlbums.value = true
  try {
    const res = await fetch('/api/albums')
    if (res.ok) {
      allAlbums.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to load albums:', e)
  }
  loadingAlbums.value = false
}

async function handleSelectAlbum(selectedAlbum) {
  settingAlbum.value = true
  const success = await setAlbum(selectedAlbum.id, currentUser.value)
  settingAlbum.value = false
  if (success) {
    closeAlbumPicker()
  }
}

async function handleSelectTrack(trackId) {
  // selectTrack handles both backend sync and Spotify playback
  await selectTrack(trackId, currentUser.value)
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

// When Spotify position drifts from room position, sync Spotify to room (room is source of truth)
watch(spotifyPosition, async (spotifyPos) => {
  if (!spotifyReady.value || spotifyPaused.value || isSyncing.value) return

  // Check for track end (auto-advance)
  if (!isAutoAdvancing.value && currentTrackDuration.value > 0 && spotifyPos >= currentTrackDuration.value - 1500) {
    autoAdvanceTrack()
    return
  }

  // Room position is source of truth - check if Spotify drifted too far
  const drift = Math.abs(playbackPosition.value - spotifyPos)
  if (drift > 2000) { // More than 2 seconds drift
    console.log(`Spotify drift detected: ${drift}ms, syncing Spotify to room position ${playbackPosition.value}ms`)
    await spotifySeek(playbackPosition.value)
  }
})

// When Spotify pauses locally (not via room controls), sync it back to room state
watch(spotifyPaused, async (paused, wasPaused) => {
  if (!spotifyReady.value || isSyncing.value) return

  // Spotify was playing and is now paused, but room is still playing
  if (paused && !wasPaused && isPlaying.value) {
    console.log('Spotify paused locally but room is playing, resuming Spotify')
    const track = currentTrack.value
    if (track?.spotify_id) {
      // Resume Spotify at room position
      await spotifyPlay(`spotify:track:${track.spotify_id}`, playbackPosition.value)
    }
  }
  // Spotify was paused and is now playing, but room is paused
  else if (!paused && wasPaused && !isPlaying.value) {
    console.log('Spotify resumed locally but room is paused, pausing Spotify')
    await spotifyPause()
  }
})

// Sync Spotify player when room playback state changes (e.g., another user plays/pauses)
watch(isPlaying, async (roomIsPlaying, wasPlaying) => {
  if (!spotifyReady.value || isSyncing.value) return

  const track = currentTrack.value
  if (!track?.spotify_id) return

  // Room started playing - sync Spotify to play
  if (roomIsPlaying && !wasPlaying) {
    if (spotifyPaused.value) {
      console.log('Room started playing, starting Spotify at position', playbackPosition.value)
      await spotifyPlay(`spotify:track:${track.spotify_id}`, playbackPosition.value)
    }
  }
  // Room paused - pause Spotify
  else if (!roomIsPlaying && wasPlaying) {
    if (!spotifyPaused.value) {
      console.log('Room paused, pausing Spotify')
      await spotifyPause()
    }
  }
})

// Redirect to rooms if session is ended (deleted by admin)
watch(session, (newSession) => {
  if (newSession === null && !loading.value) {
    router.push('/rooms')
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

    <div v-else-if="session">
      <!-- Session Header -->
      <div class="glass p-4 sm:p-6 mb-4">
        <div class="flex flex-col sm:flex-row items-center sm:items-start gap-4 sm:gap-6">
          <div class="relative">
            <img
              v-if="album?.cover_url"
              :src="album.cover_url"
              class="w-24 h-24 sm:w-32 sm:h-32 rounded-xl object-cover bg-white/10"
            />
            <div v-else class="w-24 h-24 sm:w-32 sm:h-32 rounded-xl bg-white/10 flex items-center justify-center">
              <Disc3 class="w-12 h-12 text-slate-500" />
            </div>
          </div>
          <div class="flex-1 text-center sm:text-left">
            <div class="flex items-center justify-center sm:justify-start gap-2 text-accent-primary text-sm mb-2">
              <Radio class="w-4 h-4 animate-pulse" />
              {{ session.name }}
            </div>
            <h1 v-if="album" class="text-xl sm:text-2xl font-heading font-bold mb-1">{{ album.name }}</h1>
            <h1 v-else class="text-xl sm:text-2xl font-heading font-bold mb-1 text-slate-400">No album selected</h1>
            <p v-if="album" class="text-slate-400 mb-4">{{ album.artist }}</p>
            <p v-else class="text-slate-500 mb-4">Select an album to start listening</p>

            <!-- Session Code + Change Album -->
            <div class="flex items-center justify-center sm:justify-start gap-3 flex-wrap">
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
              <button
                @click="openAlbumPicker"
                class="flex items-center gap-2 px-3 py-2 glass glass-hover rounded-lg text-sm min-h-[44px]"
              >
                <Disc3 class="w-4 h-4" />
                {{ album ? 'Change Album' : 'Select Album' }}
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

      <!-- Album Picker Prompt (when no album) -->
      <div v-if="!hasAlbum" class="glass p-8 mb-4 text-center">
        <Disc3 class="w-16 h-16 mx-auto mb-4 text-slate-500" />
        <h2 class="text-xl font-heading font-medium text-slate-300 mb-2">No album selected</h2>
        <p class="text-slate-500 mb-6">Choose an album to start listening together</p>
        <button
          @click="openAlbumPicker"
          class="inline-flex items-center gap-2 px-6 py-3 bg-accent-primary text-black font-medium rounded-xl hover:bg-accent-primary/90 transition-colors"
        >
          <Disc3 class="w-5 h-5" />
          Select Album
        </button>
      </div>

      <!-- Spotify Connect Banner (only when album is selected) -->
      <div v-if="hasAlbum && !spotifyConnected" class="glass p-4 mb-4 flex items-center justify-between">
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

      <!-- Spotify Status Banner (when initializing, only when album is selected) -->
      <div v-else-if="hasAlbum && spotifyConnected && !spotifyReady" class="glass p-4 mb-4 flex items-center justify-between">
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

      <!-- Spotify Ready Banner (when fully connected and ready) -->
      <div v-else-if="hasAlbum && spotifyReady" class="glass p-4 mb-4 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 bg-[#1DB954] rounded-full flex items-center justify-center">
            <Music class="w-5 h-5 text-black" />
          </div>
          <div>
            <p class="font-medium text-sm sm:text-base text-[#1DB954]">Spotify Ready</p>
            <p class="text-xs text-slate-400">Playing through your Spotify</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button
            @click="handleSyncAudio"
            :disabled="isSyncing"
            class="p-2 hover:bg-white/10 rounded-full transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
            :class="{ 'animate-spin': isSyncing }"
            title="Sync with room"
          >
            <RefreshCw class="w-5 h-5 text-slate-400" />
          </button>
          <button
            @click="handleSpotifyConnect"
            class="px-4 py-2 border border-slate-600 text-slate-300 font-medium rounded-full hover:bg-white/10 transition-colors text-sm min-h-[44px]"
          >
            Disconnect
          </button>
        </div>
      </div>

      <!-- Track List (only when album is selected) -->
      <div v-if="hasAlbum && album" class="glass overflow-hidden">
        <div
          v-for="track in album.tracks"
          :key="track.id"
          @click="handleSelectTrack(track.id)"
          class="flex items-center gap-2 sm:gap-4 px-3 sm:px-4 py-3 cursor-pointer transition-all duration-150 border-b border-white/5 last:border-0"
          :class="session.current_track_id === track.id
            ? 'bg-accent-primary/10 border-l-2 border-l-accent-primary'
            : 'hover:bg-white/5 border-l-2 border-l-transparent'"
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

    <!-- Album Picker Modal -->
    <div
      v-if="showAlbumPicker"
      class="fixed inset-0 z-50 flex items-start justify-center p-4 pt-20 bg-black/70 overflow-y-auto"
      @click.self="closeAlbumPicker"
    >
      <div class="glass w-full max-w-2xl rounded-2xl overflow-hidden">
        <div class="p-4 border-b border-white/10 flex items-center gap-4">
          <Search class="w-5 h-5 text-slate-400" />
          <input
            v-model="albumSearch"
            type="text"
            placeholder="Search albums..."
            class="flex-1 bg-transparent text-white placeholder-slate-500 focus:outline-none"
            autofocus
          />
          <button @click="closeAlbumPicker" class="btn-ghost">
            <X class="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <div class="max-h-96 overflow-y-auto">
          <div v-if="loadingAlbums" class="p-8 text-center text-slate-400">
            Loading albums...
          </div>

          <div v-else-if="filteredAlbums.length > 0" class="p-2 space-y-1">
            <div
              v-for="a in filteredAlbums"
              :key="a.id"
              @click="handleSelectAlbum(a)"
              class="flex items-center gap-4 p-3 hover:bg-white/5 rounded-xl transition-colors cursor-pointer"
              :class="{ 'opacity-50 pointer-events-none': settingAlbum }"
            >
              <img
                :src="a.cover_url || '/placeholder.svg'"
                :alt="a.name"
                class="w-14 h-14 rounded-lg object-cover bg-white/10"
              />

              <div class="flex-1 min-w-0">
                <h3 class="font-heading font-medium truncate">{{ a.name }}</h3>
                <p class="text-sm text-slate-400 truncate">{{ a.artist }}</p>
                <p class="text-xs text-slate-500">{{ a.tracks?.length || 0 }} tracks</p>
              </div>

              <div v-if="album?.id === a.id" class="px-3 py-1 bg-accent-primary/20 text-accent-primary rounded-lg text-sm">
                Current
              </div>
            </div>
          </div>

          <div v-else class="p-8 text-center text-slate-500">
            No albums found
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
