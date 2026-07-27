<script setup>
import { Music, SlidersHorizontal } from 'lucide-vue-next'

const props = defineProps({
  track: { type: Object, default: null },
  isPlaying: { type: Boolean, default: false },
  position: { type: Number, default: 0 },
  duration: { type: Number, default: 0 },
  myScore: { type: Number, default: null }
})

const emit = defineEmits(['quick-rate', 'open-rating'])

function formatDuration(ms) {
  if (!ms) return '0:00'
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function getScoreColor(score) {
  if (score == null) return 'text-text-subdued'
  if (score >= 8) return 'text-green-400'
  if (score >= 6) return 'text-yellow-400'
  if (score >= 4) return 'text-orange-400'
  return 'text-red-400'
}
</script>

<template>
  <div v-if="track" class="glass p-4 sm:p-5 mb-4">
    <div class="flex items-center gap-2 text-xs text-text-subdued uppercase tracking-wider mb-3">
      <Music class="w-3.5 h-3.5" />
      Now Playing
    </div>

    <!-- Track info (playback controls live in the player bar) -->
    <div class="flex items-center gap-3 sm:gap-4 mb-4">
      <div class="flex-1 min-w-0">
        <p class="font-heading font-semibold text-base sm:text-lg truncate" :class="{ 'text-accent-primary': isPlaying }">
          {{ track.track_number }}. {{ track.name }}
        </p>
        <p class="text-xs text-text-subdued tabular-nums">
          {{ formatDuration(position) }} / {{ formatDuration(duration) }}
        </p>
      </div>
    </div>

    <!-- Inline quick rate -->
    <div>
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm text-text-subdued">
          Your rating:
          <span v-if="myScore != null" class="font-heading font-bold ml-1" :class="getScoreColor(myScore)">{{ myScore.toFixed(1) }}</span>
          <span v-else class="text-text-subdued ml-1">tap to rate</span>
        </span>
        <button
          @click="emit('open-rating')"
          class="flex items-center gap-1.5 px-2 py-1 text-xs text-text-subdued hover:text-white hover:bg-surface-highlight rounded-full transition-colors"
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
            : 'bg-surface-highlight hover:bg-surface-elevated text-white/90'"
          :aria-label="`Rate ${n}`"
        >
          {{ n }}
        </button>
      </div>
    </div>
  </div>
</template>
