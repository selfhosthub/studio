# workers/studio_workers/engines/comfyui/__init__.py

"""ComfyUI REST client and manifest-driven workflow handling."""

from .client import ComfyUIClient

__all__ = [
    'ComfyUIClient',
]
