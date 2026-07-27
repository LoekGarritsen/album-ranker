<script setup>
import { ref, inject, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Play, Pause, SkipBack, SkipForward, X, Radio, RefreshCw,
  Mic, ListMusic, Heart, ThumbsUp, ThumbsDown
} from 'lucide-vue-next'
import { useSession } from '../composables/useSession'
import { useFavorites } from '../composables/useFavorites'
import { usePanel } from '../composables/usePanel'

const router = useRouter()
const currentUser = inject('currentUser')
const { panelView, togglePanel } = usePanel()
const { loadFavorites, isFavorite, toggleFavorite } = useFavorites()

const {
  session,
  album,
  media,
  mediaVotes,
  isPlaying,
  currentTrack,
  progressPercent,
  playbackPosition,
  currentTrackDuration,
  hasAlbum,
  isHangout,
  togglePlayback,
  skipPrevious,
  skipNext,
  seekTo,
  voteMedia,
  leaveSession,
  formatDuration,
  syncWithServer
} = useSession()

// Hangout shows the room's media, never a ranking album retained from a
// mode switch — its skip buttons would hijack the room into album playback.
const showSkip = computed(() => hasAlbum.value && !isHangout.value)
const displayTitle = computed(() => (isHangout.value
  ? media.value?.name
  : currentTrack.value?.name || media.value?.name) || 'No track')
const displaySubtitle = computed(() => (isHangout.value
  ? media.value?.artist
  : album.value?.artist || media.value?.artist) || '')
const displayImage = computed(() => (isHangout.value
  ? media.value?.image
  : album.value?.cover_url || media.value?.image) || '/placeholder.svg')

// Hangout album context: Spotify drives the clock, no room seek
const canSeek = computed(() => (isHangout.value ? media.value?.type === 'track' : hasAlbum.value))
const myMediaVote = computed(() =>
  mediaVotes.value.voters?.find(v => v.user_id === currentUser?.value?.id)?.vote || 0
)
const mediaIsFavorite = computed(() => (media.value ? isFavorite(media.value.spotify_id) : false))

const isSyncing = ref(false)

function goToSession() {
  if (session.value?.code) {
    router.push(`/session/${session.value.code}`)
  }
}

async function handleLeave() {
  await leaveSession()
  router.push('/')
}

function handleSkipPrevious() {
  skipPrevious(currentUser?.value)
}

function handleSkipNext() {
  skipNext(currentUser?.value)
}

function handleTogglePlayback() {
  togglePlayback(currentUser?.value)
}

function handleSeek(event) {
  if (!canSeek.value) return
  const rect = event.currentTarget.getBoundingClientRect()
  const percent = ((event.clientX - rect.left) / rect.width) * 100
  seekTo(Math.max(0, Math.min(100, percent)), currentUser?.value)
}

function handleVote(vote) {
  voteMedia(vote)
}

async function handleFavorite() {
  if (media.value) await toggleFavorite(media.value)
}

async function handleSync() {
  if (isSyncing.value) return
  isSyncing.value = true
  await syncWithServer()
  isSyncing.value = false
}

onMounted(() => {
  if (currentUser?.value) loadFavorites()
})
</script>

<template>
  <div
    v-if="session && (isHangout ? !!media : (hasAlbum || !!media))"
    class="shrink-0 bg-surface-base safe-area-bottom"
  >
    <!-- Mobile: thin progress strip (seek row is hidden there) -->
    <div class="progress-bar mx-2 !h-1 sm:hidden" @click="handleSeek">
      <div class="progress-bar-fill" :style="{ width: progressPercent + '%' }"></div>
    </div>

    <div class="px-3 sm:px-4 py-2 grid grid-cols-[minmax(0,1fr)_auto_auto] sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 sm:gap-4">
      <!-- Left: track info + hangout reactions -->
      <div class="flex items-center gap-2 sm:gap-3 min-w-0">
        <div
          @click="goToSession"
          class="flex items-center gap-3 min-w-0 cursor-pointer group"
        >
          <div class="relative shrink-0">
            <img
              :src="displayImage"
              class="w-12 h-12 sm:w-14 sm:h-14 rounded-md object-cover bg-surface-highlight"
            />
            <div class="absolute -top-1 -right-1 w-4 h-4 bg-accent-primary rounded-full flex items-center justify-center">
              <Radio class="w-2.5 h-2.5 text-black" />
            </div>
          </div>
          <div class="min-w-0">
            <p class="truncate font-semibold text-sm group-hover:underline" :class="{ 'text-accent-primary': isPlaying }">
              {{ displayTitle }}
            </p>
            <p class="truncate text-xs text-text-subdued">
              {{ displaySubtitle }} · {{ session.code }}
            </p>
          </div>
        </div>

        <template v-if="isHangout && media">
          <button
            @click="handleFavorite"
            class="p-2 rounded-full transition-colors shrink-0"
            :class="mediaIsFavorite ? 'text-pink-400' : 'text-text-subdued hover:text-pink-400'"
            :aria-label="mediaIsFavorite ? 'Remove from favorites' : 'Add to favorites'"
            :aria-pressed="mediaIsFavorite"
          >
            <Heart class="w-4 h-4" :class="mediaIsFavorite ? 'fill-pink-400' : ''" />
          </button>
          <button
            @click="handleVote('up')"
            class="hidden md:flex items-center gap-1 p-2 rounded-full text-xs transition-colors shrink-0"
            :class="myMediaVote === 1 ? 'text-green-400' : 'text-text-subdued hover:text-green-400'"
            aria-label="Like this song"
            :aria-pressed="myMediaVote === 1"
          >
            <ThumbsUp class="w-4 h-4" />
            <span class="tabular-nums">{{ mediaVotes.likes }}</span>
          </button>
          <button
            @click="handleVote('down')"
            class="hidden md:flex items-center gap-1 p-2 rounded-full text-xs transition-colors shrink-0"
            :class="myMediaVote === -1 ? 'text-red-400' : 'text-text-subdued hover:text-red-400'"
            aria-label="Dislike this song"
            :aria-pressed="myMediaVote === -1"
            title="Majority dislikes skip the song"
          >
            <ThumbsDown class="w-4 h-4" />
            <span class="tabular-nums">{{ mediaVotes.dislikes }}</span>
          </button>
        </template>
      </div>

      <!-- Center: transport + seek -->
      <div class="flex flex-col items-center gap-1 min-w-0">
        <div class="flex items-center gap-1 sm:gap-2">
          <button
            v-if="showSkip"
            @click="handleSkipPrevious"
            class="p-2 text-text-subdued hover:text-white rounded-full transition-colors"
            aria-label="Previous track"
          >
            <SkipBack class="w-5 h-5 fill-current" />
          </button>
          <button
            @click="handleTogglePlayback"
            class="w-9 h-9 sm:w-10 sm:h-10 flex items-center justify-center bg-white text-black rounded-full hover:scale-[1.06] active:scale-100 transition-transform"
            :aria-label="isPlaying ? 'Pause' : 'Play'"
          >
            <Pause v-if="isPlaying" class="w-5 h-5 fill-current" />
            <Play v-else class="w-5 h-5 ml-0.5 fill-current" />
          </button>
          <button
            v-if="showSkip"
            @click="handleSkipNext"
            class="p-2 text-text-subdued hover:text-white rounded-full transition-colors"
            aria-label="Next track"
          >
            <SkipForward class="w-5 h-5 fill-current" />
          </button>
        </div>
        <div class="hidden sm:flex items-center gap-2 w-[24rem] max-w-[32vw]">
          <span class="text-xs text-text-subdued tabular-nums shrink-0">{{ formatDuration(playbackPosition) }}</span>
          <div
            class="progress-bar flex-1"
            :class="canSeek ? '' : '!cursor-default'"
            @click="handleSeek"
            role="slider"
            :aria-valuenow="Math.round(progressPercent)"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-label="Seek"
          >
            <div class="progress-bar-fill" :style="{ width: progressPercent + '%' }"></div>
          </div>
          <span class="text-xs text-text-subdued tabular-nums shrink-0">{{ formatDuration(currentTrackDuration) }}</span>
        </div>
      </div>

      <!-- Right: panel toggles + sync + leave -->
      <div class="flex items-center justify-end gap-0.5 sm:gap-1">
        <button
          @click="togglePanel('lyrics')"
          class="p-2 rounded-full transition-colors"
          :class="panelView === 'lyrics' ? 'text-accent-primary' : 'text-text-subdued hover:text-white'"
          title="Lyrics"
          :aria-pressed="panelView === 'lyrics'"
        >
          <Mic class="w-4 h-4" />
        </button>
        <button
          @click="togglePanel('queue')"
          class="p-2 rounded-full transition-colors"
          :class="panelView === 'queue' ? 'text-accent-primary' : 'text-text-subdued hover:text-white'"
          title="Queue"
          :aria-pressed="panelView === 'queue'"
        >
          <ListMusic class="w-4 h-4" />
        </button>
        <button
          @click="handleSync"
          class="hidden sm:block p-2 text-text-subdued hover:text-white rounded-full transition-colors"
          :class="{ 'animate-spin': isSyncing }"
          title="Sync with server"
        >
          <RefreshCw class="w-4 h-4" />
        </button>
        <button
          @click="handleLeave"
          class="p-2 rounded-full transition-colors text-text-subdued hover:text-white"
          title="Leave session"
        >
          <X class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.safe-area-bottom {
  padding-bottom: env(safe-area-inset-bottom, 0);
}
</style>
