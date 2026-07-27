<script setup>
import { ref, computed, onMounted } from 'vue'
import { Search, X } from 'lucide-vue-next'
import { useModal } from '../composables/useModal'

const props = defineProps({
  currentAlbumId: { type: Number, default: null },
  busy: { type: Boolean, default: false }
})

const emit = defineEmits(['close', 'select'])

const container = ref(null)
useModal(container, () => emit('close'))

const allAlbums = ref([])
const search = ref('')
const loading = ref(true)

const filteredAlbums = computed(() => {
  if (!search.value.trim()) return allAlbums.value
  const q = search.value.toLowerCase()
  return allAlbums.value.filter(a =>
    a.name.toLowerCase().includes(q) || a.artist.toLowerCase().includes(q)
  )
})

onMounted(async () => {
  try {
    const res = await fetch('/api/albums')
    if (res.ok) allAlbums.value = await res.json()
  } catch (e) {
    console.error('Failed to load albums:', e)
  }
  loading.value = false
})
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-start justify-center p-4 pt-20 bg-black/70 overflow-y-auto"
    @click.self="emit('close')"
    role="dialog"
    aria-modal="true"
    aria-label="Select album"
  >
    <div ref="container" class="glass w-full max-w-2xl rounded-2xl overflow-hidden">
      <div class="p-4 border-b border-white/10 flex items-center gap-4">
        <Search class="w-5 h-5 text-text-subdued" />
        <input
          v-model="search"
          type="text"
          placeholder="Search albums..."
          class="flex-1 bg-transparent text-white placeholder-text-subdued focus:outline-none"
          autofocus
        />
        <button @click="emit('close')" class="btn-ghost" aria-label="Close">
          <X class="w-5 h-5 text-text-subdued" />
        </button>
      </div>

      <div class="max-h-96 overflow-y-auto">
        <div v-if="loading" class="p-8 text-center text-text-subdued">
          Loading albums...
        </div>

        <div v-else-if="filteredAlbums.length > 0" class="p-2 space-y-1">
          <button
            v-for="a in filteredAlbums"
            :key="a.id"
            @click="emit('select', a)"
            :disabled="busy"
            class="w-full text-left flex items-center gap-4 p-3 hover:bg-white/5 rounded-xl transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:bg-white/10"
          >
            <img
              :src="a.cover_url || '/placeholder.svg'"
              :alt="a.name"
              class="w-14 h-14 rounded-lg object-cover bg-white/10"
            />
            <div class="flex-1 min-w-0">
              <h3 class="font-heading font-medium truncate">{{ a.name }}</h3>
              <p class="text-sm text-text-subdued truncate">{{ a.artist }}</p>
              <p class="text-xs text-text-subdued">{{ a.tracks?.length || 0 }} tracks</p>
            </div>
            <div v-if="currentAlbumId === a.id" class="px-3 py-1 bg-accent-primary/20 text-accent-primary rounded-lg text-sm flex-shrink-0">
              Current
            </div>
          </button>
        </div>

        <div v-else class="p-8 text-center text-text-subdued">
          No albums found
        </div>
      </div>
    </div>
  </div>
</template>
