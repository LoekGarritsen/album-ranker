<script setup>
import { ref, onMounted } from 'vue'
import {
  Activity, Star, Disc3, ListMusic, Trophy, Radio, Heart,
  Search, UserPlus, UserCheck, Bookmark, Check
} from 'lucide-vue-next'
import { useSession } from '../composables/useSession'

const { showToast } = useSession()

const activeTab = ref('activity')
const feed = ref([])
const releases = ref([])
const artists = ref([])
const loading = ref(true)
const releasesLoading = ref(false)

// Artist search (follow UI)
const query = ref('')
const searchResults = ref([])
let searchTimer = null

async function loadFeed() {
  try {
    const res = await fetch('/api/feed')
    if (res.ok) feed.value = (await res.json()).feed
  } catch (e) {
    console.error('Failed to load feed:', e)
  }
  loading.value = false
}

async function loadReleases() {
  releasesLoading.value = true
  try {
    const [rel, fol] = await Promise.all([
      fetch('/api/artists/releases'),
      fetch('/api/artists/follows'),
    ])
    if (rel.ok) releases.value = (await rel.json()).releases
    if (fol.ok) artists.value = (await fol.json()).artists
  } catch (e) {
    console.error('Failed to load releases:', e)
  }
  releasesLoading.value = false
}

function onSearchInput() {
  clearTimeout(searchTimer)
  if (!query.value.trim()) { searchResults.value = []; return }
  searchTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/artists/search?q=${encodeURIComponent(query.value.trim())}`)
      if (res.ok) searchResults.value = (await res.json()).artists
    } catch {}
  }, 350)
}

function isFollowed(artistId) {
  return artists.value.some(a => a.spotify_artist_id === artistId && a.followed_by_me)
}

async function toggleFollow(artist) {
  const res = await fetch('/api/artists/follows', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      spotify_artist_id: artist.spotify_artist_id,
      name: artist.name,
      image: artist.image || null,
    }),
  })
  if (res.ok) {
    const { followed } = await res.json()
    showToast(followed ? `Following ${artist.name}` : `Unfollowed ${artist.name}`, 'success')
    await loadReleases()
  }
}

async function toggleLike(event) {
  const res = await fetch('/api/likes/toggle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind: 'album', ranking_id: event.ranking_id }),
  })
  if (res.ok) {
    const { liked, count } = await res.json()
    event.liked_by_me = liked ? 1 : 0
    event.likes = count
  }
}

async function saveRelease(release) {
  const res = await fetch('/api/listen-later', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      spotify_id: release.spotify_id,
      name: release.name,
      artist: release.artist,
      image: release.image || null,
      release_date: release.release_date || null,
    }),
  })
  if (res.ok) {
    const { saved } = await res.json()
    release.in_backlog = saved
    showToast(saved ? 'Saved to backlog' : 'Removed from backlog', 'success')
  }
}

function timeAgo(ts) {
  if (!ts) return ''
  const then = new Date(ts.includes('T') ? ts : ts.replace(' ', 'T') + 'Z')
  const secs = Math.floor((Date.now() - then.getTime()) / 1000)
  if (secs < 60) return 'just now'
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  if (secs < 604800) return `${Math.floor(secs / 86400)}d ago`
  return then.toLocaleDateString()
}

const CLUB_STATUS_TEXT = {
  nominating: 'opened for nominations',
  voting: 'moved to voting',
  rating: 'started blind rating',
  revealed: 'revealed its scores',
}

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'releases' && !releases.value.length && !artists.value.length) loadReleases()
}

onMounted(loadFeed)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-8">
      <h1 class="text-3xl font-heading font-bold flex items-center gap-3">
        <Activity class="w-8 h-8 text-accent-primary" />
        Feed
      </h1>
    </div>

    <!-- Tabs -->
    <div class="flex gap-2 mb-6">
      <button @click="switchTab('activity')"
              class="flex items-center gap-2 px-4 py-2 rounded-full transition-colors min-h-[44px]"
              :class="activeTab === 'activity' ? 'bg-white text-black' : 'bg-surface-highlight text-white hover:bg-surface-elevated'">
        <Activity class="w-4 h-4" /> Activity
      </button>
      <button @click="switchTab('releases')"
              class="flex items-center gap-2 px-4 py-2 rounded-full transition-colors min-h-[44px]"
              :class="activeTab === 'releases' ? 'bg-white text-black' : 'bg-surface-highlight text-white hover:bg-surface-elevated'">
        <Radio class="w-4 h-4" /> New Releases
      </button>
    </div>

    <!-- ACTIVITY -->
    <div v-if="activeTab === 'activity'">
      <div v-if="loading" class="text-center py-12 text-text-subdued">Loading…</div>
      <div v-else-if="feed.length" class="space-y-2">
        <div v-for="(event, i) in feed" :key="i" class="glass p-3 flex items-center gap-3">
          <img v-if="event.cover_url" :src="event.cover_url" class="w-11 h-11 rounded object-cover bg-surface-highlight shrink-0" />
          <div v-else class="w-11 h-11 rounded bg-surface-highlight flex items-center justify-center shrink-0">
            <ListMusic v-if="event.kind === 'list_created'" class="w-5 h-5 text-text-subdued" />
            <Trophy v-else-if="event.kind === 'club_round'" class="w-5 h-5 text-accent-primary" />
            <Disc3 v-else class="w-5 h-5 text-text-subdued" />
          </div>

          <div class="min-w-0 flex-1 text-sm">
            <template v-if="event.kind === 'album_rating'">
              <p class="truncate">
                <span class="font-semibold">{{ event.user_name }}</span> rated
                <span class="font-semibold">{{ event.album_name }}</span>
                <span class="text-accent-primary font-heading font-bold"> {{ event.score }}/10</span>
              </p>
              <p v-if="event.comment" class="text-xs text-text-subdued truncate">“{{ event.comment }}”</p>
            </template>
            <template v-else-if="event.kind === 'track_burst'">
              <p class="truncate">
                <span class="font-semibold">{{ event.user_name }}</span> rated
                {{ event.track_count }} tracks on <span class="font-semibold">{{ event.album_name }}</span>
                <span class="text-text-subdued">(avg {{ event.avg_score }})</span>
              </p>
            </template>
            <template v-else-if="event.kind === 'album_added'">
              <p class="truncate">
                <span class="font-semibold">{{ event.album_name }}</span> by {{ event.artist }} joined the library
              </p>
            </template>
            <template v-else-if="event.kind === 'list_created'">
              <p class="truncate">
                <span class="font-semibold">{{ event.user_name }}</span> made a list:
                <RouterLink :to="`/lists/${event.list_id}`" class="text-accent-primary hover:underline">{{ event.title }}</RouterLink>
              </p>
            </template>
            <template v-else-if="event.kind === 'club_round'">
              <p class="truncate">
                Club round <span class="font-semibold">{{ event.title }}</span>
                {{ CLUB_STATUS_TEXT[event.status] }}
                <span v-if="event.album_name && event.status !== 'nominating'" class="text-text-subdued">— {{ event.album_name }}</span>
              </p>
            </template>
            <p class="text-[11px] text-text-subdued mt-0.5">{{ timeAgo(event.at) }}</p>
          </div>

          <button v-if="event.kind === 'album_rating' && event.comment" @click="toggleLike(event)"
                  class="shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs transition-colors"
                  :class="event.liked_by_me ? 'bg-accent-primary/20 text-accent-primary' : 'bg-surface-highlight text-text-subdued hover:text-white'">
            <Heart class="w-3.5 h-3.5" :class="{ 'fill-current': event.liked_by_me }" />
            {{ event.likes || '' }}
          </button>
        </div>
      </div>
      <div v-else class="text-center py-16 text-text-subdued">No activity yet.</div>
    </div>

    <!-- RELEASES -->
    <div v-else>
      <!-- Artist follow manager -->
      <div class="glass p-4 mb-6">
        <div class="relative max-w-xl mb-3">
          <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-text-subdued" />
          <input v-model="query" @input="onSearchInput" placeholder="Search artists to follow…" class="input-base pl-9 w-full" />
        </div>
        <div v-if="searchResults.length" class="space-y-1 mb-3 max-h-64 overflow-y-auto">
          <div v-for="artist in searchResults" :key="artist.spotify_artist_id" class="flex items-center gap-3 p-2 rounded-lg hover:bg-white/5">
            <img :src="artist.image || '/placeholder.svg'" class="w-9 h-9 rounded-full object-cover bg-surface-highlight" />
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm">{{ artist.name }}</p>
              <p class="truncate text-xs text-text-subdued">{{ artist.genres?.join(', ') }}</p>
            </div>
            <button @click="toggleFollow(artist)"
                    class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-colors"
                    :class="isFollowed(artist.spotify_artist_id)
                      ? 'bg-accent-primary text-black font-semibold'
                      : 'bg-surface-highlight hover:bg-surface-elevated'">
              <UserCheck v-if="isFollowed(artist.spotify_artist_id)" class="w-3.5 h-3.5" />
              <UserPlus v-else class="w-3.5 h-3.5" />
              {{ isFollowed(artist.spotify_artist_id) ? 'Following' : 'Follow' }}
            </button>
          </div>
        </div>
        <div v-if="artists.length" class="flex gap-2 flex-wrap">
          <button v-for="artist in artists" :key="artist.spotify_artist_id" @click="toggleFollow(artist)"
                  class="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs transition-colors"
                  :class="artist.followed_by_me ? 'bg-surface-highlight' : 'bg-surface-highlight/40 text-text-subdued'"
                  :title="artist.followed_by_me ? 'Click to unfollow' : 'Followed by others — click to follow too'">
            <img v-if="artist.image" :src="artist.image" class="w-4 h-4 rounded-full object-cover" />
            {{ artist.name }}
            <span v-if="artist.followers > 1" class="text-text-subdued">×{{ artist.followers }}</span>
          </button>
        </div>
        <p v-else class="text-xs text-text-subdued">Follow artists the group loves — their new drops land here.</p>
      </div>

      <div v-if="releasesLoading" class="text-center py-12 text-text-subdued">Checking Spotify…</div>
      <div v-else-if="releases.length" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        <div v-for="release in releases" :key="release.spotify_id" class="card-interactive rounded-lg p-3 relative group">
          <img :src="release.image || '/placeholder.svg'" class="w-full aspect-square rounded-md object-cover bg-surface-highlight mb-2" />
          <p class="text-sm truncate">{{ release.name }}</p>
          <p class="text-xs text-text-subdued truncate">{{ release.artist }}</p>
          <p class="text-[11px] text-text-subdued mt-0.5">
            {{ release.release_date }} · {{ release.album_type }}
            <span v-if="release.in_library" class="text-green-400"> · in library</span>
          </p>
          <button @click="saveRelease(release)" :title="release.in_backlog ? 'Remove from backlog' : 'Save to backlog'"
                  class="absolute top-2 right-2 p-1.5 rounded-full bg-black/60 transition-opacity hover:bg-black/80"
                  :class="release.in_backlog ? '' : 'opacity-0 group-hover:opacity-100'">
            <Check v-if="release.in_backlog" class="w-4 h-4 text-accent-primary" />
            <Bookmark v-else class="w-4 h-4" />
          </button>
        </div>
      </div>
      <div v-else class="text-center py-16 text-text-subdued">
        <Radio class="w-12 h-12 mx-auto mb-3 opacity-40" />
        <p>No recent releases from followed artists.</p>
      </div>
    </div>
  </div>
</template>
