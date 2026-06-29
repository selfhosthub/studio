# workers/engines/comfyui_remote/comfyui_init.py

"""ComfyUI REST client and templates for the remote worker. No server lifecycle."""

from engines.comfyui.client import ComfyUIClient
from engines.comfyui.templates import (
    load_workflow_template,
    inject_parameters,
    AVAILABLE_WORKFLOWS,
)

__all__ = [
    "ComfyUIClient",
    "load_workflow_template",
    "inject_parameters",
    "AVAILABLE_WORKFLOWS",
]
