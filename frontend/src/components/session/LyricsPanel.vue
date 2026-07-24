<script setup>
import { computed, ref, watch, nextTick, toRef } from 'vue'
import { Mic, Music } from 'lucide-vue-next'
import { useLyrics } from '../../composables/useLyrics'

const props = defineProps({
  // { spotifyId, name, artist, album, durationMs } | null
  track: { type: Object, default: null },
  position: { type: Number, default: 0 },
  playing: { type: Boolean, default: false }
})

const { loading, found, instrumental, syncedLines, plainLyrics, activeIndex } =
  useLyrics(
    toRef(props, 'track'),
    toRef(props, 'position'),
    toRef(props, 'playing')
  )

const hasSynced = computed(() => syncedLines.value.length > 0)
const scrollEl = ref(null)
const lineEls = ref([])

// Auto-scroll suspends while the user scrolls; resumes after 3s idle
const userScrolling = ref(false)
let scrollIdleTimer = null
let autoScrolling = false

function onScroll() {
  if (autoScrolling) return
  userScrolling.value = true
  clearTimeout(scrollIdleTimer)
  scrollIdleTimer = setTimeout(() => { userScrolling.value = false }, 3000)
}

watch(activeIndex, async (idx) => {
  if (idx < 0 || userScrolling.value || !scrollEl.value) return
  await nextTick()
  const el = lineEls.value[idx]
  if (!el) return
  autoScrolling = true
  const container = scrollEl.value
  const target = el.offsetTop - container.clientHeight / 2 + el.clientHeight / 2
  container.scrollTo({ top: Math.max(0, target), behavior: 'smooth' })
  // Smooth scroll fires scroll events for a while — release the flag late
  setTimeout(() => { autoScrolling = false }, 600)
})

// Jump back to top on track change
watch(() => props.track?.spotifyId, () => {
  lineEls.value = []
  userScrolling.value = false
  if (scrollEl.value) scrollEl.value.scrollTop = 0
})
</script>

<template>
  <div class="glass overflow-hidden">
    <div class="flex items-center gap-3 p-4 border-b border-white/10">
      <Mic class="w-5 h-5 text-accent-primary" />
      <span class="font-medium">Lyrics</span>
      <span v-if="track && hasSynced" class="text-xs text-slate-500 ml-auto truncate">{{ track.name }}</span>
    </div>

    <!-- Nothing playing -->
    <div v-if="!track" class="p-8 text-center text-slate-500 text-sm">
      <Music class="w-8 h-8 mx-auto mb-2 text-slate-600" />
      Nothing playing
    </div>

    <div v-else-if="loading" class="p-8 text-center text-slate-500 text-sm">
      Looking up lyrics…
    </div>

    <div v-else-if="instrumental" class="p-8 text-center text-slate-500 text-sm">
      ♪ Instrumental
    </div>

    <!-- Synced lyrics -->
    <div
      v-else-if="hasSynced"
      ref="scrollEl"
      @scroll="onScroll"
      class="max-h-[420px] overflow-y-auto px-5 py-6 space-y-1 scroll-smooth"
    >
      <p
        v-for="(line, i) in syncedLines"
        :key="i"
        :ref="el => { if (el) lineEls[i] = el }"
        class="py-1.5 text-lg leading-snug transition-all duration-300 font-heading"
        :class="i === activeIndex
          ? 'text-white font-semibold scale-[1.02] origin-left'
          : i < activeIndex ? 'text-slate-500' : 'text-slate-400'"
      >
        {{ line.text || '♪' }}
      </p>
      <div class="h-32"></div>
    </div>

    <!-- Plain lyrics fallback (no timestamps) -->
    <div v-else-if="plainLyrics" class="max-h-[420px] overflow-y-auto px-5 py-6">
      <p class="text-xs text-slate-500 mb-3">No synced version — plain lyrics</p>
      <p class="whitespace-pre-line text-slate-300 leading-relaxed">{{ plainLyrics }}</p>
    </div>

    <div v-else class="p-8 text-center text-slate-500 text-sm">
      No lyrics found for this track
    </div>
  </div>
</template>
