"""Request/response payloads for the household API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LoginPayload(BaseModel):
    username: str
    password: str


class RedeemPayload(BaseModel):
    token: str
    username: str
    password: str


class InvitePayload(BaseModel):
    role: str
    expires_in_seconds: int = 7 * 24 * 3600


class RequestPayload(BaseModel):
    title: str
    guid: str = ""
    kind: Optional[str] = None
    download_url: str = ""
    category: Optional[Any] = None
    author: str = ""
    isbn: str = ""
    q: str = ""
    series: str = ""
    issue: str = ""
    artist: str = ""
    album: str = ""
    year: str = ""
    size: Optional[int] = None
    cover: str = ""
    book_title: str = ""
    poster: str = ""
    category_name: str = ""
    sought: Optional[Dict[str, Any]] = None
    selected: Optional[Dict[str, Any]] = None
    retrieved: Optional[Dict[str, Any]] = None
    candidates: Optional[List[Dict[str, Any]]] = None
    rank_method: str = ""
    rank_reason: str = ""


class ReviewApplyPayload(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    kind: Optional[str] = None
    series_name: Optional[str] = None
    series_index: Optional[str] = None
    year: Optional[int] = None
    isbn: Optional[str] = None
    folder: Optional[str] = None


class ExtraIndexerPayload(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    api_token: Optional[str] = None
    enabled: Optional[bool] = True


class RssFeedPayload(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    kind: Optional[str] = None
    enabled: Optional[bool] = None


class MailPayload(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    resend_api_key: Optional[str] = None
    subject_prefix: Optional[str] = None
    footer_text: Optional[str] = None
    logo_url: Optional[str] = None


class MailTestPayload(BaseModel):
    to_email: Optional[str] = Field(default=None, max_length=320)


class SettingsPayload(BaseModel):
    sabnzbd_url: Optional[str] = None
    sabnzbd_api_key: Optional[str] = None
    nzbfinder_url: Optional[str] = None
    nzbfinder_api_token: Optional[str] = None
    books_root: Optional[str] = None
    magazines_root: Optional[str] = None
    comics_root: Optional[str] = None
    audiobooks_root: Optional[str] = None
    incoming_music_root: Optional[str] = None
    music_root: Optional[str] = None
    complete_root: Optional[str] = None
    audiobook_target: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_profiles: Optional[Dict[str, Any]] = None
    household_name: Optional[str] = None
    hardcover_api_token: Optional[str] = None
    nyt_books_api_key: Optional[str] = None
    comicvine_api_key: Optional[str] = None
    komga_url: Optional[str] = None
    komga_api_key: Optional[str] = None
    komga_library_id: Optional[str] = None
    watch_root: Optional[str] = None
    watch_enabled: Optional[bool] = None
    extra_indexers: Optional[List[ExtraIndexerPayload]] = None
    audiobookshelf_url: Optional[str] = None
    audiobookshelf_api_token: Optional[str] = None
    show_extra_categories: Optional[bool] = None
    radarr_url: Optional[str] = None
    radarr_api_key: Optional[str] = None
    sonarr_url: Optional[str] = None
    sonarr_api_key: Optional[str] = None
    sab_movie_category: Optional[str] = None
    sab_tv_category: Optional[str] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    mail: Optional[MailPayload] = None


class IngestPayload(BaseModel):
    path: str


class ProgressPayload(BaseModel):
    position: str = ""
    fraction: Optional[float] = None
    finished: bool = False


class ConvertPayload(BaseModel):
    format: str = "epub"


class PrefsPayload(BaseModel):
    ambient: Optional[str] = None
    ui_theme: Optional[str] = None
    ui_font_step: Optional[int] = None


class WhisperPayload(BaseModel):
    body: str


class WorkMetadataPayload(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    year: Optional[int] = None
    description: Optional[str] = None
    genre: Optional[str] = None
    series_name: Optional[str] = None
    series_index: Optional[str] = None
    kind: Optional[str] = None
    synopsis_source: Optional[str] = None
    llm_blurb: Optional[str] = None
    cover_url: Optional[str] = None


class ApplyMatchPayload(BaseModel):
    match_key: str = ""


class CelebrationSeenPayload(BaseModel):
    key: str


class FinishSetEtaPayload(BaseModel):
    missing_count: int = 0
    kind: str = ""
    total_bytes: Optional[int] = None
    multipart: bool = False


class LlmListPayload(BaseModel):
    preset: str = "hardcover-fiction"
    date: str = "current"
    query: str = ""


class LlmListChaseItem(BaseModel):
    title: str
    author: str
    isbn: str = ""


class LlmListChasePayload(BaseModel):
    items: List[LlmListChaseItem] = []


