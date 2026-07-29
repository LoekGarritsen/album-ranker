<script setup>
import { ref, onMounted, inject, computed } from 'vue'
import { BarChart3, TrendingUp, TrendingDown, Flame, Music, Disc3, Users } from 'lucide-vue-next'

const currentUser = inject('currentUser')
const users = inject('users')

const stats = ref(null)
const hotTakes = ref([])
const growers = ref([])
const fellOff = ref([])
const loading = ref(true)

async function loadStats() {
  loading.value = true
  try {
    const [statsRes, hotTakesRes, growersRes] = await Promise.all([
      fetch('/api/stats'),
      fetch('/api/hot-takes'),
      fetch('/api/rating-history/growers')
    ])
    if (statsRes.ok) stats.value = await statsRes.json()
    if (hotTakesRes.ok) {
      const data = await hotTakesRes.json()
      hotTakes.value = data.hot_takes || []
    }
    if (growersRes.ok) {
      const data = await growersRes.json()
      growers.value = data.growers || []
      fellOff.value = data.fell_off || []
    }
  } catch (e) {
    console.error('Failed to load stats:', e)
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

onMounted(loadStats)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6 sm:mb-8">
      <h1 class="text-2xl sm:text-3xl font-heading font-bold">Stats</h1>
    </div>

    <div v-if="loading" class="text-center py-12 text-text-subdued">
      Loading stats...
    </div>

    <div v-else-if="stats" class="space-y-8">
      <!-- Global Stats -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="glass p-4 text-center">
          <Disc3 class="w-8 h-8 mx-auto mb-2 text-accent-primary" />
          <div class="text-2xl font-heading font-bold">{{ stats.total_albums }}</div>
          <div class="text-sm text-text-subdued">Albums</div>
        </div>
        <div class="glass p-4 text-center">
          <Music class="w-8 h-8 mx-auto mb-2 text-blue-400" />
          <div class="text-2xl font-heading font-bold">{{ stats.total_tracks }}</div>
          <div class="text-sm text-text-subdued">Tracks</div>
        </div>
        <div class="glass p-4 text-center">
          <BarChart3 class="w-8 h-8 mx-auto mb-2 text-yellow-400" />
          <div class="text-2xl font-heading font-bold">{{ stats.total_album_ratings }}</div>
          <div class="text-sm text-text-subdued">Album Ratings</div>
        </div>
        <div class="glass p-4 text-center">
          <Users class="w-8 h-8 mx-auto mb-2 text-purple-400" />
          <div class="text-2xl font-heading font-bold">{{ stats.total_track_ratings }}</div>
          <div class="text-sm text-text-subdued">Track Ratings</div>
        </div>
      </div>

      <!-- User Stats -->
      <div>
        <h2 class="text-xl font-heading font-semibold mb-4">User Stats</h2>
        <div class="grid md:grid-cols-2 gap-4">
          <div v-for="user in stats.user_stats" :key="user.user_id" class="glass p-4">
            <h3 class="font-heading font-semibold text-lg mb-3">{{ user.user_name }}</h3>
            <div class="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span class="text-text-subdued">Albums rated:</span>
                <span class="ml-2 font-medium">{{ user.albums_rated }}</span>
              </div>
              <div>
                <span class="text-text-subdued">Tracks rated:</span>
                <span class="ml-2 font-medium">{{ user.tracks_rated }}</span>
              </div>
              <div>
                <span class="text-text-subdued">Avg album:</span>
                <span class="ml-2 font-medium" :class="getScoreColor(user.average_album_score)">
                  {{ user.average_album_score || '-' }}
                </span>
              </div>
              <div>
                <span class="text-text-subdued">Avg track:</span>
                <span class="ml-2 font-medium" :class="getScoreColor(user.average_track_score)">
                  {{ user.average_track_score || '-' }}
                </span>
              </div>
            </div>
            <div v-if="user.highest_rated_album" class="mt-3 pt-3 border-t border-white/10 text-sm">
              <div class="flex items-center gap-2 text-green-400">
                <TrendingUp class="w-4 h-4" />
                <span>Favorite: {{ user.highest_rated_album }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Top Tracks -->
      <div v-if="stats.top_tracks?.length">
        <h2 class="text-lg sm:text-xl font-heading font-semibold mb-4">Top Rated Tracks</h2>
        <div class="glass overflow-hidden">
          <div
            v-for="(track, i) in stats.top_tracks"
            :key="i"
            class="flex items-center gap-2 sm:gap-4 p-2 sm:p-3 border-b border-white/5 last:border-0"
          >
            <div class="w-6 sm:w-8 text-center text-text-subdued font-medium text-sm">{{ i + 1 }}</div>
            <img
              :src="track.cover_url || '/placeholder.svg'"
              class="w-8 h-8 sm:w-10 sm:h-10 rounded-md object-cover bg-surface-highlight flex-shrink-0"
            />
            <div class="flex-1 min-w-0">
              <p class="truncate font-medium text-sm sm:text-base">{{ track.name }}</p>
              <p class="text-xs sm:text-sm text-text-subdued truncate">{{ track.artist }}</p>
            </div>
            <div class="text-lg sm:text-xl font-heading font-bold" :class="getScoreColor(track.avg_score)">
              {{ track.avg_score?.toFixed(1) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Hot Takes -->
      <div v-if="hotTakes.length">
        <h2 class="text-lg sm:text-xl font-heading font-semibold mb-3 sm:mb-4 flex items-center gap-2">
          <Flame class="w-5 h-5 text-orange-400" />
          Hot Takes
        </h2>
        <p class="text-text-subdued text-xs sm:text-sm mb-4">Ratings that differ most from the average</p>
        <div class="space-y-2 sm:space-y-3">
          <div
            v-for="(take, i) in hotTakes"
            :key="i"
            class="glass p-3 sm:p-4 flex items-center gap-3 sm:gap-4"
          >
            <img
              :src="take.cover_url || '/placeholder.svg'"
              class="w-10 h-10 sm:w-12 sm:h-12 rounded-md object-cover bg-surface-highlight flex-shrink-0"
            />
            <div class="flex-1 min-w-0">
              <p class="truncate font-medium text-sm sm:text-base">{{ take.track_name }}</p>
              <p class="text-xs sm:text-sm text-text-subdued truncate">{{ take.album_name }}</p>
              <p class="text-xs text-text-subdued">{{ take.user_name }}'s take</p>
            </div>
            <div class="text-right flex-shrink-0">
              <div class="text-base sm:text-lg font-heading font-bold" :class="getScoreColor(take.user_score)">
                {{ take.user_score }}
              </div>
              <div class="text-[10px] sm:text-xs text-text-subdued">
                avg: {{ take.average_score }}
                <span :class="take.user_score > take.average_score ? 'text-green-400' : 'text-red-400'">
                  ({{ take.user_score > take.average_score ? '+' : '' }}{{ (take.user_score - take.average_score).toFixed(1) }})
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Growers & fell off (re-rates) -->
      <div v-if="growers.length || fellOff.length" class="grid md:grid-cols-2 gap-6">
        <div v-if="growers.length">
          <h2 class="text-lg sm:text-xl font-heading font-semibold mb-3 flex items-center gap-2">
            <TrendingUp class="w-5 h-5 text-green-400" />
            Growers
          </h2>
          <p class="text-text-subdued text-xs sm:text-sm mb-3">Re-rates that climbed the most</p>
          <div class="space-y-2">
            <div v-for="(item, i) in growers" :key="i" class="glass p-3 flex items-center gap-3">
              <img :src="item.cover_url || '/placeholder.svg'" class="w-10 h-10 rounded-md object-cover bg-surface-highlight flex-shrink-0" />
              <div class="flex-1 min-w-0">
                <p class="truncate text-sm font-medium">{{ item.name }}</p>
                <p class="text-xs text-text-subdued truncate">{{ item.user_name }} · {{ item.kind }}</p>
              </div>
              <div class="text-sm flex-shrink-0">
                <span class="text-text-subdued">{{ item.first_score }}</span>
                <span class="text-text-subdued mx-1">→</span>
                <span class="font-heading font-bold" :class="getScoreColor(item.last_score)">{{ item.last_score }}</span>
                <span class="text-green-400 text-xs ml-1">+{{ item.delta }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="fellOff.length">
          <h2 class="text-lg sm:text-xl font-heading font-semibold mb-3 flex items-center gap-2">
            <TrendingDown class="w-5 h-5 text-red-400" />
            Fell Off
          </h2>
          <p class="text-text-subdued text-xs sm:text-sm mb-3">Re-rates that dropped the most</p>
          <div class="space-y-2">
            <div v-for="(item, i) in fellOff" :key="i" class="glass p-3 flex items-center gap-3">
              <img :src="item.cover_url || '/placeholder.svg'" class="w-10 h-10 rounded-md object-cover bg-surface-highlight flex-shrink-0" />
              <div class="flex-1 min-w-0">
                <p class="truncate text-sm font-medium">{{ item.name }}</p>
                <p class="text-xs text-text-subdued truncate">{{ item.user_name }} · {{ item.kind }}</p>
              </div>
              <div class="text-sm flex-shrink-0">
                <span class="text-text-subdued">{{ item.first_score }}</span>
                <span class="text-text-subdued mx-1">→</span>
                <span class="font-heading font-bold" :class="getScoreColor(item.last_score)">{{ item.last_score }}</span>
                <span class="text-red-400 text-xs ml-1">{{ item.delta }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Genres -->
      <div v-if="Object.keys(stats.genres || {}).length">
        <h2 class="text-xl font-heading font-semibold mb-4">Top Genres</h2>
        <div class="flex flex-wrap gap-2">
          <span
            v-for="(count, genre) in stats.genres"
            :key="genre"
            class="px-3 py-1 bg-accent-primary/20 text-accent-primary rounded-full text-sm"
          >
            {{ genre }} ({{ count }})
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
