<script setup>
import { computed } from 'vue'
import { Music, Disc3, Search } from 'lucide-vue-next'

const props = defineProps({
  media: { type: Object, default: null },
  isPlaying: { type: Boolean, default: false },
  // Spotify's own now-playing (album context advances tracks by itself)
  liveTrackName: { type: String, default: null }
})

const emit = defineEmits(['search'])

const isTrack = computed(() => props.media?.type === 'track')
</script>

<template>
  <div class="glass overflow-hidden">
    <!-- Empty: nothing on yet -->
    <div v-if="!media" class="p-6 text-center">
      <Music class="w-10 h-10 mx-auto mb-3 text-white/40" />
      <p class="text-text-subdued font-medium mb-1">Nothing playing</p>
      <p class="text-sm text-text-subdued mb-4">Put on a song or album for the room</p>
      <button
        @click="emit('search')"
        class="inline-flex items-center gap-2 px-5 py-2.5 bg-accent-primary text-black font-bold rounded-full hover:bg-accent-bright transition-colors"
      >
        <Search class="w-4 h-4" />
        Search music
      </button>
    </div>

    <template v-else>
      <!-- Big cover; playback, votes, and favorite live in the player bar -->
      <div class="relative aspect-square w-full bg-white/5">
        <img v-if="media.image" :src="media.image" :alt="media.name" class="w-full h-full object-cover" />
        <div v-else class="w-full h-full flex items-center justify-center">
          <Disc3 class="w-16 h-16 text-white/40" />
        </div>
        <span class="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-black/60 text-xs font-medium">
          <component :is="isTrack ? Music : Disc3" class="w-3 h-3" />
          {{ isTrack ? 'Song' : 'Album' }}
        </span>
      </div>

      <div class="p-4">
        <p class="font-heading font-semibold truncate" :class="{ 'text-accent-primary': isPlaying }">
          {{ media.name }}
        </p>
        <p class="text-sm text-text-subdued truncate">{{ media.artist }}</p>
        <p v-if="!isTrack && liveTrackName" class="text-xs text-text-subdued truncate mt-0.5">
          ♪ {{ liveTrackName }}
        </p>
        <p v-if="!isTrack" class="text-xs text-text-subdued mt-2">Full album — Spotify plays it through</p>
      </div>
    </template>
  </div>
</template>
