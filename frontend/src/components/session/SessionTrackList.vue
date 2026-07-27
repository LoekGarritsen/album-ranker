<script setup>
import { computed } from 'vue'
import { Play, Star, Info, Disc3 } from 'lucide-vue-next'

const props = defineProps({
  album: { type: Object, required: true },
  currentTrackId: { type: Number, default: null },
  isPlaying: { type: Boolean, default: false },
  currentUserId: { type: Number, default: null }
})

const emit = defineEmits(['select', 'rate', 'detail'])

const albumIsMultiDisc = computed(() =>
  props.album?.tracks?.some(t => (t.disc_number || 1) > 1) || false
)

const groupedTracks = computed(() => {
  if (!props.album?.tracks) return []
  const groups = []
  let currentDisc = null
  for (const track of props.album.tracks) {
    const disc = track.disc_number || 1
    if (disc !== currentDisc) {
      groups.push({ type: 'disc', disc_number: disc })
      currentDisc = disc
    }
    groups.push({ type: 'track', track })
  }
  return groups
})

// Only show score columns for users who actually rated something on this
// album — placeholder entries exist for every registered user.
const activeRaterIds = computed(() => {
  const ids = new Set()
  for (const t of props.album?.tracks || []) {
    for (const r of t.rankings || []) {
      if (r.score != null) ids.add(r.user_id)
    }
  }
  return ids
})

function visibleRankings(track) {
  return (track.rankings || []).filter(r => activeRaterIds.value.has(r.user_id))
}

function getTrackAvg(track) {
  const scored = (track.rankings || []).filter(r => r.score != null)
  if (!scored.length) return null
  return scored.reduce((sum, r) => sum + r.score, 0) / scored.length
}

function getUserScore(track) {
  return track.rankings?.find(r => r.user_id === props.currentUserId && r.score != null)?.score ?? null
}

function getScoreColor(score) {
  if (score == null) return 'text-text-subdued'
  if (score >= 8) return 'text-green-400'
  if (score >= 6) return 'text-yellow-400'
  if (score >= 4) return 'text-orange-400'
  return 'text-red-400'
}

function formatDuration(ms) {
  if (!ms) return '0:00'
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}
</script>

<template>
  <div class="glass overflow-hidden">
    <template v-for="item in groupedTracks" :key="item.type === 'disc' ? `disc-${item.disc_number}` : item.track.id">
      <div v-if="item.type === 'disc' && albumIsMultiDisc" class="flex items-center gap-2 px-3 sm:px-4 py-2 bg-white/5 border-b border-white/5">
        <Disc3 class="w-3.5 h-3.5 text-text-subdued" />
        <span class="text-xs font-medium text-text-subdued uppercase tracking-wider">Disc {{ item.disc_number }}</span>
      </div>
      <div
        v-else-if="item.type === 'track'"
        @click="emit('select', item.track.id)"
        @keydown.enter.prevent="emit('select', item.track.id)"
        @keydown.space.prevent="emit('select', item.track.id)"
        role="button"
        tabindex="0"
        :aria-label="`Play ${item.track.name}`"
        class="flex items-center gap-2 sm:gap-4 px-3 sm:px-4 py-3 cursor-pointer transition-all duration-150 border-b border-white/5 last:border-0 focus-visible:outline-none focus-visible:bg-white/10"
        :class="currentTrackId === item.track.id
          ? 'bg-accent-primary/10 border-l-2 border-l-accent-primary'
          : 'hover:bg-white/5 border-l-2 border-l-transparent'"
      >
        <div class="w-6 sm:w-8 text-center flex-shrink-0">
          <div v-if="currentTrackId === item.track.id && isPlaying" class="flex items-center justify-center gap-0.5">
            <span class="w-1 h-3 bg-accent-primary rounded-full animate-pulse"></span>
            <span class="w-1 h-4 bg-accent-primary rounded-full animate-pulse" style="animation-delay: 0.2s"></span>
            <span class="w-1 h-2 bg-accent-primary rounded-full animate-pulse" style="animation-delay: 0.4s"></span>
          </div>
          <Play
            v-else-if="currentTrackId === item.track.id"
            class="w-4 h-4 text-accent-primary mx-auto"
          />
          <span v-else class="text-xs sm:text-sm text-text-subdued">{{ item.track.track_number }}</span>
        </div>
        <div class="flex-1 min-w-0">
          <p class="truncate text-sm sm:text-base" :class="currentTrackId === item.track.id ? 'text-accent-primary font-medium' : ''">
            {{ item.track.name }}
          </p>
          <p class="text-xs text-text-subdued">{{ formatDuration(item.track.duration_ms) }}</p>
        </div>
        <!-- Mobile: group average -->
        <div v-if="getTrackAvg(item.track) != null" class="sm:hidden text-center flex-shrink-0">
          <div class="text-[10px] text-text-subdued">avg</div>
          <div class="font-heading font-bold text-sm" :class="getScoreColor(getTrackAvg(item.track))">
            {{ getTrackAvg(item.track).toFixed(1) }}
          </div>
        </div>
        <!-- Desktop: per-rater scores -->
        <div class="hidden sm:flex items-center gap-3">
          <div v-for="ranking in visibleRankings(item.track)" :key="ranking.user_id" class="text-center">
            <div class="text-xs text-text-subdued">{{ ranking.user_name?.split(' ')[0] }}</div>
            <div class="font-heading font-bold" :class="getScoreColor(ranking.score)">
              {{ ranking.score?.toFixed(1) || '-' }}
            </div>
          </div>
        </div>
        <button
          @click.stop="emit('detail', item.track)"
          class="p-2 hover:bg-surface-highlight rounded-full transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center flex-shrink-0"
          title="Track info"
          aria-label="Track info"
        >
          <Info class="w-4 h-4 text-text-subdued" />
        </button>
        <button
          @click.stop="emit('rate', item.track)"
          class="flex items-center gap-1 px-2 sm:px-3 py-2 bg-surface-highlight text-white rounded-full hover:bg-surface-elevated transition-colors text-sm min-h-[44px] min-w-[44px] justify-center flex-shrink-0"
          :aria-label="getUserScore(item.track) != null ? 'Update your rating' : 'Rate this track'"
        >
          <Star class="w-3 h-3" :class="getUserScore(item.track) != null ? 'fill-yellow-400 text-yellow-400' : ''" />
          <span>{{ getUserScore(item.track)?.toFixed(1) || 'Rate' }}</span>
        </button>
      </div>
    </template>
  </div>
</template>
