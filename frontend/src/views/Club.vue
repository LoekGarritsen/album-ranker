<script setup>
import { ref, computed, inject, onMounted } from 'vue'
import {
  Trophy, Search, Vote, EyeOff, Eye, Sparkles, ChevronRight,
  Disc3, Check, X, Bookmark
} from 'lucide-vue-next'
import { useSession } from '../composables/useSession'

const currentUser = inject('currentUser')
const isAdmin = inject('isAdmin')
const { showToast } = useSession()

const rounds = ref([])
const current = ref(null)
const loading = ref(true)
const busy = ref(false)

// New round form
const newTitle = ref('')

// Nomination search
const query = ref('')
const searchResults = ref([])
const searching = ref(false)
const backlog = ref([])
let searchTimer = null

const canManage = computed(() =>
  current.value && (isAdmin.value || current.value.created_by === currentUser.value?.id)
)

const myNomination = computed(() =>
  current.value?.nominations.find(n => n.user_id === currentUser.value?.id)
)

const STEPS = ['nominating', 'voting', 'rating', 'revealed']
const STEP_LABELS = { nominating: 'Nominate', voting: 'Vote', rating: 'Blind rate', revealed: 'Reveal' }
const NEXT_LABEL = { nominating: 'Open voting', voting: 'Pick winner & start rating', rating: 'Reveal scores' }

async function load() {
  try {
    const res = await fetch('/api/club/rounds')
    if (res.ok) {
      const data = await res.json()
      rounds.value = data.rounds
      current.value = data.current
    }
  } catch (e) {
    console.error('Failed to load club rounds:', e)
  }
  loading.value = false
}

async function loadBacklog() {
  try {
    const res = await fetch('/api/listen-later')
    if (res.ok) backlog.value = (await res.json()).items
  } catch {}
}

async function createRound() {
  if (!newTitle.value.trim() || busy.value) return
  busy.value = true
  try {
    const res = await fetch('/api/club/rounds', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle.value.trim() }),
    })
    if (res.ok) {
      newTitle.value = ''
      await load()
    } else {
      showToast((await res.json()).detail || 'Could not start round', 'error')
    }
  } finally {
    busy.value = false
  }
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

async function nominate(album) {
  if (busy.value) return
  busy.value = true
  try {
    const res = await fetch(`/api/club/rounds/${current.value.id}/nominate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        spotify_id: album.spotify_id,
        name: album.name,
        artist: album.artist,
        cover_url: album.cover_url || album.image || null,
        release_date: album.release_date || null,
      }),
    })
    if (res.ok) {
      current.value = await res.json()
      query.value = ''
      searchResults.value = []
      showToast('Nomination locked in', 'success')
    }
  } finally {
    busy.value = false
  }
}

async function vote(nomination) {
  const res = await fetch(`/api/club/rounds/${current.value.id}/vote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nomination_id: nomination.id }),
  })
  if (res.ok) current.value = await res.json()
}

async function advance() {
  const next = STEPS[STEPS.indexOf(current.value.status) + 1]
  if (!next || busy.value) return
  busy.value = true
  try {
    const res = await fetch(`/api/club/rounds/${current.value.id}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: next }),
    })
    if (res.ok) {
      await load()
      showToast(next === 'revealed' ? 'Scores revealed!' : `Round moved to ${STEP_LABELS[next]}`, 'success')
    } else {
      showToast((await res.json()).detail || 'Could not advance round', 'error')
    }
  } finally {
    busy.value = false
  }
}

const pastRounds = computed(() => rounds.value.filter(r => r.status === 'revealed'))

onMounted(() => { load(); loadBacklog() })
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-8">
      <h1 class="text-3xl font-heading font-bold flex items-center gap-3">
        <Trophy class="w-8 h-8 text-accent-primary" />
        Album Club
      </h1>
    </div>

    <div v-if="loading" class="text-center py-12 text-text-subdued">Loading…</div>

    <template v-else>
      <!-- No open round: start one -->
      <div v-if="!current" class="glass p-6 mb-8 text-center">
        <Sparkles class="w-10 h-10 mx-auto mb-3 text-accent-primary" />
        <h2 class="text-xl font-heading font-bold mb-1">Start a club round</h2>
        <p class="text-text-subdued text-sm mb-4">
          Everyone nominates an album, the group votes, then rates it blind — scores stay hidden until the reveal.
        </p>
        <form @submit.prevent="createRound" class="flex gap-2 max-w-md mx-auto">
          <input v-model="newTitle" placeholder="Round title (e.g. Week 12)" class="input-base flex-1" />
          <button type="submit" :disabled="!newTitle.trim() || busy" class="btn-primary">Start</button>
        </form>
      </div>

      <!-- Current round -->
      <div v-else class="glass p-4 sm:p-6 mb-8">
        <div class="flex items-center justify-between flex-wrap gap-3 mb-5">
          <div>
            <h2 class="text-xl font-heading font-bold">{{ current.title }}</h2>
            <p class="text-xs text-text-subdued">started by {{ current.created_by_name }}</p>
          </div>
          <button v-if="canManage && current.status !== 'revealed'" @click="advance" :disabled="busy"
                  class="btn-primary flex items-center gap-2">
            {{ NEXT_LABEL[current.status] }}
            <ChevronRight class="w-4 h-4" />
          </button>
        </div>

        <!-- Status stepper -->
        <div class="flex items-center gap-1 sm:gap-2 mb-6 text-xs sm:text-sm">
          <template v-for="(step, i) in STEPS" :key="step">
            <div class="px-2.5 py-1 rounded-full whitespace-nowrap"
                 :class="step === current.status
                   ? 'bg-accent-primary text-black font-semibold'
                   : STEPS.indexOf(current.status) > i
                     ? 'bg-surface-highlight text-white'
                     : 'bg-surface-highlight/50 text-text-subdued'">
              {{ STEP_LABELS[step] }}
            </div>
            <div v-if="i < STEPS.length - 1" class="w-3 sm:w-6 border-t border-white/15"></div>
          </template>
        </div>

        <!-- NOMINATING -->
        <div v-if="current.status === 'nominating'">
          <div class="mb-4">
            <div class="relative">
              <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-text-subdued" />
              <input v-model="query" @input="onSearchInput"
                     :placeholder="myNomination ? 'Change your nomination…' : 'Search Spotify to nominate an album…'"
                     class="input-base pl-9 w-full" />
            </div>
            <div v-if="searchResults.length" class="mt-2 bg-surface-elevated rounded-lg overflow-hidden divide-y divide-white/5 max-h-72 overflow-y-auto">
              <button v-for="album in searchResults" :key="album.spotify_id" @click="nominate(album)"
                      class="w-full flex items-center gap-3 p-2.5 hover:bg-white/10 text-left transition-colors">
                <img :src="album.image || '/placeholder.svg'" class="w-10 h-10 rounded object-cover bg-surface-highlight" />
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm">{{ album.name }}</p>
                  <p class="truncate text-xs text-text-subdued">{{ album.artist }} · {{ album.release_date?.slice(0, 4) }}</p>
                </div>
                <span class="text-xs text-accent-primary shrink-0">Nominate</span>
              </button>
            </div>
            <div v-if="!query && backlog.length" class="mt-3">
              <p class="text-xs text-text-subdued mb-2 flex items-center gap-1">
                <Bookmark class="w-3 h-3" /> From your backlog
              </p>
              <div class="flex gap-2 overflow-x-auto scrollbar-hide pb-1">
                <button v-for="item in backlog.slice(0, 10)" :key="item.id"
                        @click="nominate({ spotify_id: item.spotify_id, name: item.name, artist: item.artist, cover_url: item.image, release_date: item.release_date })"
                        class="shrink-0 w-24 text-left card-interactive rounded-lg p-1.5">
                  <img :src="item.image || '/placeholder.svg'" class="w-full aspect-square rounded object-cover bg-surface-highlight mb-1" />
                  <p class="text-[11px] truncate">{{ item.name }}</p>
                </button>
              </div>
            </div>
          </div>

          <div v-if="current.nominations.length" class="space-y-2">
            <div v-for="nom in current.nominations" :key="nom.id"
                 class="flex items-center gap-3 glass p-2.5 rounded-lg"
                 :class="{ 'ring-1 ring-accent-primary': nom.user_id === currentUser?.id }">
              <img :src="nom.cover_url || '/placeholder.svg'" class="w-10 h-10 rounded object-cover bg-surface-highlight" />
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm">{{ nom.name }}</p>
                <p class="truncate text-xs text-text-subdued">{{ nom.artist }}</p>
              </div>
              <span class="text-xs text-text-subdued shrink-0">by {{ nom.user_name }}</span>
            </div>
          </div>
          <p v-else class="text-sm text-text-subdued">No nominations yet — be the first.</p>
        </div>

        <!-- VOTING -->
        <div v-else-if="current.status === 'voting'" class="space-y-2">
          <div v-for="nom in current.nominations" :key="nom.id"
               class="flex items-center gap-3 glass p-2.5 rounded-lg">
            <img :src="nom.cover_url || '/placeholder.svg'" class="w-12 h-12 rounded object-cover bg-surface-highlight" />
            <div class="min-w-0 flex-1">
              <p class="truncate">{{ nom.name }}</p>
              <p class="truncate text-xs text-text-subdued">{{ nom.artist }} · nominated by {{ nom.user_name }}</p>
            </div>
            <span class="text-sm font-heading font-bold text-text-subdued shrink-0">{{ nom.votes }}</span>
            <button @click="vote(nom)"
                    class="shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-full text-sm transition-colors min-h-[40px]"
                    :class="current.my_vote === nom.id
                      ? 'bg-accent-primary text-black font-semibold'
                      : 'bg-surface-highlight hover:bg-surface-elevated'">
              <Vote class="w-4 h-4" />
              {{ current.my_vote === nom.id ? 'Voted' : 'Vote' }}
            </button>
          </div>
        </div>

        <!-- RATING (blind) -->
        <div v-else-if="current.status === 'rating'" class="text-center">
          <div class="flex flex-col sm:flex-row items-center gap-4 sm:gap-6 glass p-4 rounded-lg text-left">
            <img :src="current.album?.cover_url || '/placeholder.svg'"
                 class="w-32 h-32 rounded-lg object-cover bg-surface-highlight shadow-xl" />
            <div class="min-w-0 flex-1 text-center sm:text-left">
              <p class="text-xs uppercase tracking-wider text-accent-primary font-bold mb-1 flex items-center gap-1.5 justify-center sm:justify-start">
                <EyeOff class="w-4 h-4" /> Blind rating in progress
              </p>
              <h3 class="text-2xl font-heading font-bold truncate">{{ current.album?.name }}</h3>
              <p class="text-text-subdued mb-3">{{ current.album?.artist }}</p>
              <p class="text-sm text-text-subdued mb-4">
                Scores stay hidden until everyone rates. {{ current.rated_count }} rated so far
                <span v-if="current.my_rating"> — yours is in ({{ current.my_rating }}/10).</span>
                <span v-else> — yours is missing.</span>
              </p>
              <RouterLink :to="`/?album=${current.album?.id}`" class="btn-primary inline-flex items-center gap-2">
                <Disc3 class="w-4 h-4" />
                {{ current.my_rating ? 'Update your rating' : 'Rate it now' }}
              </RouterLink>
            </div>
          </div>
        </div>

        <!-- REVEALED -->
        <div v-else class="flex flex-col sm:flex-row items-center gap-4 sm:gap-6 glass p-4 rounded-lg">
          <img :src="current.album?.cover_url || '/placeholder.svg'"
               class="w-32 h-32 rounded-lg object-cover bg-surface-highlight shadow-xl" />
          <div class="min-w-0 flex-1 text-center sm:text-left">
            <p class="text-xs uppercase tracking-wider text-green-400 font-bold mb-1 flex items-center gap-1.5 justify-center sm:justify-start">
              <Eye class="w-4 h-4" /> Revealed
            </p>
            <h3 class="text-2xl font-heading font-bold truncate">{{ current.album?.name }}</h3>
            <p class="text-text-subdued mb-3">{{ current.album?.artist }}</p>
            <RouterLink to="/results" class="btn-secondary inline-flex items-center gap-2">See the scores</RouterLink>
          </div>
        </div>
      </div>

      <!-- Past rounds -->
      <div v-if="pastRounds.length">
        <h2 class="text-lg font-heading font-bold mb-3">Past rounds</h2>
        <div class="space-y-2">
          <div v-for="round in pastRounds" :key="round.id" class="glass p-3 flex items-center gap-3">
            <img :src="round.album?.cover_url || '/placeholder.svg'" class="w-10 h-10 rounded object-cover bg-surface-highlight" />
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm">{{ round.title }} — {{ round.album?.name || 'no album' }}</p>
              <p class="truncate text-xs text-text-subdued">{{ round.album?.artist }}</p>
            </div>
            <Check class="w-4 h-4 text-green-400 shrink-0" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
