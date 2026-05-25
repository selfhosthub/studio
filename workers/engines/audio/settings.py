# workers/engines/audio/settings.py

"""Audio-engine settings. Imported only by audio worker code."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.env_files import resolve_env_files

_ENVS_DIR = Path(__file__).resolve().parents[2] / "envs"
_ENV_FILES = resolve_env_files(_ENVS_DIR)


class AudioSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SHS_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    AUDIO_TTS_CFG_WEIGHT: float = 0.5
    AUDIO_TTS_EXAGGERATION: float = 0.5


settings = AudioSettings()
