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
    user_id: int
    score: float = Field(ge=1, le=10)
    comment: Optional[str] = Field(None, max_length=500)

class TrackRankingCreate(BaseModel):
    track_id: int
    user_id: int
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

# Listening session models
class ListeningSession(BaseModel):
    id: int
    code: str
    album_id: int
    album_name: str
    cover_url: Optional[str]
    current_track_id: Optional[int]
    current_track_name: Optional[str]
    participants: list[str]
    is_active: bool

class SessionCreate(BaseModel):
    album_id: int

class SessionJoin(BaseModel):
    code: str
