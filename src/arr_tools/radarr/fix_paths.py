"""Created by arr_tools.devtools.create_module."""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Annotated

import typer
from requests import RequestException
from rich.table import Table

from arr_tools.core import ProjectContext  # noqa: TC001
from arr_tools.logging_config import get_console, get_logger
from arr_tools.radarr.utils import (
    get_all_wanted_movies,
    get_filesystem,
    refresh_movies,
    update_movie,
)

if TYPE_CHECKING:
    from arr_tools.radarr.models import Directories, MovieResource

logger = get_logger(__name__)

app = typer.Typer()
console = get_console()


TT = re.compile(r"\s*[\{\[](?:imdb(?:id)?-)?tt\d+[\}\]]", re.I)

CANDIDATE_TEMP_PATH = Path("tmp/candidate_paths")


def clean_path(path: PurePosixPath) -> set[PurePosixPath]:
    """Clean a movie path and create candidate paths.

    Operates on the stem of the path (the filename without the directory).

    Standard is to remove IMDb IDs and surrounding brackets from the path.

    Candidates will also remove most punctuation from the path.
    """
    candidates: set[PurePosixPath] = set()
    path_stem = path.stem
    base_candidate = TT.sub("", path_stem)
    candidates.add(PurePosixPath(path.parent / base_candidate))
    # Remove most punctuation from the base candidate to create additional candidates
    punctuation_removed = re.sub(r"[,\'\"]", "", base_candidate)
    candidates.add(PurePosixPath(path.parent / punctuation_removed))
    return candidates


def path_from_movie(movie: MovieResource) -> PurePosixPath:
    """Generate a standardized path from a movie title."""
    title = f"{movie.title} ({movie.year})"
    cleaned_title = title
    return PurePosixPath(cleaned_title)


def normalize_path_name(path: PurePosixPath) -> str:
    name = unicodedata.normalize("NFKC", TT.sub("", path.name)).casefold()
    name = name.replace("&", " and ")
    name = re.sub(r"['\"\u2019]", "", name)
    return " ".join(re.sub(r"[^\w\s]", " ", name).split())


@dataclass(frozen=True)
class PathComparison:
    path: PurePosixPath
    raw_score: float
    normalized_score: float
    candidate_score: float
    best_candidate: PurePosixPath
    exact_match: bool
    year_status: str


def compare_path(
    query: PurePosixPath, path: PurePosixPath, candidates: set[PurePosixPath]
) -> PathComparison:
    def score(left: str, right: str) -> float:
        return 100 * SequenceMatcher(None, left, right, autojunk=False).ratio()

    candidate_scores = [
        (score(candidate.name, path.name), candidate) for candidate in sorted(candidates, key=str)
    ]
    if not candidate_scores:
        raise ValueError("No candidate scores available for comparison.")
    candidate_score, best_candidate = max(candidate_scores, key=lambda item: item[0])
    query_year = re.search(r"\((\d{4})\)", TT.sub("", query.name))
    path_year = re.search(r"\((\d{4})\)", TT.sub("", path.name))
    year_status = "missing"
    if query_year and path_year:
        year_status = "same" if query_year[1] == path_year[1] else "DIFFERENT"
    return PathComparison(
        path=path,
        raw_score=score(query.name, path.name),
        normalized_score=score(normalize_path_name(query), normalize_path_name(path)),
        candidate_score=candidate_score,
        best_candidate=best_candidate,
        exact_match=path in candidates,
        year_status=year_status,
    )


def literal_path_differences(left: PurePosixPath, right: PurePosixPath) -> list[str]:
    left_text, right_text = str(left), str(right)
    if left_text == right_text:
        return ["Full paths are literally identical."]
    differences = [
        f"Parent equal: {left.parent == right.parent}; folder name equal: {left.name == right.name}",
        f"Left ({len(left_text)} characters): {left_text!a}",
        f"Right ({len(right_text)} characters): {right_text!a}",
    ]

    def characters(text: str) -> str:
        return (
            ", ".join(
                f"{character!a} U+{ord(character):04X} {unicodedata.name(character, 'UNNAMED')}"
                for character in text
            )
            or "<empty>"
        )

    for operation, left_start, left_end, right_start, right_end in SequenceMatcher(
        None, left_text, right_text, autojunk=False
    ).get_opcodes():
        if operation == "equal":
            continue
        differences.append(
            f"{operation}: left[{left_start}:{left_end}] {characters(left_text[left_start:left_end])}"
            + f" -> right[{right_start}:{right_end}] {characters(right_text[right_start:right_end])}"
        )
    return differences


def print_match_explanation(
    query: PurePosixPath,
    comparison: PathComparison,
    candidates: set[PurePosixPath],
    lookup_keys: list[PurePosixPath] | None = None,
) -> None:
    console.print("Literal match explanation (character offsets are zero-based):")
    console.print("Query versus existing directory:")
    for line in literal_path_differences(query, comparison.path):
        console.print(line, markup=False, highlight=False)
    console.print(
        "Normalized query: " + ascii(normalize_path_name(query)), markup=False, highlight=False
    )
    console.print(
        "Normalized existing: " + ascii(normalize_path_name(comparison.path)),
        markup=False,
        highlight=False,
    )
    for candidate in sorted(candidates, key=str):
        console.print(
            "Candidate versus existing: " + ascii(str(candidate)), markup=False, highlight=False
        )
        for line in literal_path_differences(candidate, comparison.path):
            console.print(line, markup=False, highlight=False)
    if lookup_keys is not None:
        console.print("Strict lookup uses dictionary keys, not Directory.path values.")
        console.print(
            f"Candidate matches a lookup key: {any(key in candidates for key in lookup_keys)}",
            markup=False,
            highlight=False,
        )
        for key in lookup_keys:
            console.print(
                "Lookup key versus Directory.path: " + ascii(str(key)),
                markup=False,
                highlight=False,
            )
            for line in literal_path_differences(key, comparison.path):
                console.print(line, markup=False, highlight=False)


@app.command()
def compare_paths(
    query: Annotated[str, typer.Argument(help="Movie path or folder name to investigate")],
    against: Annotated[
        str | None, typer.Argument(help="Compare directly with this existing path")
    ] = None,
    directory: Annotated[
        Path | None,
        typer.Option("--directory", exists=True, file_okay=False, help="Scan local subdirectories"),
    ] = None,
    root: Annotated[str, typer.Option(help="Radarr filesystem root to scan")] = "/data/movies/",
    title: Annotated[
        str | None, typer.Option(help="Radarr movie title for its title/year candidate")
    ] = None,
    year: Annotated[int | None, typer.Option(help="Radarr movie year", min=1, max=9999)] = None,
    limit: Annotated[int, typer.Option(help="Maximum results to display", min=1)] = 10,
    explain: Annotated[
        bool, typer.Option("--explain", help="Show literal differences and Unicode code points")
    ] = False,
) -> None:
    """Explain path matches with read-only similarity scores (0-100, not probabilities)."""
    if against is not None and directory is not None:
        raise typer.BadParameter("Use either an existing path or --directory, not both.")
    if (title is None) != (year is None):
        raise typer.BadParameter("Supply --title and --year together.")

    query_path = PurePosixPath(query)
    candidates = clean_path(query_path)
    if title is not None:
        candidates.add(PurePosixPath(f"{title} ({year})"))

    console.print("Query: " + str(query_path), markup=False)
    console.print("Generated candidates (exact equality is used by fix-all-paths):")
    for candidate in sorted(candidates, key=str):
        console.print("  " + str(candidate), markup=False)
    if query_path.stem != query_path.name:
        console.print("Warning: clean_path uses .stem, which truncates dotted folder names.")

    directory_keys: dict[PurePosixPath, list[PurePosixPath]] = {}
    if against is not None:
        paths = [PurePosixPath(against)]
    elif directory is not None:
        paths = [PurePosixPath(path.as_posix()) for path in directory.iterdir() if path.is_dir()]
    else:
        filesystem = get_filesystem(path=root)
        paths = [directory.path for directory in filesystem.directories.values()]
        for key, resource in filesystem.directories.items():
            directory_keys.setdefault(resource.path, []).append(key)

    comparisons = sorted(
        (compare_path(query_path, path, candidates) for path in paths),
        key=lambda result: (
            not result.exact_match,
            -result.normalized_score,
            -result.raw_score,
            str(result.path),
        ),
    )
    table = Table(title=f"Path comparisons ({len(comparisons)} scanned)")
    table.add_column("Existing path", overflow="fold")
    table.add_column("Raw", justify="right")
    table.add_column("Normalized", justify="right")
    table.add_column("Candidate", justify="right")
    table.add_column("Exact")
    table.add_column("Year")
    table.add_column("Best candidate", overflow="fold")
    for result in comparisons[:limit]:
        table.add_row(
            str(result.path),
            f"{result.raw_score:.1f}",
            f"{result.normalized_score:.1f}",
            f"{result.candidate_score:.1f}",
            "yes" if result.exact_match else "no",
            result.year_status,
            str(result.best_candidate),
        )
    console.print(table)
    console.print(
        "Raw/Candidate compare folder names; Normalized ignores case, IMDb IDs and punctuation, and maps & to and."
    )
    console.print(
        "Exact compares full paths, including parents and case. A score of 100 does not imply an exact match."
    )
    if explain:
        for result in comparisons[:limit]:
            print_match_explanation(query_path, result, candidates, directory_keys.get(result.path))
    if not comparisons:
        console.print("No existing directories found.")


def get_best_match(
    query: PurePosixPath,
    existing_directories: Directories,
    candidates: set[PurePosixPath] | None = None,
) -> PathComparison | None:
    if candidates is None:
        candidates = clean_path(query)
    comparisons = sorted(
        (
            compare_path(query, directory.path, candidates)
            for directory in existing_directories.values()
        ),
        key=lambda result: (
            not result.exact_match,
            -result.normalized_score,
            -result.raw_score,
            str(result.path),
        ),
    )
    return comparisons[0] if comparisons else None


@app.command()
def fix_all_paths(
    ctx: ProjectContext,
    force_refresh: Annotated[
        bool,
        typer.Option(
            "-F",
            "--force-refresh",
            help="Force a refresh of all movie paths even if they appear correct",
        ),
    ] = False,
):
    dry_run = ctx.obj.dry_run
    existing_directories = get_filesystem(path="/data/movies/")
    all_wanted = get_all_wanted_movies()

    console.print(
        f"Found {len(existing_directories.directories)} existing directories and {len(all_wanted)} wanted movies"
    )

    fixed: list[int] = []
    skipped: list[tuple[MovieResource, str]] = []

    for m in all_wanted:
        if m.has_file:
            console.print(f"[dim yellow]Found movie with file: {m.title}; skipping[/]")
            skipped.append((m, "Has file"))
            continue

        if m.path is None:
            console.print(f"[bold red]Found movie without path: {m.title}; wtf?; skipping[/]")
            skipped.append((m, "No path"))
            continue

        candidates = clean_path(m.path)
        candidates.add(m.path.parent / path_from_movie(m))

        # for candidate in candidates:
        #     candidate_path = CANDIDATE_TEMP_PATH / candidate.name
        #     candidate_path.parent.mkdir(parents=True, exist_ok=True)
        #     candidate_path.touch(exist_ok=True)

        if len(candidates) > 1:
            logger.debug(f"[dim green]Multiple candidate paths generated for movie: {m.title}[/]")

        matches = [c for c in candidates if c in existing_directories.directories]
        if matches:
            console.print(
                f"[blue]Found matching existing directories for movie: {m.title}: {[str(m) for m in matches]}[/]"
            )
            if len(matches) > 1:
                console.print(
                    f"[yellow]Multiple matches found for movie: {m.title}; using first match[/]"
                )
            original_path = m.path
            assert original_path is not None, "Original path should not be None"
            m.path = original_path.parent / matches[0]
            if not dry_run:
                try:
                    if m.path == original_path:
                        console.print(
                            f"[dim yellow]Movie path for {m.title} is already correct; skipping update[/]"
                        )
                        if not force_refresh:
                            skipped.append((m, "Path already correct"))
                            continue
                    else:
                        _update_response = update_movie(movie=m)
                except RequestException as e:
                    console.print(f"[red]Failed to update movie: {m.title}; error: {e}[/]")
                    # request_body = m.model_dump_json(
                    #     indent=2, exclude_unset=True, exclude_none=True, by_alias=True
                    # )
                    # # request_body = m
                    # console.print(request_body)
                    skipped.append((m, f"Failed to update: {e}"))
                    continue

            fixed.append(m.id)
        else:
            reason = "No matching directory"
            best_match = get_best_match(m.path, existing_directories.directories, candidates)
            if best_match:
                match best_match.normalized_score:
                    case 100:
                        console.print(f"[green]Normalized 100 match found for movie: {m.title}[/]")
                        print_match_explanation(
                            m.path,
                            best_match,
                            candidates,
                            [
                                key
                                for key, directory in existing_directories.directories.items()
                                if directory.path == best_match.path
                            ],
                        )
                        reason = "Non-exact yet perfect match."
                    case score if score >= 75:
                        console.print(f"[yellow]Good match found for movie: {m.title}[/]")
                        reason = "Good match found."
                    case _:
                        console.print(f"[red]Poor match found for movie: {m.title}[/]")
                        reason = "Poor match found."
                console.print(
                    f"[blue]Best match for movie: {m.title}: {best_match.path!s}; score: {best_match.normalized_score}[/]"
                )
            else:
                console.print(
                    f"[red]No matching existing directories found for movie: {m.title} \\[{m.path}][/]"
                )
                console.print(
                    f"Generated candidate paths for movie: {m.title}: {[str(c) for c in candidates]}"
                )
            skipped.append((m, reason))

    if fixed:
        console.print(f"[green]Successfully fixed paths for {len(fixed)} movies.[/]")
        fixed_table = Table(title=f"Fixed Movies \\[{len(fixed)}]")
        fixed_table.add_column("ID", style="magenta")
        fixed_table.add_column("Title", style="cyan")
        fixed_table.add_column("New Path", style="green")
        for m in sorted(all_wanted, key=lambda x: x.sort_title or x.title or ""):
            if m.id in fixed:
                fixed_table.add_row(str(m.id), m.title, str(m.path))
        console.print(fixed_table)

        if not dry_run:
            _refresh_response = refresh_movies(movie_ids=fixed)
            task_id = int(_refresh_response.json()["id"])  # pyright: ignore[reportAny]
            console.print(f"[magenta]Triggered refresh task with ID: {task_id}[/]")
        else:
            console.print("[dim]Dry run enabled; not rescanning movies.[/]")

    if skipped:
        table = Table(title=f"Skipped Movies \\[{len(skipped)}]")
        table.add_column("Title", style="cyan")
        table.add_column("Reason", style="yellow")
        table.add_column("Path", style="magenta")
        for movie, reason in skipped:
            table.add_row(movie.title, reason, str(movie.path))
        console.print(table)


if __name__ == "__main__":
    app()
