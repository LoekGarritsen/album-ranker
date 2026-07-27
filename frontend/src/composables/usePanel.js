import { ref } from 'vue'

// Right-hand now-playing panel (Spotify-style): 'lyrics' | 'queue' | null.
// Singleton so the player bar and App shell share one state.
const panelView = ref(null)

export function usePanel() {
  function togglePanel(view) {
    panelView.value = panelView.value === view ? null : view
  }

  function closePanel() {
    panelView.value = null
  }

  return { panelView, togglePanel, closePanel }
}
