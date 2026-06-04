# workers/engines/video/settings.py

"""Video-engine settings. Imported only by video worker code."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.env_files import resolve_env_files

_ENVS_DIR = Path(__file__).resolve().parents[2] / "envs"
_ENV_FILES = resolve_env_files(_ENVS_DIR)


class VideoSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SHS_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    DEFAULT_SCENE_DURATION_S: int = 5
    DEFAULT_SMOOTHNESS: int = 3
    FFMPEG_ENCODER: str = "libx264"
    FFMPEG_LOGGING_LEVEL: str = "warning"
    FFMPEG_TIMEOUT_SECONDS: int = 1800
    VIDEO_CACHE_DIR: str | None = None
    VIDEO_CACHE_MAX_MB: int = 1000
    WHISPER_MODEL: str = "base"


settings = VideoSettings()
