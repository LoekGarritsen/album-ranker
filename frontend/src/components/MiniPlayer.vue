<script setup>
import { ref, inject, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Play, Pause, SkipBack, SkipForward, X, Radio, RefreshCw } from 'lucide-vue-next'
import { useSession } from '../composables/useSession'

const router = useRouter()
const route = useRoute()
const currentUser = inject('currentUser')

const {
  session,
  album,
  media,
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

const isSyncing = ref(false)

// Hide mini player when on the session page itself
const isOnSessionPage = computed(() => {
  return route.path.startsWith('/session/')
})

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

async function handleSync() {
  if (isSyncing.value) return
  isSyncing.value = true
  await syncWithServer()
  isSyncing.value = false
}
</script>

<template>
  <div
    v-if="session && (isHangout ? !!media : (hasAlbum || !!media)) && !isOnSessionPage"
    class="shrink-0 bg-surface-base safe-area-bottom"
  >
    <!-- Progress bar at top -->
    <div class="progress-bar mx-2 !h-1">
      <div
        class="progress-bar-fill"
        :style="{ width: progressPercent + '%' }"
      ></div>
    </div>

    <div class="px-4 py-2.5">
      <div class="flex items-center gap-3">
        <!-- Album art & info (clickable to go to session) -->
        <div
          @click="goToSession"
          class="flex items-center gap-3 flex-1 min-w-0 cursor-pointer group"
        >
          <div class="relative">
            <img
              :src="displayImage"
              class="w-14 h-14 rounded-md object-cover bg-surface-highlight"
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

        <!-- Time -->
        <div class="hidden sm:block text-xs text-text-subdued tabular-nums">
          {{ formatDuration(playbackPosition) }} / {{ formatDuration(currentTrackDuration) }}
        </div>

        <!-- Controls -->
        <div class="flex items-center gap-1">
          <button
            @click="handleSync"
            class="p-2 text-text-subdued hover:text-white rounded-full transition-colors"
            :class="{ 'animate-spin': isSyncing }"
            title="Sync with server"
          >
            <RefreshCw class="w-4 h-4" />
          </button>
          <button
            v-if="showSkip"
            @click="handleSkipPrevious"
            class="p-2 text-text-subdued hover:text-white rounded-full transition-colors"
          >
            <SkipBack class="w-5 h-5 fill-current" />
          </button>
          <button
            @click="handleTogglePlayback"
            class="w-10 h-10 flex items-center justify-center bg-white text-black rounded-full hover:scale-[1.06] active:scale-100 transition-transform"
          >
            <Pause v-if="isPlaying" class="w-5 h-5 fill-current" />
            <Play v-else class="w-5 h-5 ml-0.5 fill-current" />
          </button>
          <button
            v-if="showSkip"
            @click="handleSkipNext"
            class="p-2 text-text-subdued hover:text-white rounded-full transition-colors"
          >
            <SkipForward class="w-5 h-5 fill-current" />
          </button>
        </div>

        <!-- Leave button -->
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
