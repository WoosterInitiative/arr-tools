"""Created by arr_tools.devtools.create_module."""

from typing import TYPE_CHECKING, Annotated, Literal

import typer
from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from arr_tools.core import ProjectContext  # noqa: TC001
from arr_tools.logging_config import get_console, get_logger
from arr_tools.radarr.utils import get_wanted_movies
from arr_tools.settings import get_settings

from .clean_orphaned_folders import app as clean_orphaned_folders_app
from .fix_paths import app as fix_paths_app

if TYPE_CHECKING:
    from arr_tools.radarr.models import MovieResourcePagingResource

logger = get_logger(__name__)

app = typer.Typer()
app.add_typer(fix_paths_app)
app.add_typer(clean_orphaned_folders_app)
console = get_console()


settings = get_settings()


def print_movie_page(paged: MovieResourcePagingResource, title: str = "Movies") -> None:
    """Print a paged movie result as a rich panel with a table of titles."""
    summary = (
        f"[bold]Page:[/bold] {paged.page}    "
        f"[bold]Page size:[/bold] {paged.page_size}    "
        f"[bold]Total records:[/bold] {paged.total_records}    "
        f"[bold]Sort direction:[/bold] {paged.sort_direction}"
    )
    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Title")
    table.add_column("Year", justify="right")
    for index, movie in enumerate(paged.records, start=1):
        table.add_row(str(index), movie.title or "<untitled>", str(movie.year))
    console.print(Panel(Group(summary, table), title=title, border_style="cyan"))


@app.command()
def list_wanted_movies(
    ctx: ProjectContext,
    page: Annotated[
        int | None, typer.Option("-p", "--page", help="Page number of the wanted movies list")
    ] = None,
    page_size: Annotated[
        int | None, typer.Option("-s", "--page-size", help="Number of movies per page")
    ] = None,
    sort_by: Annotated[
        str | None,
        typer.Option(
            "-o",
            "--sort-by",
            help="Sort the wanted movies by this field. Use `-` for descending order.",
        ),
    ] = None,
    include_unmonitored: Annotated[
        bool,
        typer.Option("-u", "--include-unmonitored", help="Include unmonitored movies in the list"),
    ] = False,
):
    """List wanted movies from Radarr."""
    _dry_run = ctx.obj.dry_run

    sort_direction: Literal["default", "ascending", "descending"] | None = None
    if sort_by is not None:
        sort_direction = "descending" if sort_by.startswith("-") else "ascending"
        sort_by = sort_by.lstrip("-")

    wanted_movies = get_wanted_movies(
        page=page,
        page_size=page_size,
        sort_key=sort_by,
        monitored=not include_unmonitored,
        sort_direction=sort_direction,
    )
    print_movie_page(wanted_movies, title="Wanted Movies")
