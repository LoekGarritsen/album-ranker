"""
Shared application state for real-time session management.

This module contains global state that needs to be shared across routers,
particularly for WebSocket session management.
"""

# Active listening sessions with real-time state, keyed by room code:
# {connections, mode, album_id, current_track_id, media, media_seq,
#  media_track, media_votes, is_playing, playback_position, playback_started_at}
active_sessions: dict = {}

# Short-lived Spotify OAuth states (CSRF nonce -> {"user_id", "expires_at"}).
# In-memory: the OAuth round-trip completes in seconds. A container restart
# mid-flow just means the user retries the connect.
spotify_oauth_states: dict = {}
