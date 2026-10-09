"""Created by arr_tools.devtools.create_module."""

from typing import TYPE_CHECKING, Literal

import requests
from rich.pretty import pretty_repr

from arr_tools.logging_config import get_logger
from arr_tools.radarr.models import (
    CommandResources,
    FileSystemResource,
    MovieResource,
    MovieResourcePagingResource,
    MovieResources,
)
from arr_tools.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pydantic import AnyUrl

    from arr_tools.core import Headers, JsonType, ParamsType

logger = get_logger(__name__)
settings = get_settings()


def build_headers() -> Headers:
    return {"X-Api-Key": settings.radarr.api_key.get_secret_value()}


DEFAULT_HEADERS = build_headers()


def get_filesystem(
    host: str | AnyUrl = settings.radarr.host,
    headers: Headers | None = DEFAULT_HEADERS,
    *,
    path: str | None = None,
    include_files: bool | None = None,
    allow_folders_without_trailing_slashes: bool | None = None,
) -> FileSystemResource:
    """Get the filesystem information from the Radarr API."""
    params: ParamsType = {}
    if path is not None:
        params["path"] = path
    if include_files is not None:
        params["includeFiles"] = include_files
    if allow_folders_without_trailing_slashes is not None:
        params["allowFoldersWithoutTrailingSlashes"] = allow_folders_without_trailing_slashes

    path = f"{str(host).rstrip('/')}/api/v3/filesystem"
    logger.debug("Requesting filesystem from URL: %s with params: %s", path, pretty_repr(params))

    response = requests.get(path, headers=headers, params=params)
    response.raise_for_status()
    return FileSystemResource.model_validate_json(response.content)


def get_all_movies(
    host: str | AnyUrl = settings.radarr.host,
    headers: Headers | None = DEFAULT_HEADERS,
    *,
    tmdb_id: int | None = None,
    exclude_local_covers: bool | None = None,
    languade_id: int | None = None,
) -> MovieResources:
    """Get all movies from the Radarr API."""
    params: ParamsType = {}
    if tmdb_id is not None:
        params["tmdbId"] = tmdb_id
    if exclude_local_covers is not None:
        params["excludeLocalCovers"] = exclude_local_covers
    if languade_id is not None:
        params["languageId"] = languade_id

    path = f"{str(host).rstrip('/')}/api/v3/movie"
    logger.debug("Requesting all movies from URL: %s with params: %s", path, pretty_repr(params))

    response = requests.get(path, headers=headers, params=params, timeout=60)
    response.raise_for_status()
    return MovieResources.model_validate_json(response.content)


def get_wanted_movies(
    host: str | AnyUrl = settings.radarr.host,
    headers: Headers | None = DEFAULT_HEADERS,
    *,
    page: int | None = None,
    page_size: int | None = None,
    sort_key: str | None = None,
    sort_direction: Literal["default", "ascending", "descending"] | None = None,
    monitored: bool = True,
) -> MovieResourcePagingResource:
    """Get the wanted movies from the Radarr API."""
    params: ParamsType = {}
    if not monitored:
        params["monitored"] = False
    if page is not None:
        params["page"] = page
    if page_size is not None:
        params["pageSize"] = page_size
    if sort_key is not None:
        params["sortKey"] = sort_key
    if sort_direction is not None:
        params["sortDirection"] = sort_direction

    path = f"{str(host).rstrip('/')}/api/v3/wanted/missing"
    logger.debug("Requesting wanted movies from URL: %s with params: %s", path, pretty_repr(params))

    response = requests.get(path, headers=headers, params=params)
    response.raise_for_status()
    return MovieResourcePagingResource.model_validate_json(response.content, by_alias=True)


def get_all_wanted_movies(
    host: str | AnyUrl = settings.radarr.host,
    headers: Headers | None = DEFAULT_HEADERS,
    *,
    chunk_size: int = 100,
    monitored: bool = True,
) -> MovieResources:
    """Get all wanted movies from the Radarr API by paginating through all pages."""

    all_movies: MovieResources = MovieResources.empty()
    page = 1
    while True:
        logger.debug("Fetching page %d of wanted movies", page)
        movies = get_wanted_movies(
            host=host,
            headers=headers,
            page=page,
            page_size=chunk_size,
            monitored=monitored,
        )
        all_movies += movies.records
        if page * movies.page_size >= movies.total_records:
            logger.debug("All wanted movies have been fetched")
            break
        page += 1
    return all_movies


def update_movie(
    host: str | AnyUrl = settings.radarr.host,
    headers: Headers | None = DEFAULT_HEADERS,
    *,
    movie: MovieResource,
    move_files: bool = False,
) -> requests.Response:
    """Update the path of a movie in the Radarr API."""
    path = f"{str(host).rstrip('/')}/api/v3/movie/{movie.id}"
    params = {"moveFiles": move_files}
    logger.debug("Updating movie path at URL: %s with payload: %s", path, pretty_repr(movie))
    response = requests.put(
        path,
        headers=headers,
        params=params,
        json=movie.model_dump(mode="json", exclude_unset=True, exclude_none=True, by_alias=True),
    )
    response.raise_for_status()
    return response


def get_commands(
    host: str | AnyUrl = settings.radarr.host,
    headers: Headers | None = DEFAULT_HEADERS,
):
    path = f"{str(host).rstrip('/')}/api/v3/command"
    logger.debug("Requesting commands from URL: %s", path)
    response = requests.get(path, headers=headers)
    response.raise_for_status()
    return CommandResources.model_validate_json(response.content)


def rescan_movie(
    host: str | AnyUrl = settings.radarr.host,
    headers: Headers | None = DEFAULT_HEADERS,
    *,
    movie_id: int,
) -> requests.Response:
    """Trigger a rescan of a specific movie in the Radarr API."""
    path = f"{str(host).rstrip('/')}/api/v3/command"
    payload = {"name": "RescanMovie", "movieId": movie_id}
    logger.debug(
        "Triggering rescan of movie with ID %d at URL: %s with payload: %s",
        movie_id,
        path,
        pretty_repr(payload),
    )
    response = requests.post(path, headers=headers, json=payload)
    response.raise_for_status()
    return response


def refresh_movies(
    host: str | AnyUrl = settings.radarr.host,
    headers: Headers | None = DEFAULT_HEADERS,
    *,
    movie_ids: Iterable[int] | None = None,
) -> requests.Response:
    """Trigger a refresh of a list movies in the Radarr API.

    If `movie_ids` is provided, only the specified movies will be refreshed.
    Otherwise, all movies will be refreshed.
    """
    path = f"{str(host).rstrip('/')}/api/v3/command"
    payload: JsonType = {"name": "RefreshMovie"}
    if movie_ids is not None:
        payload["movieIds"] = list(movie_ids)
    logger.debug(
        "Triggering refresh of all movies at URL: %s with payload: %s",
        path,
        pretty_repr(payload),
    )
    response = requests.post(path, headers=headers, json=payload)
    response.raise_for_status()
    return response
