<script setup>
import { ref, onMounted, inject, watch, computed } from 'vue'
import { Calendar, Star, Music, Disc3, TrendingUp, TrendingDown, Download } from 'lucide-vue-next'

const currentUser = inject('currentUser')

const selectedYear = ref(new Date().getFullYear())
const review = ref(null)
const loading = ref(true)
const rendering = ref(false)

const years = computed(() => {
  const current = new Date().getFullYear()
  return Array.from({ length: 5 }, (_, i) => current - i)
})

const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

async function loadReview() {
  if (!currentUser.value) return

  loading.value = true
  try {
    const res = await fetch(`/api/year-review/${selectedYear.value}?user_id=${currentUser.value.id}`)
    if (res.ok) {
      review.value = await res.json()
    }
  } catch (e) {
    console.error('Failed to load year review:', e)
  }
  loading.value = false
}

function getScoreColor(score) {
  if (!score) return 'text-text-subdued'
  if (score >= 8) return 'text-green-400'
  if (score >= 6) return 'text-yellow-400'
  if (score >= 4) return 'text-orange-400'
  return 'text-red-400'
}

function getActivityHeight(count) {
  if (!count) return 'h-1'
  if (count >= 50) return 'h-full'
  if (count >= 30) return 'h-4/5'
  if (count >= 20) return 'h-3/5'
  if (count >= 10) return 'h-2/5'
  return 'h-1/5'
}

// Cover images go through the backend proxy (authed fetch -> blob) so the
// canvas stays untainted and toBlob() works.
async function loadCover(url) {
  if (!url) return null
  try {
    const res = await fetch(`/api/image-proxy?url=${encodeURIComponent(url)}`)
    if (!res.ok) return null
    const blob = await res.blob()
    const img = new Image()
    img.src = URL.createObjectURL(blob)
    await img.decode()
    return img
  } catch {
    return null
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

async function downloadCard() {
  if (!review.value || rendering.value) return
  rendering.value = true
  try {
    const W = 1080, H = 1350
    const canvas = document.createElement('canvas')
    canvas.width = W
    canvas.height = H
    const ctx = canvas.getContext('2d')

    const bg = ctx.createLinearGradient(0, 0, W, H)
    bg.addColorStop(0, '#0f172a')
    bg.addColorStop(0.5, '#1e1b4b')
    bg.addColorStop(1, '#0a0a0a')
    ctx.fillStyle = bg
    ctx.fillRect(0, 0, W, H)

    ctx.fillStyle = '#1db954'
    ctx.font = 'bold 40px system-ui, sans-serif'
    ctx.fillText('ALBUM RANKER · YEAR IN REVIEW', 70, 110)

    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 150px system-ui, sans-serif'
    ctx.fillText(String(selectedYear.value), 70, 260)

    ctx.fillStyle = 'rgba(255,255,255,0.7)'
    ctx.font = '48px system-ui, sans-serif'
    ctx.fillText(currentUser.value?.name || '', 70, 330)

    // Stats row
    const stats = [
      [String(review.value.albums_rated || 0), 'albums rated'],
      [String(review.value.tracks_rated || 0), 'tracks rated'],
      [String(review.value.average_album_score ?? '-'), 'avg album'],
    ]
    stats.forEach(([num, label], i) => {
      const x = 70 + i * 330
      ctx.fillStyle = 'rgba(255,255,255,0.06)'
      roundRect(ctx, x, 380, 300, 160, 20)
      ctx.fill()
      ctx.fillStyle = '#1db954'
      ctx.font = 'bold 64px system-ui, sans-serif'
      ctx.fillText(num, x + 30, 465)
      ctx.fillStyle = 'rgba(255,255,255,0.6)'
      ctx.font = '30px system-ui, sans-serif'
      ctx.fillText(label, x + 30, 512)
    })

    // Top 5 albums with covers
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 44px system-ui, sans-serif'
    ctx.fillText('Top albums', 70, 640)

    const top = (review.value.top_albums || []).slice(0, 5)
    const covers = await Promise.all(top.map(a => loadCover(a.cover_url)))
    top.forEach((album, i) => {
      const y = 680 + i * 120
      ctx.fillStyle = 'rgba(255,255,255,0.05)'
      roundRect(ctx, 70, y, W - 140, 104, 16)
      ctx.fill()

      ctx.fillStyle = 'rgba(255,255,255,0.35)'
      ctx.font = 'bold 44px system-ui, sans-serif'
      ctx.fillText(String(i + 1), 95, y + 66)

      if (covers[i]) {
        ctx.save()
        roundRect(ctx, 160, y + 12, 80, 80, 10)
        ctx.clip()
        ctx.drawImage(covers[i], 160, y + 12, 80, 80)
        ctx.restore()
      }

      ctx.fillStyle = '#ffffff'
      ctx.font = 'bold 36px system-ui, sans-serif'
      const name = album.name.length > 32 ? album.name.slice(0, 31) + '…' : album.name
      ctx.fillText(name, 270, y + 48)
      ctx.fillStyle = 'rgba(255,255,255,0.55)'
      ctx.font = '28px system-ui, sans-serif'
      const artist = album.artist.length > 40 ? album.artist.slice(0, 39) + '…' : album.artist
      ctx.fillText(artist, 270, y + 84)

      ctx.fillStyle = '#1db954'
      ctx.font = 'bold 48px system-ui, sans-serif'
      const score = album.score?.toFixed(1) || '-'
      ctx.fillText(score, W - 190, y + 68)
    })

    ctx.fillStyle = 'rgba(255,255,255,0.35)'
    ctx.font = '30px system-ui, sans-serif'
    ctx.fillText('albums.garritsen.dev', 70, H - 60)

    canvas.toBlob((blob) => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `year-review-${selectedYear.value}-${(currentUser.value?.name || 'me').toLowerCase()}.png`
      a.click()
      URL.revokeObjectURL(a.href)
    }, 'image/png')
  } finally {
    rendering.value = false
  }
}

onMounted(loadReview)
watch([selectedYear, currentUser], loadReview)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-8 flex-wrap gap-4">
      <h1 class="text-3xl font-heading font-bold flex items-center gap-3">
        <Calendar class="w-8 h-8 text-accent-primary" />
        Year in Review
      </h1>

      <div class="flex items-center gap-2">
        <select
          v-model="selectedYear"
          class="px-4 py-2 bg-surface-highlight border border-transparent rounded-lg text-white focus:outline-none focus:border-accent-primary"
        >
          <option v-for="year in years" :key="year" :value="year">
            {{ year }}
          </option>
        </select>
        <button
          v-if="review && (review.albums_rated || review.tracks_rated)"
          @click="downloadCard"
          :disabled="rendering"
          class="btn-primary flex items-center gap-2"
        >
          <Download class="w-4 h-4" />
          {{ rendering ? 'Rendering…' : 'Share card' }}
        </button>
      </div>
    </div>

    <div v-if="!currentUser" class="text-center py-12 text-text-subdued">
      Select a user to see their year in review
    </div>

    <div v-else-if="loading" class="text-center py-12 text-text-subdued">
      Loading year review...
    </div>

    <div v-else-if="review" class="space-y-8">
      <!-- Stats Cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="glass p-4 text-center">
          <Disc3 class="w-8 h-8 mx-auto mb-2 text-accent-primary" />
          <div class="text-3xl font-heading font-bold">{{ review.albums_rated || 0 }}</div>
          <div class="text-sm text-text-subdued">Albums Rated</div>
        </div>
        <div class="glass p-4 text-center">
          <Music class="w-8 h-8 mx-auto mb-2 text-blue-400" />
          <div class="text-3xl font-heading font-bold">{{ review.tracks_rated || 0 }}</div>
          <div class="text-sm text-text-subdued">Tracks Rated</div>
        </div>
        <div class="glass p-4 text-center">
          <Star class="w-8 h-8 mx-auto mb-2 text-yellow-400" />
          <div class="text-3xl font-heading font-bold" :class="getScoreColor(review.average_album_score)">
            {{ review.average_album_score || '-' }}
          </div>
          <div class="text-sm text-text-subdued">Avg Album Score</div>
        </div>
        <div class="glass p-4 text-center">
          <Star class="w-8 h-8 mx-auto mb-2 text-purple-400" />
          <div class="text-3xl font-heading font-bold" :class="getScoreColor(review.average_track_score)">
            {{ review.average_track_score || '-' }}
          </div>
          <div class="text-sm text-text-subdued">Avg Track Score</div>
        </div>
      </div>

      <!-- Monthly Activity -->
      <div v-if="review.monthly_activity && Object.keys(review.monthly_activity).length" class="glass p-4 sm:p-6">
        <h2 class="text-lg font-heading font-semibold mb-4">Monthly Activity</h2>
        <div class="flex items-end gap-1 sm:gap-2 h-24 sm:h-32">
          <div
            v-for="(month, i) in months"
            :key="month"
            class="flex-1 flex flex-col items-center gap-1"
          >
            <div class="w-full bg-white/5 rounded-t relative h-16 sm:h-24 flex items-end">
              <div
                :class="getActivityHeight(review.monthly_activity[String(i + 1).padStart(2, '0')])"
                class="w-full bg-accent-primary/60 rounded-t transition-all"
              ></div>
            </div>
            <span class="text-[10px] sm:text-xs text-text-subdued">{{ month.slice(0, 1) }}</span>
          </div>
        </div>
        <div class="flex justify-between text-xs text-text-subdued mt-2 sm:hidden">
          <span>Jan</span>
          <span>Dec</span>
        </div>
      </div>

      <!-- Top Albums -->
      <div v-if="review.top_albums?.length" class="glass p-6">
        <h2 class="text-lg font-heading font-semibold mb-4 flex items-center gap-2">
          <TrendingUp class="w-5 h-5 text-green-400" />
          Top Albums
        </h2>
        <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="(album, i) in review.top_albums"
            :key="i"
            class="flex items-center gap-3 p-3 bg-surface-highlight rounded-lg"
          >
            <div class="text-2xl font-heading font-bold text-white/40 w-8">{{ i + 1 }}</div>
            <img
              :src="album.cover_url || '/placeholder.svg'"
              class="w-12 h-12 rounded-md object-cover bg-surface-highlight"
            />
            <div class="flex-1 min-w-0">
              <p class="truncate font-medium">{{ album.name }}</p>
              <p class="text-sm text-text-subdued truncate">{{ album.artist }}</p>
            </div>
            <div class="text-xl font-heading font-bold" :class="getScoreColor(album.score)">
              {{ album.score?.toFixed(1) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Top Tracks -->
      <div v-if="review.top_tracks?.length" class="glass p-6">
        <h2 class="text-lg font-heading font-semibold mb-4 flex items-center gap-2">
          <Music class="w-5 h-5 text-accent-primary" />
          Top Tracks
        </h2>
        <div class="space-y-2">
          <div
            v-for="(track, i) in review.top_tracks.slice(0, 10)"
            :key="i"
            class="flex items-center gap-3 p-2 hover:bg-white/5 rounded-lg transition-colors"
          >
            <div class="text-sm font-medium text-text-subdued w-6">{{ i + 1 }}</div>
            <img
              :src="track.cover_url || '/placeholder.svg'"
              class="w-10 h-10 rounded-md object-cover bg-surface-highlight"
            />
            <div class="flex-1 min-w-0">
              <p class="truncate">{{ track.name }}</p>
              <p class="text-xs text-text-subdued truncate">{{ track.album_name }}</p>
            </div>
            <div class="font-heading font-bold" :class="getScoreColor(track.score)">
              {{ track.score?.toFixed(1) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Worst Tracks (if any) -->
      <div v-if="review.worst_tracks?.length" class="glass p-6">
        <h2 class="text-lg font-heading font-semibold mb-4 flex items-center gap-2">
          <TrendingDown class="w-5 h-5 text-red-400" />
          Least Favorite Tracks
        </h2>
        <div class="space-y-2">
          <div
            v-for="(track, i) in review.worst_tracks"
            :key="i"
            class="flex items-center gap-3 p-2 hover:bg-white/5 rounded-lg transition-colors"
          >
            <img
              :src="track.cover_url || '/placeholder.svg'"
              class="w-10 h-10 rounded-md object-cover bg-surface-highlight"
            />
            <div class="flex-1 min-w-0">
              <p class="truncate">{{ track.name }}</p>
              <p class="text-xs text-text-subdued truncate">{{ track.album_name }}</p>
            </div>
            <div class="font-heading font-bold" :class="getScoreColor(track.score)">
              {{ track.score?.toFixed(1) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-if="!review.tracks_rated && !review.albums_rated" class="text-center py-12 text-text-subdued">
        No ratings found for {{ selectedYear }}
      </div>
    </div>
  </div>
</template>
