<script setup>
import { ref, computed, onMounted } from 'vue'
import { X, Disc3, Music } from 'lucide-vue-next'

const props = defineProps({
  type: { type: String, required: true }, // 'album' or 'track'
  item: { type: Object, required: true },
  album: { type: Object, required: true },
  currentUser: { type: Object, default: null }
})

const emit = defineEmits(['close', 'submit'])

const score = ref(5.0)
const comment = ref('')

const existingRanking = computed(() => {
  if (!props.currentUser) return null
  const rankings = props.type === 'album' ? props.album.album_rankings : props.item.rankings
  return rankings?.find(r => r.user_id === props.currentUser.id)
})

onMounted(() => {
  if (existingRanking.value) {
    score.value = existingRanking.value.score || 5.0
    comment.value = existingRanking.value.comment || ''
  }
})

function submit() {
  emit('submit', {
    score: parseFloat(score.value),
    comment: comment.value.trim() || null
  })
}

function getScoreLabel(val) {
  const v = parseFloat(val)
  if (v >= 9.5) return 'Masterpiece'
  if (v >= 8.5) return 'Excellent'
  if (v >= 7.5) return 'Great'
  if (v >= 6.5) return 'Good'
  if (v >= 5.5) return 'Above Average'
  if (v >= 4.5) return 'Average'
  if (v >= 3.5) return 'Below Average'
  if (v >= 2.5) return 'Poor'
  if (v >= 1.5) return 'Bad'
  return 'Terrible'
}

function getScoreColor(val) {
  const v = parseFloat(val)
  if (v >= 8) return 'text-green-400'
  if (v >= 6) return 'text-yellow-400'
  if (v >= 4) return 'text-orange-400'
  return 'text-red-400'
}

const displayScore = computed(() => {
  return parseFloat(score.value).toFixed(1)
})
</script>

<template>
  <div
    class="fixed inset-0 z-[60] flex items-end sm:items-center justify-center p-4 bg-black/70"
    @click.self="emit('close')"
  >
    <div class="bg-bg-secondary border border-white/10 w-full max-w-md rounded-t-3xl sm:rounded-3xl overflow-hidden shadow-2xl">
      <!-- Header -->
      <div class="relative p-6 pb-4 border-b border-white/10">
        <button
          @click="emit('close')"
          class="absolute top-4 right-4 p-2 hover:bg-white/10 rounded-lg transition-colors"
        >
          <X class="w-5 h-5" />
        </button>

        <div class="flex items-center gap-4">
          <img
            :src="album.cover_url || '/placeholder.svg'"
            :alt="album.name"
            class="w-16 h-16 rounded-lg object-cover bg-white/10"
          />
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 text-xs text-slate-500 mb-1">
              <Disc3 v-if="type === 'album'" class="w-3 h-3" />
              <Music v-else class="w-3 h-3" />
              {{ type === 'album' ? 'Rating Album' : 'Rating Track' }}
            </div>
            <h3 class="font-heading font-semibold truncate">
              {{ type === 'album' ? album.name : item.name }}
            </h3>
            <p class="text-sm text-slate-400 truncate">{{ album.artist }}</p>
          </div>
        </div>
      </div>

      <!-- Content -->
      <div class="p-6">
        <!-- Score display -->
        <div class="text-center mb-4">
          <div class="text-5xl font-heading font-bold" :class="getScoreColor(score)">
            {{ displayScore }}
          </div>
          <div class="text-sm text-slate-400 mt-1">{{ getScoreLabel(score) }}</div>
        </div>

        <!-- Slider -->
        <div class="mb-6">
          <input
            v-model="score"
            type="range"
            min="1"
            max="10"
            step="0.1"
            class="w-full"
          />
          <div class="flex justify-between text-xs text-slate-500 mt-2">
            <span>1.0</span>
            <span>10.0</span>
          </div>
        </div>

        <!-- Comment -->
        <div class="mb-6">
          <label class="block text-sm text-slate-400 mb-2">Comment (optional)</label>
          <textarea
            v-model="comment"
            :placeholder="type === 'album' ? 'Thoughts on this album?' : 'Thoughts on this track?'"
            rows="2"
            class="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-accent-primary transition-colors resize-none"
          />
        </div>

        <!-- Submit -->
        <button
          @click="submit"
          class="w-full py-3 bg-accent-primary text-black font-medium rounded-xl hover:bg-accent-primary/90 transition-colors"
        >
          {{ existingRanking ? 'Update Rating' : 'Submit Rating' }}
        </button>
      </div>
    </div>
  </div>
</template>
