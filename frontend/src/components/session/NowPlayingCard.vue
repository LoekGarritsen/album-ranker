<script setup>
import { computed } from 'vue'
import { Play, Pause, SkipBack, SkipForward, RefreshCw, Music, SlidersHorizontal } from 'lucide-vue-next'

const props = defineProps({
  track: { type: Object, default: null },
  isPlaying: { type: Boolean, default: false },
  position: { type: Number, default: 0 },
  duration: { type: Number, default: 0 },
  isSyncing: { type: Boolean, default: false },
  showSync: { type: Boolean, default: false },
  myScore: { type: Number, default: null }
})

const emit = defineEmits(['toggle', 'next', 'prev', 'seek', 'quick-rate', 'open-rating', 'sync'])

const progressPercent = computed(() => {
  if (!props.duration) return 0
  return Math.min(100, (props.position / props.duration) * 100)
})

function formatDuration(ms) {
  if (!ms) return '0:00'
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function handleProgressClick(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  const percent = ((event.clientX - rect.left) / rect.width) * 100
  emit('seek', Math.max(0, Math.min(100, percent)))
}

function getScoreColor(score) {
  if (score == null) return 'text-slate-500'
  if (score >= 8) return 'text-green-400'
  if (score >= 6) return 'text-yellow-400'
  if (score >= 4) return 'text-orange-400'
  return 'text-red-400'
}
</script>

<template>
  <div v-if="track" class="glass p-4 sm:p-5 mb-4">
    <div class="flex items-center gap-2 text-xs text-slate-500 uppercase tracking-wider mb-3">
      <Music class="w-3.5 h-3.5" />
      Now Playing
    </div>

    <!-- Track info + controls -->
    <div class="flex items-center gap-3 sm:gap-4 mb-3">
      <div class="flex-1 min-w-0">
        <p class="font-heading font-semibold text-base sm:text-lg truncate" :class="{ 'text-accent-primary': isPlaying }">
          {{ track.track_number }}. {{ track.name }}
        </p>
        <p class="text-xs text-slate-500 tabular-nums">
          {{ formatDuration(position) }} / {{ formatDuration(duration) }}
        </p>
      </div>

      <div class="flex items-center gap-1 flex-shrink-0">
        <button
          v-if="showSync"
          @click="emit('sync')"
          :disabled="isSyncing"
          class="p-2 hover:bg-white/10 rounded-full transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
          :class="{ 'animate-spin': isSyncing }"
          aria-label="Sync with room"
          title="Sync with room"
        >
          <RefreshCw class="w-4 h-4 text-slate-400" />
        </button>
        <button
          @click="emit('prev')"
          class="p-2 hover:bg-white/10 rounded-full transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
          aria-label="Previous track"
        >
          <SkipBack class="w-5 h-5" />
        </button>
        <button
          @click="emit('toggle')"
          class="p-3 bg-accent-primary text-black rounded-full hover:bg-accent-primary/90 transition-colors flex items-center justify-center"
          :aria-label="isPlaying ? 'Pause' : 'Play'"
        >
          <Pause v-if="isPlaying" class="w-6 h-6" />
          <Play v-else class="w-6 h-6 ml-0.5" />
        </button>
        <button
          @click="emit('next')"
          class="p-2 hover:bg-white/10 rounded-full transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
          aria-label="Next track"
        >
          <SkipForward class="w-5 h-5" />
        </button>
      </div>
    </div>

    <!-- Seekable progress -->
    <div
      class="h-2 bg-white/10 rounded-full overflow-hidden cursor-pointer mb-4"
      @click="handleProgressClick"
      role="slider"
      :aria-valuenow="Math.round(progressPercent)"
      aria-valuemin="0"
      aria-valuemax="100"
      aria-label="Seek"
    >
      <div class="h-full bg-accent-primary rounded-full transition-all duration-100" :style="{ width: progressPercent + '%' }"></div>
    </div>

    <!-- Inline quick rate -->
    <div>
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm text-slate-400">
          Your rating:
          <span v-if="myScore != null" class="font-heading font-bold ml-1" :class="getScoreColor(myScore)">{{ myScore.toFixed(1) }}</span>
          <span v-else class="text-slate-500 ml-1">tap to rate</span>
        </span>
        <button
          @click="emit('open-rating')"
          class="flex items-center gap-1.5 px-2 py-1 text-xs text-slate-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          aria-label="Fine-tune rating and add comment"
        >
          <SlidersHorizontal class="w-3.5 h-3.5" />
          Fine-tune / comment
        </button>
      </div>
      <div class="grid grid-cols-10 gap-1">
        <button
          v-for="n in 10"
          :key="n"
          @click="emit('quick-rate', n)"
          class="py-2 rounded-lg text-xs sm:text-sm font-medium transition-colors"
          :class="myScore != null && Math.round(myScore) === n
            ? 'bg-accent-primary text-black'
            : 'bg-white/5 hover:bg-white/15 text-slate-300'"
          :aria-label="`Rate ${n}`"
        >
          {{ n }}
        </button>
      </div>
    </div>
  </div>
</template>
