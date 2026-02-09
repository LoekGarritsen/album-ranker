<script setup>
import { ref, onMounted, inject, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Search as SearchIcon, Plus, Check, Loader2, BarChart3, X, ChevronDown, Star, Trash2, Music, Sparkles, TrendingUp, Calendar, Users, Layers, Disc3 } from 'lucide-vue-next'
import RatingModal from '../components/RatingModal.vue'
import TrackDetailModal from '../components/TrackDetailModal.vue'

const router = useRouter()

const currentUser = inject('currentUser')
const isAdmin = inject('isAdmin')

const albums = ref([])
const loading = ref(true)
const expandedAlbumId = ref(null)

// Rating modal state
const ratingModal = ref({ show: false, type: null, item: null, album: null })

// Track detail modal state
const selectedTrackId = ref(null)
const selectedTrackAlbum = ref(null)

// Search state
const showSearch = ref(false)
const query = ref('')
const searchResults = ref([])
const searching = ref(false)
const addedIds = ref(new Set())
const addingId = ref(null)

// New releases state
const showNewReleases = ref(false)
const newReleases = ref([])
const loadingReleases = ref(false)

let debounceTimer = null

async function loadAlbums() {
  loading.value = true
  const res = await fetch('/api/albums')
  if (res.ok) {
    albums.value = await res.json()
    albums.value.forEach(a => addedIds.value.add(a.spotify_id))
  }
  loading.value = false
}

function toggleAlbum(albumId) {
  expandedAlbumId.value = expandedAlbumId.value === albumId ? null : albumId
}

function onSearch() {
  clearTimeout(debounceTimer)
  if (!query.value.trim()) {
    searchResults.value = []
    return
  }

  debounceTimer = setTimeout(async () => {
    searching.value = true
    try {
      const res = await fetch(`/api/spotify/search?q=${encodeURIComponent(query.value)}`, {
        headers: { 'X-User-Id': currentUser.value?.id?.toString() || '' }
      })
      if (res.ok) {
        searchResults.value = await res.json()
      }
    } catch (e) {
      console.error('Search error:', e)
    }
    searching.value = false
  }, 300)
}

async function addAlbum(album) {
  addingId.value = album.spotify_id
  try {
    const res = await fetch('/api/albums', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': currentUser.value?.id?.toString() || ''
      },
      body: JSON.stringify(album)
    })

    if (res.ok) {
      addedIds.value.add(album.spotify_id)
      await loadAlbums()
    }
  } catch (e) {
    console.error('Add error:', e)
  }
  addingId.value = null
}

async function loadNewReleases() {
  loadingReleases.value = true
  try {
    const res = await fetch('/api/spotify/new-releases')
    if (res.ok) {
      newReleases.value = await res.json()
    }
  } catch (e) {
    console.error('New releases error:', e)
  }
  loadingReleases.value = false
}

function openNewReleases() {
  showNewReleases.value = true
  if (newReleases.value.length === 0) {
    loadNewReleases()
  }
}

function closeNewReleases() {
  showNewReleases.value = false
}

async function removeAlbum(albumId) {
  if (!confirm('Remove this album and all its ratings?')) return

  await fetch(`/api/albums/${albumId}`, {
    method: 'DELETE',
    headers: { 'X-User-Id': currentUser.value?.id?.toString() || '' }
  })
  await loadAlbums()
}

function openAlbumRating(album) {
  ratingModal.value = { show: true, type: 'album', item: album, album }
}

function openTrackRating(track, album) {
  ratingModal.value = { show: true, type: 'track', item: track, album }
}

function openTrackDetail(track, album) {
  selectedTrackId.value = track.id
  selectedTrackAlbum.value = album
}

function closeTrackDetail() {
  selectedTrackId.value = null
  selectedTrackAlbum.value = null
}

async function handleTrackDetailRate(track) {
  // Save album reference before closing (closeTrackDetail sets it to null)
  const album = selectedTrackAlbum.value
  closeTrackDetail()
  // Wait for DOM to update before showing rating modal
  await nextTick()
  openTrackRating(track, album)
}

function closeRating() {
  ratingModal.value = { show: false, type: null, item: null, album: null }
}

async function submitRating(data) {
  const endpoint = ratingModal.value.type === 'album' ? '/api/rankings/album' : '/api/rankings/track'
  const idField = ratingModal.value.type === 'album' ? 'album_id' : 'track_id'

  const res = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      [idField]: ratingModal.value.item.id,
      user_id: currentUser.value.id,
      score: data.score,
      comment: data.comment || null
    })
  })

  if (res.ok) {
    await loadAlbums()
    closeRating()
  }
}

function closeSearch() {
  showSearch.value = false
  query.value = ''
  searchResults.value = []
}

function getUserRanking(rankings) {
  return rankings?.find(r => r.user_id === currentUser.value?.id)
}

function getScoreColor(score) {
  if (!score) return 'text-slate-500'
  if (score >= 8) return 'text-green-400'
  if (score >= 6) return 'text-yellow-400'
  if (score >= 4) return 'text-orange-400'
  return 'text-red-400'
}

function formatDuration(ms) {
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function isMultiDisc(album) {
  if (!album.tracks?.length) return false
  return album.tracks.some(t => (t.disc_number || 1) > 1)
}

function groupTracksByDisc(tracks) {
  const groups = []
  let currentDisc = null
  for (const track of tracks) {
    const disc = track.disc_number || 1
    if (disc !== currentDisc) {
      groups.push({ type: 'disc', disc_number: disc })
      currentDisc = disc
    }
    groups.push({ type: 'track', track })
  }
  return groups
}

onMounted(loadAlbums)
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-6 sm:mb-8 flex-wrap gap-3">
      <h1 class="text-2xl sm:text-3xl font-heading font-bold">Albums</h1>
      <div class="flex gap-2 sm:gap-3">
        <button
          @click="openNewReleases"
          class="flex items-center gap-2 px-3 sm:px-4 py-2 glass glass-hover min-h-[44px]"
        >
          <Sparkles class="w-5 h-5 text-accent-primary" />
          <span class="hidden sm:inline">New Releases</span>
          <span class="sm:hidden">New</span>
        </button>
        <button
          v-if="isAdmin"
          @click="showSearch = true"
          class="flex items-center gap-2 px-3 sm:px-4 py-2 bg-accent-primary text-black font-medium rounded-xl hover:bg-accent-primary/90 transition-colors min-h-[44px]"
        >
          <Plus class="w-5 h-5" />
          <span class="hidden sm:inline">Add Album</span>
          <span class="sm:hidden">Add</span>
        </button>
      </div>
    </div>

    <!-- Navigation -->
    <div class="flex gap-2 mb-6 overflow-x-auto pb-2 -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap scrollbar-hide">
      <router-link to="/stats" class="flex items-center gap-2 px-3 py-2 glass glass-hover text-sm whitespace-nowrap min-h-[44px]">
        <TrendingUp class="w-4 h-4" />
        Stats
      </router-link>
      <router-link to="/compare" class="flex items-center gap-2 px-3 py-2 glass glass-hover text-sm whitespace-nowrap min-h-[44px]">
        <Users class="w-4 h-4" />
        Compare
      </router-link>
      <router-link to="/tiers" class="flex items-center gap-2 px-3 py-2 glass glass-hover text-sm whitespace-nowrap min-h-[44px]">
        <Layers class="w-4 h-4" />
        Tiers
      </router-link>
      <router-link to="/year-review" class="flex items-center gap-2 px-3 py-2 glass glass-hover text-sm whitespace-nowrap min-h-[44px]">
        <Calendar class="w-4 h-4" />
        Year
      </router-link>
      <router-link to="/results" class="flex items-center gap-2 px-3 py-2 glass glass-hover text-sm whitespace-nowrap min-h-[44px]">
        <BarChart3 class="w-4 h-4" />
        Results
      </router-link>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading" class="space-y-4">
      <div v-for="i in 3" :key="i" class="glass p-4">
        <div class="flex items-center gap-4">
          <div class="skeleton w-16 h-16 rounded-lg"></div>
          <div class="flex-1 space-y-2">
            <div class="skeleton h-5 w-48 rounded"></div>
            <div class="skeleton h-4 w-32 rounded"></div>
            <div class="skeleton h-3 w-20 rounded"></div>
          </div>
          <div class="skeleton h-8 w-16 rounded-lg"></div>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="albums.length === 0" class="text-center py-16">
      <Music class="w-16 h-16 mx-auto mb-4 text-slate-600" />
      <h2 class="text-xl font-heading font-medium text-slate-400 mb-2">No albums yet</h2>
      <p class="text-slate-500 mb-6">
        {{ isAdmin ? 'Search Spotify to add albums' : 'Waiting for admin to add albums' }}
      </p>
    </div>

    <!-- Albums list -->
    <div v-else class="space-y-4">
      <div
        v-for="album in albums"
        :key="album.id"
        class="glass overflow-hidden transition-all duration-200 hover:shadow-lg hover:shadow-accent-primary/5"
      >
        <!-- Album header -->
        <div
          class="flex items-center gap-3 sm:gap-4 p-3 sm:p-4 cursor-pointer hover:bg-white/5 transition-colors"
          @click="toggleAlbum(album.id)"
        >
          <img
            :src="album.cover_url || '/placeholder.svg'"
            :alt="album.name"
            class="w-14 h-14 sm:w-16 sm:h-16 rounded-lg object-cover bg-white/10 flex-shrink-0"
          />

          <div class="flex-1 min-w-0">
            <h3 class="font-heading font-semibold truncate text-sm sm:text-base">{{ album.name }}</h3>
            <p class="text-xs sm:text-sm text-slate-400 truncate">{{ album.artist }}</p>
            <p class="text-xs text-slate-500">{{ album.tracks?.length || 0 }} tracks</p>
          </div>

          <!-- Album score -->
          <div class="text-right">
            <div v-if="album.average_album_score" class="text-lg sm:text-xl font-heading font-bold" :class="getScoreColor(album.average_album_score)">
              {{ album.average_album_score }}
            </div>
            <div class="text-xs text-slate-500 hidden sm:block">album</div>
          </div>

          <!-- Rate album button -->
          <button
            @click.stop="openAlbumRating(album)"
            class="flex items-center gap-1 px-2 sm:px-3 py-2 bg-accent-primary/20 text-accent-primary rounded-lg hover:bg-accent-primary/30 transition-colors text-sm min-h-[44px] min-w-[44px] justify-center"
          >
            <Star class="w-4 h-4" />
            <span class="hidden sm:inline">{{ getUserRanking(album.album_rankings)?.score || 'Rate' }}</span>
          </button>

          <!-- Delete button - hidden on mobile -->
          <button
            v-if="isAdmin"
            @click.stop="removeAlbum(album.id)"
            class="hidden sm:flex p-2 text-slate-500 hover:text-red-400 hover:bg-white/10 rounded-lg transition-colors min-h-[44px] min-w-[44px] items-center justify-center"
          >
            <Trash2 class="w-4 h-4" />
          </button>

          <ChevronDown
            class="w-5 h-5 text-slate-400 transition-transform flex-shrink-0"
            :class="{ 'rotate-180': expandedAlbumId === album.id }"
          />
        </div>

        <!-- Tracks (expanded) -->
        <div v-if="expandedAlbumId === album.id" class="border-t border-white/10">
          <template v-if="isMultiDisc(album)">
            <template v-for="item in groupTracksByDisc(album.tracks)" :key="item.type === 'disc' ? `disc-${item.disc_number}` : item.track.id">
              <div v-if="item.type === 'disc'" class="flex items-center gap-2 px-3 sm:px-4 py-2 bg-white/5 border-b border-white/5">
                <Disc3 class="w-3.5 h-3.5 text-slate-400" />
                <span class="text-xs font-medium text-slate-400 uppercase tracking-wider">Disc {{ item.disc_number }}</span>
              </div>
              <div
                v-else
                class="flex items-center gap-2 sm:gap-4 px-3 sm:px-4 py-3 hover:bg-white/5 transition-colors border-b border-white/5 last:border-0"
              >
                <div class="w-6 sm:w-8 text-center text-xs sm:text-sm text-slate-500 flex-shrink-0">
                  {{ item.track.track_number }}
                </div>
                <div
                  class="flex-1 min-w-0 cursor-pointer hover:text-accent-primary transition-colors"
                  @click="openTrackDetail(item.track, album)"
                >
                  <p class="truncate text-sm sm:text-base">{{ item.track.name }}</p>
                  <p class="text-xs text-slate-500">{{ formatDuration(item.track.duration_ms) }}</p>
                </div>
                <div class="hidden sm:flex items-center gap-3">
                  <div v-for="ranking in item.track.rankings" :key="ranking.user_id" class="text-center">
                    <div class="text-xs text-slate-500">{{ ranking.user_name?.split(' ')[0] }}</div>
                    <div class="font-heading font-bold" :class="getScoreColor(ranking.score)">
                      {{ ranking.score || '-' }}
                    </div>
                  </div>
                </div>
                <div v-if="item.track.average_score" class="text-center min-w-[36px] sm:min-w-[40px]">
                  <div class="text-xs text-slate-500 hidden sm:block">Avg</div>
                  <div class="font-heading font-bold text-sm sm:text-base" :class="getScoreColor(item.track.average_score)">
                    {{ item.track.average_score }}
                  </div>
                </div>
                <button
                  @click.stop="openTrackRating(item.track, album)"
                  class="flex items-center gap-1 px-2 sm:px-3 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors text-sm min-h-[44px] min-w-[44px] justify-center flex-shrink-0"
                >
                  <Star class="w-3 h-3" />
                  <span class="hidden sm:inline">{{ getUserRanking(item.track.rankings)?.score || 'Rate' }}</span>
                </button>
              </div>
            </template>
          </template>
          <template v-else>
            <div
              v-for="track in album.tracks"
              :key="track.id"
              class="flex items-center gap-2 sm:gap-4 px-3 sm:px-4 py-3 hover:bg-white/5 transition-colors border-b border-white/5 last:border-0"
            >
              <div class="w-6 sm:w-8 text-center text-xs sm:text-sm text-slate-500 flex-shrink-0">
                {{ track.track_number }}
              </div>
              <div
                class="flex-1 min-w-0 cursor-pointer hover:text-accent-primary transition-colors"
                @click="openTrackDetail(track, album)"
              >
                <p class="truncate text-sm sm:text-base">{{ track.name }}</p>
                <p class="text-xs text-slate-500">{{ formatDuration(track.duration_ms) }}</p>
              </div>
              <div class="hidden sm:flex items-center gap-3">
                <div v-for="ranking in track.rankings" :key="ranking.user_id" class="text-center">
                  <div class="text-xs text-slate-500">{{ ranking.user_name?.split(' ')[0] }}</div>
                  <div class="font-heading font-bold" :class="getScoreColor(ranking.score)">
                    {{ ranking.score || '-' }}
                  </div>
                </div>
              </div>
              <div v-if="track.average_score" class="text-center min-w-[36px] sm:min-w-[40px]">
                <div class="text-xs text-slate-500 hidden sm:block">Avg</div>
                <div class="font-heading font-bold text-sm sm:text-base" :class="getScoreColor(track.average_score)">
                  {{ track.average_score }}
                </div>
              </div>
              <button
                @click.stop="openTrackRating(track, album)"
                class="flex items-center gap-1 px-2 sm:px-3 py-2 bg-white/10 text-white rounded-lg hover:bg-white/20 transition-colors text-sm min-h-[44px] min-w-[44px] justify-center flex-shrink-0"
              >
                <Star class="w-3 h-3" />
                <span class="hidden sm:inline">{{ getUserRanking(track.rankings)?.score || 'Rate' }}</span>
              </button>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- Search Modal -->
    <div
      v-if="showSearch"
      class="fixed inset-0 z-50 flex items-start justify-center p-4 pt-20 bg-black/70 overflow-y-auto"
      @click.self="closeSearch"
    >
      <div class="glass w-full max-w-2xl rounded-2xl overflow-hidden">
        <div class="p-4 border-b border-white/10 flex items-center gap-4">
          <SearchIcon class="w-5 h-5 text-slate-400" />
          <input
            v-model="query"
            @input="onSearch"
            type="text"
            placeholder="Search Spotify for albums..."
            class="flex-1 bg-transparent text-white placeholder-slate-500 focus:outline-none"
            autofocus
          />
          <Loader2 v-if="searching" class="w-5 h-5 text-slate-400 animate-spin" />
          <button @click="closeSearch" class="p-1 hover:bg-white/10 rounded-lg">
            <X class="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <div class="max-h-96 overflow-y-auto">
          <div v-if="searchResults.length > 0" class="p-2 space-y-1">
            <div
              v-for="album in searchResults"
              :key="album.spotify_id"
              class="flex items-center gap-4 p-3 hover:bg-white/5 rounded-xl transition-colors"
            >
              <img
                :src="album.cover_url || '/placeholder.svg'"
                :alt="album.name"
                class="w-14 h-14 rounded-lg object-cover bg-white/10"
              />

              <div class="flex-1 min-w-0">
                <h3 class="font-heading font-medium truncate">{{ album.name }}</h3>
                <p class="text-sm text-slate-400 truncate">{{ album.artist }}</p>
                <p class="text-xs text-slate-500">{{ album.release_date }}</p>
              </div>

              <button
                @click="addAlbum(album)"
                :disabled="addedIds.has(album.spotify_id) || addingId === album.spotify_id"
                class="flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all text-sm"
                :class="addedIds.has(album.spotify_id)
                  ? 'bg-accent-primary/20 text-accent-primary cursor-default'
                  : 'bg-accent-primary text-black hover:bg-accent-primary/90 disabled:opacity-50'"
              >
                <Loader2 v-if="addingId === album.spotify_id" class="w-4 h-4 animate-spin" />
                <Check v-else-if="addedIds.has(album.spotify_id)" class="w-4 h-4" />
                <Plus v-else class="w-4 h-4" />
                {{ addedIds.has(album.spotify_id) ? 'Added' : 'Add' }}
              </button>
            </div>
          </div>

          <div v-else-if="query && !searching" class="p-8 text-center text-slate-400">
            No albums found
          </div>

          <div v-else-if="!query" class="p-8 text-center text-slate-500">
            Start typing to search Spotify
          </div>
        </div>
      </div>
    </div>

    <!-- New Releases Modal -->
    <div
      v-if="showNewReleases"
      class="fixed inset-0 z-50 flex items-start justify-center p-4 pt-20 bg-black/70 overflow-y-auto"
      @click.self="closeNewReleases"
    >
      <div class="bg-bg-secondary border border-white/10 w-full max-w-2xl rounded-2xl overflow-hidden shadow-2xl">
        <div class="p-4 border-b border-white/10 flex items-center justify-between">
          <div class="flex items-center gap-3">
            <Sparkles class="w-5 h-5 text-accent-primary" />
            <h2 class="font-heading font-semibold text-lg">New Releases</h2>
          </div>
          <button @click="closeNewReleases" class="p-1 hover:bg-white/10 rounded-lg">
            <X class="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <div class="max-h-[70vh] overflow-y-auto">
          <div v-if="loadingReleases" class="p-8 text-center">
            <Loader2 class="w-8 h-8 text-slate-400 animate-spin mx-auto" />
            <p class="text-slate-500 mt-2">Loading new releases...</p>
          </div>

          <div v-else-if="newReleases.length > 0" class="p-2 space-y-1">
            <div
              v-for="album in newReleases"
              :key="album.spotify_id"
              class="flex items-center gap-4 p-3 hover:bg-white/5 rounded-xl transition-colors"
            >
              <img
                :src="album.cover_url || '/placeholder.svg'"
                :alt="album.name"
                class="w-14 h-14 rounded-lg object-cover bg-white/10"
              />

              <div class="flex-1 min-w-0">
                <h3 class="font-heading font-medium truncate">{{ album.name }}</h3>
                <p class="text-sm text-slate-400 truncate">{{ album.artist }}</p>
                <p class="text-xs text-slate-500">{{ album.release_date }}</p>
              </div>

              <span v-if="addedIds.has(album.spotify_id)" class="flex items-center gap-2 px-3 py-1.5 bg-accent-primary/20 text-accent-primary rounded-lg text-sm">
                <Check class="w-4 h-4" />
                Added
              </span>
              <button
                v-else-if="isAdmin"
                @click="addAlbum(album)"
                :disabled="addingId === album.spotify_id"
                class="flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all text-sm bg-accent-primary text-black hover:bg-accent-primary/90 disabled:opacity-50"
              >
                <Loader2 v-if="addingId === album.spotify_id" class="w-4 h-4 animate-spin" />
                <Plus v-else class="w-4 h-4" />
                Add
              </button>
            </div>
          </div>

          <div v-else class="p-8 text-center text-slate-500">
            No new releases found
          </div>
        </div>
      </div>
    </div>

    <!-- Track Detail Modal -->
    <TrackDetailModal
      v-if="selectedTrackId"
      :track-id="selectedTrackId"
      :current-user="currentUser"
      @close="closeTrackDetail"
      @rate="handleTrackDetailRate"
    />

    <!-- Rating modal -->
    <RatingModal
      v-if="ratingModal.show"
      :type="ratingModal.type"
      :item="ratingModal.item"
      :album="ratingModal.album"
      :current-user="currentUser"
      @close="closeRating"
      @submit="submitRating"
    />
  </div>
</template>
