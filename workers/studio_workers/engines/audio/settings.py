# workers/studio_workers/engines/audio/settings.py

"""Audio-engine settings. Imported only by audio worker code."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from studio_workers.env_files import resolve_env_files

_ENVS_DIR = Path(__file__).resolve().parents[3] / "envs"
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

    AUDIO_OUTPUT_DIR: str | None = None  # handler falls back to $WORKSPACE_ROOT/data/audio_output

    # Seconds a loaded Chatterbox model may sit idle before it is unloaded and its VRAM
    # released. 0 = never evict (the default: behaviour is unchanged unless you ask for it).
    #
    # The model is lazy-loaded on the first job and then cached forever, so a worker that
    # ran one TTS job an hour ago is still holding its VRAM. Nothing reclaims it: CUDA does
    # not arbitrate between processes, so ComfyUI on the same GPU cannot take that memory
    # back -- it can only drop into a slower low-VRAM mode to work around it.
    #
    # The cost of evicting is a cold reload (~10s) on the first job after an idle period.
    # Worth it when TTS runs in bursts and the GPU is shared; not worth it on a box that
    # does nothing else.
    AUDIO_MODEL_IDLE_SECONDS: int = 0


settings = AudioSettings()
