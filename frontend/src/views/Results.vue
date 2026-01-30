<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Trophy, MessageCircle, ChevronDown, Disc3, Music } from 'lucide-vue-next'

const router = useRouter()

const results = ref([])
const loading = ref(true)
const expandedId = ref(null)

async function loadResults() {
  loading.value = true
  const res = await fetch('/api/results')
  if (res.ok) {
    const data = await res.json()
    results.value = data.results
  }
  loading.value = false
}

function toggleExpand(albumId) {
  expandedId.value = expandedId.value === albumId ? null : albumId
}

function getRankBadge(index) {
  if (index === 0) return { icon: '1', class: 'bg-yellow-500 text-black' }
  if (index === 1) return { icon: '2', class: 'bg-slate-400 text-black' }
  if (index === 2) return { icon: '3', class: 'bg-amber-600 text-black' }
  return { icon: `${index + 1}`, class: 'bg-white/10 text-slate-400' }
}

function getScoreColor(score) {
  if (!score) return 'text-slate-500'
  if (score >= 8) return 'text-green-400'
  if (score >= 6) return 'text-yellow-400'
  if (score >= 4) return 'text-orange-400'
  return 'text-red-400'
}

onMounted(loadResults)
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center gap-3 sm:gap-4 mb-6 sm:mb-8">
      <button
        @click="router.push('/')"
        class="p-2 hover:bg-white/10 rounded-lg transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
      >
        <ArrowLeft class="w-5 h-5" />
      </button>
      <h1 class="text-2xl sm:text-3xl font-heading font-bold">Results</h1>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-slate-400">
      Loading results...
    </div>

    <!-- Empty state -->
    <div v-else-if="results.length === 0" class="text-center py-16">
      <Trophy class="w-16 h-16 mx-auto mb-4 text-slate-600" />
      <h2 class="text-xl font-heading font-medium text-slate-400 mb-2">No rankings yet</h2>
      <p class="text-slate-500">Add albums and start rating!</p>
    </div>

    <!-- Results list -->
    <div v-else class="space-y-4">
      <div
        v-for="(item, index) in results"
        :key="item.album.id"
        class="glass overflow-hidden"
      >
        <!-- Album header -->
        <div
          class="flex items-center gap-2 sm:gap-4 p-3 sm:p-4 cursor-pointer hover:bg-white/5 transition-colors"
          @click="toggleExpand(item.album.id)"
        >
          <!-- Rank -->
          <div
            class="w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center font-heading font-bold text-sm sm:text-base flex-shrink-0"
            :class="getRankBadge(index).class"
          >
            {{ getRankBadge(index).icon }}
          </div>

          <!-- Album cover -->
          <img
            :src="item.album.cover_url || '/placeholder.svg'"
            :alt="item.album.name"
            class="w-10 h-10 sm:w-14 sm:h-14 rounded-lg object-cover bg-white/10 flex-shrink-0"
          />

          <!-- Album info -->
          <div class="flex-1 min-w-0">
            <h3 class="font-heading font-semibold truncate text-sm sm:text-base">{{ item.album.name }}</h3>
            <p class="text-xs sm:text-sm text-slate-400 truncate">{{ item.album.artist }}</p>
          </div>

          <!-- Scores -->
          <div class="flex items-center gap-3 sm:gap-6">
            <div class="text-center">
              <div class="hidden sm:flex items-center gap-1 text-xs text-slate-500 mb-1">
                <Disc3 class="w-3 h-3" />
                Album
              </div>
              <div
                v-if="item.average_album_score"
                class="text-lg sm:text-2xl font-heading font-bold"
                :class="getScoreColor(item.average_album_score)"
              >
                {{ item.average_album_score }}
              </div>
              <div v-else class="text-base sm:text-lg text-slate-500">-</div>
            </div>

            <div class="text-center hidden sm:block">
              <div class="flex items-center gap-1 text-xs text-slate-500 mb-1">
                <Music class="w-3 h-3" />
                Tracks
              </div>
              <div
                v-if="item.average_track_score"
                class="text-2xl font-heading font-bold"
                :class="getScoreColor(item.average_track_score)"
              >
                {{ item.average_track_score }}
              </div>
              <div v-else class="text-lg text-slate-500">-</div>
            </div>
          </div>

          <!-- Expand icon -->
          <ChevronDown
            class="w-5 h-5 text-slate-400 transition-transform flex-shrink-0"
            :class="{ 'rotate-180': expandedId === item.album.id }"
          />
        </div>

        <!-- Expanded details -->
        <div v-if="expandedId === item.album.id" class="border-t border-white/10 bg-white/5">
          <!-- Album ratings -->
          <div v-if="item.album_rankings?.length > 0" class="p-4 border-b border-white/10">
            <h4 class="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
              <Disc3 class="w-4 h-4" />
              Album Ratings
            </h4>
            <div class="space-y-2">
              <div
                v-for="ranking in item.album_rankings"
                :key="ranking.user_name"
                class="flex items-start gap-3"
              >
                <div class="w-24 flex-shrink-0">
                  <span class="text-sm text-slate-300">{{ ranking.user_name }}</span>
                </div>
                <div
                  class="w-10 text-center font-heading font-bold"
                  :class="getScoreColor(ranking.score)"
                >
                  {{ ranking.score }}
                </div>
                <div v-if="ranking.comment" class="flex-1 text-sm text-slate-400">
                  <MessageCircle class="w-3 h-3 inline mr-1 opacity-50" />
                  {{ ranking.comment }}
                </div>
              </div>
            </div>
          </div>

          <!-- Track ratings -->
          <div v-if="item.tracks?.length > 0" class="p-4">
            <h4 class="text-sm font-medium text-slate-400 mb-3 flex items-center gap-2">
              <Music class="w-4 h-4" />
              Track Ratings
            </h4>
            <div class="space-y-3">
              <div
                v-for="track in item.tracks"
                :key="track.id"
                class="glass p-3"
              >
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-2">
                    <span class="text-slate-500 text-sm w-6">{{ track.track_number }}.</span>
                    <span class="font-medium">{{ track.name }}</span>
                  </div>
                  <div
                    v-if="track.average_score"
                    class="font-heading font-bold"
                    :class="getScoreColor(track.average_score)"
                  >
                    {{ track.average_score }}
                  </div>
                </div>
                <div v-if="track.rankings?.length > 0" class="pl-8 space-y-1">
                  <div
                    v-for="ranking in track.rankings"
                    :key="ranking.user_name"
                    class="flex items-start gap-2 text-sm"
                  >
                    <span class="text-slate-500 w-20">{{ ranking.user_name }}</span>
                    <span class="font-heading font-bold w-6" :class="getScoreColor(ranking.score)">
                      {{ ranking.score }}
                    </span>
                    <span v-if="ranking.comment" class="text-slate-500 flex-1">
                      {{ ranking.comment }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
