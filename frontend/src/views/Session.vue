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
  notifyTrackChange,
  setAlbum,
  togglePlayback,
  seekTo,
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
  currentTrack: spotifyCurrentTrack,
  error: spotifyError,
  trackEnded: spotifyTrackEnded,
  setUserId: setSpotifyUserId,
  checkConnection: checkSpotifyConnection,
  connect: connectSpotify,
  disconnect: disconnectSpotify,
  initPlayer: initSpotifyPlayer,
  play: spotifyPlay,
  playContext: spotifyPlayContext,
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
const isSelectingTrack = ref(false) // Prevents watcher interference during track selection

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

// When connected to Spotify AND the album has a Spotify context, Spotify
// plays the album gaplessly and advances tracks itself. In this mode the app
// observes advances (spotifyCurrentTrack watcher) instead of driving each
// track end, which is what kept reintroducing gaps.
const spotifyContextMode = computed(() => spotifyReady.value && !!album.value?.spotify_id)

const albumIsMultiDisc = computed(() => {
  if (!album.value?.tracks?.length) return false
  return album.value.tracks.some(t => (t.disc_number || 1) > 1)
})

const groupedTracks = computed(() => {
  if (!album.value?.tracks) return []
  const groups = []
  let currentDisc = null
  for (const track of album.value.tracks) {
    const disc = track.disc_number || 1
    if (disc !== currentDisc) {
      groups.push({ type: 'disc', disc_number: disc })
      currentDisc = disc
    }
    groups.push({ type: 'track', track })
  }
  return groups
})

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
  // Prevent watcher from interfering - selectTrack handles Spotify directly
  isSelectingTrack.value = true
  try {
    await selectTrack(trackId, currentUser.value)
  } finally {
    // Small delay to let any WebSocket messages settle before re-enabling watcher
    setTimeout(() => {
      isSelectingTrack.value = false
    }, 500)
  }
}

async function handleTogglePlayback() {
  // Just toggle room state - the isPlaying watcher handles Spotify sync
  await togglePlayback(currentUser.value)
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

async function handleSkipPrevious() {
  const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
  if (trackIdx > 0) {
    await handleSelectTrack(album.value.tracks[trackIdx - 1].id)
  }
}

async function handleSkipNext() {
  const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
  if (trackIdx >= 0 && trackIdx < album.value.tracks.length - 1) {
    await handleSelectTrack(album.value.tracks[trackIdx + 1].id)
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
  if (isAutoAdvancing.value || isSelectingTrack.value) return
  isAutoAdvancing.value = true

  try {
    const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
    if (trackIdx !== undefined && trackIdx >= 0 && trackIdx < album.value.tracks.length - 1) {
      const nextTrack = album.value.tracks[trackIdx + 1]
      await handleSelectTrack(nextTrack.id)
    } else {
      // Last track, pause
      await handleTogglePlayback()
    }
  } catch (e) {
    console.error('Auto-advance failed:', e)
  } finally {
    isAutoAdvancing.value = false
  }
}

// Spotify advanced to a new track on its own (gapless context playback).
// Mirror it to the room without re-issuing playback (would restart the track
// and reintroduce the gap). This replaces per-track-end driving in context mode.
watch(() => spotifyCurrentTrack.value?.id, async (newSpotifyId, oldSpotifyId) => {
  if (!spotifyContextMode.value || !newSpotifyId || newSpotifyId === oldSpotifyId) return
  if (isSelectingTrack.value || isSyncing.value) return
  const track = album.value?.tracks?.find(t => t.spotify_id === newSpotifyId)
  if (!track || track.id === session.value?.current_track_id) return
  await notifyTrackChange(track.id, currentUser.value)
})

// Watch for Spotify track end event (more reliable than position-based detection)
// This fires directly from the SDK when a track naturally finishes.
// Only used as fallback when NOT in context mode (album lacks a Spotify context).
watch(spotifyTrackEnded, async (ended) => {
  if (spotifyContextMode.value) return // Spotify drives advance natively
  if (ended && !isAutoAdvancing.value && !isSelectingTrack.value && isPlaying.value) {
    // Reset immediately to prevent double-firing
    spotifyTrackEnded.value = false
    autoAdvanceTrack()
  }
})

// When Spotify position drifts from room position, sync Spotify to room (room is source of truth)
watch(spotifyPosition, async (spotifyPos) => {
  if (!spotifyReady.value || isSyncing.value || isSelectingTrack.value) return

  // Backup check for track end via position (in case trackEnded event didn't fire).
  // Skipped in context mode — Spotify advances natively, the currentTrack watcher syncs.
  if (!spotifyContextMode.value && !isAutoAdvancing.value && isPlaying.value && currentTrackDuration.value > 0 && spotifyPos >= currentTrackDuration.value - 1500) {
    autoAdvanceTrack()
    return
  }

  // Only do drift correction if not paused
  if (spotifyPaused.value) return

  // Room position is source of truth - check if Spotify drifted too far
  const drift = Math.abs(playbackPosition.value - spotifyPos)
  if (drift > 2000) { // More than 2 seconds drift
    await spotifySeek(playbackPosition.value)
  }
})

// Sync Spotify player when room playback state changes (e.g., another user plays/pauses)
watch(isPlaying, async (roomIsPlaying, wasPlaying) => {
  // Skip if we're actively selecting a track - that handles Spotify directly
  if (!spotifyReady.value || isSyncing.value || isSelectingTrack.value) return

  const track = currentTrack.value
  if (!track?.spotify_id) return

  // Room started playing - sync Spotify to play
  if (roomIsPlaying && !wasPlaying) {
    if (spotifyPaused.value) {
      // If Spotify already has this track loaded, resume in place to keep the
      // gapless context. Only (re)start playback if it's a different/no track.
      if (spotifyCurrentTrack.value?.id === track.spotify_id) {
        await spotifyResume()
      } else if (spotifyContextMode.value) {
        await spotifyPlayContext(`spotify:album:${album.value.spotify_id}`, `spotify:track:${track.spotify_id}`, playbackPosition.value)
      } else {
        await spotifyPlay(`spotify:track:${track.spotify_id}`, playbackPosition.value)
      }
    }
  }
  // Room paused - pause Spotify
  else if (!roomIsPlaying && wasPlaying) {
    if (!spotifyPaused.value) {
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
        <template v-if="albumIsMultiDisc">
          <template v-for="item in groupedTracks" :key="item.type === 'disc' ? `disc-${item.disc_number}` : item.track.id">
            <div v-if="item.type === 'disc'" class="flex items-center gap-2 px-3 sm:px-4 py-2 bg-white/5 border-b border-white/5">
              <Disc3 class="w-3.5 h-3.5 text-slate-400" />
              <span class="text-xs font-medium text-slate-400 uppercase tracking-wider">Disc {{ item.disc_number }}</span>
            </div>
            <div
              v-else
              @click="handleSelectTrack(item.track.id)"
              class="flex items-center gap-2 sm:gap-4 px-3 sm:px-4 py-3 cursor-pointer transition-all duration-150 border-b border-white/5 last:border-0"
              :class="session.current_track_id === item.track.id
                ? 'bg-accent-primary/10 border-l-2 border-l-accent-primary'
                : 'hover:bg-white/5 border-l-2 border-l-transparent'"
            >
              <div class="w-6 sm:w-8 text-center flex-shrink-0">
                <div v-if="session.current_track_id === item.track.id && isPlaying" class="flex items-center justify-center gap-0.5">
                  <span class="w-1 h-3 bg-accent-primary rounded-full animate-pulse"></span>
                  <span class="w-1 h-4 bg-accent-primary rounded-full animate-pulse" style="animation-delay: 0.2s"></span>
                  <span class="w-1 h-2 bg-accent-primary rounded-full animate-pulse" style="animation-delay: 0.4s"></span>
                </div>
                <Play
                  v-else-if="session.current_track_id === item.track.id"
                  class="w-4 h-4 text-accent-primary mx-auto"
                />
                <span v-else class="text-xs sm:text-sm text-slate-500">{{ item.track.track_number }}</span>
              </div>
              <div class="flex-1 min-w-0">
                <p class="truncate text-sm sm:text-base" :class="session.current_track_id === item.track.id ? 'text-accent-primary font-medium' : ''">
                  {{ item.track.name }}
                </p>
                <p class="text-xs text-slate-500">{{ formatDuration(item.track.duration_ms) }}</p>
              </div>
              <div class="hidden sm:flex items-center gap-3">
                <div v-for="ranking in item.track.rankings" :key="ranking.user_id" class="text-center">
                  <div class="text-xs text-slate-500">{{ ranking.user_name?.split(' ')[0] }}</div>
                  <div class="font-heading font-bold" :class="getScoreColor(ranking.score)">
                    {{ ranking.score?.toFixed(1) || '-' }}
                  </div>
                </div>
              </div>
              <button
                @click.stop="openTrackDetail(item.track)"
                class="p-2 hover:bg-white/10 rounded-lg transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center flex-shrink-0"
                title="Track info"
              >
                <Info class="w-4 h-4 text-slate-400" />
              </button>
              <button
                @click.stop="openTrackRating(item.track)"
                class="flex items-center gap-1 px-2 sm:px-3 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors text-sm min-h-[44px] min-w-[44px] justify-center flex-shrink-0"
              >
                <Star class="w-3 h-3" />
                <span class="hidden sm:inline">{{ getUserRanking(item.track.rankings)?.score?.toFixed(1) || 'Rate' }}</span>
              </button>
            </div>
          </template>
        </template>
        <template v-else>
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
            <div class="hidden sm:flex items-center gap-3">
              <div v-for="ranking in track.rankings" :key="ranking.user_id" class="text-center">
                <div class="text-xs text-slate-500">{{ ranking.user_name?.split(' ')[0] }}</div>
                <div class="font-heading font-bold" :class="getScoreColor(ranking.score)">
                  {{ ranking.score?.toFixed(1) || '-' }}
                </div>
              </div>
            </div>
            <button
              @click.stop="openTrackDetail(track)"
              class="p-2 hover:bg-white/10 rounded-lg transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center flex-shrink-0"
              title="Track info"
            >
              <Info class="w-4 h-4 text-slate-400" />
            </button>
            <button
              @click.stop="openTrackRating(track)"
              class="flex items-center gap-1 px-2 sm:px-3 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors text-sm min-h-[44px] min-w-[44px] justify-center flex-shrink-0"
            >
              <Star class="w-3 h-3" />
              <span class="hidden sm:inline">{{ getUserRanking(track.rankings)?.score?.toFixed(1) || 'Rate' }}</span>
            </button>
          </div>
        </template>
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
