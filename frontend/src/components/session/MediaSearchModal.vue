<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Search, X, Music, Disc3, Play, Plus, Heart, Loader2 } from 'lucide-vue-next'
import { useModal } from '../../composables/useModal'
import { useFavorites } from '../../composables/useFavorites'

const emit = defineEmits(['close', 'select', 'queue'])

const container = ref(null)
useModal(container, () => emit('close'))

const { favorites, loadFavorites, isFavorite, toggleFavorite } = useFavorites()

const query = ref('')
const results = ref({ tracks: [], albums: [] })
const searching = ref(false)
const searched = ref(false)
const error = ref('')

let debounceTimer = null
let requestSeq = 0

// Idle modal shows your favorites for one-tap re-queue
const showFavorites = computed(() => !searched.value && !searching.value && favorites.value.length > 0)

onMounted(() => loadFavorites())

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

function withType(type, item) {
  return { ...item, type }
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

        <!-- Idle: your favorites, one tap to play or queue -->
        <div v-else-if="showFavorites" class="p-2">
          <div class="flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-400 uppercase tracking-wider">
            <Heart class="w-3.5 h-3.5" /> Your Favorites
          </div>
          <div
            v-for="f in favorites"
            :key="f.spotify_id"
            class="group flex items-center gap-3 p-2.5 hover:bg-white/5 rounded-xl transition-colors"
          >
            <img :src="f.image || '/placeholder.svg'" :alt="f.name" class="w-12 h-12 rounded-lg object-cover bg-white/10 flex-shrink-0" />
            <div class="flex-1 min-w-0">
              <p class="truncate text-sm font-medium">{{ f.name }}</p>
              <p class="truncate text-xs text-slate-400">{{ f.artist }}<span v-if="f.type === 'album'"> · Album</span></p>
            </div>
            <div class="flex items-center gap-1 flex-shrink-0">
              <button
                @click="toggleFavorite(f)"
                class="p-2 rounded-lg text-pink-400 hover:bg-white/10 transition-colors"
                :aria-label="`Remove ${f.name} from favorites`"
                title="Remove favorite"
              >
                <Heart class="w-4 h-4 fill-pink-400" />
              </button>
              <button
                @click="emit('queue', f)"
                class="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                :aria-label="`Add ${f.name} to queue`"
                title="Add to queue"
              >
                <Plus class="w-4 h-4" />
              </button>
              <button
                @click="emit('select', f)"
                class="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                :aria-label="`Play ${f.name} now`"
                title="Play now"
              >
                <Play class="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

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
            <div
              v-for="t in results.tracks"
              :key="t.spotify_id"
              class="group flex items-center gap-3 p-2.5 hover:bg-white/5 rounded-xl transition-colors"
            >
              <img :src="t.image || '/placeholder.svg'" :alt="t.name" class="w-12 h-12 rounded-lg object-cover bg-white/10 flex-shrink-0" />
              <div class="flex-1 min-w-0">
                <p class="truncate text-sm font-medium">{{ t.name }}</p>
                <p class="truncate text-xs text-slate-400">{{ t.artist }} · {{ t.album_name }}</p>
              </div>
              <span class="text-xs text-slate-500 tabular-nums flex-shrink-0">{{ formatDuration(t.duration_ms) }}</span>
              <div class="flex items-center gap-1 flex-shrink-0">
                <button
                  @click="toggleFavorite(withType('track', t))"
                  class="p-2 rounded-lg hover:bg-white/10 transition-colors"
                  :class="isFavorite(t.spotify_id) ? 'text-pink-400' : 'text-slate-500 hover:text-pink-400'"
                  :aria-label="isFavorite(t.spotify_id) ? `Remove ${t.name} from favorites` : `Add ${t.name} to favorites`"
                  :title="isFavorite(t.spotify_id) ? 'Remove favorite' : 'Favorite'"
                >
                  <Heart class="w-4 h-4" :class="isFavorite(t.spotify_id) ? 'fill-pink-400' : ''" />
                </button>
                <button
                  @click="emit('queue', withType('track', t))"
                  class="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                  :aria-label="`Add ${t.name} to queue`"
                  title="Add to queue"
                >
                  <Plus class="w-4 h-4" />
                </button>
                <button
                  @click="emit('select', withType('track', t))"
                  class="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                  :aria-label="`Play ${t.name} now`"
                  title="Play now"
                >
                  <Play class="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          <!-- Albums -->
          <div v-if="results.albums.length" class="p-2 border-t border-white/5">
            <div class="flex items-center gap-2 px-3 py-2 text-xs font-medium text-slate-400 uppercase tracking-wider">
              <Disc3 class="w-3.5 h-3.5" /> Albums
            </div>
            <div
              v-for="a in results.albums"
              :key="a.spotify_id"
              class="group flex items-center gap-3 p-2.5 hover:bg-white/5 rounded-xl transition-colors"
            >
              <img :src="a.image || '/placeholder.svg'" :alt="a.name" class="w-12 h-12 rounded-lg object-cover bg-white/10 flex-shrink-0" />
              <div class="flex-1 min-w-0">
                <p class="truncate text-sm font-medium">{{ a.name }}</p>
                <p class="truncate text-xs text-slate-400">{{ a.artist }}</p>
              </div>
              <span class="text-xs text-slate-500 flex-shrink-0">{{ a.total_tracks }} tracks</span>
              <div class="flex items-center gap-1 flex-shrink-0">
                <button
                  @click="toggleFavorite(withType('album', a))"
                  class="p-2 rounded-lg hover:bg-white/10 transition-colors"
                  :class="isFavorite(a.spotify_id) ? 'text-pink-400' : 'text-slate-500 hover:text-pink-400'"
                  :aria-label="isFavorite(a.spotify_id) ? `Remove ${a.name} from favorites` : `Add ${a.name} to favorites`"
                  :title="isFavorite(a.spotify_id) ? 'Remove favorite' : 'Favorite'"
                >
                  <Heart class="w-4 h-4" :class="isFavorite(a.spotify_id) ? 'fill-pink-400' : ''" />
                </button>
                <button
                  @click="emit('queue', withType('album', a))"
                  class="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                  :aria-label="`Add ${a.name} to queue`"
                  title="Add to queue"
                >
                  <Plus class="w-4 h-4" />
                </button>
                <button
                  @click="emit('select', withType('album', a))"
                  class="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
                  :aria-label="`Play ${a.name} now`"
                  title="Play now"
                >
                  <Play class="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          <div v-if="!results.tracks.length && !results.albums.length" class="p-8 text-center text-slate-500 text-sm">
            Nothing found for "{{ query }}"
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
