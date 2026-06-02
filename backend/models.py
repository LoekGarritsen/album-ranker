from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

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

class SessionCreate(BaseModel):
    name: str
    album_id: Optional[int] = None
    is_public: bool = True
    password: Optional[str] = None

class SessionJoin(BaseModel):
    password: Optional[str] = None

class SessionSetAlbum(BaseModel):
    album_id: int


# === WebSocket Message Models ===
# These models document the WebSocket protocol and can be used for validation

from typing import Literal, Union
from enum import Enum


class WSMessageType(str, Enum):
    """All WebSocket message types."""
    # Client -> Server
    PING = "ping"

    # Server -> Client
    PONG = "pong"
    SYNC = "sync"
    TRACK_CHANGE = "track_change"
    ALBUM_CHANGE = "album_change"
    PLAYBACK = "playback"
    RATING = "rating"
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    SESSION_ENDED = "session_ended"


# --- Client -> Server Messages ---

class WSClientPing(BaseModel):
    """Client ping to keep connection alive and sync position."""
    type: Literal["ping"] = "ping"


# --- Server -> Client Messages ---

class WSListener(BaseModel):
    """Listener info in sync messages."""
    user_id: Union[int, str]  # int for users, str for guests (guest_xxx)
    user_name: str


class WSServerPong(BaseModel):
    """Server response to ping with current playback state."""
    type: Literal["pong"] = "pong"
    position: int  # Current position in ms
    is_playing: bool


class WSServerSync(BaseModel):
    """Initial state sent to client on WebSocket connect."""
    type: Literal["sync"] = "sync"
    track_id: Optional[int]
    is_playing: bool
    position: int
    listeners: list[WSListener]


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
