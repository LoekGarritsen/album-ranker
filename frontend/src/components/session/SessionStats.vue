<script setup>
import { computed } from 'vue'
import { Disc3, Music, User, ListChecks, TrendingUp, TrendingDown, Scale, Star, MessageCircle, BarChart3 } from 'lucide-vue-next'

const props = defineProps({
  album: { type: Object, required: true },
  currentUser: { type: Object, default: null }
})

const emit = defineEmits(['rate-album'])

function getScoreColor(score) {
  if (score == null) return 'text-text-subdued'
  if (score >= 8) return 'text-green-400'
  if (score >= 6) return 'text-yellow-400'
  if (score >= 4) return 'text-orange-400'
  return 'text-red-400'
}

// Users who rated at least one track or the album (skip placeholder rows)
const raters = computed(() => {
  const map = new Map()
  for (const t of props.album?.tracks || []) {
    for (const r of t.rankings || []) {
      if (r.score != null && !map.has(r.user_id)) {
        map.set(r.user_id, { user_id: r.user_id, user_name: r.user_name })
      }
    }
  }
  for (const r of props.album?.album_rankings || []) {
    if (r.score != null && !map.has(r.user_id)) {
      map.set(r.user_id, { user_id: r.user_id, user_name: r.user_name })
    }
  }
  return [...map.values()]
})

const tracks = computed(() => props.album?.tracks || [])

function scoreFor(track, userId) {
  return track.rankings?.find(r => r.user_id === userId && r.score != null)?.score ?? null
}

function trackAvg(track) {
  const scored = (track.rankings || []).filter(r => r.score != null)
  if (!scored.length) return null
  return scored.reduce((s, r) => s + r.score, 0) / scored.length
}

const groupAlbumAvg = computed(() => {
  const scores = (props.album?.album_rankings || []).filter(r => r.score != null).map(r => r.score)
  if (!scores.length) return null
  return scores.reduce((a, b) => a + b, 0) / scores.length
})

const groupTrackAvg = computed(() => {
  const scores = tracks.value.flatMap(t => (t.rankings || []).filter(r => r.score != null).map(r => r.score))
  if (!scores.length) return null
  return scores.reduce((a, b) => a + b, 0) / scores.length
})

const myAvg = computed(() => {
  if (!props.currentUser) return null
  const scores = tracks.value
    .map(t => scoreFor(t, props.currentUser.id))
    .filter(s => s != null)
  if (!scores.length) return null
  return scores.reduce((a, b) => a + b, 0) / scores.length
})

const myRatedCount = computed(() => {
  if (!props.currentUser) return 0
  return tracks.value.filter(t => scoreFor(t, props.currentUser.id) != null).length
})

const myAlbumRanking = computed(() =>
  props.album?.album_rankings?.find(r => r.user_id === props.currentUser?.id && r.score != null) || null
)

const ratedTrackAverages = computed(() =>
  tracks.value
    .map(t => ({ track: t, avg: trackAvg(t) }))
    .filter(x => x.avg != null)
)

const bestTrack = computed(() => {
  if (!ratedTrackAverages.value.length) return null
  return ratedTrackAverages.value.reduce((a, b) => (b.avg > a.avg ? b : a))
})

const worstTrack = computed(() => {
  if (ratedTrackAverages.value.length < 2) return null
  return ratedTrackAverages.value.reduce((a, b) => (b.avg < a.avg ? b : a))
})

// Track with the widest score spread between raters (needs >=2 scores)
const biggestSplit = computed(() => {
  let result = null
  for (const t of tracks.value) {
    const scores = (t.rankings || []).filter(r => r.score != null).map(r => r.score)
    if (scores.length < 2) continue
    const range = Math.max(...scores) - Math.min(...scores)
    if (!result || range > result.range) {
      result = { track: t, range, min: Math.min(...scores), max: Math.max(...scores) }
    }
  }
  return result && result.range >= 1 ? result : null
})

const albumRatingsWithScore = computed(() =>
  (props.album?.album_rankings || []).filter(r => r.score != null)
)

const hasAnyRatings = computed(() =>
  raters.value.length > 0
)
</script>

<template>
  <div class="space-y-4">
    <!-- Empty state -->
    <div v-if="!hasAnyRatings" class="glass p-8 text-center">
      <BarChart3 class="w-12 h-12 mx-auto mb-3 text-white/40" />
      <p class="text-text-subdued font-medium mb-1">No ratings yet</p>
      <p class="text-sm text-text-subdued">Stats appear as people rate tracks</p>
    </div>

    <template v-else>
      <!-- Summary tiles -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="glass p-4 text-center">
          <Disc3 class="w-6 h-6 mx-auto mb-1.5 text-accent-primary" />
          <div class="text-2xl font-heading font-bold" :class="getScoreColor(groupAlbumAvg)">
            {{ groupAlbumAvg != null ? groupAlbumAvg.toFixed(1) : '–' }}
          </div>
          <div class="text-xs text-text-subdued">Album Score</div>
        </div>
        <div class="glass p-4 text-center">
          <Music class="w-6 h-6 mx-auto mb-1.5 text-blue-400" />
          <div class="text-2xl font-heading font-bold" :class="getScoreColor(groupTrackAvg)">
            {{ groupTrackAvg != null ? groupTrackAvg.toFixed(1) : '–' }}
          </div>
          <div class="text-xs text-text-subdued">Track Average</div>
        </div>
        <div class="glass p-4 text-center">
          <User class="w-6 h-6 mx-auto mb-1.5 text-purple-400" />
          <div class="text-2xl font-heading font-bold" :class="getScoreColor(myAvg)">
            {{ myAvg != null ? myAvg.toFixed(1) : '–' }}
          </div>
          <div class="text-xs text-text-subdued">Your Average</div>
        </div>
        <div class="glass p-4 text-center">
          <ListChecks class="w-6 h-6 mx-auto mb-1.5 text-yellow-400" />
          <div class="text-2xl font-heading font-bold" :class="myRatedCount === tracks.length ? 'text-green-400' : ''">
            {{ myRatedCount }}/{{ tracks.length }}
          </div>
          <div class="text-xs text-text-subdued">Your Progress</div>
        </div>
      </div>

      <!-- Rate album CTA -->
      <button
        v-if="myRatedCount === tracks.length && tracks.length > 0 && !myAlbumRanking"
        @click="emit('rate-album')"
        class="w-full flex items-center justify-center gap-2 px-4 py-3 bg-accent-primary text-black font-bold rounded-full hover:bg-accent-bright transition-colors"
      >
        <Star class="w-4 h-4" />
        All tracks rated — rate the album!
      </button>

      <!-- Highlights -->
      <div v-if="bestTrack" class="glass p-4 space-y-2.5">
        <div class="flex items-center gap-2 text-sm min-w-0">
          <TrendingUp class="w-4 h-4 text-green-400 flex-shrink-0" />
          <span class="text-text-subdued flex-shrink-0">Best:</span>
          <span class="truncate text-white/90">{{ bestTrack.track.name }}</span>
          <span class="font-heading font-bold ml-auto flex-shrink-0" :class="getScoreColor(bestTrack.avg)">{{ bestTrack.avg.toFixed(1) }}</span>
        </div>
        <div v-if="worstTrack && worstTrack.track.id !== bestTrack.track.id" class="flex items-center gap-2 text-sm min-w-0">
          <TrendingDown class="w-4 h-4 text-red-400 flex-shrink-0" />
          <span class="text-text-subdued flex-shrink-0">Worst:</span>
          <span class="truncate text-white/90">{{ worstTrack.track.name }}</span>
          <span class="font-heading font-bold ml-auto flex-shrink-0" :class="getScoreColor(worstTrack.avg)">{{ worstTrack.avg.toFixed(1) }}</span>
        </div>
        <div v-if="biggestSplit" class="flex items-center gap-2 text-sm min-w-0">
          <Scale class="w-4 h-4 text-orange-400 flex-shrink-0" />
          <span class="text-text-subdued flex-shrink-0">Most divisive:</span>
          <span class="truncate text-white/90">{{ biggestSplit.track.name }}</span>
          <span class="text-xs text-text-subdued ml-auto flex-shrink-0">
            {{ biggestSplit.min.toFixed(1) }}–{{ biggestSplit.max.toFixed(1) }}
            <span class="text-orange-400">(Δ{{ biggestSplit.range.toFixed(1) }})</span>
          </span>
        </div>
      </div>

      <!-- Score matrix -->
      <div v-if="raters.length" class="glass overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-white/10 text-left">
                <th class="px-3 sm:px-4 py-2.5 font-medium text-text-subdued text-xs uppercase tracking-wider">Track</th>
                <th
                  v-for="rater in raters"
                  :key="rater.user_id"
                  class="px-2 py-2.5 font-medium text-text-subdued text-xs text-center"
                  :class="{ 'text-accent-primary': rater.user_id === currentUser?.id }"
                >
                  {{ rater.user_name?.split(' ')[0] }}
                </th>
                <th class="px-2 sm:px-3 py-2.5 font-medium text-text-subdued text-xs text-center uppercase tracking-wider">Avg</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="track in tracks" :key="track.id" class="border-b border-white/5 last:border-0">
                <td class="px-3 sm:px-4 py-2 max-w-[10rem] sm:max-w-xs">
                  <span class="text-text-subdued text-xs mr-1.5">{{ track.track_number }}</span>
                  <span class="text-white/90 truncate inline-block max-w-full align-bottom">{{ track.name }}</span>
                </td>
                <td
                  v-for="rater in raters"
                  :key="rater.user_id"
                  class="px-2 py-2 text-center font-heading font-bold"
                  :class="getScoreColor(scoreFor(track, rater.user_id))"
                >
                  {{ scoreFor(track, rater.user_id)?.toFixed(1) ?? '–' }}
                </td>
                <td class="px-2 sm:px-3 py-2 text-center font-heading font-bold bg-white/[0.03]" :class="getScoreColor(trackAvg(track))">
                  {{ trackAvg(track)?.toFixed(1) ?? '–' }}
                </td>
              </tr>
              <!-- Album row -->
              <tr class="border-t border-white/10 bg-white/[0.03]">
                <td class="px-3 sm:px-4 py-2.5 font-medium text-white/90">
                  <span class="flex items-center gap-1.5"><Disc3 class="w-3.5 h-3.5 text-accent-primary" /> Album</span>
                </td>
                <td
                  v-for="rater in raters"
                  :key="rater.user_id"
                  class="px-2 py-2.5 text-center font-heading font-bold"
                  :class="getScoreColor(album.album_rankings?.find(r => r.user_id === rater.user_id && r.score != null)?.score)"
                >
                  {{ album.album_rankings?.find(r => r.user_id === rater.user_id && r.score != null)?.score?.toFixed(1) ?? '–' }}
                </td>
                <td class="px-2 sm:px-3 py-2.5 text-center font-heading font-bold" :class="getScoreColor(groupAlbumAvg)">
                  {{ groupAlbumAvg?.toFixed(1) ?? '–' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Album rating comments -->
      <div v-if="albumRatingsWithScore.some(r => r.comment)" class="space-y-2">
        <h3 class="text-sm font-medium text-text-subdued">Album takes</h3>
        <div
          v-for="r in albumRatingsWithScore.filter(r => r.comment)"
          :key="r.user_id"
          class="glass p-3 sm:p-4"
        >
          <div class="flex items-center justify-between mb-1.5">
            <span class="font-medium text-sm">{{ r.user_name }}</span>
            <span class="font-heading font-bold" :class="getScoreColor(r.score)">{{ r.score.toFixed(1) }}</span>
          </div>
          <div class="text-sm text-text-subdued flex items-start gap-2">
            <MessageCircle class="w-4 h-4 mt-0.5 flex-shrink-0 text-text-subdued" />
            <span>{{ r.comment }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
