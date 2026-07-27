<script setup>
import { computed } from 'vue'
import { Play, Pause, Music, Disc3, Search, Heart, RefreshCw, ThumbsUp, ThumbsDown } from 'lucide-vue-next'

const props = defineProps({
  media: { type: Object, default: null },
  isPlaying: { type: Boolean, default: false },
  position: { type: Number, default: 0 },
  duration: { type: Number, default: 0 },
  // Spotify's own now-playing (album context advances tracks by itself)
  liveTrackName: { type: String, default: null },
  isFavorite: { type: Boolean, default: false },
  // Room-wide like/dislike on the current song; majority dislike skips it
  likes: { type: Number, default: 0 },
  dislikes: { type: Number, default: 0 },
  myVote: { type: Number, default: 0 }, // 1 | -1 | 0
  showSync: { type: Boolean, default: false },
  isSyncing: { type: Boolean, default: false }
})

const emit = defineEmits(['toggle', 'seek', 'search', 'favorite', 'vote', 'sync'])

const isTrack = computed(() => props.media?.type === 'track')

const progressPercent = computed(() => {
  if (!props.duration) return 0
  return Math.min(100, (props.position / props.duration) * 100)
})

function formatDuration(ms) {
  if (!ms) return '0:00'
  const mins = Math.floor(ms / 60000)
  const secs = Math.floor((ms % 60000) / 1000)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

function handleProgressClick(event) {
  if (!isTrack.value) return
  const rect = event.currentTarget.getBoundingClientRect()
  const percent = ((event.clientX - rect.left) / rect.width) * 100
  emit('seek', Math.max(0, Math.min(100, percent)))
}
</script>

<template>
  <div class="glass overflow-hidden">
    <!-- Empty: nothing on yet -->
    <div v-if="!media" class="p-6 text-center">
      <Music class="w-10 h-10 mx-auto mb-3 text-white/40" />
      <p class="text-text-subdued font-medium mb-1">Nothing playing</p>
      <p class="text-sm text-text-subdued mb-4">Put on a song or album for the room</p>
      <div class="flex items-center justify-center gap-2">
        <button
          @click="emit('search')"
          class="inline-flex items-center gap-2 px-5 py-2.5 bg-accent-primary text-black font-medium rounded-xl hover:bg-accent-primary/90 transition-colors"
        >
          <Search class="w-4 h-4" />
          Search music
        </button>
        <button
          @click="emit('sync')"
          :disabled="isSyncing"
          class="p-2.5 rounded-xl hover:bg-white/10 transition-colors text-text-subdued"
          :class="{ 'animate-spin': isSyncing }"
          aria-label="Refresh room state"
          title="Refresh room state"
        >
          <RefreshCw class="w-4 h-4" />
        </button>
      </div>
    </div>

    <template v-else>
      <!-- Big cover -->
      <div class="relative aspect-square w-full bg-white/5">
        <img v-if="media.image" :src="media.image" :alt="media.name" class="w-full h-full object-cover" />
        <div v-else class="w-full h-full flex items-center justify-center">
          <Disc3 class="w-16 h-16 text-white/40" />
        </div>
        <span class="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-black/60 backdrop-blur text-xs font-medium">
          <component :is="isTrack ? Music : Disc3" class="w-3 h-3" />
          {{ isTrack ? 'Song' : 'Album' }}
        </span>
      </div>

      <div class="p-4">
        <div class="flex items-center gap-3 mb-3">
          <div class="flex-1 min-w-0">
            <p class="font-heading font-semibold truncate" :class="{ 'text-accent-primary': isPlaying }">
              {{ media.name }}
            </p>
            <p class="text-sm text-text-subdued truncate">{{ media.artist }}</p>
            <p v-if="!isTrack && liveTrackName" class="text-xs text-text-subdued truncate mt-0.5">
              ♪ {{ liveTrackName }}
            </p>
          </div>
          <button
            v-if="showSync"
            @click="emit('sync')"
            :disabled="isSyncing"
            class="p-2.5 rounded-full hover:bg-white/10 transition-colors flex-shrink-0 text-text-subdued"
            :class="{ 'animate-spin': isSyncing }"
            aria-label="Sync with room"
            title="Sync with room"
          >
            <RefreshCw class="w-5 h-5" />
          </button>
          <button
            @click="emit('favorite')"
            class="p-2.5 rounded-full hover:bg-white/10 transition-colors flex-shrink-0"
            :class="isFavorite ? 'text-pink-400' : 'text-text-subdued hover:text-pink-400'"
            :aria-label="isFavorite ? 'Remove from favorites' : 'Add to favorites'"
            :aria-pressed="isFavorite"
          >
            <Heart class="w-5 h-5" :class="isFavorite ? 'fill-pink-400' : ''" />
          </button>
          <button
            @click="emit('toggle')"
            class="p-3 bg-accent-primary text-black rounded-full hover:bg-accent-primary/90 transition-colors flex-shrink-0"
            :aria-label="isPlaying ? 'Pause' : 'Play'"
          >
            <Pause v-if="isPlaying" class="w-5 h-5" />
            <Play v-else class="w-5 h-5 ml-0.5" />
          </button>
        </div>

        <!-- Room vote on the current song: majority dislike skips it -->
        <div class="flex items-center gap-2 mb-3">
          <button
            @click="emit('vote', 'up')"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-colors min-h-[36px]"
            :class="myVote === 1 ? 'bg-green-400/15 text-green-400' : 'bg-white/5 text-text-subdued hover:text-green-400 hover:bg-white/10'"
            aria-label="Like this song"
            :aria-pressed="myVote === 1"
          >
            <ThumbsUp class="w-4 h-4" />
            <span class="tabular-nums">{{ likes }}</span>
          </button>
          <button
            @click="emit('vote', 'down')"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm transition-colors min-h-[36px]"
            :class="myVote === -1 ? 'bg-red-400/15 text-red-400' : 'bg-white/5 text-text-subdued hover:text-red-400 hover:bg-white/10'"
            aria-label="Dislike this song"
            :aria-pressed="myVote === -1"
            title="Majority dislikes skip the song"
          >
            <ThumbsDown class="w-4 h-4" />
            <span class="tabular-nums">{{ dislikes }}</span>
          </button>
        </div>

        <!-- Track: seekable progress. Album: Spotify drives track order. -->
        <template v-if="isTrack">
          <div
            class="h-2 bg-white/10 rounded-full overflow-hidden cursor-pointer"
            @click="handleProgressClick"
            role="slider"
            :aria-valuenow="Math.round(progressPercent)"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-label="Seek"
          >
            <div class="h-full bg-accent-primary rounded-full transition-all duration-100" :style="{ width: progressPercent + '%' }"></div>
          </div>
          <div class="flex justify-between text-xs text-text-subdued tabular-nums mt-1.5">
            <span>{{ formatDuration(position) }}</span>
            <span>{{ formatDuration(duration) }}</span>
          </div>
        </template>
        <p v-else class="text-xs text-text-subdued">Full album — Spotify plays it through</p>
      </div>
    </template>
  </div>
</template>
