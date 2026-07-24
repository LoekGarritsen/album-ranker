import { ref, computed } from 'vue'
import { useSpotifyPlayer } from './useSpotifyPlayer'

// Global session state (singleton)
const session = ref(null)
const album = ref(null)
// Hangout now-playing: individual Spotify track/album, independent of the
// ranking library ({ type, spotify_id, name, artist, image, duration_ms })
const media = ref(null)
// Shared play queue (hangout mode): [{ id, type, spotify_id, name, artist,
// image, duration_ms, added_by, added_by_name }], FIFO, server-authoritative
const queue = ref([])
// Server's media_seq: sent with advance requests so a stale/duplicate
// track-end report from another client can't double-skip the queue.
let mediaSeq = 0
// Live track within hangout album media ({ spotify_id, name, duration_ms }),
// server-reported. Lets a rejoin resume mid-album instead of at track 1.
const mediaTrack = ref(null)
// Like/dislike on the current song — ephemeral, reset on every media change.
// Majority dislike (server-decided) skips the song.
const mediaVotes = ref({ likes: 0, dislikes: 0, voters: [] })
const isPlaying = ref(false)
const playbackPosition = ref(0)
const currentTrackDuration = ref(0)
const listeners = ref([])
const ws = ref(null)
const toasts = ref([])
const sessionUser = ref(null) // Store current user for auto-advance

// Chat state (hangout mode + listening chat)
const chatMessages = ref([])
const chatHasMore = ref(false)
const typingUsers = ref([]) // [{ user_id, user_name }]
const chatOpen = ref(false)
const unreadChatCount = ref(0)

let progressInterval = null
let pingInterval = null
let toastId = 0
let reconnectTimer = null
let reconnectAttempts = 0
let typingSentAt = 0
const typingTimers = new Map() // user_id -> hide timeout

// Track if we're actively in a session
const isInSession = computed(() => !!session.value?.code)

// Track if session has an album selected
const hasAlbum = computed(() => !!session.value?.album_id && !!album.value)

// Hangout rooms are chat-first; music is optional
const isHangout = computed(() => session.value?.mode === 'hangout')

const currentTrack = computed(() => {
  if (!album.value?.tracks || !session.value?.current_track_id) return null
  return album.value.tracks.find(t => t.id === session.value.current_track_id)
})

const progressPercent = computed(() => {
  if (!currentTrackDuration.value) return 0
  return Math.min(100, (playbackPosition.value / currentTrackDuration.value) * 100)
})

export function useSession() {
  // Get Spotify player (singleton)
  const {
    isReady: spotifyReady,
    isPaused: spotifyPaused,
    currentTrack: spotifyPlayerTrack,
    contextUri: spotifyContextUri,
    position: spotifyPosition,
    play: spotifyPlay,
    playContext: spotifyPlayContext,
    pause: spotifyPause,
    resume: spotifyResume,
    seek: spotifySeek
  } = useSpotifyPlayer()

  // Is this track the one loaded in the local Spotify player? Relinked tracks
  // (market availability) report a different id; linked_from has the original.
  function spotifyHasTrack(track) {
    const loaded = spotifyPlayerTrack.value
    if (!loaded || !track?.spotify_id) return false
    return loaded.id === track.spotify_id || loaded.linked_from?.id === track.spotify_id
  }

  // Is the hangout media (track) the one loaded in the local player?
  function spotifyHasMedia(m) {
    const loaded = spotifyPlayerTrack.value
    if (!loaded || !m?.spotify_id) return false
    return loaded.id === m.spotify_id || loaded.linked_from?.id === m.spotify_id
  }

  // Start Spotify playback for hangout media (single track or album context).
  // offsetTrackId resumes an album context at a specific track instead of track 1.
  async function playMediaOnSpotify(m, positionMs = 0, offsetTrackId = null) {
    if (!spotifyReady.value || !m?.spotify_id) return
    if (m.type === 'album') {
      const offsetUri = offsetTrackId ? `spotify:track:${offsetTrackId}` : null
      await spotifyPlayContext(`spotify:album:${m.spotify_id}`, offsetUri, offsetUri ? positionMs : 0)
    } else {
      await spotifyPlay(`spotify:track:${m.spotify_id}`, positionMs)
    }
  }

  // Start Spotify playback for a track. When the album has a Spotify context,
  // play it as an album context so Spotify advances tracks gaplessly. Falls
  // back to single-track playback otherwise.
  async function playTrackOnSpotify(track, positionMs = 0) {
    if (!spotifyReady.value || !track?.spotify_id) return
    if (album.value?.spotify_id) {
      await spotifyPlayContext(
        `spotify:album:${album.value.spotify_id}`,
        `spotify:track:${track.spotify_id}`,
        positionMs
      )
    } else {
      await spotifyPlay(`spotify:track:${track.spotify_id}`, positionMs)
    }
  }
  function showToast(message, type = 'info') {
    const id = ++toastId
    toasts.value.push({ id, message, type })
    setTimeout(() => {
      toasts.value = toasts.value.filter(t => t.id !== id)
    }, 3000)
  }

  function formatDuration(ms) {
    if (!ms) return '0:00'
    const mins = Math.floor(ms / 60000)
    const secs = Math.floor((ms % 60000) / 1000)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  function startProgressInterval() {
    stopProgressInterval()
    // Advance by real elapsed time, not a fixed +100. Background tabs throttle
    // setInterval to >=1s (Chrome 88+), so a fixed increment massively
    // undercounts and the room clock drifts behind real playback.
    let last = performance.now()
    progressInterval = setInterval(() => {
      const now = performance.now()
      const delta = now - last
      last = now
      if (isPlaying.value && currentTrackDuration.value > 0) {
        const newPosition = playbackPosition.value + delta
        if (newPosition >= currentTrackDuration.value) {
          playbackPosition.value = currentTrackDuration.value
          stopProgressInterval()
          // Auto-advance to next track
          autoAdvanceToNext()
        } else {
          playbackPosition.value = newPosition
        }
      }
    }, 100)
  }

  function autoAdvanceToNext() {
    // Local timer drives advance only for non-Spotify listeners; Spotify users
    // advance via the SDK. Letting both fire double-advances and skips tracks.
    if (spotifyReady.value) return
    if (isHangout.value) {
      // Hangout: the server pops the shared queue (seq-guarded, so several
      // clients reporting the same track end advance it exactly once).
      advanceQueue()
      return
    }
    const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
    if (trackIdx >= 0 && trackIdx < album.value.tracks.length - 1) {
      // There's a next track, advance to it
      selectTrack(album.value.tracks[trackIdx + 1].id, sessionUser.value)
    } else {
      // Last track ended — pause on the server too, else its clock keeps
      // running and pong flips the room back to "playing" every 10s.
      togglePlayback(sessionUser.value)
      isPlaying.value = false
      stopProgressInterval()
    }
  }

  function stopProgressInterval() {
    if (progressInterval) {
      clearInterval(progressInterval)
      progressInterval = null
    }
  }

  function connectWebSocket(code, userId, currentUser, onMessage) {
    // Clear any existing connection and pending reconnect
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws.value) {
      ws.value.close()
    }
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    // Browsers can't set WS headers, so identity rides as the session token in
    // the query string (validated server-side; absent/invalid => guest).
    const authToken = localStorage.getItem('authToken') || ''
    const wsUrl = `${protocol}//${window.location.host}/api/sessions/${code}/ws?token=${encodeURIComponent(authToken)}`

    const socket = new WebSocket(wsUrl)
    ws.value = socket

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleWebSocketMessage(data, currentUser, onMessage)
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e, event.data)
      }
    }

    socket.onopen = () => {
      reconnectAttempts = 0
      // Ping every 10 seconds for more responsive sync (room is source of truth)
      pingInterval = setInterval(() => {
        if (ws.value?.readyState === WebSocket.OPEN) {
          const payload = { type: 'ping' }
          // Hangout: our Spotify is the clock — report which track (within an
          // album context) and where, so the server clock survives rejoins.
          if (media.value && spotifyReady.value && !spotifyPaused.value && spotifyPlayerTrack.value) {
            const t = spotifyPlayerTrack.value
            payload.progress = {
              media_seq: mediaSeq,
              track_spotify_id: t.linked_from?.id || t.id,
              track_name: t.name,
              duration_ms: t.duration_ms || 0,
              position: spotifyPosition.value
            }
          }
          ws.value.send(JSON.stringify(payload))
        }
      }, 10000)
    }

    socket.onclose = () => {
      // A superseded socket (we opened a newer one) must not schedule
      // reconnects — that spawned duplicate connections.
      if (ws.value !== socket) return
      if (pingInterval) {
        clearInterval(pingInterval)
        pingInterval = null
      }
      // Reconnect with exponential backoff + jitter
      const delay = Math.min(15000, 1000 * 2 ** reconnectAttempts) + Math.random() * 500
      reconnectAttempts++
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        if (session.value?.code === code && ws.value === socket) {
          connectWebSocket(code, userId, currentUser, onMessage)
        }
      }, delay)
    }

    socket.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  }

  function handleWebSocketMessage(data, currentUser, onMessage) {
    switch (data.type) {
      case 'sync': {
        // Stop any existing interval first
        stopProgressInterval()

        if (session.value) {
          session.value.current_track_id = data.track_id
        }
        // Track may have changed while disconnected — refresh duration too,
        // or the local timer runs against the old track's length.
        const syncTrack = album.value?.tracks?.find(t => t.id === data.track_id)
        if (syncTrack) {
          currentTrackDuration.value = syncTrack.duration_ms
        }
        if (data.media !== undefined) {
          media.value = data.media
          if (!syncTrack && data.media) {
            // Album media has no single duration — progress bar hides at 0.
            currentTrackDuration.value = data.media.type === 'track' ? data.media.duration_ms : 0
          }
        }
        if (data.media_seq !== undefined) mediaSeq = data.media_seq
        if (data.media_track !== undefined) mediaTrack.value = data.media_track
        if (data.media_votes !== undefined) {
          mediaVotes.value = data.media_votes || { likes: 0, dislikes: 0, voters: [] }
        }
        if (data.queue !== undefined) queue.value = data.queue || []
        playbackPosition.value = data.position || 0
        isPlaying.value = data.is_playing || false
        listeners.value = data.listeners || []

        // Only start interval if actually playing
        if (isPlaying.value) {
          startProgressInterval()
        }

        // Reconnect catch-up: the DB is the replay buffer — fetch anything
        // missed while the socket was down (dedup happens in the merge).
        catchUpChat()
        break
      }

      case 'track_change': {
        stopProgressInterval()
        if (session.value) {
          session.value.current_track_id = data.track_id
        }
        currentTrackDuration.value = data.duration || 0
        playbackPosition.value = data.position || 0
        isPlaying.value = data.is_playing || false

        const remoteChange = data.changed_by && data.changed_by !== currentUser?.id
        if (remoteChange) {
          const trackName = album.value?.tracks?.find(t => t.id === data.track_id)?.name
          showToast(`${data.changed_by_name || 'Someone'} selected "${trackName || 'a track'}"`)
        }

        // Remote manual pick: start Spotify here (single ordered path — the
        // old pause->play watcher flip raced and killed fresh playback).
        // keep_playing = native context advance: our Spotify advances itself.
        if (remoteChange && data.is_playing && !data.keep_playing && spotifyReady.value) {
          const track = album.value?.tracks?.find(t => t.id === data.track_id)
          if (track?.spotify_id) {
            playTrackOnSpotify(track, 0)
          }
        }

        if (isPlaying.value) {
          startProgressInterval()
        }
        break
      }

      case 'playback': {
        stopProgressInterval()
        playbackPosition.value = data.position || 0
        const track = currentTrack.value

        if (data.action === 'play') {
          isPlaying.value = true
          // Sync Spotify here (ordered with the state change) instead of via
          // a watcher racing other broadcasts.
          if (spotifyReady.value && track?.spotify_id) {
            if (spotifyHasTrack(track)) {
              // Right track loaded — resume in place to keep the gapless context
              if (spotifyPaused.value) spotifyResume()
            } else {
              playTrackOnSpotify(track, data.position || 0)
            }
          } else if (spotifyReady.value && media.value?.spotify_id) {
            // Hangout media. Album context position is per-track, so resume in
            // place when anything is loaded; cold-start (empty player, e.g.
            // fresh page load) at the server-reported track + position.
            if (!spotifyPlayerTrack.value) {
              playMediaOnSpotify(media.value, data.position || 0,
                media.value.type === 'album' ? mediaTrack.value?.spotify_id : null)
            } else if (spotifyHasMedia(media.value) || media.value.type === 'album') {
              if (spotifyPaused.value) spotifyResume()
            } else {
              playMediaOnSpotify(media.value, data.position || 0)
            }
          }
          startProgressInterval()
        } else if (data.action === 'pause') {
          isPlaying.value = false
          if (spotifyReady.value && !spotifyPaused.value) {
            spotifyPause()
          }
        } else if (data.action === 'seek') {
          // Mirror remote seeks into Spotify; skip our own echo — we already
          // seeked optimistically, a second seek would stutter playback.
          if (spotifyReady.value && data.by !== currentUser?.id) {
            spotifySeek(data.position || 0)
          }
          // Keep current playing state, just update position
          if (isPlaying.value) {
            startProgressInterval()
          }
        }
        break
      }

      case 'pong': {
        if (data.media_track !== undefined) mediaTrack.value = data.media_track
        // In context mode Spotify's clock is mirrored into the room locally;
        // a server correction here would fight it and make the bar jump.
        // Same for hangout while our Spotify is audibly playing — we ARE the clock.
        const inContextMode = (spotifyReady.value && !!album.value?.spotify_id) ||
          (media.value && spotifyReady.value && !spotifyPaused.value)
        if (!inContextMode && data.position !== undefined) {
          const drift = Math.abs(playbackPosition.value - data.position)
          // Only correct if drift is more than 500ms
          if (drift > 500) {
            playbackPosition.value = data.position
          }
        }
        // Also sync play/pause state from server (covers a missed broadcast);
        // bring Spotify along so audio matches the recovered room state.
        if (data.is_playing !== undefined && data.is_playing !== isPlaying.value) {
          isPlaying.value = data.is_playing
          const track = currentTrack.value
          if (isPlaying.value) {
            if (spotifyReady.value && track?.spotify_id) {
              if (spotifyHasTrack(track)) {
                if (spotifyPaused.value) spotifyResume()
              } else {
                playTrackOnSpotify(track, playbackPosition.value)
              }
            } else if (spotifyReady.value && media.value?.spotify_id) {
              if (spotifyPaused.value && spotifyPlayerTrack.value) spotifyResume()
              else if (!spotifyPlayerTrack.value) {
                playMediaOnSpotify(media.value, playbackPosition.value,
                  media.value.type === 'album' ? mediaTrack.value?.spotify_id : null)
              }
            }
            startProgressInterval()
          } else {
            if (spotifyReady.value && !spotifyPaused.value) {
              spotifyPause()
            }
            stopProgressInterval()
          }
        }
        break
      }

      case 'user_joined':
        if (!listeners.value.find(l => l.user_id === data.user_id)) {
          listeners.value.push({ user_id: data.user_id, user_name: data.user_name })
          if (data.user_id !== currentUser?.id) {
            showToast(`${data.user_name} joined the session`, 'success')
          }
        }
        break

      case 'user_left': {
        const leftUser = listeners.value.find(l => l.user_id === data.user_id)
        listeners.value = listeners.value.filter(l => l.user_id !== data.user_id)
        if (leftUser && data.user_id !== currentUser?.id) {
          showToast(`${leftUser.user_name || data.user_name} left the session`)
        }
        break
      }

      case 'rating':
        if (album.value?.tracks) {
          const track = album.value.tracks.find(t => t.id === data.track_id)
          if (track) {
            const existingIdx = track.rankings?.findIndex(r => r.user_id === data.user_id)
            const newRanking = {
              user_id: data.user_id,
              user_name: data.user_name,
              score: data.score,
              comment: data.comment
            }
            if (existingIdx >= 0) {
              track.rankings[existingIdx] = newRanking
            } else {
              if (!track.rankings) track.rankings = []
              track.rankings.push(newRanking)
            }
            if (data.user_id !== currentUser?.id) {
              showToast(`${data.user_name} rated "${track.name}" ${data.score.toFixed(1)}`, 'success')
            }
          }
        }
        break

      case 'album_rating':
        if (album.value?.id === data.album_id) {
          if (!album.value.album_rankings) album.value.album_rankings = []
          const idx = album.value.album_rankings.findIndex(r => r.user_id === data.user_id)
          const entry = {
            user_id: data.user_id,
            user_name: data.user_name,
            score: data.score,
            comment: data.comment
          }
          if (idx >= 0) {
            album.value.album_rankings[idx] = entry
          } else {
            album.value.album_rankings.push(entry)
          }
          if (data.user_id !== currentUser?.id) {
            showToast(`${data.user_name} rated the album ${data.score.toFixed(1)}`, 'success')
          }
        }
        break

      case 'album_change':
        // Album was changed by someone - need to reload album data
        if (session.value) {
          session.value.album_id = data.album_id
          session.value.album_name = data.album_name
          session.value.cover_url = data.cover_url
          session.value.current_track_id = data.track_id
        }
        currentTrackDuration.value = data.track_duration || 0
        playbackPosition.value = 0
        isPlaying.value = false
        stopProgressInterval()

        // Reload the full album data
        loadAlbumData(data.album_id)

        if (data.changed_by !== currentUser?.id) {
          showToast(`${data.changed_by_name || 'Someone'} selected album "${data.album_name}"`)
        }
        break

      case 'mode_change':
        if (session.value) {
          session.value.mode = data.mode
        }
        if (data.changed_by !== currentUser?.id) {
          showToast(`${data.changed_by_name || 'Someone'} switched to ${data.mode} mode`)
        }
        break

      case 'media_change': {
        // Hangout now-playing changed (individual Spotify track/album).
        stopProgressInterval()
        media.value = data.media
        if (data.media_seq !== undefined) mediaSeq = data.media_seq
        mediaTrack.value = null
        // New song, fresh slate for like/dislike
        mediaVotes.value = { likes: 0, dislikes: 0, voters: [] }
        currentTrackDuration.value = data.media?.type === 'track' ? (data.media.duration_ms || 0) : 0
        playbackPosition.value = data.position || 0
        isPlaying.value = data.is_playing || false

        if (data.auto && !data.media) {
          showToast(data.skip_reason === 'votes' ? 'Skipped by vote — queue is empty' : 'Queue finished')
        } else if (data.skip_reason === 'votes') {
          showToast(`Skipped by vote — up next: "${data.media?.name}"`)
        } else if (data.auto) {
          // Queue advance — attribution is whoever queued the item.
          showToast(`Up next: "${data.media?.name}"${data.changed_by_name ? ` (added by ${data.changed_by_name})` : ''}`)
        } else if (data.changed_by !== currentUser?.id) {
          showToast(`${data.changed_by_name || 'Someone'} put on "${data.media?.name}"`)
        }
        // Single ordered playback path for everyone, including the picker —
        // no optimistic Spotify start in setMedia, so nothing double-fires.
        if (isPlaying.value && spotifyReady.value && data.media?.spotify_id) {
          playMediaOnSpotify(data.media, 0)
        } else if (!isPlaying.value && spotifyReady.value && !spotifyPaused.value) {
          // Now-playing cleared (vote-skip into an empty queue) while our
          // player is still going — stop the audio too.
          spotifyPause()
        }
        if (isPlaying.value) {
          startProgressInterval()
        }
        break
      }

      case 'queue_update': {
        queue.value = data.queue || []
        if (data.action === 'added' && data.by !== currentUser?.id) {
          showToast(`${data.by_name || 'Someone'} queued "${data.item?.name}"`)
        }
        break
      }

      case 'media_vote': {
        mediaVotes.value = {
          likes: data.likes || 0,
          dislikes: data.dislikes || 0,
          voters: data.voters || []
        }
        break
      }

      case 'chat_message': {
        // Reconcile the sender's optimistic bubble by client_id first.
        const pendingIdx = data.client_id
          ? chatMessages.value.findIndex(m => m.pending && m.client_id === data.client_id)
          : -1
        const message = {
          id: data.id,
          user_id: data.user_id,
          user_name: data.user_name,
          content: data.content,
          kind: data.kind || 'text',
          created_at: data.created_at,
          reactions: []
        }
        if (pendingIdx >= 0) {
          chatMessages.value[pendingIdx] = message
        } else if (!chatMessages.value.some(m => m.id === data.id)) {
          chatMessages.value.push(message)
        }
        // A real message replaces the sender's typing indicator instantly.
        clearTypingUser(data.user_id)
        if (data.user_id !== currentUser?.id && !chatOpen.value) {
          unreadChatCount.value++
        }
        break
      }

      case 'user_typing':
        if (data.user_id !== currentUser?.id) {
          upsertTypingUser(data.user_id, data.user_name)
        }
        break

      case 'reaction': {
        const msg = chatMessages.value.find(m => m.id === data.message_id)
        if (msg) {
          if (!msg.reactions) msg.reactions = []
          if (data.action === 'added') {
            msg.reactions.push({ emoji: data.emoji, user_id: data.user_id, user_name: data.user_name })
          } else {
            msg.reactions = msg.reactions.filter(
              r => !(r.emoji === data.emoji && r.user_id === data.user_id)
            )
          }
        }
        break
      }

      case 'session_ended':
        // Room was closed/deleted
        showToast(data.message || 'This room has been closed', 'error')
        // Clear session state - the WebSocket will close automatically
        session.value = null
        album.value = null
        media.value = null
        queue.value = []
        mediaVotes.value = { likes: 0, dislikes: 0, voters: [] }
        sessionUser.value = null
        isPlaying.value = false
        playbackPosition.value = 0
        currentTrackDuration.value = 0
        listeners.value = []
        resetChatState()
        stopProgressInterval()
        break
    }

    // Forward to component handler if provided
    if (onMessage) {
      onMessage(data)
    }
  }

  // --- Chat ---

  function upsertTypingUser(userId, userName) {
    if (!typingUsers.value.some(u => u.user_id === userId)) {
      typingUsers.value.push({ user_id: userId, user_name: userName })
    }
    // Receiver-side safety timeout: hide if not refreshed within 5s
    clearTimeout(typingTimers.get(userId))
    typingTimers.set(userId, setTimeout(() => clearTypingUser(userId), 5000))
  }

  function clearTypingUser(userId) {
    clearTimeout(typingTimers.get(userId))
    typingTimers.delete(userId)
    typingUsers.value = typingUsers.value.filter(u => u.user_id !== userId)
  }

  function resetChatState() {
    chatMessages.value = []
    chatHasMore.value = false
    unreadChatCount.value = 0
    chatOpen.value = false
    for (const t of typingTimers.values()) clearTimeout(t)
    typingTimers.clear()
    typingUsers.value = []
    typingSentAt = 0
  }

  async function loadChatHistory() {
    if (!session.value?.code) return
    try {
      const res = await fetch(`/api/sessions/${session.value.code}/messages?limit=50`)
      if (res.ok) {
        const data = await res.json()
        chatMessages.value = data.messages
        chatHasMore.value = data.has_more
      }
    } catch (e) {
      console.error('Failed to load chat history:', e)
    }
  }

  async function loadOlderChat() {
    if (!session.value?.code || !chatHasMore.value || !chatMessages.value.length) return
    const oldest = chatMessages.value.find(m => !m.pending)
    if (!oldest) return
    try {
      const res = await fetch(
        `/api/sessions/${session.value.code}/messages?limit=50&before_id=${oldest.id}`
      )
      if (res.ok) {
        const data = await res.json()
        chatMessages.value = [...data.messages, ...chatMessages.value]
        chatHasMore.value = data.has_more
      }
    } catch (e) {
      console.error('Failed to load older chat:', e)
    }
  }

  // On (re)connect: fetch anything missed while the socket was down. First
  // sync after joining doubles as the initial history load.
  async function catchUpChat() {
    if (!session.value?.code) return
    const confirmed = chatMessages.value.filter(m => !m.pending)
    if (!confirmed.length) {
      await loadChatHistory()
      return
    }
    try {
      const lastId = confirmed[confirmed.length - 1].id
      const res = await fetch(
        `/api/sessions/${session.value.code}/messages?after_id=${lastId}&limit=100`
      )
      if (res.ok) {
        const data = await res.json()
        // Dedup by id: a message can arrive both live and via catch-up.
        const known = new Set(chatMessages.value.map(m => m.id))
        const fresh = data.messages.filter(m => !known.has(m.id))
        if (fresh.length) {
          chatMessages.value.push(...fresh)
          if (!chatOpen.value) unreadChatCount.value += fresh.length
        }
      }
    } catch (e) {
      console.error('Chat catch-up failed:', e)
    }
  }

  function sendChatMessage(content, kind = 'text') {
    const text = (content || '').trim()
    if (!text || text.length > 1000) return false
    if (ws.value?.readyState !== WebSocket.OPEN) {
      showToast('Not connected — message not sent', 'error')
      return false
    }
    // Optimistic bubble, reconciled by client_id when the echo arrives.
    const clientId = crypto.randomUUID()
    chatMessages.value.push({
      id: null,
      client_id: clientId,
      pending: true,
      user_id: sessionUser.value?.id,
      user_name: sessionUser.value?.name,
      content: text,
      kind,
      created_at: new Date().toISOString(),
      reactions: []
    })
    ws.value.send(JSON.stringify({ type: 'chat', content: text, kind, client_id: clientId }))
    return true
  }

  // Throttled: at most one typing signal per 2.5s while keys are pressed
  function sendTyping() {
    const now = Date.now()
    if (now - typingSentAt < 2500) return
    typingSentAt = now
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({ type: 'typing' }))
    }
  }

  function toggleReaction(messageId, emoji) {
    if (!messageId) return
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({ type: 'reaction', message_id: messageId, emoji }))
    }
  }

  function setChatOpen(open) {
    chatOpen.value = open
    if (open) unreadChatCount.value = 0
  }

  async function loadAlbumData(albumId) {
    if (!albumId) {
      album.value = null
      return
    }

    try {
      const albumRes = await fetch(`/api/albums/${albumId}`)
      if (albumRes.ok) {
        album.value = await albumRes.json()
        if (currentTrack.value) {
          currentTrackDuration.value = currentTrack.value.duration_ms
        }
      }
    } catch (e) {
      console.error('Failed to load album data:', e)
    }
  }

  async function joinSession(code, currentUser) {
    try {
      const res = await fetch(`/api/sessions/${code}`)
      if (!res.ok) return false

      session.value = await res.json()
      sessionUser.value = currentUser // Store for auto-advance
      media.value = session.value.media || null
      mediaTrack.value = session.value.media_track || null
      currentTrackDuration.value = session.value.current_track_duration
        || (media.value?.type === 'track' ? media.value.duration_ms : 0)
        || 0
      isPlaying.value = session.value.playback?.is_playing || false
      playbackPosition.value = session.value.playback?.position || 0
      listeners.value = session.value.participants?.filter(p => p.is_online) || []

      // Load album only if session has one
      if (session.value.album_id) {
        await loadAlbumData(session.value.album_id)
      } else {
        album.value = null
      }

      // Connect WebSocket
      connectWebSocket(code, currentUser?.id, currentUser)

      if (isPlaying.value) {
        startProgressInterval()
      }

      return true
    } catch (e) {
      console.error('Failed to join session:', e)
      return false
    }
  }

  async function setAlbum(albumId, currentUser) {
    if (!session.value?.code) return false

    try {
      const headers = {}
      if (currentUser?.id) {
        headers['X-User-Id'] = currentUser.id.toString()
      }
      const res = await fetch(`/api/sessions/${session.value.code}/album?album_id=${albumId}`, {
        method: 'POST',
        headers
      })

      if (res.ok) {
        // Album data will be updated via WebSocket album_change message
        return true
      }
      return false
    } catch (e) {
      console.error('Failed to set album:', e)
      return false
    }
  }

  // Hangout: put on an individual Spotify track or album for the room.
  // Spotify playback starts via the media_change broadcast (single path).
  async function setMedia(item) {
    if (!session.value?.code) return false
    try {
      const res = await fetch(`/api/sessions/${session.value.code}/media`, {
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
      return res.ok
    } catch (e) {
      console.error('Failed to set media:', e)
      return false
    }
  }

  // Add a Spotify track/album to the shared queue. Server auto-starts it
  // instead when nothing is on (returns started: true).
  async function addToQueue(item) {
    if (!session.value?.code) return false
    try {
      const res = await fetch(`/api/sessions/${session.value.code}/queue`, {
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
      if (!res.ok) return false
      const data = await res.json()
      queue.value = data.queue || []
      showToast(data.started ? `Playing "${item.name}"` : `Queued "${item.name}"`, 'success')
      return true
    } catch (e) {
      console.error('Failed to add to queue:', e)
      return false
    }
  }

  async function removeQueueItem(itemId) {
    if (!session.value?.code) return false
    try {
      const res = await fetch(`/api/sessions/${session.value.code}/queue/${itemId}`, {
        method: 'DELETE'
      })
      if (res.status === 403) {
        showToast('You can only remove your own queue items', 'error')
        return false
      }
      if (!res.ok) return false
      const data = await res.json()
      queue.value = data.queue || []
      return true
    } catch (e) {
      console.error('Failed to remove queue item:', e)
      return false
    }
  }

  // Like/dislike the current song (toggle). Counts land via the media_vote
  // broadcast; a majority of dislikes makes the server skip it.
  async function voteMedia(vote) {
    if (!session.value?.code) return false
    try {
      const res = await fetch(
        `/api/sessions/${session.value.code}/media/vote?vote=${vote}`,
        { method: 'POST' }
      )
      return res.ok
    } catch (e) {
      console.error('Failed to vote on current song:', e)
      return false
    }
  }

  // Like/dislike a queue item (toggle). Reordered queue lands via broadcast.
  async function voteQueueItem(itemId, vote) {
    if (!session.value?.code) return false
    try {
      const res = await fetch(
        `/api/sessions/${session.value.code}/queue/${itemId}/vote?vote=${vote}`,
        { method: 'POST' }
      )
      if (!res.ok) return false
      const data = await res.json()
      queue.value = data.queue || []
      return true
    } catch (e) {
      console.error('Failed to vote on queue item:', e)
      return false
    }
  }

  // Pop the queue head into now-playing. Sends the media_seq we last saw so
  // simultaneous track-end reports (or double skips) can't advance twice —
  // the server no-ops stale requests. State lands via the broadcasts.
  async function advanceQueue() {
    if (!session.value?.code) return false
    try {
      const res = await fetch(
        `/api/sessions/${session.value.code}/queue/next?seq=${mediaSeq}`,
        { method: 'POST' }
      )
      return res.ok
    } catch (e) {
      console.error('Failed to advance queue:', e)
      return false
    }
  }

  async function leaveSession() {
    stopProgressInterval()
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
    }
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    session.value = null
    album.value = null
    media.value = null
    queue.value = []
    mediaVotes.value = { likes: 0, dislikes: 0, voters: [] }
    sessionUser.value = null
    isPlaying.value = false
    playbackPosition.value = 0
    currentTrackDuration.value = 0
    listeners.value = []
    resetChatState()
  }

  async function selectTrack(trackId, currentUser) {
    if (!session.value?.code) return

    try {
      const headers = {}
      if (currentUser?.id) {
        headers['X-User-Id'] = currentUser.id.toString()
      }
      // Optimistic local state; play=true makes track+playback one atomic
      // broadcast (the old track/seek/play triplet raced on remote clients).
      stopProgressInterval()
      session.value.current_track_id = trackId
      const track = album.value?.tracks?.find(t => t.id === trackId)
      if (track) {
        currentTrackDuration.value = track.duration_ms
      }
      playbackPosition.value = 0
      isPlaying.value = true
      startProgressInterval()

      await Promise.all([
        fetch(`/api/sessions/${session.value.code}/track?track_id=${trackId}&play=true`, {
          method: 'POST',
          headers
        }),
        playTrackOnSpotify(track, 0)
      ])
    } catch (e) {
      console.error('Failed to select track:', e)
    }
  }

  // Spotify advanced to the next track on its own (gapless context playback).
  // Mirror that to the room/server WITHOUT re-issuing Spotify playback —
  // re-playing would restart the track and reintroduce the gap.
  async function notifyTrackChange(trackId, currentUser) {
    if (!session.value?.code) return
    try {
      const headers = {}
      if (currentUser?.id) {
        headers['X-User-Id'] = currentUser.id.toString()
      }
      await fetch(`/api/sessions/${session.value.code}/track?track_id=${trackId}&keep_playing=true`, {
        method: 'POST',
        headers
      })
      session.value.current_track_id = trackId
      const track = album.value?.tracks?.find(t => t.id === trackId)
      if (track) {
        currentTrackDuration.value = track.duration_ms
      }
      playbackPosition.value = 0
      isPlaying.value = true
      startProgressInterval()
    } catch (e) {
      console.error('Failed to notify track change:', e)
    }
  }

  async function togglePlayback(currentUser) {
    if (!session.value?.code) return

    const action = isPlaying.value ? 'pause' : 'play'

    try {
      const headers = {}
      if (currentUser?.id) {
        headers['X-User-Id'] = currentUser.id.toString()
      }
      await fetch(`/api/sessions/${session.value.code}/playback?action=${action}`, {
        method: 'POST',
        headers
      })
      // State + Spotify sync happen via the WebSocket 'playback' broadcast
    } catch (e) {
      console.error('Failed to toggle playback:', e)
    }
  }

  async function seekTo(percent, currentUser) {
    if (!session.value?.code) return

    const position = Math.floor((percent / 100) * currentTrackDuration.value)
    playbackPosition.value = position

    try {
      const headers = {}
      if (currentUser?.id) {
        headers['X-User-Id'] = currentUser.id.toString()
      }
      await fetch(`/api/sessions/${session.value.code}/playback?action=seek&position=${position}`, {
        method: 'POST',
        headers
      })

      // Seek on Spotify if connected
      if (spotifyReady.value) {
        await spotifySeek(position)
      }
    } catch (e) {
      console.error('Failed to seek:', e)
    }
  }

  function skipPrevious(currentUser) {
    const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
    if (trackIdx > 0) {
      selectTrack(album.value.tracks[trackIdx - 1].id, currentUser)
    }
  }

  function skipNext(currentUser) {
    const trackIdx = album.value?.tracks?.findIndex(t => t.id === session.value?.current_track_id)
    if (trackIdx >= 0 && trackIdx < album.value.tracks.length - 1) {
      selectTrack(album.value.tracks[trackIdx + 1].id, currentUser)
    }
  }

  async function syncWithServer() {
    if (!session.value?.code) return false

    try {
      // Stop interval first to prevent race conditions
      stopProgressInterval()

      const res = await fetch(`/api/sessions/${session.value.code}`)
      if (!res.ok) {
        showToast('Sync failed: server error', 'error')
        return false
      }

      const data = await res.json()

      // Update local state with server state
      if (data.playback) {
        const serverPos = data.playback.position || 0
        const serverIsPlaying = data.playback.is_playing || false

        // Set position from server
        playbackPosition.value = serverPos
        isPlaying.value = serverIsPlaying
      }

      // Update track if different
      if (data.current_track_id && data.current_track_id !== session.value.current_track_id) {
        session.value.current_track_id = data.current_track_id
        const track = album.value?.tracks?.find(t => t.id === data.current_track_id)
        if (track) {
          currentTrackDuration.value = track.duration_ms
        }
      }

      // Refresh hangout media + shared queue too
      if (data.media !== undefined) {
        media.value = data.media
        if (!currentTrack.value && data.media) {
          currentTrackDuration.value = data.media.type === 'track' ? data.media.duration_ms : 0
        }
      }
      if (data.media_track !== undefined) mediaTrack.value = data.media_track
      if (data.queue !== undefined) queue.value = data.queue || []

      // Sync Spotify player if connected
      if (spotifyReady.value) {
        const track = currentTrack.value
        if (track?.spotify_id) {
          if (isPlaying.value) {
            await playTrackOnSpotify(track, playbackPosition.value)
          } else {
            await spotifyPause()
            // Only seek if we have a valid position
            if (playbackPosition.value > 0) {
              await spotifySeek(playbackPosition.value)
            }
          }
        } else if (media.value?.spotify_id) {
          // Album context already loaded and audible — restarting would yank
          // everyone back, so leave Spotify's clock alone.
          const albumAlreadyOn = media.value.type === 'album' &&
            spotifyContextUri.value === `spotify:album:${media.value.spotify_id}` &&
            !spotifyPaused.value
          if (isPlaying.value) {
            if (!albumAlreadyOn) {
              // Album: resume at the server-reported live track, not track 1.
              const offsetId = media.value.type === 'album' ? mediaTrack.value?.spotify_id : null
              await playMediaOnSpotify(
                media.value,
                media.value.type === 'track' || offsetId ? playbackPosition.value : 0,
                offsetId
              )
            }
          } else if (!spotifyPaused.value) {
            await spotifyPause()
          }
        }
      }

      // Restart interval only if playing
      if (isPlaying.value) {
        startProgressInterval()
      }

      // Album media has no room clock, so a position stamp would always read 0:00
      if (media.value?.type === 'album') {
        showToast('Synced with room', 'success')
      } else {
        showToast(`Synced: ${formatDuration(playbackPosition.value)}`, 'success')
      }
      return true
    } catch (e) {
      console.error('Failed to sync with server:', e)
      showToast('Sync failed', 'error')
      return false
    }
  }

  return {
    // State
    session,
    album,
    media,
    mediaTrack,
    queue,
    mediaVotes,
    isPlaying,
    playbackPosition,
    currentTrackDuration,
    listeners,
    toasts,
    isInSession,
    hasAlbum,
    isHangout,
    currentTrack,
    progressPercent,

    // Chat
    chatMessages,
    chatHasMore,
    typingUsers,
    chatOpen,
    unreadChatCount,
    sendChatMessage,
    sendTyping,
    toggleReaction,
    loadOlderChat,
    setChatOpen,

    // Methods
    joinSession,
    leaveSession,
    selectTrack,
    notifyTrackChange,
    setAlbum,
    setMedia,
    addToQueue,
    removeQueueItem,
    voteQueueItem,
    voteMedia,
    advanceQueue,
    loadAlbumData,
    togglePlayback,
    seekTo,
    skipPrevious,
    skipNext,
    showToast,
    formatDuration,
    startProgressInterval,
    stopProgressInterval,
    connectWebSocket,
    syncWithServer
  }
}
