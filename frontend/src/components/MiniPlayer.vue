<script setup>
import { inject, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Play, Pause, SkipBack, SkipForward, X, Radio } from 'lucide-vue-next'
import { useSession } from '../composables/useSession'

const router = useRouter()
const route = useRoute()
const currentUser = inject('currentUser')

const {
  session,
  album,
  isPlaying,
  currentTrack,
  progressPercent,
  playbackPosition,
  currentTrackDuration,
  togglePlayback,
  skipPrevious,
  skipNext,
  leaveSession,
  formatDuration
} = useSession()

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
</script>

<template>
  <div
    v-if="session && !isOnSessionPage"
    class="fixed bottom-0 left-0 right-0 z-40 bg-bg-secondary/95 backdrop-blur-xl border-t border-white/10 safe-area-bottom"
  >
    <!-- Progress bar at top -->
    <div class="h-1 bg-white/10">
      <div
        class="h-full bg-accent-primary transition-all duration-100"
        :style="{ width: progressPercent + '%' }"
      ></div>
    </div>

    <div class="px-4 py-3">
      <div class="flex items-center gap-3">
        <!-- Album art & info (clickable to go to session) -->
        <div
          @click="goToSession"
          class="flex items-center gap-3 flex-1 min-w-0 cursor-pointer hover:opacity-80 transition-opacity"
        >
          <div class="relative">
            <img
              :src="album?.cover_url || '/placeholder.svg'"
              class="w-12 h-12 rounded-lg object-cover bg-white/10"
            />
            <div class="absolute -top-1 -right-1 w-4 h-4 bg-accent-primary rounded-full flex items-center justify-center">
              <Radio class="w-2.5 h-2.5 text-black" />
            </div>
          </div>
          <div class="min-w-0">
            <p class="truncate font-medium text-sm" :class="{ 'text-accent-primary': isPlaying }">
              {{ currentTrack?.name || 'No track' }}
            </p>
            <p class="truncate text-xs text-slate-400">
              {{ album?.artist }} · {{ session.code }}
            </p>
          </div>
        </div>

        <!-- Time -->
        <div class="hidden sm:block text-xs text-slate-500 tabular-nums">
          {{ formatDuration(playbackPosition) }} / {{ formatDuration(currentTrackDuration) }}
        </div>

        <!-- Controls -->
        <div class="flex items-center gap-1">
          <button
            @click="skipPrevious(currentUser)"
            class="p-2 hover:bg-white/10 rounded-full transition-colors"
          >
            <SkipBack class="w-4 h-4" />
          </button>
          <button
            @click="togglePlayback(currentUser)"
            class="p-2 bg-accent-primary text-black rounded-full hover:bg-accent-primary/90 transition-colors"
          >
            <Pause v-if="isPlaying" class="w-5 h-5" />
            <Play v-else class="w-5 h-5 ml-0.5" />
          </button>
          <button
            @click="skipNext(currentUser)"
            class="p-2 hover:bg-white/10 rounded-full transition-colors"
          >
            <SkipForward class="w-4 h-4" />
          </button>
        </div>

        <!-- Leave button -->
        <button
          @click="handleLeave"
          class="p-2 hover:bg-white/10 rounded-full transition-colors text-slate-400 hover:text-white"
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
