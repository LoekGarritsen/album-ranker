<script setup>
import { ref, onMounted } from 'vue'
import { Bookmark, BookmarkX, Search, Disc3, Check } from 'lucide-vue-next'
import { useSession } from '../composables/useSession'

const { showToast } = useSession()

const items = ref([])
const loading = ref(true)

const query = ref('')
const searchResults = ref([])
const searching = ref(false)
let searchTimer = null

async function load() {
  try {
    const res = await fetch('/api/listen-later')
    if (res.ok) items.value = (await res.json()).items
  } catch (e) {
    console.error('Failed to load backlog:', e)
  }
  loading.value = false
}

function onSearchInput() {
  clearTimeout(searchTimer)
  if (!query.value.trim()) { searchResults.value = []; return }
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      const res = await fetch(`/api/spotify/search-media?q=${encodeURIComponent(query.value.trim())}`)
      if (res.ok) searchResults.value = (await res.json()).albums || []
    } catch {}
    searching.value = false
  }, 350)
}

function inBacklog(spotifyId) {
  return items.value.some(i => i.spotify_id === spotifyId)
}

async function toggle(album) {
  const res = await fetch('/api/listen-later', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      spotify_id: album.spotify_id,
      name: album.name,
      artist: album.artist,
      image: album.image || album.cover_url || null,
      release_date: album.release_date || null,
    }),
  })
  if (res.ok) {
    const { saved } = await res.json()
    showToast(saved ? 'Added to your backlog' : 'Removed from your backlog', 'success')
    await load()
  }
}
onMounted(load)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-8">
      <h1 class="text-3xl font-heading font-bold flex items-center gap-3">
        <Bookmark class="w-8 h-8 text-accent-primary" />
        Listen Later
      </h1>
    </div>

    <!-- Search to add -->
    <div class="mb-6">
      <div class="relative max-w-xl">
        <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-text-subdued" />
        <input v-model="query" @input="onSearchInput"
               placeholder="Search Spotify for albums to save…" class="input-base pl-9 w-full" />
      </div>
      <div v-if="searchResults.length" class="mt-2 max-w-xl bg-surface-elevated rounded-lg overflow-hidden divide-y divide-white/5 max-h-80 overflow-y-auto">
        <div v-for="album in searchResults" :key="album.spotify_id"
             class="flex items-center gap-3 p-2.5">
          <img :src="album.image || '/placeholder.svg'" class="w-10 h-10 rounded object-cover bg-surface-highlight" />
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm">{{ album.name }}</p>
            <p class="truncate text-xs text-text-subdued">{{ album.artist }} · {{ album.release_date?.slice(0, 4) }}</p>
          </div>
          <button @click="toggle(album)"
                  class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-colors"
                  :class="inBacklog(album.spotify_id)
                    ? 'bg-accent-primary text-black font-semibold'
                    : 'bg-surface-highlight hover:bg-surface-elevated'">
            <Check v-if="inBacklog(album.spotify_id)" class="w-3.5 h-3.5" />
            <Bookmark v-else class="w-3.5 h-3.5" />
            {{ inBacklog(album.spotify_id) ? 'Saved' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="text-center py-12 text-text-subdued">Loading…</div>

    <div v-else-if="items.length" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
      <div v-for="item in items" :key="item.id" class="card-interactive rounded-lg p-3 group relative">
        <img :src="item.image || '/placeholder.svg'" class="w-full aspect-square rounded-md object-cover bg-surface-highlight mb-2" />
        <p class="text-sm truncate">{{ item.name }}</p>
        <p class="text-xs text-text-subdued truncate">{{ item.artist }}</p>
        <p v-if="item.library_album_id" class="text-[11px] text-green-400 mt-1 flex items-center gap-1">
          <Disc3 class="w-3 h-3" /> In the library
        </p>
        <button @click="toggle(item)" title="Remove from backlog"
                class="absolute top-2 right-2 p-1.5 rounded-full bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/80">
          <BookmarkX class="w-4 h-4 text-red-400" />
        </button>
      </div>
    </div>

    <div v-else class="text-center py-16 text-text-subdued">
      <Bookmark class="w-12 h-12 mx-auto mb-3 opacity-40" />
      <p>Nothing saved yet. Search above to build your backlog —</p>
      <p class="text-sm">backlog albums show up as quick picks when nominating in the club.</p>
    </div>
  </div>
</template>
