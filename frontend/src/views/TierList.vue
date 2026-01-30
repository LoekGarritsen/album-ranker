<script setup>
import { ref, onMounted, inject, watch } from 'vue'

const users = inject('users')
const currentUser = inject('currentUser')

const selectedUserId = ref(null)
const tiers = ref(null)
const loading = ref(true)

const tierColors = {
  S: 'bg-gradient-to-r from-yellow-500 to-amber-500',
  A: 'bg-gradient-to-r from-green-500 to-emerald-500',
  B: 'bg-gradient-to-r from-blue-500 to-cyan-500',
  C: 'bg-gradient-to-r from-purple-500 to-violet-500',
  D: 'bg-gradient-to-r from-orange-500 to-red-500',
  F: 'bg-gradient-to-r from-red-600 to-red-800',
  Unrated: 'bg-gradient-to-r from-slate-600 to-slate-700'
}

const tierLabels = {
  S: 'Masterpiece (9+)',
  A: 'Excellent (8-9)',
  B: 'Great (6.5-8)',
  C: 'Average (5-6.5)',
  D: 'Below Average (3.5-5)',
  F: 'Poor (<3.5)',
  Unrated: 'Not Rated'
}

async function loadTierList() {
  loading.value = true
  try {
    const url = selectedUserId.value
      ? `/api/tier-list?user_id=${selectedUserId.value}`
      : '/api/tier-list'
    const res = await fetch(url)
    if (res.ok) {
      const data = await res.json()
      tiers.value = data.tiers
    }
  } catch (e) {
    console.error('Failed to load tier list:', e)
  }
  loading.value = false
}

onMounted(() => {
  if (currentUser.value) {
    selectedUserId.value = currentUser.value.id
  }
  loadTierList()
})

watch(selectedUserId, loadTierList)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-8 flex-wrap gap-4">
      <h1 class="text-3xl font-heading font-bold">Tier List</h1>

      <select
        v-model="selectedUserId"
        class="px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-accent-primary"
      >
        <option :value="null">Everyone (Average)</option>
        <option v-for="user in users" :key="user.id" :value="user.id">
          {{ user.name }}
        </option>
      </select>
    </div>

    <div v-if="loading" class="text-center py-12 text-slate-400">
      Loading tier list...
    </div>

    <div v-else-if="tiers" class="space-y-3 sm:space-y-4">
      <div
        v-for="tier in ['S', 'A', 'B', 'C', 'D', 'F', 'Unrated']"
        :key="tier"
        class="flex flex-col sm:flex-row gap-2 sm:gap-4"
      >
        <!-- Tier Label -->
        <div
          :class="tierColors[tier]"
          class="w-full sm:w-20 flex-shrink-0 rounded-lg flex items-center justify-center"
        >
          <div class="text-center py-2 sm:py-4 flex sm:block items-center gap-2">
            <div class="text-xl sm:text-2xl font-heading font-bold text-white drop-shadow-lg">{{ tier }}</div>
            <div class="text-xs text-white/80 sm:hidden">{{ tierLabels[tier] }}</div>
          </div>
        </div>

        <!-- Albums in Tier -->
        <div class="flex-1 glass rounded-lg p-3 min-h-[60px] sm:min-h-[80px]">
          <div v-if="tiers[tier]?.length" class="flex flex-wrap gap-2 sm:gap-3">
            <div
              v-for="album in tiers[tier]"
              :key="album.id"
              class="group relative"
            >
              <img
                :src="album.cover_url || '/placeholder.svg'"
                :alt="album.name"
                class="w-12 h-12 sm:w-16 sm:h-16 rounded-lg object-cover bg-white/10 cursor-pointer transition-transform sm:hover:scale-110"
              />
              <!-- Tooltip - desktop only -->
              <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 hidden sm:block">
                <div class="bg-bg-primary border border-white/20 rounded-lg p-2 text-xs whitespace-nowrap shadow-xl">
                  <p class="font-medium">{{ album.name }}</p>
                  <p class="text-slate-400">{{ album.artist }}</p>
                  <p v-if="album.score" class="text-accent-primary mt-1">{{ album.score }}</p>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="h-full flex items-center justify-center text-slate-500 text-xs sm:text-sm">
            No albums
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
