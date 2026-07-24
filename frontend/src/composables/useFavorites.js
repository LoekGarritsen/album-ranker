import { ref } from 'vue'

// Personal favorites (singleton): saved Spotify tracks/albums for quick
// re-queue. Server is authoritative; toggles are optimistic with rollback.
const favorites = ref([])
let loaded = false

export function useFavorites() {
  async function loadFavorites(force = false) {
    if (loaded && !force) return
    try {
      const res = await fetch('/api/favorites')
      if (res.ok) {
        const data = await res.json()
        favorites.value = data.favorites || []
        loaded = true
      }
    } catch (e) {
      console.error('Failed to load favorites:', e)
    }
  }

  function isFavorite(spotifyId) {
    return favorites.value.some(f => f.spotify_id === spotifyId)
  }

  async function toggleFavorite(item) {
    if (!item?.spotify_id) return false
    const was = isFavorite(item.spotify_id)
    // Optimistic flip; rolled back if the request fails.
    if (was) {
      favorites.value = favorites.value.filter(f => f.spotify_id !== item.spotify_id)
    } else {
      favorites.value = [{ ...item }, ...favorites.value]
    }
    try {
      const res = await fetch('/api/favorites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: item.type,
          spotify_id: item.spotify_id,
          name: item.name,
          artist: item.artist || '',
          image: item.image || null,
          duration_ms: item.duration_ms || 0
        })
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return true
    } catch (e) {
      console.error('Failed to toggle favorite:', e)
      await loadFavorites(true)
      return false
    }
  }

  return { favorites, loadFavorites, isFavorite, toggleFavorite }
}
