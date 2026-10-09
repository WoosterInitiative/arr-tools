"""Project level core functionality that doesn't fit into a more specific module."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from os import PathLike

from attrmagic import ClassBase
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel
from typer import Context

from .logging_config import get_logger, set_log_level

logger = get_logger(__name__)

# A type alias for inputs that can be either a string or a PathLike object representing a filesystem path. This is used for type annotations in functions that accept file paths, allowing for flexibility in the types of path inputs while maintaining type safety.
type PathInput = PathLike[str] | str


@dataclass
class GlobalCLIOptions:
    verbosity: int
    dry_run: bool = False

    def __post_init__(self) -> None:
        set_log_level(self.verbosity)


class ProjectContext(Context):
    """Custom Typer Context that adds the proper typing for `obj`."""

    obj: GlobalCLIOptions


type Headers = Mapping[str, str | bytes]


class ApiBase(ClassBase):
    model_config: ConfigDict = ConfigDict(  # pyright: ignore[reportIncompatibleVariableOverride]
        from_attributes=True, alias_generator=to_camel, extra="allow"
    )


type _ParamsMappingValueType = (
    str | bytes | int | float | Iterable[str | bytes | int | float] | None
)

type ParamsType = dict[str, _ParamsMappingValueType]

type JsonValue = bool | int | float | str | Sequence["JsonValue"] | Mapping[str, "JsonValue"] | None
type JsonType = dict[str, JsonValue]
