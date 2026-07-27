<script setup>
import { computed, inject } from 'vue'
import { X, Mic, ListMusic, Music, Disc3, ThumbsUp, Play } from 'lucide-vue-next'
import LyricsPanel from './session/LyricsPanel.vue'
import { useSession } from '../composables/useSession'
import { useSpotifyPlayer } from '../composables/useSpotifyPlayer'
import { usePanel } from '../composables/usePanel'

const currentUser = inject('currentUser', null)

const {
  session,
  album,
  media,
  queue,
  currentTrack,
  isPlaying,
  playbackPosition,
  currentTrackDuration,
  isHangout,
  hasAlbum,
  selectTrack,
  formatDuration
} = useSession()

const {
  isReady: spotifyReady,
  isPaused: spotifyPaused,
  position: spotifyPosition,
  duration: spotifyDuration,
  currentTrack: spotifyCurrentTrack
} = useSpotifyPlayer()

const { panelView, closePanel } = usePanel()

const coverImage = computed(() => (isHangout.value
  ? media.value?.image
  : album.value?.cover_url || media.value?.image) || null)

const nowTitle = computed(() => (isHangout.value
  ? media.value?.name
  : currentTrack.value?.name || media.value?.name) || 'Nothing playing')

const nowSubtitle = computed(() => (isHangout.value
  ? media.value?.artist
  : album.value?.artist || media.value?.artist) || '')

// "what number is playing" — track position within the album
const trackPosition = computed(() => {
  if (isHangout.value || !currentTrack.value || !album.value?.tracks?.length) return null
  return `Track ${currentTrack.value.track_number} of ${album.value.tracks.length}`
})

// Upcoming album tracks (listening mode queue equivalent)
const upcomingTracks = computed(() => {
  if (isHangout.value || !album.value?.tracks || !currentTrack.value) return []
  return album.value.tracks.filter(t => t.track_number > currentTrack.value.track_number)
})

// Same source logic as Session.vue: hangout album context only has lyrics
// for the local SDK listener; everyone else lacks a track identity.
const lyricsTrack = computed(() => {
  if (isHangout.value) {
    const m = media.value
    if (!m) return null
    if (m.type === 'track') {
      return {
        spotifyId: m.spotify_id,
        name: m.name,
        artist: m.artist,
        album: m.album_name || '',
        durationMs: m.duration_ms || 0
      }
    }
    const t = spotifyReady.value ? spotifyCurrentTrack.value : null
    if (!t) return null
    return {
      spotifyId: t.id,
      name: t.name,
      artist: t.artists?.[0]?.name || m.artist,
      album: t.album?.name || m.name,
      durationMs: spotifyDuration.value || 0
    }
  }
  const t = currentTrack.value
  if (!t) return null
  return {
    spotifyId: t.spotify_id,
    name: t.name,
    artist: album.value?.artist || '',
    album: album.value?.name || '',
    durationMs: t.duration_ms || currentTrackDuration.value || 0
  }
})

const lyricsPosition = computed(() =>
  isHangout.value && media.value?.type === 'album' ? spotifyPosition.value : playbackPosition.value
)
const lyricsPlaying = computed(() =>
  isHangout.value && media.value?.type === 'album' ? !spotifyPaused.value : isPlaying.value
)

function playTrack(track) {
  selectTrack(track.id, currentUser?.value)
}
</script>

<template>
  <aside class="fixed inset-x-2 top-2 bottom-2 z-40 lg:static lg:z-auto lg:w-80 lg:shrink-0 flex flex-col">
    <div class="bg-bg-primary rounded-lg flex-1 flex flex-col min-h-0 overflow-hidden shadow-2xl shadow-black/60 lg:shadow-none">
      <!-- Header -->
      <div class="flex items-center gap-2 px-4 py-3 shrink-0">
        <component :is="panelView === 'lyrics' ? Mic : ListMusic" class="w-4 h-4 text-accent-primary" />
        <span class="font-bold text-sm truncate">{{ panelView === 'lyrics' ? 'Lyrics' : 'Queue' }}</span>
        <span class="text-xs text-text-subdued truncate">· {{ session?.name }}</span>
        <button @click="closePanel" class="ml-auto p-1.5 rounded-full text-text-subdued hover:text-white hover:bg-surface-highlight transition-colors" aria-label="Close panel">
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Now playing summary -->
      <div class="flex items-center gap-3 px-4 pb-3 shrink-0">
        <img v-if="coverImage" :src="coverImage" class="w-12 h-12 rounded-md object-cover bg-surface-highlight" />
        <div v-else class="w-12 h-12 rounded-md bg-surface-highlight flex items-center justify-center">
          <Music class="w-5 h-5 text-text-subdued" />
        </div>
        <div class="min-w-0">
          <p class="truncate font-semibold text-sm" :class="{ 'text-accent-primary': isPlaying }">{{ nowTitle }}</p>
          <p class="truncate text-xs text-text-subdued">{{ nowSubtitle }}</p>
          <p v-if="trackPosition" class="text-xs text-text-subdued">{{ trackPosition }}</p>
        </div>
      </div>
      <div class="mx-4 border-t border-white/10 shrink-0"></div>

      <!-- Lyrics view -->
      <LyricsPanel
        v-if="panelView === 'lyrics'"
        bare
        :track="lyricsTrack"
        :position="lyricsPosition"
        :playing="lyricsPlaying"
      />

      <!-- Queue view -->
      <div v-else class="flex-1 min-h-0 overflow-y-auto px-2 py-3">
        <!-- Hangout: shared queue -->
        <template v-if="isHangout">
          <p class="px-2 mb-2 text-xs font-bold uppercase tracking-wider text-text-subdued">Next in queue</p>
          <div v-if="queue.length === 0" class="px-2 py-6 text-center text-sm text-text-subdued">
            Queue is empty — anyone can add songs
          </div>
          <div
            v-for="item in queue"
            :key="item.id"
            class="flex items-center gap-3 px-2 py-2 rounded-md hover:bg-white/5"
          >
            <img v-if="item.image" :src="item.image" class="w-10 h-10 rounded-md object-cover bg-surface-highlight" />
            <div v-else class="w-10 h-10 rounded-md bg-surface-highlight flex items-center justify-center">
              <component :is="item.type === 'album' ? Disc3 : Music" class="w-4 h-4 text-text-subdued" />
            </div>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium truncate">{{ item.name }}</p>
              <p class="text-xs text-text-subdued truncate">{{ item.artist }}<span v-if="item.type === 'album'"> · Album</span></p>
            </div>
            <span v-if="item.votes?.length" class="flex items-center gap-1 text-xs text-text-subdued shrink-0">
              <ThumbsUp class="w-3 h-3" />{{ item.votes.reduce((s, v) => s + v.vote, 0) }}
            </span>
          </div>
        </template>

        <!-- Listening: rest of the album -->
        <template v-else-if="hasAlbum">
          <p class="px-2 mb-2 text-xs font-bold uppercase tracking-wider text-text-subdued">Next from {{ album.name }}</p>
          <div v-if="upcomingTracks.length === 0" class="px-2 py-6 text-center text-sm text-text-subdued">
            End of the album
          </div>
          <button
            v-for="track in upcomingTracks"
            :key="track.id"
            @click="playTrack(track)"
            class="w-full flex items-center gap-3 px-2 py-2 rounded-md hover:bg-white/5 text-left group transition-colors"
          >
            <span class="w-6 text-center text-sm text-text-subdued tabular-nums shrink-0">
              <span class="group-hover:hidden">{{ track.track_number }}</span>
              <Play class="w-4 h-4 mx-auto hidden group-hover:block fill-current text-white" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="text-sm font-medium truncate">{{ track.name }}</p>
              <p class="text-xs text-text-subdued">{{ formatDuration(track.duration_ms) }}</p>
            </div>
          </button>
        </template>

        <div v-else class="px-2 py-6 text-center text-sm text-text-subdued">
          Nothing queued yet
        </div>
      </div>
    </div>
  </aside>
</template>
