"""Created by arr_tools.devtools.create_module."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, override

from attrmagic import SimpleDict, SimpleListRoot
from pydantic import (
    AnyUrl,
    Field,
    field_validator,
    model_validator,
)
from rich import print as rprint

from arr_tools.core import ApiBase
from arr_tools.logging_config import get_logger

logger = get_logger(__name__)


class MediaCover(ApiBase):
    cover_type: Literal[
        "unknown", "poster", "banner", "fanart", "screenshot", "headshot", "clearlogo"
    ]
    url: PurePosixPath | None = None
    remote_url: PurePosixPath | None = None


class Availability(StrEnum):
    TO_BE_ANNOUNCED = "tba"
    ANNOUNCED = "announced"
    IN_CINEMAS = "inCinemas"
    RELEASED = "released"
    DELETED = "deleted"

    @override
    def __repr__(self) -> str:
        return self.name


class AddMovieOptions(ApiBase):
    ignore_episodes_with_files: bool
    ignore_episodes_without_files: bool
    monitor: Literal["movieOnly", "movieAndCollection", None]
    search_for_movie: bool
    add_method: Literal["manual", "list", "collection"]


class RatingChild(ApiBase):
    value: float
    votes: int
    type: Literal["user", "critic"]


class Language(ApiBase):
    id: int
    name: str | None = None


class Ratings(ApiBase):
    imdb: RatingChild | None = None
    tmdb: RatingChild | None = None
    metacritic: RatingChild | None = None
    rotten_tomatoes: RatingChild | None = None
    trakt: RatingChild | None = None


class Quality(ApiBase):
    id: int
    name: str | None = None
    source: (
        Literal[
            "unknown",
            "cam",
            "telesync",
            "telecine",
            "workprint",
            "dvd",
            "tv",
            "webdl",
            "webrip",
            "bluray",
        ]
        | None
    ) = None
    resolution: int
    modifier: Literal["regional", "screener", "rawhd", "brdisk", "remux", None]

    @field_validator("modifier", mode="before")
    @classmethod
    def modifier_validator(cls, v: Any) -> Any:  # pyright: ignore[reportExplicitAny, reportAny]
        if isinstance(v, str) and v.lower() == "none":
            return None
        return v


class Revision(ApiBase):
    version: int
    real: int
    is_repack: bool


class QualityModel(ApiBase):
    quality: Quality
    revision: Revision


class CustomFormatSpecificationSchema(ApiBase):
    id: int
    name: str | None = None
    implementation: str | None = None
    implementation_name: str | None = None
    info_link: str | None = None
    negate: bool
    required: bool


class MediaInfoResource(ApiBase):
    # id: int
    audio_bitrate: int
    audio_channels: float
    audio_codec: str | None = None
    audio_languages: str | None = None
    audio_stream_count: int
    video_bit_depth: int
    video_bitrate: int
    video_codec: str | None = None
    video_fps: float
    video_dynamic_range: str | None = None
    video_dynamic_range_type: str | None = None
    resolution: str | None = None
    run_time: str | None = None
    scan_type: str | None = None
    subtitles: str | None = None


class MovieFileResource(ApiBase):
    id: int
    movie_id: int
    relative_path: PurePosixPath | None = None
    path: PurePosixPath | None = None
    size: int
    date_added: datetime
    scene_name: str | None = None
    release_group: str | None = None
    edition: str | None = None
    languages: list[Language] | None = None
    quality: QualityModel
    custom_formats: list[CustomFormatSpecificationSchema] | None = None
    custom_format_score: int | None = None
    indexer_flags: int | None = None
    media_info: MediaInfoResource | None = None
    original_file_path: PurePosixPath | None = None
    quality_cutoff_not_met: bool


class MovieCollectionResource(ApiBase):
    title: str | None = None
    tmdb_id: int


class MovieStatisticsResource(ApiBase):
    movie_file_count: int
    size_on_disk: int
    release_groups: list[str] | None = None


class AlternativeTitleResource(ApiBase):
    id: int
    source_type: Literal["tmdb", "mappings", "user", "indexer"]
    movie_metadata_id: int
    title: str | None = None
    clean_title: str | None = None


class MovieResource(ApiBase):
    id: int
    title: str | None = None
    original_title: str | None = None
    sort_title: str | None = None
    year: int
    path: PurePosixPath | None = None
    movie_file_id: int
    folder_name: str | None = None
    clean_title: str | None = None
    imdb_id: str | None = None
    tmdb_id: int
    title_slug: str | None = None
    root_folder_path: str | None = None
    folder: str | None = None
    has_file: bool | None = None
    original_language: dict[str, int | str]
    alternate_titles: list[AlternativeTitleResource] = Field(default_factory=list)
    secondary_year_source_id: int
    size_on_disk: int | None = None
    status: Availability
    overview: str | None = None
    in_cinemas: datetime | None = None
    physical_release: datetime | None = None
    digital_release: datetime | None = None
    release_date: datetime | None = None
    physical_release_note: str | None = None
    images: list[MediaCover] | None = None
    website: AnyUrl | None = None
    remote_poster: str | None = None
    you_tube_trailer_id: str | None = None
    studio: str | None = None
    quality_profile_id: int | None = None
    monitored: bool
    minimum_availability: Availability
    is_available: bool
    runtime: int
    certification: str | None = None
    genres: list[str] | None = None
    keywords: list[str] | None = None
    tags: list[int] | None = None
    added: datetime | None = None
    add_options: AddMovieOptions | None = None
    ratings: Ratings
    movie_file: MovieFileResource | None = None
    collection: MovieCollectionResource | None = None
    popularity: float
    last_search_time: datetime | None = None
    statistics: MovieStatisticsResource

    @field_validator("tags", mode="after")
    @classmethod
    def ensure_unique(cls, v: list[int] | None) -> list[int] | None:
        if v is not None:
            if len(set(v)) != len(v):
                rprint("Duplicate tags found and removed: %s", v)
            return list(set(v))
        return v

    @field_validator("website", mode="before")
    @classmethod
    def none_if_empty(cls, v: Any) -> Any:  # pyright: ignore[reportExplicitAny, reportAny]
        if not v:
            return None
        return v  # pyright: ignore[reportAny]


class MovieResources(SimpleListRoot[MovieResource]):
    pass


class MovieResourcePagingResource(ApiBase):
    page: int
    page_size: int
    sort_key: str | None = None
    sort_direction: Literal["default", "ascending", "descending"]
    total_records: int
    records: MovieResources = Field(default_factory=MovieResources.empty)


class Directory(ApiBase):
    type: str
    name: str
    path: PurePosixPath
    size: int
    last_modified: datetime


class Directories(SimpleDict[PurePosixPath, Directory]):
    @model_validator(mode="before")
    @classmethod
    def validate_root(cls, v: Any) -> Any:  # pyright: ignore[reportExplicitAny, reportAny]
        if isinstance(v, Sequence):
            return {cls.clean_path(p["path"]): p for p in v}  # pyright: ignore[reportIndexIssue]
        return v  # pyright: ignore[reportAny]

    @staticmethod
    def clean_path(path: str) -> str:
        # matches = re.findall(r"[^\w\s/\(\)&-{}]", path)
        # if matches:
        #     rprint("Found punctuation in path: %s", matches)
        return path.strip()


class FileSystemResource(ApiBase):
    parent: PurePosixPath
    directories: Directories = Field(default_factory=Directories.empty)


class Command(ApiBase):
    send_updates_to_client: bool
    update_scheduled_task: Annotated[bool, Field(frozen=True)]
    completion_message: Annotated[str | None, Field(frozen=True)] = None
    requires_disk_access: Annotated[bool, Field(frozen=True)]


class CommandResource(ApiBase):
    id: int
    name: str | None = None
    command_name: str | None = None
    message: str | None = None
    body: Command
    priority: Literal["low", "normal", "high"]
    status: Literal["queued", "started", "completed", "failed", "aborted", "cancelled", "orphaned"]
    result: Literal["unknown", "successful", "unsuccessful"]
    queued: datetime
    started: datetime | None = None
    ended: datetime | None = None
    duration: timedelta | None = None
    exception: str | None = None
    trigger: Literal["unspecified", "manual", "scheduled"]
    client_user_agent: str | None = None
    state_change_time: datetime | None = None
    send_updates_to_client: bool
    update_scheduled_task: bool
    last_execution_time: datetime | None = None


class CommandResources(SimpleListRoot[CommandResource]):
    pass
