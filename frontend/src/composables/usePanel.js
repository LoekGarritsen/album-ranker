import { ref } from 'vue'

const WIDTH_KEY = 'panelWidth'
const MIN_WIDTH = 280
const MAX_WIDTH = 520

function clampWidth(w) {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(w)))
}

function storedWidth() {
  try {
    const w = parseInt(localStorage.getItem(WIDTH_KEY), 10)
    if (!Number.isNaN(w)) return clampWidth(w)
  } catch {}
  return 320
}

// Right-hand now-playing panel (Spotify-style): 'lyrics' | 'queue' | null.
// Singleton so the player bar and App shell share one state.
const panelView = ref(null)
const panelWidth = ref(storedWidth())

export function usePanel() {
  function togglePanel(view) {
    panelView.value = panelView.value === view ? null : view
  }

  function closePanel() {
    panelView.value = null
  }

  function setPanelWidth(w) {
    panelWidth.value = clampWidth(w)
    try { localStorage.setItem(WIDTH_KEY, String(panelWidth.value)) } catch {}
  }

  return { panelView, panelWidth, togglePanel, closePanel, setPanelWidth }
}
