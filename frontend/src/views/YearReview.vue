<script setup>
import { ref, onMounted, inject, watch, computed } from 'vue'
import { Calendar, Star, Music, Disc3, TrendingUp, TrendingDown } from 'lucide-vue-next'

const currentUser = inject('currentUser')

const selectedYear = ref(new Date().getFullYear())
const review = ref(null)
const loading = ref(true)

const years = computed(() => {
  const current = new Date().getFullYear()
  return Array.from({ length: 5 }, (_, i) => current - i)
})

const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

async function loadReview() {
  if (!currentUser.value) return

  loading.value = true
  try {
    const res = await fetch(`/api/year-review/${selectedYear.value}?user_id=${currentUser.value.id}`)
    if (res.ok) {
      review.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to load year review:', e)
  }
  loading.value = false
}

function getScoreColor(score) {
  if (!score) return 'text-slate-500'
  if (score >= 8) return 'text-green-400'
  if (score >= 6) return 'text-yellow-400'
  if (score >= 4) return 'text-orange-400'
  return 'text-red-400'
}

function getActivityHeight(count) {
  if (!count) return 'h-1'
  if (count >= 50) return 'h-full'
  if (count >= 30) return 'h-4/5'
  if (count >= 20) return 'h-3/5'
  if (count >= 10) return 'h-2/5'
  return 'h-1/5'
}

onMounted(loadReview)
watch([selectedYear, currentUser], loadReview)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-8 flex-wrap gap-4">
      <h1 class="text-3xl font-heading font-bold flex items-center gap-3">
        <Calendar class="w-8 h-8 text-accent-primary" />
        Year in Review
      </h1>

      <select
        v-model="selectedYear"
        class="px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-accent-primary"
      >
        <option v-for="year in years" :key="year" :value="year">
          {{ year }}
        </option>
      </select>
    </div>

    <div v-if="!currentUser" class="text-center py-12 text-slate-400">
      Select a user to see their year in review
    </div>

    <div v-else-if="loading" class="text-center py-12 text-slate-400">
      Loading year review...
    </div>

    <div v-else-if="review" class="space-y-8">
      <!-- Stats Cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="glass p-4 text-center">
          <Disc3 class="w-8 h-8 mx-auto mb-2 text-accent-primary" />
          <div class="text-3xl font-heading font-bold">{{ review.albums_rated || 0 }}</div>
          <div class="text-sm text-slate-400">Albums Rated</div>
        </div>
        <div class="glass p-4 text-center">
          <Music class="w-8 h-8 mx-auto mb-2 text-blue-400" />
          <div class="text-3xl font-heading font-bold">{{ review.tracks_rated || 0 }}</div>
          <div class="text-sm text-slate-400">Tracks Rated</div>
        </div>
        <div class="glass p-4 text-center">
          <Star class="w-8 h-8 mx-auto mb-2 text-yellow-400" />
          <div class="text-3xl font-heading font-bold" :class="getScoreColor(review.average_album_score)">
            {{ review.average_album_score || '-' }}
          </div>
          <div class="text-sm text-slate-400">Avg Album Score</div>
        </div>
        <div class="glass p-4 text-center">
          <Star class="w-8 h-8 mx-auto mb-2 text-purple-400" />
          <div class="text-3xl font-heading font-bold" :class="getScoreColor(review.average_track_score)">
            {{ review.average_track_score || '-' }}
          </div>
          <div class="text-sm text-slate-400">Avg Track Score</div>
        </div>
      </div>

      <!-- Monthly Activity -->
      <div v-if="review.monthly_activity && Object.keys(review.monthly_activity).length" class="glass p-4 sm:p-6">
        <h2 class="text-lg font-heading font-semibold mb-4">Monthly Activity</h2>
        <div class="flex items-end gap-1 sm:gap-2 h-24 sm:h-32">
          <div
            v-for="(month, i) in months"
            :key="month"
            class="flex-1 flex flex-col items-center gap-1"
          >
            <div class="w-full bg-white/5 rounded-t relative h-16 sm:h-24 flex items-end">
              <div
                :class="getActivityHeight(review.monthly_activity[String(i + 1).padStart(2, '0')])"
                class="w-full bg-accent-primary/60 rounded-t transition-all"
              ></div>
            </div>
            <span class="text-[10px] sm:text-xs text-slate-500">{{ month.slice(0, 1) }}</span>
          </div>
        </div>
        <div class="flex justify-between text-xs text-slate-500 mt-2 sm:hidden">
          <span>Jan</span>
          <span>Dec</span>
        </div>
      </div>

      <!-- Top Albums -->
      <div v-if="review.top_albums?.length" class="glass p-6">
        <h2 class="text-lg font-heading font-semibold mb-4 flex items-center gap-2">
          <TrendingUp class="w-5 h-5 text-green-400" />
          Top Albums
        </h2>
        <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="(album, i) in review.top_albums"
            :key="i"
            class="flex items-center gap-3 p-3 bg-white/5 rounded-xl"
          >
            <div class="text-2xl font-heading font-bold text-slate-600 w-8">{{ i + 1 }}</div>
            <img
              :src="album.cover_url || '/placeholder.svg'"
              class="w-12 h-12 rounded object-cover bg-white/10"
            />
            <div class="flex-1 min-w-0">
              <p class="truncate font-medium">{{ album.name }}</p>
              <p class="text-sm text-slate-400 truncate">{{ album.artist }}</p>
            </div>
            <div class="text-xl font-heading font-bold" :class="getScoreColor(album.score)">
              {{ album.score?.toFixed(1) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Top Tracks -->
      <div v-if="review.top_tracks?.length" class="glass p-6">
        <h2 class="text-lg font-heading font-semibold mb-4 flex items-center gap-2">
          <Music class="w-5 h-5 text-accent-primary" />
          Top Tracks
        </h2>
        <div class="space-y-2">
          <div
            v-for="(track, i) in review.top_tracks.slice(0, 10)"
            :key="i"
            class="flex items-center gap-3 p-2 hover:bg-white/5 rounded-lg transition-colors"
          >
            <div class="text-sm font-medium text-slate-500 w-6">{{ i + 1 }}</div>
            <img
              :src="track.cover_url || '/placeholder.svg'"
              class="w-10 h-10 rounded object-cover bg-white/10"
            />
            <div class="flex-1 min-w-0">
              <p class="truncate">{{ track.name }}</p>
              <p class="text-xs text-slate-500 truncate">{{ track.album_name }}</p>
            </div>
            <div class="font-heading font-bold" :class="getScoreColor(track.score)">
              {{ track.score?.toFixed(1) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Worst Tracks (if any) -->
      <div v-if="review.worst_tracks?.length" class="glass p-6">
        <h2 class="text-lg font-heading font-semibold mb-4 flex items-center gap-2">
          <TrendingDown class="w-5 h-5 text-red-400" />
          Least Favorite Tracks
        </h2>
        <div class="space-y-2">
          <div
            v-for="(track, i) in review.worst_tracks"
            :key="i"
            class="flex items-center gap-3 p-2 hover:bg-white/5 rounded-lg transition-colors"
          >
            <img
              :src="track.cover_url || '/placeholder.svg'"
              class="w-10 h-10 rounded object-cover bg-white/10"
            />
            <div class="flex-1 min-w-0">
              <p class="truncate">{{ track.name }}</p>
              <p class="text-xs text-slate-500 truncate">{{ track.album_name }}</p>
            </div>
            <div class="font-heading font-bold" :class="getScoreColor(track.score)">
              {{ track.score?.toFixed(1) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-if="!review.tracks_rated && !review.albums_rated" class="text-center py-12 text-slate-400">
        No ratings found for {{ selectedYear }}
      </div>
    </div>
  </div>
</template>
