<script setup>
import { ref, onMounted } from 'vue'
import { X, Star, Loader2, MessageCircle } from 'lucide-vue-next'
import { useModal } from '../composables/useModal'

const props = defineProps({
  trackId: { type: Number, required: true },
  currentUser: { type: Object, default: null }
})

const emit = defineEmits(['close', 'rate'])

const track = ref(null)
const loading = ref(true)
const error = ref(null)

async function loadTrack() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch(`/api/tracks/${props.trackId}`)
    if (res.ok) {
      track.value = await res.json()
    } else {
      error.value = 'Failed to load track'
    }
  } catch (e) {
    error.value = 'Failed to load track'
  }
  loading.value = false
}

function getScoreColor(score) {
  if (!score) return 'text-text-subdued'
  if (score >= 8) return 'text-green-400'
  if (score >= 6) return 'text-yellow-400'
  if (score >= 4) return 'text-orange-400'
  return 'text-red-400'
}

function formatDuration(ms) {
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function getUserRanking() {
  if (!props.currentUser || !track.value) return null
  return track.value.rankings?.find(r => r.user_id === props.currentUser.id)
}

function handleRate() {
  if (track.value) {
    emit('rate', track.value)
  }
}

const container = ref(null)
useModal(container, () => emit('close'))

onMounted(loadTrack)
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/80"
    @click.self="emit('close')"
    role="dialog"
    aria-modal="true"
    aria-label="Track details"
  >
    <div ref="container" class="bg-bg-secondary w-full sm:max-w-4xl max-h-[90vh] sm:max-h-[85vh] rounded-t-lg sm:rounded-lg overflow-hidden flex flex-col shadow-2xl">
      <!-- Header -->
      <div class="p-3 sm:p-4 border-b border-white/10 flex items-center gap-3 sm:gap-4 bg-bg-primary/50">
        <img
          v-if="track"
          :src="track.cover_url || '/placeholder.svg'"
          :alt="track.album_name"
          class="w-12 h-12 sm:w-14 sm:h-14 rounded-md object-cover bg-white/10 flex-shrink-0"
        />
        <div v-if="track" class="flex-1 min-w-0">
          <h2 class="font-heading font-semibold text-base sm:text-lg truncate text-white">{{ track.name }}</h2>
          <p class="text-xs sm:text-sm text-text-subdued truncate">{{ track.artist }} · {{ track.album_name }}</p>
          <p class="text-xs text-text-subdued">{{ formatDuration(track.duration_ms) }}</p>
        </div>
        <div v-if="track" class="flex-shrink-0">
          <button
            @click="handleRate"
            class="flex items-center gap-1 px-3 py-2 bg-accent-primary text-black rounded-full text-sm font-bold hover:bg-accent-bright transition-colors min-h-[44px]"
          >
            <Star class="w-3 h-3" />
            {{ getUserRanking()?.score?.toFixed(1) || 'Rate' }}
          </button>
        </div>
        <button
          @click="emit('close')"
          class="p-2 hover:bg-surface-highlight rounded-lg transition-colors flex-shrink-0 min-h-[44px] min-w-[44px] flex items-center justify-center"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-hidden">
        <!-- Loading -->
        <div v-if="loading" class="flex items-center justify-center h-64">
          <Loader2 class="w-8 h-8 text-text-subdued animate-spin" />
        </div>

        <!-- Error -->
        <div v-else-if="error" class="flex items-center justify-center h-64 text-text-subdued">
          {{ error }}
        </div>

        <!-- Content grid -->
        <div v-else-if="track" class="grid grid-cols-1 md:grid-cols-2 h-full">
          <!-- Lyrics -->
          <div class="p-4 sm:p-5 overflow-y-auto border-b md:border-b-0 md:border-r border-white/10 max-h-[40vh] sm:max-h-[60vh] bg-black/20">
            <h3 class="font-heading font-semibold text-white mb-3 sm:mb-4">Lyrics</h3>
            <div v-if="track.lyrics" class="text-sm text-white/90 whitespace-pre-line leading-relaxed">
              {{ track.lyrics }}
            </div>
            <div v-else class="text-text-subdued italic text-sm">
              No lyrics available
            </div>
          </div>

          <!-- Rankings -->
          <div class="p-4 sm:p-5 overflow-y-auto max-h-[40vh] sm:max-h-[60vh]">
            <h3 class="font-heading font-semibold text-white mb-3 sm:mb-4">Ratings</h3>

            <div v-if="track.rankings?.length > 0" class="space-y-3">
              <div
                v-for="ranking in track.rankings"
                :key="ranking.user_id"
                class="bg-surface-highlight rounded-lg p-3 sm:p-4"
              >
                <div class="flex items-center justify-between mb-2">
                  <span class="font-medium text-white text-sm sm:text-base">{{ ranking.user_name }}</span>
                  <span
                    class="text-xl sm:text-2xl font-heading font-bold"
                    :class="getScoreColor(ranking.score)"
                  >
                    {{ ranking.score?.toFixed(1) }}
                  </span>
                </div>
                <div v-if="ranking.comment" class="text-xs sm:text-sm text-text-subdued flex items-start gap-2">
                  <MessageCircle class="w-4 h-4 mt-0.5 flex-shrink-0 text-text-subdued" />
                  <span>{{ ranking.comment }}</span>
                </div>
                <div v-else class="text-xs sm:text-sm text-white/40 italic">
                  No comment
                </div>
              </div>
            </div>

            <div v-else class="text-text-subdued italic text-sm">
              No ratings yet
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
