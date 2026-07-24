<script setup>
import { ref, onMounted, onUnmounted, inject, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Users, Copy, Check, Star, ChevronLeft, Radio, Music, Unplug, Disc3, Search, BarChart3, ListMusic, MessageCircle, ChevronDown, ChevronUp, Mic } from 'lucide-vue-next'
import RatingModal from '../components/RatingModal.vue'
import TrackDetailModal from '../components/TrackDetailModal.vue'
import AlbumPickerModal from '../components/AlbumPickerModal.vue'
import NowPlayingCard from '../components/session/NowPlayingCard.vue'
import SessionTrackList from '../components/session/SessionTrackList.vue'
import SessionStats from '../components/session/SessionStats.vue'
import SessionChat from '../components/session/SessionChat.vue'
import MediaSearchModal from '../components/session/MediaSearchModal.vue'
import MediaNowPlaying from '../components/session/MediaNowPlaying.vue'
import SessionQueue from '../components/session/SessionQueue.vue'
import LyricsPanel from '../components/session/LyricsPanel.vue'
import { useSpotifyPlayer } from '../composables/useSpotifyPlayer'
import { useSession } from '../composables/useSession'
import { useFavorites } from '../composables/useFavorites'

const route = useRoute()
const router = useRouter()
const currentUser = inject('currentUser')

// Global session state
const {
  session,
  album,
  media,
  queue,
  isPlaying,
  playbackPosition,
  currentTrackDuration,
  listeners,
  currentTrack,
  isInSession,
  hasAlbum,
  isHangout,
  chatOpen,
  unreadChatCount,
  setChatOpen,
  joinSession,
  leaveSession,
  selectTrack,
  notifyTrackChange,
  setAlbum,
  setMedia,
  addToQueue,
  removeQueueItem,
  voteQueueItem,
  advanceQueue,
  togglePlayback,
  seekTo,
  showToast,
  startProgressInterval,
  stopProgressInterval,
  syncWithServer
} = useSession()

// Spotify player
const {
  isReady: spotifyReady,
  isConnected: spotifyConnected,
  isPaused: spotifyPaused,
  position: spotifyPosition,
  duration: spotifyDuration,
  currentTrack: spotifyCurrentTrack,
  error: spotifyError,
  trackEnded: spotifyTrackEnded,
  setUserId: setSpotifyUserId,
  checkConnection: checkSpotifyConnection,
  connect: connectSpotify,
  disconnect: disconnectSpotify,
  initPlayer: initSpotifyPlayer,
  pause: spotifyPause,
  seek: spotifySeek,
  startPositionTracking,
  stopPositionTracking
} = useSpotifyPlayer()

// Personal favorites (heart on now-playing + quick re-queue in search modal)
const { loadFavorites, isFavorite, toggleFavorite } = useFavorites()

const loading = ref(true)
const copied = ref(false)

// Sync state
const isSyncing = ref(false)
const isAutoAdvancing = ref(false)
const isSelectingTrack = ref(false) // Prevents watcher interference during track selection

// Modals
const ratingModal = ref({ show: false, type: null, item: null, album: null })
const trackDetailModal = ref({ show: false, trackId: null })
const showAlbumPicker = ref(false)
const settingAlbum = ref(false)
const showMediaSearch = ref(false)

// Listening mode main column tab
const mainTab = ref('tracks')

const sessionCode = computed(() => route.params.code)

// Spotify connected + album has a Spotify context: Spotify plays the album
// gaplessly and advances tracks itself; the app observes advances
// (spotifyCurrentTrack watcher) instead of driving each track end.
const spotifyContextMode = computed(() => spotifyReady.value && !!album.value?.spotify_id)

const myAlbumRanking = computed(() =>
  album.value?.album_rankings?.find(r => r.user_id === currentUser.value?.id && r.score != null) || null
)

// Room mode switching (creator or admin only)
const canSwitchMode = computed(() =>
  session.value?.created_by === currentUser.value?.id || !!currentUser.value?.is_admin
)
const switchingMode = ref(false)

async function switchMode() {
  if (switchingMode.value || !session.value) return
  const target = isHangout.value ? 'listening' : 'hangout'
  switchingMode.value = true
  try {
    const res = await fetch(`/api/sessions/${sessionCode.value}/mode?mode=${target}`, { method: 'POST' })
    if (res.ok) {
      session.value.mode = target
    } else {
      showToast('Failed to switch mode', 'error')
    }
  } catch (e) {
    showToast('Failed to switch mode', 'error')
  }
  switchingMode.value = false
}

const myCurrentTrackScore = computed(() =>
  currentTrack.value?.rankings?.find(r => r.user_id === currentUser.value?.id && r.score != null)?.score ?? null
)

// Album context: what Spotify is actually playing right now (hangout albums
// advance track-by-track inside the SDK; mirror the name for the room card)
const liveSpotifyTrackName = computed(() =>
  spotifyReady.value && media.value?.type === 'album' && !spotifyPaused.value
    ? spotifyCurrentTrack.value?.name || null
    : null
)

const headerImage = computed(() => album.value?.cover_url || media.value?.image || null)

// What the lyrics panel should show. Hangout album context: only the local
// Spotify SDK knows the actual track; other listeners get no lyrics there.
const lyricsTrack = computed(() => {
  if (isHangout.value) {
    const m = media.value
    if (!m) return null
    if (m.type === 'track') {
      return {
        spotifyId: m.spotify_id,
        name: m.name,
        artist: m.artist,
        album: m.album_name || '',
        durationMs: m.duration_ms || 0
      }
    }
    const t = spotifyReady.value ? spotifyCurrentTrack.value : null
    if (!t) return null
    return {
      spotifyId: t.id,
      name: t.name,
      artist: t.artists?.[0]?.name || m.artist,
      album: t.album?.name || m.name,
      durationMs: spotifyDuration.value || 0
    }
  }
  const t = currentTrack.value
  if (!t) return null
  return {
    spotifyId: t.spotify_id,
    name: t.name,
    artist: album.value?.artist || '',
    album: album.value?.name || '',
    durationMs: t.duration_ms || currentTrackDuration.value || 0
  }
})

// Hangout album context has no room clock — Spotify's local clock drives it
const lyricsPosition = computed(() =>
  isHangout.value && media.value?.type === 'album' ? spotifyPosition.value : playbackPosition.value
)
const lyricsPlaying = computed(() =>
  isHangout.value && media.value?.type === 'album' ? !spotifyPaused.value : isPlaying.value
)

async function handleSyncAudio() {
  if (isSyncing.value) return
  isSyncing.value = true
  await syncWithServer()
  isSyncing.value = false
}

async function loadSession() {
  if (!sessionCode.value) return

  loading.value = true

  try {
    // Check if already in this session
    if (session.value?.code === sessionCode.value) {
      loading.value = false
      initSpotifyIfNeeded()
      return
    }

    const success = await joinSession(sessionCode.value, currentUser.value)
    if (!success) {
      router.push('/')
      return
    }

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

async function handleSelectAlbum(selectedAlbum) {
  settingAlbum.value = true
  const success = await setAlbum(selectedAlbum.id, currentUser.value)
  settingAlbum.value = false
  if (success) {
    showAlbumPicker.value = false
  }
}

async function handleSelectMedia(item) {
  showMediaSearch.value = false
  const ok = await setMedia(item)
  if (!ok) showToast('Could not start playback', 'error')
}

// Modal stays open so several songs can be queued in one go.
async function handleQueueMedia(item) {
  const ok = await addToQueue(item)
  if (!ok) showToast('Could not add to queue', 'error')
}

async function handleRemoveQueueItem(itemId) {
  await removeQueueItem(itemId)
}

function handleVoteQueueItem(itemId, vote) {
  voteQueueItem(itemId, vote)
}

async function handleSkipQueue() {
  await advanceQueue()
}

async function handleToggleFavoriteMedia() {
  if (!media.value) return
  await toggleFavorite(media.value)
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
  await togglePlayback(currentUser.value)
}

async function handleSeekTo(percent) {
  await seekTo(percent, currentUser.value)
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

function openAlbumRating() {
  if (!album.value) return
  ratingModal.value = { show: true, type: 'album', item: album.value, album: album.value }
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

async function postRating(isAlbum, body) {
  const res = await fetch(`/api/rankings/${isAlbum ? 'album' : 'track'}?session_code=${sessionCode.value}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  return res.ok
}

async function submitRating(data) {
  const isAlbum = ratingModal.value.type === 'album'
  const body = isAlbum
    ? { album_id: album.value.id, score: data.score, comment: data.comment || null }
    : { track_id: ratingModal.value.item.id, score: data.score, comment: data.comment || null }

  try {
    if (await postRating(isAlbum, body)) closeRating()
    else showToast('Failed to save rating', 'error')
  } catch (e) {
    showToast('Failed to save rating', 'error')
  }
}

// One-tap rating from the now-playing card
async function quickRateCurrentTrack(score) {
  if (!currentTrack.value) return
  try {
    const ok = await postRating(false, { track_id: currentTrack.value.id, score, comment: null })
    if (!ok) showToast('Failed to save rating', 'error')
  } catch (e) {
    showToast('Failed to save rating', 'error')
  }
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
  // Relinked tracks (market availability) report a different id than the
  // stored catalog id; linked_from carries the original.
  const linkedId = spotifyCurrentTrack.value?.linked_from?.id
  const track = album.value?.tracks?.find(
    t => t.spotify_id === newSpotifyId || (linkedId && t.spotify_id === linkedId)
  )
  if (!track) {
    // Spotify moved past the album (autoplay/recommendations) — stop instead
    // of playing foreign tracks while the UI still shows the album.
    await spotifyPause()
    if (isPlaying.value) await handleTogglePlayback()
    return
  }
  if (track.id === session.value?.current_track_id) return
  await notifyTrackChange(track.id, currentUser.value)
})

// Watch for Spotify track end event (more reliable than position-based detection)
watch(spotifyTrackEnded, async (ended) => {
  if (!ended || isAutoAdvancing.value || isSelectingTrack.value || !isPlaying.value) return
  // Reset immediately to prevent double-firing
  spotifyTrackEnded.value = false

  if (isHangout.value) {
    // Song (or whole album context) finished — pop the shared queue. The
    // server plays the next item, or pauses the room if the queue is empty.
    // seq-guarded server-side, so many clients reporting the same end is fine.
    await advanceQueue()
    return
  }

  if (spotifyContextMode.value) {
    // Spotify advances mid-album natively; an end event here means the album
    // finished — pause the room so the server clock stops too.
    const idx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
    if (idx >= 0 && idx === album.value.tracks.length - 1) {
      await handleTogglePlayback()
    }
    return
  }
  autoAdvanceTrack()
})

// When Spotify position drifts from room position, sync Spotify to room (room is source of truth)
watch(spotifyPosition, async (spotifyPos) => {
  if (!spotifyReady.value || isSyncing.value || isSelectingTrack.value) return

  // Hangout: Spotify is the clock authority (we started it) — mirror it into
  // the room card. Album media has no single-track bar, skip entirely.
  if (isHangout.value) {
    if (media.value?.type === 'track' && !spotifyPaused.value) {
      playbackPosition.value = spotifyPos
    }
    return
  }

  // Context mode: Spotify's clock is authoritative — mirror it INTO the room.
  if (spotifyContextMode.value) {
    if (!spotifyPaused.value) playbackPosition.value = spotifyPos
    return
  }

  // Backup check for track end via position (in case trackEnded event didn't fire).
  if (!isAutoAdvancing.value && isPlaying.value && currentTrackDuration.value > 0 && spotifyPos >= currentTrackDuration.value - 1500) {
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

// Spotify became ready while the room is already playing (joined a live
// room) — sync to the room instead of sitting silent until a manual sync.
watch(spotifyReady, async (ready, wasReady) => {
  if (ready && !wasReady && isPlaying.value && (currentTrack.value?.spotify_id || media.value?.spotify_id)) {
    await handleSyncAudio()
  }
})

// Hangout rooms are chat-first: chat is the main panel, always open
watch(isHangout, (hangout) => {
  if (hangout) setChatOpen(true)
}, { immediate: true })

function toggleChat() {
  setChatOpen(!chatOpen.value)
}

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
    // Come back to this room after the OAuth round-trip
    try { localStorage.setItem('spotifyReturnPath', route.fullPath) } catch {}
    await connectSpotify()
  }
}

onMounted(() => {
  loadSession()
  loadFavorites()
})

onUnmounted(() => {
  // Don't cleanup session - keep it running in background
  stopPositionTracking()
})
</script>

<template>
  <div>
    <router-link to="/rooms" class="inline-flex items-center gap-2 text-slate-400 hover:text-white mb-4 py-2 min-h-[44px]">
      <ChevronLeft class="w-4 h-4" />
      All Rooms
    </router-link>

    <div v-if="loading" class="text-center py-12 text-slate-400">
      Loading session...
    </div>

    <div v-else-if="session">
      <!-- Session Header (full width) -->
      <div class="glass p-4 sm:p-6 mb-4">
        <div class="flex flex-col sm:flex-row items-center sm:items-start gap-4 sm:gap-6">
          <div class="relative flex-shrink-0">
            <img
              v-if="headerImage"
              :src="headerImage"
              class="w-24 h-24 sm:w-32 sm:h-32 rounded-xl object-cover bg-white/10"
            />
            <div v-else class="w-24 h-24 sm:w-32 sm:h-32 rounded-xl bg-white/10 flex items-center justify-center">
              <component :is="isHangout ? MessageCircle : Disc3" class="w-12 h-12 text-slate-500" />
            </div>
          </div>
          <div class="flex-1 text-center sm:text-left min-w-0">
            <div class="flex items-center justify-center sm:justify-start gap-2 text-accent-primary text-sm mb-2">
              <component :is="isHangout ? MessageCircle : Radio" class="w-4 h-4 animate-pulse" />
              {{ session.name }}
              <span v-if="isHangout" class="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 text-xs font-medium">
                Hangout
              </span>
            </div>
            <template v-if="isHangout">
              <h1 class="text-xl sm:text-2xl font-heading font-bold mb-1 truncate">
                {{ media?.name || 'Hanging out' }}
              </h1>
              <p class="text-slate-400 mb-4 truncate">{{ media?.artist || 'Chat with friends — put on anything from Spotify' }}</p>
            </template>
            <template v-else>
              <h1 v-if="album" class="text-xl sm:text-2xl font-heading font-bold mb-1 truncate">{{ album.name }}</h1>
              <h1 v-else class="text-xl sm:text-2xl font-heading font-bold mb-1 text-slate-400">No album selected</h1>
              <p v-if="album" class="text-slate-400 mb-4 truncate">{{ album.artist }}</p>
              <p v-else class="text-slate-500 mb-4">Pick an album from the library to rank together</p>
            </template>

            <!-- Code + mode-specific actions -->
            <div class="flex items-center justify-center sm:justify-start gap-3 flex-wrap">
              <div class="px-4 py-2 bg-white/10 rounded-lg font-mono text-base sm:text-lg tracking-wider">
                {{ sessionCode }}
              </div>
              <button
                @click="copyCode"
                class="p-2 glass glass-hover rounded-lg min-h-[44px] min-w-[44px] flex items-center justify-center"
                aria-label="Copy room code"
              >
                <Check v-if="copied" class="w-5 h-5 text-green-400" />
                <Copy v-else class="w-5 h-5" />
              </button>

              <template v-if="isHangout">
                <button
                  @click="showMediaSearch = true"
                  class="flex items-center gap-2 px-4 py-2 bg-accent-primary text-black font-medium rounded-lg text-sm min-h-[44px] hover:bg-accent-primary/90 transition-colors"
                >
                  <Search class="w-4 h-4" />
                  Search music
                </button>
                <button
                  v-if="canSwitchMode"
                  @click="switchMode"
                  :disabled="switchingMode"
                  class="flex items-center gap-2 px-3 py-2 glass glass-hover rounded-lg text-sm min-h-[44px] disabled:opacity-50"
                  title="Switch this room to listening mode"
                >
                  <Radio class="w-4 h-4" />
                  To Listening
                </button>
              </template>
              <template v-else>
                <button
                  v-if="album"
                  @click="openAlbumRating"
                  class="flex items-center gap-2 px-3 py-2 glass glass-hover rounded-lg text-sm min-h-[44px]"
                  :class="myAlbumRanking ? 'text-yellow-400' : ''"
                >
                  <Star class="w-4 h-4" :class="myAlbumRanking ? 'fill-yellow-400' : ''" />
                  {{ myAlbumRanking ? `Album: ${myAlbumRanking.score.toFixed(1)}` : 'Rate Album' }}
                </button>
                <button
                  @click="showAlbumPicker = true"
                  class="flex items-center gap-2 px-3 py-2 glass glass-hover rounded-lg text-sm min-h-[44px]"
                >
                  <Disc3 class="w-4 h-4" />
                  {{ album ? 'Change Album' : 'Select Album' }}
                </button>
                <button
                  v-if="canSwitchMode"
                  @click="switchMode"
                  :disabled="switchingMode"
                  class="flex items-center gap-2 px-3 py-2 glass glass-hover rounded-lg text-sm min-h-[44px] disabled:opacity-50"
                  title="Switch this room to hangout mode"
                >
                  <MessageCircle class="w-4 h-4" />
                  To Hangout
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- ===================== HANGOUT LAYOUT ===================== -->
      <div v-if="isHangout" class="grid gap-4 lg:grid-cols-3 items-start">
        <!-- Sidebar: now playing + people (mobile: above chat) -->
        <div class="space-y-4 lg:order-2">
          <MediaNowPlaying
            :media="media"
            :is-playing="isPlaying"
            :position="playbackPosition"
            :duration="currentTrackDuration"
            :live-track-name="liveSpotifyTrackName"
            :is-favorite="media ? isFavorite(media.spotify_id) : false"
            @toggle="handleTogglePlayback"
            @seek="handleSeekTo"
            @search="showMediaSearch = true"
            @favorite="handleToggleFavoriteMedia"
          />

          <!-- Shared queue: anyone adds, votes reorder, top item plays next -->
          <SessionQueue
            :queue="queue"
            :current-user-id="currentUser?.id"
            :can-moderate="canSwitchMode"
            @add="showMediaSearch = true"
            @remove="handleRemoveQueueItem"
            @vote="handleVoteQueueItem"
            @skip="handleSkipQueue"
          />

          <LyricsPanel
            v-if="media"
            :track="lyricsTrack"
            :position="lyricsPosition"
            :playing="lyricsPlaying"
          />

          <!-- Spotify status (compact) -->
          <div class="glass p-3 flex items-center justify-between gap-3">
            <div class="flex items-center gap-2.5 min-w-0">
              <div class="w-8 h-8 bg-[#1DB954] rounded-full flex items-center justify-center flex-shrink-0" :class="{ 'animate-pulse': spotifyConnected && !spotifyReady }">
                <Music class="w-4 h-4 text-black" />
              </div>
              <div class="min-w-0">
                <p class="text-sm font-medium truncate" :class="spotifyReady ? 'text-[#1DB954]' : ''">
                  {{ spotifyReady ? 'Spotify ready' : spotifyConnected ? (spotifyError || 'Starting player…') : 'Connect Spotify to hear it' }}
                </p>
              </div>
            </div>
            <button
              @click="handleSpotifyConnect"
              class="px-3 py-1.5 rounded-full text-xs font-medium min-h-[36px] flex-shrink-0 transition-colors"
              :class="spotifyConnected ? 'border border-slate-600 text-slate-300 hover:bg-white/10' : 'bg-[#1DB954] text-black hover:bg-[#1ed760]'"
            >
              {{ spotifyConnected ? 'Disconnect' : 'Connect' }}
            </button>
          </div>

          <!-- People here -->
          <div class="glass p-4">
            <div class="flex items-center gap-3 mb-3">
              <Users class="w-5 h-5 text-accent-primary" />
              <span class="font-medium">Here Now</span>
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
                No one here yet — share the code
              </div>
            </div>
          </div>
        </div>

        <!-- Main: chat fills the room -->
        <div class="lg:col-span-2 lg:order-1 glass overflow-hidden">
          <div class="flex items-center gap-3 p-4 border-b border-white/10">
            <MessageCircle class="w-5 h-5 text-accent-primary" />
            <span class="font-medium">Chat</span>
          </div>
          <SessionChat :current-user="currentUser" tall />
        </div>
      </div>

      <!-- ===================== LISTENING LAYOUT ===================== -->
      <div v-else class="grid gap-4 lg:grid-cols-3 items-start">
        <!-- Main column -->
        <div class="lg:col-span-2 space-y-4">
          <!-- Album picker prompt -->
          <div v-if="!hasAlbum" class="glass p-8 text-center">
            <Disc3 class="w-16 h-16 mx-auto mb-4 text-slate-500" />
            <h2 class="text-xl font-heading font-medium text-slate-300 mb-2">No album selected</h2>
            <p class="text-slate-500 mb-6">Choose an album from the library to rank together</p>
            <button
              @click="showAlbumPicker = true"
              class="inline-flex items-center gap-2 px-6 py-3 bg-accent-primary text-black font-medium rounded-xl hover:bg-accent-primary/90 transition-colors"
            >
              <Disc3 class="w-5 h-5" />
              Select Album
            </button>
          </div>

          <template v-else>
            <NowPlayingCard
              :track="currentTrack"
              :is-playing="isPlaying"
              :position="playbackPosition"
              :duration="currentTrackDuration"
              :is-syncing="isSyncing"
              :show-sync="spotifyReady"
              :my-score="myCurrentTrackScore"
              @toggle="handleTogglePlayback"
              @next="handleSkipNext"
              @prev="handleSkipPrevious"
              @seek="handleSeekTo"
              @quick-rate="quickRateCurrentTrack"
              @open-rating="currentTrack && openTrackRating(currentTrack)"
              @sync="handleSyncAudio"
            />

            <!-- Tracks / Stats tabs -->
            <div>
              <div class="flex items-center gap-1 mb-3" role="tablist">
                <button
                  @click="mainTab = 'tracks'"
                  role="tab"
                  :aria-selected="mainTab === 'tracks'"
                  class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors min-h-[44px]"
                  :class="mainTab === 'tracks' ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-white hover:bg-white/5'"
                >
                  <ListMusic class="w-4 h-4" />
                  Tracks
                </button>
                <button
                  @click="mainTab = 'stats'"
                  role="tab"
                  :aria-selected="mainTab === 'stats'"
                  class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors min-h-[44px]"
                  :class="mainTab === 'stats' ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-white hover:bg-white/5'"
                >
                  <BarChart3 class="w-4 h-4" />
                  Stats
                </button>
                <button
                  @click="mainTab = 'lyrics'"
                  role="tab"
                  :aria-selected="mainTab === 'lyrics'"
                  class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors min-h-[44px]"
                  :class="mainTab === 'lyrics' ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-white hover:bg-white/5'"
                >
                  <Mic class="w-4 h-4" />
                  Lyrics
                </button>
              </div>

              <SessionTrackList
                v-if="mainTab === 'tracks'"
                :album="album"
                :current-track-id="session.current_track_id"
                :is-playing="isPlaying"
                :current-user-id="currentUser?.id"
                @select="handleSelectTrack"
                @rate="openTrackRating"
                @detail="openTrackDetail"
              />
              <SessionStats
                v-else-if="mainTab === 'stats'"
                :album="album"
                :current-user="currentUser"
                @rate-album="openAlbumRating"
              />
              <LyricsPanel
                v-else
                :track="lyricsTrack"
                :position="lyricsPosition"
                :playing="lyricsPlaying"
              />
            </div>
          </template>
        </div>

        <!-- Sidebar -->
        <div class="space-y-4">
          <!-- Spotify status (compact) -->
          <div v-if="hasAlbum" class="glass p-3 flex items-center justify-between gap-3">
            <div class="flex items-center gap-2.5 min-w-0">
              <div class="w-8 h-8 bg-[#1DB954] rounded-full flex items-center justify-center flex-shrink-0" :class="{ 'animate-pulse': spotifyConnected && !spotifyReady }">
                <Music class="w-4 h-4 text-black" />
              </div>
              <div class="min-w-0">
                <p class="text-sm font-medium truncate" :class="spotifyReady ? 'text-[#1DB954]' : ''">
                  {{ spotifyReady ? 'Spotify ready' : spotifyConnected ? (spotifyError || 'Starting player…') : 'Connect Spotify' }}
                </p>
                <p v-if="!spotifyConnected" class="text-xs text-slate-500">Play in sync (Premium)</p>
              </div>
            </div>
            <button
              @click="handleSpotifyConnect"
              class="px-3 py-1.5 rounded-full text-xs font-medium min-h-[36px] flex-shrink-0 transition-colors flex items-center gap-1.5"
              :class="spotifyConnected ? 'border border-slate-600 text-slate-300 hover:bg-white/10' : 'bg-[#1DB954] text-black hover:bg-[#1ed760]'"
            >
              <Unplug v-if="spotifyConnected" class="w-3.5 h-3.5" />
              {{ spotifyConnected ? 'Disconnect' : 'Connect' }}
            </button>
          </div>

          <!-- Listeners -->
          <div class="glass p-4">
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

          <!-- Chat (collapsible) -->
          <div class="glass overflow-hidden">
            <button
              @click="toggleChat"
              class="w-full flex items-center gap-3 p-4 min-h-[44px] text-left hover:bg-white/5 transition-colors"
            >
              <MessageCircle class="w-5 h-5 text-accent-primary" />
              <span class="font-medium">Chat</span>
              <span
                v-if="unreadChatCount > 0 && !chatOpen"
                class="px-2 py-0.5 bg-accent-primary text-black text-xs font-bold rounded-full"
              >
                {{ unreadChatCount }}
              </span>
              <component :is="chatOpen ? ChevronUp : ChevronDown" class="w-4 h-4 text-slate-400 ml-auto" />
            </button>
            <SessionChat v-if="chatOpen" :current-user="currentUser" />
          </div>
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

    <!-- Album picker (listening mode: library albums for ranking) -->
    <AlbumPickerModal
      v-if="showAlbumPicker"
      :current-album-id="album?.id || null"
      :busy="settingAlbum"
      @close="showAlbumPicker = false"
      @select="handleSelectAlbum"
    />

    <!-- Media search (hangout mode: whole Spotify catalog) -->
    <MediaSearchModal
      v-if="showMediaSearch"
      @close="showMediaSearch = false"
      @select="handleSelectMedia"
      @queue="handleQueueMedia"
    />
  </div>
</template>
