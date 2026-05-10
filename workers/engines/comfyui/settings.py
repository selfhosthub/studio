# workers/engines/comfyui/settings.py

"""ComfyUI-engine settings. Imported by both engines/comfyui and engines/comfyui_remote."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.env_files import resolve_env_files

_ENVS_DIR = Path(__file__).resolve().parents[2] / "envs"
_ENV_FILES = resolve_env_files(_ENVS_DIR)


class ComfyUISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SHS_",
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    COMFYUI_CLIENT_TIMEOUT_S: float = 300
    COMFYUI_EXTERNAL_URL: str | None = None
    COMFYUI_HEALTH_POLL_INTERVAL_S: float = 2
    COMFYUI_JOB_TIMEOUT_S: int = 600
    COMFYUI_OUTPUT_DIR: str | None = None  # handler falls back to $WORKSPACE_ROOT/data/comfyui_output
    COMFYUI_PATH: str = "/app/ComfyUI"
    COMFYUI_POLL_INTERVAL_S: float = 5
    COMFYUI_RESTART_PAUSE_S: int = 2
    COMFYUI_RETRY_INTERVAL_S: float = 10
    COMFYUI_STARTUP_TIMEOUT_S: int = 120
    COMFYUI_STOP_TIMEOUT_S: int = 10
    COMFYUI_URL: str = ""


settings = ComfyUISettings()
