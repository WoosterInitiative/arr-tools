"""
Centralized application settings.

Uses pydantic-settings to load environment variables and .env file.
Controls things like DEBUG mode and logging defaults.

Additional settings can be added as needed.
"""

import logging
from functools import cache
from pathlib import PurePosixPath

from pydantic import AnyUrl, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RadarrSettings(BaseModel):
    host: AnyUrl
    api_key: SecretStr
    internal_root: PurePosixPath
    local_root: PurePosixPath


class Settings(BaseSettings):
    model_config: SettingsConfigDict = SettingsConfigDict(  # pyright: ignore[reportIncompatibleVariableOverride]
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="ARR_TOOLS_",
        extra="ignore",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
    )

    radarr: RadarrSettings = Field(default_factory=RadarrSettings)  # pyright: ignore[reportArgumentType, reportUnknownVariableType]

    debug: bool = False
    log_level: str | None = None

    @property
    def default_log_level(self) -> int:
        if self.debug:
            return logging.DEBUG
        return logging.INFO


@cache
def get_settings() -> Settings:
    return Settings()
