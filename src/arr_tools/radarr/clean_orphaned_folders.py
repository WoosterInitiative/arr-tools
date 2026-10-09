"""Created by arr_tools.devtools.create_module."""

from pathlib import PurePath, PurePosixPath
from typing import TYPE_CHECKING, Annotated, Literal

import typer
from rich.table import Table

from arr_tools.core import ProjectContext  # noqa: TC001
from arr_tools.logging_config import get_console, get_logger
from arr_tools.radarr.utils import get_all_movies, get_filesystem
from arr_tools.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Iterable

    from arr_tools.radarr.models import Directories, MovieResources

logger = get_logger(__name__)

settings = get_settings()

app = typer.Typer()
console = get_console()


def build_folder_table(paths: Iterable[PurePath], title: str = "Folders") -> Table:
    table = Table(title=title)
    table.add_column("Path", style="cyan", no_wrap=True)
    for path in paths:
        table.add_row(str(path))
    return table


@app.command()
def get_messy_folders(
    ctx: ProjectContext,
    tables: Annotated[
        Literal["folders", "orphaned", "missing", "all"],
        typer.Option("-t", "--tables", help="Specify which tables to display"),
    ] = "all",
):
    """Get the list of messy folders for the given project context."""
    _dry_run = ctx.obj.dry_run

    all_movies = get_all_movies()
    filesystem = get_filesystem(path=str(settings.radarr.internal_root) + "/")
    directories = filesystem.directories
    if "folders" in tables or "all" in tables:
        console.print(
            build_folder_table(get_paths_from_directories(directories), title="All Folders")
        )

    orphaned_folders = get_orphaned_folders(all_movies, directories)
    missing_folders = get_missing_folders(all_movies, directories)
    if "orphaned" in tables or "all" in tables:
        console.print(
            build_folder_table(
                orphaned_folders, title=f"Orphaned Folders     Count: {len(orphaned_folders)}"
            )
        )
    if "missing" in tables or "all" in tables:
        console.print(
            build_folder_table(
                missing_folders, title=f"Missing Folders     Count: {len(missing_folders)}"
            )
        )


def to_local(path: PurePath) -> PurePosixPath:
    """Replace the internal Radarr path with the local filesystem path."""
    return PurePosixPath(
        str(path).replace(str(settings.radarr.internal_root), str(settings.radarr.local_root))
    )


def get_paths_from_movies(movies: MovieResources) -> set[PurePosixPath]:
    """Convert the internal Radarr paths of the given movies to local filesystem paths."""
    return set(m.path for m in movies if m.path is not None)


def get_paths_from_directories(directories: Directories) -> set[PurePosixPath]:
    logger.debug("Getting paths from directories: %s", directories)
    return set(d for d in directories.keys())


def get_orphaned_folders(movies: MovieResources, folders: Directories) -> set[PurePosixPath]:
    """Get the list of orphaned folders that do not contain any of the given movies."""
    return get_paths_from_directories(folders) - get_paths_from_movies(movies)


def get_missing_folders(movies: MovieResources, folders: Directories) -> set[PurePosixPath]:
    """Get the list of folders that should exist for the given movies but are missing."""
    return get_paths_from_movies(movies) - get_paths_from_directories(folders)
