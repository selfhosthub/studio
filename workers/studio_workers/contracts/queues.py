# workers/studio_workers/contracts/queues.py

"""Registered job queues. The allowlist a comfyui package's service.queue
must name; shared by worker_types.py and the API's install-time validation."""

REGISTERED_QUEUES = frozenset(
    {
        "step_jobs",
        "video_jobs",
        "comfyui_image_jobs",
        "comfyui_image_edit_jobs",
        "comfyui_video_jobs",
        "audio_jobs",
        "transfer_jobs",
    }
)
