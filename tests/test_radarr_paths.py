import json
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import pytest
from pydantic import TypeAdapter
from typer.testing import CliRunner

from arr_tools.radarr.fix_paths import (
    app,
    clean_path,
    compare_path,
    get_best_match,
    literal_path_differences,
)
from arr_tools.radarr.models import (
    Directories,
    Directory,
    FileSystemResource,
    MediaCover,
    MovieFileResource,
    MovieResource,
)

if TYPE_CHECKING:
    from arr_tools.core import ApiBase


@pytest.mark.parametrize(
    ("model_type", "field_name"),
    [
        (MediaCover, "url"),
        (MediaCover, "remote_url"),
        (MovieFileResource, "relative_path"),
        (MovieFileResource, "path"),
        (MovieFileResource, "original_file_path"),
        (MovieResource, "path"),
        (Directory, "path"),
        (FileSystemResource, "parent"),
    ],
)
@pytest.mark.parametrize("path", ["/data/movies/Example (2026)", "Example/movie.mkv"])
def test_api_paths_use_posix_semantics_and_json(
    model_type: type[ApiBase], field_name: str, path: str
) -> None:
    adapter: TypeAdapter[PurePosixPath | None] = TypeAdapter(
        model_type.model_fields[field_name].annotation  # pyright: ignore[reportArgumentType]
    )
    value = adapter.validate_python(path)
    resource = model_type.model_construct(**{field_name: value})  # pyright: ignore[reportArgumentType]

    assert isinstance(value, PurePosixPath)
    assert str(value) == path
    assert resource.model_dump(mode="json", exclude_unset=True)[field_name] == path
    assert json.loads(resource.model_dump_json(exclude_unset=True))[field_name] == path


def test_nested_filesystem_paths_round_trip() -> None:
    payload = {
        "parent": "/data/movies",
        "directories": {
            "Example": {
                "type": "directory",
                "name": "Example",
                "path": "/data/movies/Example",
                "size": 0,
                "lastModified": "2026-10-08T00:00:00",
            }
        },
    }
    resource = FileSystemResource.model_validate(payload)

    assert resource.parent.is_absolute()
    assert resource.model_dump(mode="json", by_alias=True) == payload
    assert json.loads(resource.model_dump_json(by_alias=True)) == payload


def test_clean_path_candidates_keep_posix_semantics() -> None:
    path = PurePosixPath("/data/movies/Example, Movie (2026) [tt1234567]")
    candidates = clean_path(path)

    assert candidates == {
        PurePosixPath("Example, Movie (2026)"),
        PurePosixPath("Example Movie (2026)"),
    }
    assert all(isinstance(candidate, PurePosixPath) for candidate in candidates)
    assert str(path.parent / PurePosixPath("Example Movie (2026)")) == (
        "/data/movies/Example Movie (2026)"
    )


def test_compare_path_exposes_dotted_folder_truncation() -> None:
    path = PurePosixPath("/data/movies/Guardians of the Galaxy Vol. 2 (2017)")
    result = compare_path(path, path, clean_path(path))

    assert result.raw_score == 100
    assert result.normalized_score == 100
    assert result.candidate_score < 100
    assert result.best_candidate.name == "Guardians of the Galaxy Vol"
    assert not result.exact_match


def test_compare_path_distinguishes_name_and_full_path_matches() -> None:
    query = PurePosixPath("/data/movies/Example (2026)")
    path = PurePosixPath("/other/Example (2026)")
    result = compare_path(query, path, clean_path(query))

    assert result.candidate_score == 100
    assert not result.exact_match
    assert result.year_status == "same"


@pytest.mark.parametrize(
    ("query", "path", "year_status"),
    [
        ("Bill & Ted's Adventure (1989) [tt12345]", "bill and teds adventure (1989)", "same"),
        ("Example (2026)", "Example (2025)", "DIFFERENT"),
        ("Example", "Example (2026)", "missing"),
    ],
)
def test_compare_path_reports_normalization_and_years(
    query: str, path: str, year_status: str
) -> None:
    query_path = PurePosixPath(query)
    result = compare_path(query_path, PurePosixPath(path), clean_path(query_path))

    assert result.year_status == year_status
    if year_status == "same":
        assert result.normalized_score == 100
        assert result.raw_score < 100
        assert not result.exact_match


def test_compare_paths_cli_direct_comparison() -> None:
    result = CliRunner().invoke(
        app,
        ["compare-paths", "Example (2026)", "Example (2026)"],
    )

    assert result.exit_code == 0, result.output
    assert "100.0" in result.output
    assert "yes" in result.output


def test_compare_paths_cli_local_directory(tmp_path: Path) -> None:
    (tmp_path / "Example (2026)").mkdir()
    (tmp_path / "Not a movie.txt").touch()
    result = CliRunner().invoke(
        app,
        ["compare-paths", "Example (2026)", "--directory", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "1 scanned" in result.output
    assert "Not a movie" not in result.output


def test_compare_paths_cli_requires_title_and_year_together() -> None:
    result = CliRunner().invoke(app, ["compare-paths", "Example", "Example", "--title", "Example"])

    assert result.exit_code == 2
    assert "together" in result.output


@pytest.mark.parametrize(
    ("left", "right", "detail"),
    [
        ("/data/Example (2026)", "/other/Example (2026)", "folder name equal: True"),
        ("Example (2026)", "example (2026)", "U+0045 LATIN CAPITAL LETTER E"),
        ("Example (2026)", "Example\u00a0(2026)", "U+00A0 NO-BREAK SPACE"),
        ("Ted's (2026)", "Ted\u2019s (2026)", "U+2019 RIGHT SINGLE QUOTATION MARK"),
    ],
)
def test_literal_path_differences_expose_invisible_and_parent_differences(
    left: str, right: str, detail: str
) -> None:
    output = "\n".join(literal_path_differences(PurePosixPath(left), PurePosixPath(right)))

    assert detail in output
    assert ascii(left) in output
    assert ascii(right) in output


def test_literal_path_differences_identical_paths() -> None:
    path = PurePosixPath("Example (2026)")
    assert literal_path_differences(path, path) == ["Full paths are literally identical."]


def test_compare_paths_explain_shows_candidate_truncation() -> None:
    path = "/data/movies/Guardians of the Galaxy Vol. 2 (2017)"
    result = CliRunner().invoke(app, ["compare-paths", path, path, "--explain"])

    assert result.exit_code == 0, result.output
    assert "Full paths are literally identical." in result.output
    assert "Candidate versus existing" in result.output
    assert "U+002E FULL STOP" in result.output


def test_compare_paths_explain_shows_dictionary_key_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filesystem = FileSystemResource.model_validate(
        {
            "parent": "/data/movies",
            "directories": {
                "Example": {
                    "type": "directory",
                    "name": "Example (2026)",
                    "path": "/data/movies/Example (2026)",
                    "size": 0,
                    "lastModified": "2026-10-08T00:00:00",
                }
            },
        }
    )
    monkeypatch.setattr("arr_tools.radarr.fix_paths.get_filesystem", lambda **kwargs: filesystem)
    result = CliRunner().invoke(app, ["compare-paths", "/data/movies/Example (2026)", "--explain"])

    assert result.exit_code == 0, result.output
    assert "Full paths are literally identical." in result.output
    assert "Candidate matches a lookup key: False" in result.output
    assert "Lookup key versus Directory.path: 'Example'" in result.output


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Guardians of the Galaxy Vol. 2 (2017)", "Guardians of the Galaxy Vol. 2 (2017)"),
        ("Bill & Ted's Adventure (1989) [tt12345]", "bill and teds adventure (1989)"),
    ],
)
def test_get_best_match_ranks_directory_paths_after_strict_match_fails(
    query: str, expected: str
) -> None:
    filesystem = FileSystemResource.model_validate(
        {
            "parent": "/data/movies",
            "directories": {
                label: {
                    "type": "directory",
                    "name": name,
                    "path": f"/data/movies/{name}",
                    "size": 0,
                    "lastModified": "2026-10-08T00:00:00",
                }
                for label, name in [("unrelated-key", "Unrelated (2020)"), ("match-key", expected)]
            },
        }
    )
    query_path = PurePosixPath("/data/movies") / query
    candidates = clean_path(query_path)

    assert not any(candidate in filesystem.directories for candidate in candidates)
    result = get_best_match(query_path, filesystem.directories)

    assert result is not None
    assert result.path == PurePosixPath("/data/movies") / expected
    assert result.normalized_score == 100
    assert result == compare_path(query_path, result.path, candidates)


def test_get_best_match_with_no_directories_returns_none() -> None:
    assert get_best_match(PurePosixPath("Example (2026)"), Directories.empty()) is None


def test_get_best_match_uses_supplied_movie_candidates() -> None:
    path = PurePosixPath("/data/movies/Example (2026)")
    directories = Directories.model_validate(
        {
            "Example": {
                "type": "directory",
                "name": path.name,
                "path": str(path),
                "size": 0,
                "lastModified": "2026-10-08T00:00:00",
            }
        }
    )
    result = get_best_match(PurePosixPath("Old name (2026)"), directories, {path})

    assert result is not None
    assert result.exact_match
    assert result.best_candidate == path
