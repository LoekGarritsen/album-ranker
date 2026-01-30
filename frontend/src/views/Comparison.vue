<script setup>
import { ref, onMounted, inject, watch } from 'vue'
import { ArrowLeftRight, Disc3, Music } from 'lucide-vue-next'

const users = inject('users')
const currentUser = inject('currentUser')

const user1Id = ref(null)
const user2Id = ref(null)
const comparison = ref(null)
const loading = ref(false)
const activeTab = ref('albums')

async function loadComparison() {
  if (!user1Id.value || !user2Id.value) return

  loading.value = true
  try {
    const res = await fetch(`/api/comparison?user1_id=${user1Id.value}&user2_id=${user2Id.value}`)
    if (res.ok) {
      comparison.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to load comparison:', e)
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

function getDiffColor(diff) {
  if (!diff) return 'text-slate-500'
  if (diff >= 3) return 'text-red-400'
  if (diff >= 2) return 'text-orange-400'
  if (diff >= 1) return 'text-yellow-400'
  return 'text-green-400'
}

onMounted(() => {
  if (users.value?.length >= 2) {
    user1Id.value = users.value[0]?.id
    user2Id.value = users.value[1]?.id
  }
})

watch([user1Id, user2Id], loadComparison)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-8">
      <h1 class="text-3xl font-heading font-bold">Compare Scores</h1>
    </div>

    <!-- User Selection -->
    <div class="glass p-4 mb-6">
      <div class="flex items-center gap-3 sm:gap-4 flex-wrap justify-center sm:justify-start">
        <select
          v-model="user1Id"
          class="px-3 sm:px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-accent-primary min-h-[44px] text-sm sm:text-base"
        >
          <option v-for="user in users" :key="user.id" :value="user.id">
            {{ user.name }}
          </option>
        </select>

        <ArrowLeftRight class="w-5 h-5 text-slate-400" />

        <select
          v-model="user2Id"
          class="px-3 sm:px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-accent-primary min-h-[44px] text-sm sm:text-base"
        >
          <option v-for="user in users" :key="user.id" :value="user.id">
            {{ user.name }}
          </option>
        </select>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-2 mb-6">
      <button
        @click="activeTab = 'albums'"
        class="flex items-center gap-2 px-3 sm:px-4 py-2 rounded-lg transition-colors min-h-[44px]"
        :class="activeTab === 'albums' ? 'bg-accent-primary text-black' : 'glass'"
      >
        <Disc3 class="w-4 h-4" />
        Albums
      </button>
      <button
        @click="activeTab = 'tracks'"
        class="flex items-center gap-2 px-3 sm:px-4 py-2 rounded-lg transition-colors min-h-[44px]"
        :class="activeTab === 'tracks' ? 'bg-accent-primary text-black' : 'glass'"
      >
        <Music class="w-4 h-4" />
        Tracks
      </button>
    </div>

    <div v-if="loading" class="text-center py-12 text-slate-400">
      Loading comparison...
    </div>

    <div v-else-if="comparison">
      <!-- Header -->
      <div class="glass p-3 mb-4 grid grid-cols-[1fr,50px,50px,40px] sm:grid-cols-[1fr,80px,80px,60px] gap-2 sm:gap-4 text-xs sm:text-sm text-slate-400">
        <div>{{ activeTab === 'albums' ? 'Album' : 'Track' }}</div>
        <div class="text-center truncate">{{ comparison.user1.name.split(' ')[0] }}</div>
        <div class="text-center truncate">{{ comparison.user2.name.split(' ')[0] }}</div>
        <div class="text-center">Diff</div>
      </div>

      <!-- Albums List -->
      <div v-if="activeTab === 'albums'" class="space-y-2">
        <div
          v-for="album in comparison.albums"
          :key="album.id"
          class="glass p-2 sm:p-3 grid grid-cols-[1fr,50px,50px,40px] sm:grid-cols-[1fr,80px,80px,60px] gap-2 sm:gap-4 items-center"
        >
          <div class="flex items-center gap-2 sm:gap-3 min-w-0">
            <img
              :src="album.cover_url || '/placeholder.svg'"
              class="w-8 h-8 sm:w-10 sm:h-10 rounded object-cover bg-white/10 flex-shrink-0"
            />
            <span class="truncate text-sm sm:text-base">{{ album.name }}</span>
          </div>
          <div class="text-center font-heading font-bold text-sm sm:text-base" :class="getScoreColor(album.user1_score)">
            {{ album.user1_score?.toFixed(1) || '-' }}
          </div>
          <div class="text-center font-heading font-bold text-sm sm:text-base" :class="getScoreColor(album.user2_score)">
            {{ album.user2_score?.toFixed(1) || '-' }}
          </div>
          <div class="text-center font-medium text-sm sm:text-base" :class="getDiffColor(album.difference)">
            {{ album.difference?.toFixed(1) || '-' }}
          </div>
        </div>

        <div v-if="comparison.albums.length === 0" class="text-center py-8 text-slate-400">
          No albums rated by both users
        </div>
      </div>

      <!-- Tracks List -->
      <div v-else class="space-y-2">
        <div
          v-for="track in comparison.tracks"
          :key="track.id"
          class="glass p-2 sm:p-3 grid grid-cols-[1fr,50px,50px,40px] sm:grid-cols-[1fr,80px,80px,60px] gap-2 sm:gap-4 items-center"
        >
          <div class="flex items-center gap-2 sm:gap-3 min-w-0">
            <img
              :src="track.cover_url || '/placeholder.svg'"
              class="w-8 h-8 sm:w-10 sm:h-10 rounded object-cover bg-white/10 flex-shrink-0"
            />
            <div class="min-w-0">
              <p class="truncate text-sm sm:text-base">{{ track.name }}</p>
              <p class="text-xs text-slate-500 truncate hidden sm:block">{{ track.album_name }}</p>
            </div>
          </div>
          <div class="text-center font-heading font-bold text-sm sm:text-base" :class="getScoreColor(track.user1_score)">
            {{ track.user1_score?.toFixed(1) || '-' }}
          </div>
          <div class="text-center font-heading font-bold text-sm sm:text-base" :class="getScoreColor(track.user2_score)">
            {{ track.user2_score?.toFixed(1) || '-' }}
          </div>
          <div class="text-center font-medium text-sm sm:text-base" :class="getDiffColor(track.difference)">
            {{ track.difference?.toFixed(1) || '-' }}
          </div>
        </div>

        <div v-if="comparison.tracks.length === 0" class="text-center py-8 text-slate-400">
          No tracks rated by both users
        </div>
      </div>
    </div>

    <div v-else class="text-center py-12 text-slate-400">
      Select two users to compare their ratings
    </div>
  </div>
</template>
