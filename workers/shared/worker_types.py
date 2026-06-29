# workers/shared/worker_types.py

"""
Standard Worker Types

Defines the official worker types supported by Studio.
Each worker type has specific capabilities and resource requirements.

Worker Types:
- general: Lightweight API workers - handles ALL service types not claimed by specialized workers
- image: GPU workers for AI image generation
- video: GPU workers for video processing (FFmpeg, frame extraction)

Service Type Routing:
- ServiceTypes are defined in studio (CORE, AI, DATA_TRANSFORMATION, etc.)
- Specialized workers (image, video) explicitly claim certain ServiceTypes
- General worker automatically handles everything else (catch-all)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Set

logger = logging.getLogger(__name__)


class ServiceType(str, Enum):
    """Service type categories (n8n-inspired) for organizing providers and routing jobs."""

    CORE = "core"  # Webhooks, set_fields, core utilities
    AI = "ai"  # Image gen, text gen, embeddings, etc.
    DATA_TRANSFORMATION = "data_transformation"  # Data transforms, parsing
    PRODUCTIVITY = "productivity"  # Airtable, Google Sheets, etc.
    COMMUNICATION = "communication"  # Email, SMS, Slack
    DEVELOPMENT = "development"  # Git, CI/CD, APIs
    STORAGE = "storage"  # S3, Google Drive, file storage
    SOCIAL_MEDIA = "social_media"  # YouTube, Instagram, TikTok


# Which ServiceTypes each specialized worker handles
# General worker handles everything NOT in these sets
SPECIALIZED_SERVICE_TYPES: Dict[str, Set[ServiceType]] = {
    "image": {
        ServiceType.AI,  # Image worker handles all AI services
    },
    "video": set(),  # Future: When we add video-specific categories
}


def get_general_service_types() -> Set[ServiceType]:
    """
    Compute which ServiceTypes the general worker handles.

    Returns all ServiceTypes NOT claimed by specialized workers.
    This is the "smart" part - general automatically gets everything else.
    """
    all_types = set(ServiceType)
    specialized_types: Set[ServiceType] = set()
    for types in SPECIALIZED_SERVICE_TYPES.values():
        specialized_types.update(types)
    return all_types - specialized_types


@dataclass
class WorkerTypeConfig:
    """Configuration for a standard worker type."""

    type_id: str
    display_name: str
    description: str
    queue_name: str
    queue_labels: List[str]
    capabilities: Dict[str, Any]
    service_types: Set[ServiceType] = field(
        default_factory=set
    )  # Which ServiceTypes this worker handles
    resource_requirements: Dict[str, Any] = field(default_factory=dict)


# Standard Worker Type Definitions
# Note: service_types is computed dynamically for "general" worker
WORKER_TYPES: Dict[str, WorkerTypeConfig] = {
    "general": WorkerTypeConfig(
        type_id="general",
        display_name="General Worker",
        description="Lightweight worker - handles ALL service types not claimed by specialized workers",
        queue_name="step_jobs",
        # NOTE: queue_labels MUST include queue_name for JWT authorization
        queue_labels=["step_jobs", "general", "step", "api", "http"],
        capabilities={
            "type": "general",
            "handles": ["step_jobs"],
            "gpu": False,
            "max_concurrent_jobs": 10,
        },
        # service_types computed dynamically via get_general_service_types()
        service_types=set(),  # Will be populated at runtime
        resource_requirements={
            "cpu": "0.5",
            "memory": "512Mi",
            "gpu": None,
        },
    ),
    "video": WorkerTypeConfig(
        type_id="video",
        display_name="Video Worker",
        description="GPU worker for video processing with Whisper STT (shs-video provider)",
        queue_name="video_jobs",
        # NOTE: queue_labels MUST include queue_name for JWT authorization
        queue_labels=["video_jobs", "video", "gpu", "ffmpeg", "whisper", "shs-video"],
        capabilities={
            "type": "video",
            "provider": "shs-video",
            "handles": ["video_jobs"],
            "gpu": True,
            "gpu_type": "cuda",  # For hardware-accelerated encoding + Whisper
            "max_concurrent_jobs": 2,
            "operations": [
                "shs_create_video",  # Scenes → video with effects, audio, subtitles
            ],
            "features": [
                "zoom_pan_effects",  # Ken Burns style zoom in/out
                "whisper_stt",  # Speech-to-text with Whisper
                "karaoke_subtitles",  # ASS subtitles with word highlighting
                "quality_presets",  # low/medium/high encoding
                "aspect_ratio",  # Crop or letterbox modes
            ],
        },
        service_types=SPECIALIZED_SERVICE_TYPES["video"],
        resource_requirements={
            "cpu": "4",
            "memory": "8Gi",
            "gpu": "1",
            "gpu_memory": "8Gi",  # Whisper needs GPU memory
        },
    ),
    "comfyui-image": WorkerTypeConfig(
        type_id="comfyui-image",
        display_name="ComfyUI Image Worker",
        description="GPU worker for image generation with ComfyUI (Flux, SDXL, SD1.5)",
        queue_name="comfyui_image_jobs",
        # NOTE: queue_labels MUST include queue_name for JWT authorization
        queue_labels=["comfyui_image_jobs", "comfyui", "gpu", "flux", "shs-comfyui"],
        capabilities={
            "type": "comfyui-image",
            "provider": "shs-comfyui",
            "handles": ["comfyui_image_jobs"],
            "gpu": True,
            "gpu_type": "cuda",
            "max_concurrent_jobs": 1,  # GPU-bound, single job at a time
            "operations": [
                "comfyui_txt2img",
            ],
            "features": [
                "text_to_image",
                "customizable_workflows",  # Workflows can be injected in job payload
            ],
        },
        service_types=set(),  # ComfyUI handles its own services
        resource_requirements={
            "cpu": "4",
            "memory": "16Gi",
            "gpu": "1",
            "gpu_memory": "24Gi",  # Flux needs substantial VRAM
        },
    ),
    "comfyui-image-edit": WorkerTypeConfig(
        type_id="comfyui-image-edit",
        display_name="ComfyUI Image Edit Worker",
        description="GPU worker for image editing with ComfyUI (Flux 2 Klein model)",
        queue_name="comfyui_image_edit_jobs",
        # NOTE: queue_labels MUST include queue_name for JWT authorization
        queue_labels=[
            "comfyui_image_edit_jobs",
            "comfyui",
            "gpu",
            "flux2",
            "shs-comfyui",
        ],
        capabilities={
            "type": "comfyui-image-edit",
            "provider": "shs-comfyui",
            "handles": ["comfyui_image_edit_jobs"],
            "gpu": True,
            "gpu_type": "cuda",
            "max_concurrent_jobs": 1,  # GPU-bound, single job at a time
            "operations": [
                "comfyui_imgedit",
            ],
            "features": [
                "image_to_image",
                "reference_latent",  # Uses reference image for edits
                "customizable_workflows",
            ],
        },
        service_types=set(),  # ComfyUI handles its own services
        resource_requirements={
            "cpu": "4",
            "memory": "16Gi",
            "gpu": "1",
            "gpu_memory": "12Gi",  # Flux 2 Klein is smaller than full Flux
        },
    ),
    "comfyui-video": WorkerTypeConfig(
        type_id="comfyui-video",
        display_name="ComfyUI Video Worker",
        description="GPU worker for video generation with ComfyUI (longer run times, larger models)",
        queue_name="comfyui_video_jobs",
        # NOTE: queue_labels MUST include queue_name for JWT authorization
        queue_labels=[
            "comfyui_video_jobs",
            "comfyui-video",
            "gpu",
            "shs-comfyui-video",
        ],
        capabilities={
            "type": "comfyui-video",
            "provider": "shs-comfyui-video",
            "handles": ["comfyui_video_jobs"],
            "gpu": True,
            "gpu_type": "cuda",
            "max_concurrent_jobs": 1,  # GPU-bound, single job at a time
            "operations": [
                # TBD: video workflows
            ],
            "features": [
                "image_to_video",
                "video_to_video",
                "customizable_workflows",  # Workflows can be injected in job payload
            ],
        },
        service_types=set(),  # ComfyUI handles its own services
        resource_requirements={
            "cpu": "4",
            "memory": "32Gi",
            "gpu": "1",
            "gpu_memory": "48Gi",  # Video models need more VRAM
        },
    ),
    "audio": WorkerTypeConfig(
        type_id="audio",
        display_name="Audio Worker",
        description="GPU worker for text-to-speech with Chatterbox TTS (shs-audio provider)",
        queue_name="audio_jobs",
        # NOTE: queue_labels MUST include queue_name for JWT authorization
        queue_labels=["audio_jobs", "audio", "gpu", "tts", "shs-audio"],
        capabilities={
            "type": "audio",
            "provider": "shs-audio",
            "handles": ["audio_jobs"],
            "gpu": True,
            "gpu_type": "cuda",  # Falls back to MPS/CPU automatically
            "max_concurrent_jobs": 2,
            "operations": [
                "tts",  # Standard Chatterbox TTS
                "tts_turbo",  # Turbo variant (350M params, paralinguistic tags)
            ],
            "features": [
                "text_to_speech",
                "voice_cloning",  # Clone voice from ~10s reference audio
                "paralinguistic_tags",  # [laugh], [chuckle], [cough] (turbo only)
            ],
        },
        service_types=set(),  # Audio has its own queue, not routed by ServiceType
        resource_requirements={
            "cpu": "2",
            "memory": "4Gi",
            "gpu": "1",
            "gpu_memory": "4Gi",  # Chatterbox is relatively lightweight
        },
    ),
    "comfyui-remote": WorkerTypeConfig(
        type_id="comfyui-remote",
        display_name="ComfyUI Remote Worker",
        description="Lightweight worker that calls external ComfyUI server (RunPod, cloud GPU, etc.)",
        queue_name="comfyui_image_jobs",  # Same queue as embedded - they're interchangeable
        # NOTE: queue_labels MUST include queue_name for JWT authorization
        queue_labels=["comfyui_image_jobs", "comfyui", "remote", "shs-comfyui"],
        capabilities={
            "type": "comfyui-remote",
            "provider": "shs-comfyui",
            "handles": ["comfyui_image_jobs"],
            "gpu": False,  # No GPU needed in container - GPU is on remote server
            "max_concurrent_jobs": 4,  # Can handle more since no local GPU constraint
            "operations": [
                "comfyui_txt2img",
            ],
            "features": [
                "text_to_image",
                "customizable_workflows",
                "remote_execution",  # Distinguishes from embedded
            ],
        },
        service_types=set(),  # ComfyUI handles its own services
        resource_requirements={
            "cpu": "0.5",
            "memory": "512Mi",
            "gpu": None,  # No GPU required
        },
    ),
    "transfer": WorkerTypeConfig(
        type_id="transfer",
        display_name="Transfer Worker",
        description="Lightweight worker for streaming file transfers (upload/download to external platforms)",
        queue_name="transfer_jobs",
        # NOTE: queue_labels MUST include queue_name for JWT authorization
        queue_labels=["transfer_jobs", "transfer", "upload", "download"],
        capabilities={
            "type": "transfer",
            "handles": ["transfer_jobs"],
            "gpu": False,
            "max_concurrent_jobs": 4,
            "operations": [
                "file_upload",  # Stream file as HTTP body
                "file_download",  # Download file from URL
            ],
            "features": [
                "chunked_streaming",  # Never loads full file into memory
                "response_headers",  # Captures response headers for downstream steps
                "extended_timeout",  # Configurable timeout for large transfers
                "progress_reporting",  # Logs upload progress
            ],
        },
        service_types=set(),  # Transfer has its own queue, not routed by ServiceType
        resource_requirements={
            "cpu": "0.5",
            "memory": "512Mi",
            "gpu": None,
        },
    ),
}


def get_worker_config(worker_type: str) -> WorkerTypeConfig:
    """Return config for a worker type; raises ValueError if unrecognized.

    For "general", service_types is computed dynamically to cover all types
    not claimed by specialized workers.
    """
    if worker_type not in WORKER_TYPES:
        valid_types = ", ".join(WORKER_TYPES.keys())
        raise ValueError(
            f"Unknown worker type: {worker_type}. Valid types: {valid_types}"
        )

    config = WORKER_TYPES[worker_type]

    # For general worker, compute service_types dynamically
    if worker_type == "general" and not config.service_types:
        config.service_types = get_general_service_types()

    return config


def get_capabilities_for_type(worker_type: str) -> Dict[str, Any]:
    """
    Get capabilities dict for a worker type (for API registration).

    Includes the service_types list for job routing.
    """
    config = get_worker_config(worker_type)
    capabilities = config.capabilities.copy()
    # Add service_types to capabilities for registration
    capabilities["service_types"] = [st.value for st in config.service_types]
    return capabilities


def get_queue_labels_for_type(worker_type: str) -> List[str]:
    """Get queue labels for a worker type (for API registration)."""
    config = get_worker_config(worker_type)
    return config.queue_labels


def get_queue_name_for_type(worker_type: str) -> str:
    config = get_worker_config(worker_type)
    return config.queue_name


def get_service_types_for_worker(worker_type: str) -> List[str]:
    """
    Get list of ServiceType values this worker handles.

    Returns lowercase string values (e.g., "image_generation", "text_generation").
    """
    config = get_worker_config(worker_type)
    return [st.value for st in config.service_types]


def get_worker_for_service_type(service_type: str) -> str:
    # Check specialized workers first
    for worker_type, service_types in SPECIALIZED_SERVICE_TYPES.items():
        if any(st.value == service_type for st in service_types):
            return worker_type

    # Default to general worker
    return "general"


def print_service_type_routing():
    logger.debug("Service Type to Worker Routing:")

    for worker_type in WORKER_TYPES.keys():
        config = get_worker_config(worker_type)
        service_types = get_service_types_for_worker(worker_type)
        if service_types:
            service_list = ", ".join(sorted(service_types))
            logger.debug(
                f"  {worker_type.upper()} worker ({config.queue_name}): {service_list}"
            )
        else:
            logger.debug(
                f"  {worker_type.upper()} worker ({config.queue_name}): (no service types assigned)"
            )


# Example usage when run directly
if __name__ == "__main__":
    print_service_type_routing()
