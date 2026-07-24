<script setup>
import { ref, watch, onUnmounted } from 'vue'
import { Search, X, Music, Disc3, Play, Loader2 } from 'lucide-vue-next'
import { useModal } from '../../composables/useModal'

const emit = defineEmits(['close', 'select'])

const container = ref(null)
useModal(container, () => emit('close'))

const query = ref('')
const results = ref({ tracks: [], albums: [] })
const searching = ref(false)
const searched = ref(false)
const error = ref('')

let debounceTimer = null
let requestSeq = 0

watch(query, (q) => {
  clearTimeout(debounceTimer)
  error.value = ''
  if (!q.trim()) {
    results.value = { tracks: [], albums: [] }
    searched.value = false
    return
  }
  debounceTimer = setTimeout(runSearch, 350)
})

async function runSearch() {
  const q = query.value.trim()
  if (!q) return
  const seq = ++requestSeq
  searching.value = true
  try {
    const res = await fetch(`/api/spotify/search-media?q=${encodeURIComponent(q)}`)
    if (seq !== requestSeq) return // stale response, a newer search is out
    if (res.ok) {
      results.value = await res.json()
      searched.value = true
    } else {
      error.value = 'Search failed — try again'
    }
  } catch (e) {
    if (seq === requestSeq) error.value = 'Search failed — try again'
  }
  if (seq === requestSeq) searching.value = false
}

function pick(type, item) {
  emit('select', { ...item, type })
}

function formatDuration(ms) {
  if (!ms) return ''
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

onUnmounted(() => clearTimeout(debounceTimer))
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-start justify-center p-4 pt-20 bg-black/70 overflow-y-auto"
    @click.self="emit('close')"
    role="dialog"
    aria-modal="true"
    aria-label="Search music"
  >
    <div ref="container" class="glass w-full max-w-2xl rounded-2xl overflow-hidden">
      <div class="p-4 border-b border-white/10 flex items-center gap-4">
        <Loader2 v-if="searching" class="w-5 h-5 text-accent-primary animate-spin" />
        <Search v-else class="w-5 h-5 text-slate-400" />
        <input
          v-model="query"
          type="text"
          placeholder="Search Spotify for songs or albums…"
          class="flex-1 bg-transparent text-white placeholder-slate-500 focus:outline-none"
          autofocus
        />
        <button @click="emit('close')" class="btn-ghost" aria-label="Close">
          <X class="w-5 h-5 text-slate-400" />
        </button>
      </div>

      <div class="max-h-[28rem] overflow-y-auto">
        <div v-if="error" class="p-8 text-center text-red-400 text-sm">{{ error }}</div>

        <div v-else-if="!searched" class="p-10 text-center text-slate-500">
          <Music class="w-10 h-10 mx-auto mb-3 text-slate-600" />
          <p class="text-sm">Type to search the whole Spotify catalog</p>
        </div>

        <template v-else>
          <!-- Songs -->
          <div v-if="results.tracks.length" class="p-2">
            <div class="flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-400 uppercase tracking-wider">
              <Music class="w-3.5 h-3.5" /> Songs
            </div>
            <button
              v-for="t in results.tracks"
              :key="t.spotify_id"
              @click="pick('track', t)"
              class="group w-full text-left flex items-center gap-3 p-2.5 hover:bg-white/5 rounded-xl transition-colors focus-visible:outline-none focus-visible:bg-white/10"
            >
              <div class="relative flex-shrink-0">
                <img :src="t.image || '/placeholder.svg'" :alt="t.name" class="w-12 h-12 rounded-lg object-cover bg-white/10" />
                <div class="absolute inset-0 hidden group-hover:flex items-center justify-center bg-black/50 rounded-lg">
                  <Play class="w-5 h-5 text-white" />
                </div>
              </div>
              <div class="flex-1 min-w-0">
                <p class="truncate text-sm font-medium">{{ t.name }}</p>
                <p class="truncate text-xs text-slate-400">{{ t.artist }} · {{ t.album_name }}</p>
              </div>
              <span class="text-xs text-slate-500 tabular-nums flex-shrink-0">{{ formatDuration(t.duration_ms) }}</span>
            </button>
          </div>

          <!-- Albums -->
          <div v-if="results.albums.length" class="p-2 border-t border-white/5">
            <div class="flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-400 uppercase tracking-wider">
              <Disc3 class="w-3.5 h-3.5" /> Albums
            </div>
            <button
              v-for="a in results.albums"
              :key="a.spotify_id"
              @click="pick('album', a)"
              class="group w-full text-left flex items-center gap-3 p-2.5 hover:bg-white/5 rounded-xl transition-colors focus-visible:outline-none focus-visible:bg-white/10"
            >
              <div class="relative flex-shrink-0">
                <img :src="a.image || '/placeholder.svg'" :alt="a.name" class="w-12 h-12 rounded-lg object-cover bg-white/10" />
                <div class="absolute inset-0 hidden group-hover:flex items-center justify-center bg-black/50 rounded-lg">
                  <Play class="w-5 h-5 text-white" />
                </div>
              </div>
              <div class="flex-1 min-w-0">
                <p class="truncate text-sm font-medium">{{ a.name }}</p>
                <p class="truncate text-xs text-slate-400">{{ a.artist }}</p>
              </div>
              <span class="text-xs text-slate-500 flex-shrink-0">{{ a.total_tracks }} tracks</span>
            </button>
          </div>

          <div v-if="!results.tracks.length && !results.albums.length" class="p-8 text-center text-slate-500 text-sm">
            Nothing found for "{{ query }}"
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
