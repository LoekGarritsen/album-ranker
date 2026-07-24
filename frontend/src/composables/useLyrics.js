import { ref, watch, onUnmounted } from 'vue'

// Parse an LRC string into [{ time, text }] sorted by time (ms).
// Handles multiple timestamps per line, [offset:±ms], and skips metadata tags.
export function parseLrc(lrc) {
  if (!lrc) return []

  let offset = 0
  const offsetMatch = lrc.match(/\[offset:\s*([+-]?\d+)\s*\]/i)
  if (offsetMatch) offset = parseInt(offsetMatch[1], 10)

  const lines = []
  const timeTag = /\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]/g

  for (const raw of lrc.split('\n')) {
    const tags = [...raw.matchAll(timeTag)]
    if (!tags.length) continue

    const text = raw.replace(timeTag, '').trim()
    for (const tag of tags) {
      const mins = parseInt(tag[1], 10)
      const secs = parseInt(tag[2], 10)
      // Fraction: ".5" = 500ms, ".50" = 500ms, ".500" = 500ms
      const frac = tag[3] ? parseInt(tag[3].padEnd(3, '0'), 10) : 0
      lines.push({ time: mins * 60000 + secs * 1000 + frac - offset, text })
    }
  }

  return lines.sort((a, b) => a.time - b.time)
}

// Lyrics for the given track, with a rAF-smoothed playback clock and active
// line tracking. `track`, `position`, `playing` are refs/computeds:
// track = { spotifyId, name, artist, album, durationMs } | null
export function useLyrics(track, position, playing) {
  const loading = ref(false)
  const found = ref(false)
  const instrumental = ref(false)
  const syncedLines = ref([])
  const plainLyrics = ref(null)
  const activeIndex = ref(-1)

  // Smooth clock: anchor on every position update, interpolate with rAF
  let basePos = 0
  let baseTime = 0
  let rafId = null

  watch(position, (pos) => {
    basePos = pos
    baseTime = performance.now()
  }, { immediate: true })

  function smoothPosition() {
    return playing.value ? basePos + (performance.now() - baseTime) : basePos
  }

  function tick() {
    const lines = syncedLines.value
    if (lines.length) {
      const pos = smoothPosition()
      // Lines advance monotonically — step from the last index; fall back to
      // a full scan on seeks/backwards jumps.
      let idx = activeIndex.value
      if (idx >= 0 && idx < lines.length && lines[idx].time > pos) idx = -1
      while (idx + 1 < lines.length && lines[idx + 1].time <= pos) idx++
      if (idx !== activeIndex.value) activeIndex.value = idx
    }
    rafId = requestAnimationFrame(tick)
  }

  let fetchSeq = 0
  async function load(t) {
    const seq = ++fetchSeq
    syncedLines.value = []
    plainLyrics.value = null
    found.value = false
    instrumental.value = false
    activeIndex.value = -1

    if (!t?.spotifyId || !t?.name || !t?.artist) return

    loading.value = true
    try {
      const params = new URLSearchParams({
        spotify_track_id: t.spotifyId,
        track_name: t.name,
        artist_name: t.artist,
        album_name: t.album || '',
        duration_ms: String(t.durationMs || 0)
      })
      const res = await fetch(`/api/lyrics?${params}`)
      if (seq !== fetchSeq) return // stale response, a newer track took over
      if (res.ok) {
        const data = await res.json()
        if (seq !== fetchSeq) return
        found.value = data.found
        instrumental.value = data.instrumental
        syncedLines.value = parseLrc(data.synced_lyrics)
        plainLyrics.value = data.plain_lyrics
      }
    } catch {
      // Leave the not-found state; panel shows its empty message
    } finally {
      if (seq === fetchSeq) loading.value = false
    }
  }

  watch(() => track.value?.spotifyId, () => load(track.value), { immediate: true })

  rafId = requestAnimationFrame(tick)
  onUnmounted(() => {
    if (rafId) cancelAnimationFrame(rafId)
  })

  return { loading, found, instrumental, syncedLines, plainLyrics, activeIndex }
}
