from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Literal

# User models
class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)

class User(BaseModel):
    id: int
    name: str
    is_admin: bool = False
    created_at: datetime

class PinVerify(BaseModel):
    user_id: int
    pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")

# Ranking models
class AlbumRankingCreate(BaseModel):
    album_id: int
    user_id: Optional[int] = None  # ignored; rating is attributed to the caller
    score: float = Field(ge=1, le=10)
    comment: Optional[str] = Field(None, max_length=500)

class TrackRankingCreate(BaseModel):
    track_id: int
    user_id: Optional[int] = None  # ignored; rating is attributed to the caller
    score: float = Field(ge=1, le=10)
    comment: Optional[str] = Field(None, max_length=500)

class UserRanking(BaseModel):
    user_id: int
    user_name: str
    score: Optional[float] = None
    comment: Optional[str] = None

# Track models
class TrackWithRankings(BaseModel):
    id: int
    spotify_id: str
    name: str
    artist: str
    disc_number: int = 1
    track_number: int
    duration_ms: int
    rankings: list[UserRanking] = []
    average_score: Optional[float] = None

# Album models
class AlbumAdd(BaseModel):
    spotify_id: str
    name: str
    artist: str
    cover_url: Optional[str] = None
    release_date: Optional[str] = None

class Album(BaseModel):
    id: int
    spotify_id: str
    name: str
    artist: str
    cover_url: Optional[str]
    release_date: Optional[str]
    added_at: datetime

class SpotifyAlbum(BaseModel):
    spotify_id: str
    name: str
    artist: str
    cover_url: Optional[str]
    release_date: Optional[str]

class AlbumWithTracks(BaseModel):
    id: int
    spotify_id: str
    name: str
    artist: str
    cover_url: Optional[str]
    release_date: Optional[str]
    genres: Optional[list[str]] = None
    tracks: list[TrackWithRankings] = []
    album_rankings: list[UserRanking] = []  # Album-level ratings
    average_album_score: Optional[float] = None  # Average of album ratings
    average_track_score: Optional[float] = None  # Average of all track ratings

# Stats models
class UserStats(BaseModel):
    user_id: int
    user_name: str
    albums_rated: int
    tracks_rated: int
    average_album_score: Optional[float]
    average_track_score: Optional[float]
    highest_rated_album: Optional[str]
    lowest_rated_album: Optional[str]

class HotTake(BaseModel):
    track_name: str
    album_name: str
    cover_url: Optional[str]
    user_name: str
    user_score: float
    average_score: float
    difference: float

class ComparisonItem(BaseModel):
    id: int
    name: str
    album_name: Optional[str] = None
    cover_url: Optional[str]
    user1_score: Optional[float]
    user2_score: Optional[float]
    difference: Optional[float]

# Listening session (room) models
class ListeningSession(BaseModel):
    id: int
    code: str
    name: str
    album_id: Optional[int] = None
    album_name: Optional[str] = None
    cover_url: Optional[str] = None
    current_track_id: Optional[int] = None
    current_track_name: Optional[str] = None
    participant_count: int = 0
    is_public: bool = True
    has_password: bool = False
    created_by_name: Optional[str] = None
    is_active: bool = True
    mode: str = "listening"

class SessionCreate(BaseModel):
    name: str
    album_id: Optional[int] = None
    is_public: bool = True
    password: Optional[str] = None
    mode: Literal["listening", "hangout"] = "listening"

class SessionJoin(BaseModel):
    password: Optional[str] = None

class SessionSetAlbum(BaseModel):
    album_id: int

class SessionMediaSet(BaseModel):
    """Hangout now-playing: an individual Spotify track or full album."""
    type: Literal["track", "album"]
    spotify_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=300)
    artist: str = Field(default="", max_length=300)
    image: Optional[str] = Field(default=None, max_length=500)
    duration_ms: int = Field(default=0, ge=0)
    # Source album of a track — rides along for lyrics (LRCLIB) matching
    album_name: Optional[str] = Field(default=None, max_length=300)


# === WebSocket Message Models ===
# These models document the WebSocket protocol and can be used for validation

from typing import Literal, Union
from enum import Enum


class WSMessageType(str, Enum):
    """All WebSocket message types."""
    # Client -> Server
    PING = "ping"
    CHAT = "chat"
    TYPING = "typing"
    REACTION = "reaction"

    # Server -> Client
    PONG = "pong"
    CHAT_MESSAGE = "chat_message"
    USER_TYPING = "user_typing"
    REACTION_UPDATE = "reaction"  # broadcast echo of a reaction toggle
    SYNC = "sync"
    TRACK_CHANGE = "track_change"
    ALBUM_CHANGE = "album_change"
    MODE_CHANGE = "mode_change"
    MEDIA_CHANGE = "media_change"
    MEDIA_VOTE = "media_vote"
    QUEUE_UPDATE = "queue_update"
    PLAYBACK = "playback"
    RATING = "rating"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    SESSION_ENDED = "session_ended"
    ERROR = "error"


# --- Client -> Server Messages ---

class WSPingProgress(BaseModel):
    """Hangout Spotify clock report riding on a ping (latest report wins)."""
    media_seq: int
    track_spotify_id: str
    track_name: str = ""
    duration_ms: int = 0
    position: int


class WSClientPing(BaseModel):
    """Client ping to keep connection alive and sync position."""
    type: Literal["ping"] = "ping"
    progress: Optional[WSPingProgress] = None


class WSClientReaction(BaseModel):
    """Toggle an emoji reaction on a chat message (authed users only)."""
    type: Literal["reaction"] = "reaction"
    message_id: int
    emoji: str = Field(min_length=1, max_length=16)


# --- Server -> Client Messages ---

class WSListener(BaseModel):
    """Listener info in sync messages."""
    user_id: Union[int, str]  # int for users, str for guests (guest_xxx)
    user_name: str


class WSMediaTrack(BaseModel):
    """Live track within hangout album media, reported via ping progress."""
    spotify_id: str
    name: str = ""
    duration_ms: int = 0


class WSMediaVotes(BaseModel):
    """Ephemeral like/dislike tally on the current hangout media."""
    likes: int
    dislikes: int
    voters: list[dict] = []  # [{user_id, vote}]


class WSServerPong(BaseModel):
    """Server response to ping with current playback state."""
    type: Literal["pong"] = "pong"
    position: int  # Current position in ms
    is_playing: bool
    media_track: Optional[WSMediaTrack] = None


class WSServerSync(BaseModel):
    """Initial state sent to client on WebSocket connect. Carries mode and
    album_id so a reconnect catches up on switches missed while down."""
    type: Literal["sync"] = "sync"
    mode: Literal["listening", "hangout"]
    album_id: Optional[int]
    track_id: Optional[int]
    media: Optional[dict]  # SessionMediaSet shape
    media_seq: int
    media_track: Optional[WSMediaTrack]
    media_votes: WSMediaVotes
    is_playing: bool
    position: int
    listeners: list[WSListener]
    queue: list[dict]


class WSServerTrackChange(BaseModel):
    """Broadcast when track changes."""
    type: Literal["track_change"] = "track_change"
    track_id: int
    duration: int
    position: int = 0
    is_playing: bool = False
    changed_by: Optional[Union[int, str]] = None
    changed_by_name: Optional[str] = None


class WSServerAlbumChange(BaseModel):
    """Broadcast when album changes."""
    type: Literal["album_change"] = "album_change"
    album_id: int
    album_name: str
    cover_url: Optional[str]
    track_id: Optional[int]
    track_name: Optional[str]
    track_duration: Optional[int]
    changed_by: Optional[Union[int, str]] = None
    changed_by_name: Optional[str] = None


class WSServerPlayback(BaseModel):
    """Broadcast for playback control (play/pause/seek)."""
    type: Literal["playback"] = "playback"
    action: Literal["play", "pause", "seek"]
    position: int


class WSServerRating(BaseModel):
    """Broadcast when a user submits a track rating."""
    type: Literal["rating"] = "rating"
    track_id: int
    user_id: int
    user_name: str
    score: float
    comment: Optional[str] = None


class WSServerUserJoined(BaseModel):
    """Broadcast when a user joins the session."""
    type: Literal["user_joined"] = "user_joined"
    user_id: Union[int, str]
    user_name: str
    active_count: int


class WSServerUserLeft(BaseModel):
    """Broadcast when a user leaves the session."""
    type: Literal["user_left"] = "user_left"
    user_id: Union[int, str]
    user_name: str
    active_count: int


class WSServerSessionEnded(BaseModel):
    """Broadcast when session is closed by admin."""
    type: Literal["session_ended"] = "session_ended"
    message: str


class WSServerModeChange(BaseModel):
    """Broadcast when the room switches between listening and hangout."""
    type: Literal["mode_change"] = "mode_change"
    mode: Literal["listening", "hangout"]
    changed_by: Optional[int] = None
    changed_by_name: Optional[str] = None


class WSServerMediaChange(BaseModel):
    """Broadcast when the hangout now-playing changes (set, queue advance,
    or vote-skip). media None = queue drained, nothing on."""
    type: Literal["media_change"] = "media_change"
    media: Optional[dict]  # SessionMediaSet shape
    media_seq: int
    is_playing: bool
    position: int
    auto: bool = False
    skip_reason: Optional[str] = None
    changed_by: Optional[int] = None
    changed_by_name: Optional[str] = None


class WSServerMediaVote(BaseModel):
    """Broadcast on every like/dislike toggle of the current media."""
    type: Literal["media_vote"] = "media_vote"
    likes: int
    dislikes: int
    voters: list[dict] = []
    by: Optional[int] = None
    by_name: Optional[str] = None


class WSServerQueueUpdate(BaseModel):
    """Broadcast whenever the shared queue changes; carries the full queue."""
    type: Literal["queue_update"] = "queue_update"
    action: Literal["added", "removed", "voted", "moved", "advanced"]
    item: Optional[dict]
    by: Optional[int]
    by_name: Optional[str]
    queue: list[dict]


class WSServerReaction(BaseModel):
    """Broadcast when a chat-message reaction is toggled."""
    type: Literal["reaction"] = "reaction"
    message_id: int
    emoji: str
    user_id: int
    user_name: str
    action: Literal["added", "removed"]


class WSServerError(BaseModel):
    """Direct reply when a client message is rejected (e.g. guest chat)."""
    type: Literal["error"] = "error"
    message: str


# --- Chat (hangout mode) ---

class WSClientChat(BaseModel):
    """Client sends a chat message (authed users only). client_id reconciles
    the sender's optimistic bubble when the broadcast echoes back."""
    type: Literal["chat"] = "chat"
    content: str = Field(min_length=1, max_length=1000)
    kind: Literal["text", "gif"] = "text"
    client_id: Optional[str] = None


class WSClientTyping(BaseModel):
    """Client signals it is typing (throttled client-side, not persisted)."""
    type: Literal["typing"] = "typing"


class WSServerChatMessage(BaseModel):
    """Broadcast when a chat message is posted. client_id echoes the sender's
    optimistic-bubble id; kind distinguishes text from Giphy GIF messages."""
    type: Literal["chat_message"] = "chat_message"
    id: int
    client_id: Optional[str] = None
    user_id: int
    user_name: str
    content: str
    kind: Literal["text", "gif"] = "text"
    created_at: str


class WSServerUserTyping(BaseModel):
    """Broadcast typing indicator to other clients."""
    type: Literal["user_typing"] = "user_typing"
    user_id: Union[int, str]
    user_name: str


class ChatMessage(BaseModel):
    """Chat message as returned by the history endpoint."""
    id: int
    user_id: int
    user_name: str
    content: str
    created_at: str
