# workers/engines/video/handler.py


import os
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx

from shared.utils import WorkerBase, create_job_client
from shared.utils.file_upload_client import FileUploadClient
from shared.utils.result_publisher import ResultPublisher
from shared.settings import settings
from shared.worker_types import get_worker_config

from engines.video.settings import settings as video_settings
from engines.video import (
    create_video,
    merge_video_audio,
    burn_subtitles_only,
    normalize_params,
    has_audio_tracks,
    concatenate_videos,
)
from engines.video.normalize import _extract_subtitles
from shared.utils.redaction import redact_url
from contracts.group_expansion import expand_group, AUTO_DURATION_PADDING_S

logger = logging.getLogger(__name__)


class VideoWorker(WorkerBase):

    OPERATIONS = {
        "shs_create_video": create_video,
    }

    def __init__(self, worker_type: str = "video"):
        config = get_worker_config(worker_type)

        super().__init__(
            worker_type=config.type_id,
            queue_labels=config.queue_labels,
            capabilities=config.capabilities,
        )

        self.queue_name = config.queue_name

        # Job client initialized after registration so we have real worker_id from the API.
        self.job_client = None
        self.result_publisher = ResultPublisher(token_getter=self.get_token)
        self._file_upload_client = FileUploadClient(token_getter=self.get_token)

        cache_dir = video_settings.VIDEO_CACHE_DIR
        if not cache_dir:
            cache_dir = os.path.join(settings.WORKSPACE_ROOT, "data", "video_cache")
        self.cache_dir: str = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.max_cache_mb = video_settings.VIDEO_CACHE_MAX_MB

    def process_jobs(self):
        logger.info(f"{self.worker_type.upper()} Worker Started")
        logger.info(f"Monitoring queue: {self.queue_name}")
        logger.debug(f"Cache directory: {self.cache_dir}")
        logger.debug(f"Operations: {', '.join(self.OPERATIONS.keys())}")

        self.job_client = create_job_client(
            worker_id=self.worker_id or self.worker_name,
            token_getter=self.get_token,
        )

        if self.worker_token:
            logger.debug(f"Using JWT auth (worker_id: {self.worker_id})")
        elif self.worker_id:
            logger.debug(f"Using registered worker_id: {self.worker_id} (legacy mode)")
        else:
            logger.warning(
                "Not registered - job claims may fail. Waiting for registration..."
            )

        try:
            while self.running:
                job = self.job_client.claim_job(
                    self.queue_name, timeout=settings.JOB_CLAIM_TIMEOUT_S
                )

                if job is None:
                    sleep_duration = self.job_client.get_sleep_duration()
                    if sleep_duration > 0:
                        time.sleep(sleep_duration)
                    continue

                self._process_job(job)

        finally:
            self.job_client.close()
            self.result_publisher.close()

    def _process_job(self, job: Dict[str, Any]):
        job_id = job.get("job_id", "unknown")
        step_id = job.get("step_id", job_id)

        service_id = job.get("service_id", "")
        if "." in service_id:
            operation = service_id.split(".")[-1]
        else:
            operation = job.get("operation", "unknown")

        step_config = job.get("step_config") or {}
        job_config = step_config.get("job") or {}
        parameters = job_config.get("parameters") or step_config.get("parameters") or {}

        logger.info(f"Processing Video Job: {job_id}")
        logger.debug(f"Operation: {operation}")

        if job.get("notify_api", True):
            self.result_publisher.publish_step_result(status="PROCESSING")
            logger.debug("Published PROCESSING status")

        job_cache_dir = os.path.join(self.cache_dir, job_id)

        # set_busy must receive queued_jobs.id - workers.current_job_id FKs
        # to it, so instance_id trips a FK violation on busy heartbeats.
        self.set_busy(job_id)
        job_start_time = time.time()
        try:
            if operation not in self.OPERATIONS:
                raise ValueError(
                    f"Unknown operation: {operation}. "
                    f"Valid operations: {', '.join(self.OPERATIONS.keys())}"
                )

            parameters["cache_dir"] = job_cache_dir

            scenes = parameters.get("scenes", [])
            has_item_groups = any(
                isinstance(s, dict) and s.get("type") == "item_group" for s in scenes
            )
            if operation == "shs_create_video" and has_item_groups:
                result = self._process_composable_timeline(parameters, job)
            else:
                result = self._process_standard(parameters, operation)

            output_path = result.get("output_path")
            if output_path and os.path.exists(output_path):
                storage_url = self._upload_to_storage(
                    local_path=output_path,
                    step_id=step_id,
                    job_id=job_id,
                )
                result["storage_url"] = storage_url

                file_size = os.path.getsize(output_path)
                stored_filename = os.path.basename(storage_url)
                result["downloaded_files"] = [
                    {
                        "filename": stored_filename,
                        "virtual_path": storage_url,
                        "file_size": file_size,
                        "display_name": f"Video Output ({result.get('duration', 0):.1f}s)",
                        "index": 0,
                    }
                ]

            if job.get("notify_api", True):
                if not self.result_publisher.publish_step_result(status="COMPLETED", result=result):
                    logger.critical(
                        "Failed to publish step result after retries - job will be orphaned",
                        extra={"job_id": job_id, "status": "COMPLETED"},
                    )

            webhook_url = job.get("webhook_url")
            if webhook_url:
                record_id = job.get("record_id", job_id)
                self._call_webhook(
                    webhook_url=webhook_url,
                    record_id=record_id,
                    output_url=result.get("storage_url"),
                    status="completed",
                    result=result,
                )

            duration_ms = int((time.time() - job_start_time) * 1000)
            logger.info(
                f"Video job {job_id} completed ({duration_ms}ms)",
                extra={
                    "job_id": job_id,
                    "step_id": step_id,
                    "operation": operation,
                    "duration_ms": duration_ms,
                },
            )

        except ValueError as e:
            error_msg = str(e)
            duration_ms = int((time.time() - job_start_time) * 1000)
            logger.error(
                f"Video job {job_id} failed (validation, {duration_ms}ms): {error_msg}",
                extra={"job_id": job_id, "duration_ms": duration_ms},
            )
            self._handle_failure(job, error_msg)

        except RuntimeError as e:
            error_msg = str(e)
            duration_ms = int((time.time() - job_start_time) * 1000)
            logger.error(
                f"Video job {job_id} failed (processing, {duration_ms}ms): {error_msg}",
                extra={"job_id": job_id, "duration_ms": duration_ms},
            )
            self._handle_failure(job, error_msg)

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.exception(f"Video job {job_id} failed: {error_msg}")
            self._handle_failure(job, error_msg)

        finally:
            self.set_idle()
            self._cleanup_cache(job_cache_dir)

    def _process_standard(
        self, parameters: Dict[str, Any], operation: str
    ) -> Dict[str, Any]:
        params = normalize_params(parameters)

        image_count = len(params.get("images", []))
        audio_count = len(params.get("audio_tracks", []))
        video_count = len(params.get("video_clips", []))
        logger.debug(
            f"Normalized: {image_count} images, {audio_count} audio, {video_count} video clips"
        )

        if image_count == 0 and video_count == 0 and operation == "shs_create_video":
            raise ValueError("No visual elements after normalization")

        if operation == "shs_create_video":
            result = self._render_visual(params)
        else:
            handler_fn = self.OPERATIONS[operation]
            logger.debug(f"Executing {operation}...")
            result = handler_fn(params)

        logger.debug(f"{operation} completed successfully")
        logger.debug(f"Output: {result.get('output_path', 'N/A')}")
        logger.debug(f"Duration: {result.get('duration', 0):.1f}s")

        # Post-processing: Merge audio tracks if present
        if operation == "shs_create_video" and has_audio_tracks(params):
            result = self._merge_audio_tracks(
                video_result=result,
                audio_tracks=params.get("audio_tracks", []),
                subtitles=params.get("subtitles"),
                cache_dir=params.get("cache_dir"),
            )
        # Post-processing: Burn subtitles if enabled but no audio
        elif operation == "shs_create_video" and not has_audio_tracks(params):
            subtitles = params.get("subtitles")
            if subtitles and subtitles.get("enabled"):
                result = self._burn_subtitles_only(
                    video_result=result,
                    subtitles=subtitles,
                    cache_dir=params.get("cache_dir"),
                )

        return result

    def _process_composable_timeline(
        self, parameters: Dict[str, Any], job: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process composable timeline: static scenes + item groups in order.

        Iterates through scenes array. Static scenes (type=scene) render as
        single clips. Item groups (type=item_group) expand via circular
        stacks into multiple clips. All clips are concatenated in timeline
        order (or output per-group if requested).
        """
        per_group = parameters.pop("output_per_group", False)
        scenes = parameters.get("scenes", [])

        # Extract movie-level subtitle config (defaults for all scenes)
        subtitles_config = {}
        for key in list(parameters.keys()):
            if key.startswith("subtitles_"):
                subtitles_config[key] = parameters[key]

        # Process timeline entries in order
        timeline_clips = []
        for scene_idx, scene in enumerate(scenes):
            scene_type = scene.get("type", "scene")

            if scene_type == "item_group":
                logger.debug(
                    f"Timeline[{scene_idx}]: item_group (repeat={scene.get('repeat', 1)})"
                )
                clips = self._render_item_group(scene, parameters, subtitles_config)
                timeline_clips.extend(clips)
            else:
                logger.debug(f"Timeline[{scene_idx}]: static scene")
                clip = self._render_static_scene(scene, parameters)
                timeline_clips.append(clip)

        logger.debug(f"Timeline complete: {len(timeline_clips)} clips")

        # Output
        if per_group:
            return self._build_per_group_output(timeline_clips, job)
        else:
            return self._concatenate_group_videos(
                timeline_clips, parameters.get("cache_dir")
            )

    def _render_static_scene(
        self, scene: Dict[str, Any], parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Render a static scene (type=scene) as a single clip."""
        # Build params with this single scene
        scene_params = {
            k: v
            for k, v in parameters.items()
            if k not in ("scenes", "output_per_group")
            and not k.startswith("subtitles_")
        }
        scene_params["scenes"] = [scene]

        # Normalize and render visual elements
        normalized = normalize_params(scene_params)
        video_result = self._render_visual(normalized)

        # If static scene has audio, merge it
        if has_audio_tracks(normalized):
            video_result = self._merge_audio_tracks(
                video_result=video_result,
                audio_tracks=normalized.get("audio_tracks", []),
                subtitles=None,
                cache_dir=normalized.get("cache_dir"),
                loop_video=False,
            )

        return video_result

    # -------------------------------------------------------------------------
    # Visual element rendering - registry-based dispatch
    #
    # Add a normalizer for new element types and a corresponding renderer method.
    # -------------------------------------------------------------------------

    # Maps normalized param key → renderer method name
    # Order matters: first match wins (images before video_clips)
    VISUAL_RENDERER_KEYS = ["images", "video_clips"]

    def _render_visual(self, normalized: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch to the correct renderer based on visual element type."""
        renderers = {
            "images": lambda params: create_video(params),
            "video_clips": lambda params: self._render_video_clip(
                params["video_clips"][0], params.get("cache_dir")
            ),
        }
        for key in self.VISUAL_RENDERER_KEYS:
            if normalized.get(key):
                logger.debug(f"Rendering visual type: {key}")
                return renderers[key](normalized)

        raise ValueError("No visual elements after normalization")

    def _render_video_clip(
        self, clip: Dict[str, Any], cache_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve a video clip to a local file and return as a result dict."""
        from engines.video.common import get_media_duration

        url = clip.get("url", "")
        if not url:
            raise ValueError("Video clip element has no URL")

        local_path = self._resolve_media_path(url, cache_dir, default_ext=".mp4")
        if not os.path.exists(local_path):
            raise ValueError(f"Video clip not found: {local_path}")

        try:
            duration = get_media_duration(local_path)
        except (RuntimeError, OSError) as e:
            logger.warning(f"Cannot probe video duration: {e}")
            duration = 0.0

        logger.debug(
            f"Video clip resolved: {redact_url(url)} → {local_path} ({duration:.1f}s)"
        )

        return {
            "success": True,
            "output_path": local_path,
            "duration": duration,
            "frame_count": 0,  # Not computed for passthrough clips
        }

    def _render_item_group(
        self,
        scene: Dict[str, Any],
        parameters: Dict[str, Any],
        movie_subtitles_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Expand one item_group spec into per-group clips via circular distribution and auto-duration."""
        default_dur = parameters.get(
            "default_duration", video_settings.DEFAULT_SCENE_DURATION_S
        )

        # Phases A+B via shared module: circular distribution + auto-duration
        assembled_scenes = expand_group(scene, default_duration=default_dur)

        # Build subtitle config: scene-level overrides merged with movie-level defaults
        merged_subtitles = self._merge_subtitle_config(scene, movie_subtitles_config)
        narration_texts = scene.get("subtitles_narration_texts", [])
        if isinstance(narration_texts, str):
            narration_texts = [narration_texts]

        group_clips = []

        for group_idx, assembled in enumerate(assembled_scenes):
            logger.debug(
                f"  Processing item_group iteration "
                f"{group_idx + 1}/{len(assembled_scenes)}"
            )

            group_elements = assembled.get("elements", [])
            image_elements = [e for e in group_elements if e.get("type") == "image"]
            audio_elements = [e for e in group_elements if e.get("type") == "audio"]

            # ffprobe fallback: if shared module couldn't resolve duration
            # (no pre-computed _duration), probe from audio file
            needs_probe = any(
                e.get("duration") == -1 or e.get("duration") is None
                for e in image_elements
            )
            if needs_probe and audio_elements and image_elements:
                audio_src = audio_elements[0].get("src", "")
                audio_duration = self._probe_audio_duration(
                    audio_src, parameters.get("cache_dir")
                )
                if audio_duration > 0:
                    per_image_dur = (audio_duration + AUTO_DURATION_PADDING_S) / len(
                        image_elements
                    )
                    for e in image_elements:
                        if e.get("duration") == -1 or e.get("duration") is None:
                            e["duration"] = per_image_dur
                    logger.debug(
                        f"    ffprobe fallback: {audio_duration:.2f}s / "
                        f"{len(image_elements)} images = "
                        f"{per_image_dur:.3f}s each"
                    )

            # Sub-scene split for FFmpeg: one scene per image, audio on first
            group_scenes = []
            for i, img_elem in enumerate(image_elements):
                scene_dict: Dict[str, Any] = {"elements": [img_elem]}
                if i == 0:
                    for ae in audio_elements:
                        scene_dict["elements"].append(ae)
                group_scenes.append(scene_dict)

            if not image_elements and audio_elements:
                group_scenes = [{"elements": audio_elements}]

            if not group_scenes:
                logger.warning(f"    Group {group_idx + 1} has no elements, skipping")
                continue

            group_params = {
                k: v
                for k, v in parameters.items()
                if k not in ("scenes", "output_per_group")
                and not k.startswith("subtitles_")
            }
            group_params["scenes"] = group_scenes

            normalized = normalize_params(group_params)
            video_result = self._render_visual(normalized)

            # Audio merge + subtitles
            group_subtitles = (
                _extract_subtitles(merged_subtitles) if merged_subtitles else None
            )

            if (
                group_subtitles
                and group_idx < len(narration_texts)
                and narration_texts[group_idx]
            ):
                group_subtitles["narration_text"] = narration_texts[group_idx]

            if has_audio_tracks(normalized):
                video_result = self._merge_audio_tracks(
                    video_result=video_result,
                    audio_tracks=normalized.get("audio_tracks", []),
                    subtitles=group_subtitles,
                    cache_dir=normalized.get("cache_dir"),
                    loop_video=True,
                )
            elif group_subtitles and group_subtitles.get("enabled"):
                sub_source = group_subtitles.get("source", "auto")
                if sub_source == "auto":
                    logger.debug(
                        f"    Skipping auto-subtitles for group "
                        f"{group_idx + 1} (no audio to transcribe)"
                    )
                else:
                    video_result = self._burn_subtitles_only(
                        video_result=video_result,
                        subtitles=group_subtitles,
                        cache_dir=normalized.get("cache_dir"),
                    )

            group_clips.append(video_result)
            logger.debug(
                f"    Group {group_idx + 1} complete: "
                f"{video_result.get('duration', 0):.1f}s"
            )

        return group_clips

    def _resolve_media_path(
        self, src: str, cache_dir: Optional[str], default_ext: str = ".mp3"
    ) -> str:
        """Resolve a media URL or virtual path to a local filesystem path.

        Handles three source types:
        - /orgs/... virtual paths → workspace filesystem
        - http(s) URLs → download to cache_dir
        - Anything else → treat as local path
        """
        from engines.video.common import download_file, create_http_client

        if src.startswith("/orgs/"):
            from shared.utils.security import validate_virtual_path

            return validate_virtual_path(src, settings.WORKSPACE_ROOT)

        if src.startswith("http"):
            ext = os.path.splitext(src.split("?")[0])[-1] or default_ext
            local_path = os.path.join(
                cache_dir or self.cache_dir, f"media_{uuid.uuid4().hex[:8]}{ext}"
            )
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            client = create_http_client(timeout=float(settings.HTTP_DOWNLOAD_TIMEOUT_S))
            try:
                download_file(client, src, local_path)
            finally:
                client.close()
            return local_path

        return src

    def _probe_audio_duration(self, audio_src: str, cache_dir: Optional[str]) -> float:
        """Probe duration of an audio file with ffprobe."""
        from engines.video.common import get_media_duration

        if not audio_src:
            return 0.0

        local_path = self._resolve_media_path(audio_src, cache_dir, default_ext=".mp3")

        if os.path.exists(local_path):
            try:
                duration = get_media_duration(local_path)
            except (RuntimeError, OSError) as e:
                logger.warning(f"Cannot probe audio duration: {e}")
                return 0.0
            logger.debug(
                f"Probed audio duration: {redact_url(audio_src)} → {duration:.2f}s"
            )
            return duration

        logger.warning(f"Cannot probe audio duration: {audio_src}")
        return 0.0

    def _merge_subtitle_config(
        self, scene: Dict[str, Any], movie_defaults: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge scene-level subtitle fields with movie-level defaults.

        Scene-level values override defaults. Empty string means 'use default'.
        Returns a merged dict of subtitles_* params (same format as movie-level).
        """
        merged = dict(movie_defaults)
        for key, val in scene.items():
            if key.startswith("subtitles_") and key != "subtitles_narration_texts":
                if val != "" and val is not None:
                    merged[key] = val
        return merged

    def _concatenate_group_videos(
        self,
        group_videos: List[Dict[str, Any]],
        cache_dir: Optional[str],
    ) -> Dict[str, Any]:
        """Concatenate per-group video files into a single video."""
        from engines.video.utils import generate_random_filename

        video_paths = [v["output_path"] for v in group_videos if v.get("output_path")]

        if len(video_paths) == 0:
            raise RuntimeError(
                "No video clips to concatenate - item_group produced 0 clips"
            )

        if len(video_paths) == 1:
            return group_videos[0]

        output_path = os.path.join(
            cache_dir or self.cache_dir, generate_random_filename()
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        logger.debug(f"Concatenating {len(video_paths)} group videos...")

        concatenate_videos(
            video_paths=video_paths,
            output_path=output_path,
            temp_dir=cache_dir or self.cache_dir,
            reencode=True,
        )

        from engines.video.common import get_media_duration

        duration = get_media_duration(output_path)

        # Derive from actual group clip results
        has_audio = any(v.get("has_audio") for v in group_videos)
        has_subtitles = any(v.get("has_subtitles") for v in group_videos)
        frame_count = sum(v.get("frame_count", 0) for v in group_videos)

        logger.debug(f"Concatenation complete: {output_path} ({duration:.1f}s)")

        return {
            "success": True,
            "output_path": output_path,
            "duration": duration,
            "frame_count": frame_count,
            "has_audio": has_audio,
            "has_subtitles": has_subtitles,
            "video_count": len(video_paths),
        }

    def _build_per_group_output(
        self,
        group_videos: List[Dict[str, Any]],
        job: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build downloaded_files array from per-group video results."""
        step_id = job.get("step_id", job.get("job_id", "unknown"))
        job_id: str = job.get("job_id", "unknown")

        downloaded_files = []
        total_duration = 0.0

        for i, video_result in enumerate(group_videos):
            output_path = video_result.get("output_path")
            if not output_path or not os.path.exists(output_path):
                continue

            duration = video_result.get("duration", 0)
            total_duration += duration
            file_size = os.path.getsize(output_path)

            storage_url = self._upload_to_storage(
                local_path=output_path,
                step_id=f"{step_id}_scene{i}",
                job_id=job_id,
            )

            stored_filename = os.path.basename(storage_url)
            downloaded_files.append(
                {
                    "filename": stored_filename,
                    "virtual_path": storage_url,
                    "file_size": file_size,
                    "index": i,
                    "display_name": f"Scene {i + 1} ({duration:.1f}s)",
                    "scene_index": i,
                    "duration": duration,
                }
            )

        return {
            "success": True,
            "downloaded_files": downloaded_files,
            "video_count": len(downloaded_files),
            "duration": total_duration,
            "has_audio": any(v.get("has_audio") for v in group_videos),
            "has_subtitles": any(v.get("has_subtitles") for v in group_videos),
        }

    def _handle_failure(self, job: Dict[str, Any], error_msg: str):
        """Handle job failure - write error and notify."""
        job_id = job.get("job_id", "unknown")

        if job.get("notify_api", True):
            if not self.result_publisher.publish_step_result(status="FAILED", error=error_msg):
                logger.critical(
                    "Failed to publish step result after retries - job will be orphaned",
                    extra={"job_id": job_id, "status": "FAILED"},
                )

        # Call external webhook on failure too
        webhook_url = job.get("webhook_url")
        if webhook_url:
            record_id = job.get("record_id", job_id)
            self._call_webhook(
                webhook_url=webhook_url,
                record_id=record_id,
                output_url=None,
                status="failed",
                error=error_msg,
            )

    def _upload_to_storage(
        self,
        local_path: str,
        step_id: str,
        job_id: str = "unknown",
    ) -> str:
        """Upload output file via the API upload endpoint; returns the storage URL."""
        ext = os.path.splitext(local_path)[1].lower()
        filename = f"{step_id}_output_{uuid.uuid4().hex[:8]}{ext}"
        url_path = self._file_upload_client.upload(local_path, filename=filename)
        logger.debug(f"Uploaded file to: {url_path}")
        return url_path

    def _call_webhook(
        self,
        webhook_url: str,
        record_id: str,
        output_url: Optional[str] = None,
        status: str = "completed",
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        """
        Call external webhook on job completion/failure.

        Compatible with old video API format for n8n/make.com nodes:
        - On success: {"id": record_id, "url": output_url, "status": "completed"}
        - On failure: {"id": record_id, "status": "failed", "error": "..."}
        """
        webhook_payload: Dict[str, Any] = {
            "id": record_id,
            "status": status,
        }

        if output_url:
            webhook_payload["url"] = output_url

        if error:
            webhook_payload["error"] = error

        # Include full result for callers that want more detail
        if result:
            webhook_payload["result"] = result

        try:
            logger.info(f"Calling webhook: {webhook_url}")
            with httpx.Client(timeout=float(settings.HTTP_WEBHOOK_TIMEOUT_S)) as client:
                response = client.post(webhook_url, json=webhook_payload)
                response.raise_for_status()
            logger.info("Webhook called successfully")
        except httpx.HTTPStatusError as e:
            logger.error(f"Webhook returned error status: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Webhook call failed: {e}")

    def _merge_audio_tracks(
        self,
        video_result: Dict[str, Any],
        audio_tracks: list,
        subtitles: Optional[Dict[str, Any]],
        cache_dir: Optional[str],
        loop_video: bool = False,
    ) -> Dict[str, Any]:
        """Merge audio tracks with created video.

        When loop_video=True, video loops to match audio length (audio never cut off).
        """
        if not audio_tracks:
            return video_result

        video_path = video_result.get("output_path")
        if not video_path or not os.path.exists(video_path):
            logger.warning("No video output to merge audio with")
            return video_result

        primary_audio = audio_tracks[0]
        audio_url = primary_audio.get("url")
        audio_volume = primary_audio.get("volume", 1.0)

        if not audio_url:
            logger.warning("Audio track missing URL, skipping merge")
            return video_result

        logger.debug(f"Merging audio track: {redact_url(audio_url)}")

        # Build merge parameters
        merge_params = {
            "video_path": video_path,  # Local file path (already on disk)
            "audio_url": audio_url,
            "audio_volume": audio_volume,
            "video_audio_volume": 0.0,  # Mute original (images have no audio)
            "cache_dir": cache_dir,
            "loop_video": loop_video,
        }

        # Add subtitles if enabled (pass full config to merge_video_audio)
        if subtitles and subtitles.get("enabled"):
            merge_params["subtitles"] = subtitles

        # Execute merge
        merge_result = merge_video_audio(merge_params)

        logger.debug("Audio merged successfully")
        if subtitles and subtitles.get("enabled"):
            logger.debug(f"Subtitles burned: {subtitles.get('style', 'standard')}")

        # Update result with merged output
        return {
            **video_result,
            "output_path": merge_result.get("output_path"),
            "duration": merge_result.get("duration", video_result.get("duration")),
            "has_audio": True,
            "has_subtitles": merge_result.get("has_subtitles", False),
        }

    def _burn_subtitles_only(
        self,
        video_result: Dict[str, Any],
        subtitles: Dict[str, Any],
        cache_dir: Optional[str],
    ) -> Dict[str, Any]:
        """Burn subtitles into video when there is no audio to merge."""
        video_path = video_result.get("output_path")
        if not video_path or not os.path.exists(video_path):
            logger.warning("No video output to burn subtitles into")
            return video_result

        logger.debug(
            f"Burning subtitles into video (source: {subtitles.get('source', 'auto')})"
        )

        # Build burn parameters
        burn_params = {
            "video_path": video_path,
            "cache_dir": cache_dir,
            "subtitles": subtitles,
        }

        # Execute subtitle burn
        burn_result = burn_subtitles_only(burn_params)

        logger.debug("Subtitles burned successfully")

        # Update result with subtitle output
        return {
            **video_result,
            "output_path": burn_result.get("output_path"),
            "duration": burn_result.get("duration", video_result.get("duration")),
            "has_subtitles": burn_result.get("has_subtitles", False),
        }

    def _summarize_request(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Summarize request parameters for debugging visibility.

        Shows scene/element structure without full payloads.
        """
        result = {}
        for k, v in parameters.items():
            if k == "cache_dir":
                continue  # Exclude internal fields
            elif k == "scenes" and isinstance(v, list):
                # Summarize scenes with element counts
                scenes_summary = []
                for i, scene in enumerate(v):
                    elements = scene.get("elements", [])
                    element_counts = {}
                    for el in elements:
                        el_type = el.get("type", "unknown")
                        element_counts[el_type] = element_counts.get(el_type, 0) + 1
                    scenes_summary.append(
                        {
                            "scene": i + 1,
                            "duration": scene.get("duration"),
                            "elements": element_counts,
                        }
                    )
                result["scenes"] = scenes_summary
            else:
                result[k] = v
        return result

    def _cleanup_cache(self, cache_dir: str):
        """
        Clean up temporary cache directory after job completion.

        Called after successful or failed job to prevent disk bloat.
        Also evicts oldest cache entries if total size exceeds limit.
        """
        import shutil

        if cache_dir and os.path.exists(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                logger.debug(f"Cleaned up cache: {cache_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup cache {cache_dir}: {e}")

        self._evict_cache_if_needed()

    def _evict_cache_if_needed(self):
        """Remove oldest cache subdirectories until total size is under the limit."""
        import shutil

        max_bytes = self.max_cache_mb * 1024 * 1024
        try:
            entries = []
            for entry in os.scandir(self.cache_dir):
                if entry.is_dir():
                    total = sum(
                        f.stat().st_size
                        for f in Path(entry.path).rglob("*")
                        if f.is_file()
                    )
                    entries.append((entry.path, entry.stat().st_mtime, total))

            total_size = sum(e[2] for e in entries)
            if total_size <= max_bytes:
                return

            # Sort oldest first
            entries.sort(key=lambda e: e[1])
            for path, _, size in entries:
                if total_size <= max_bytes:
                    break
                try:
                    shutil.rmtree(path)
                    total_size -= size
                    logger.debug(
                        f"Evicted cache dir: {os.path.basename(path)} (freed {size // 1024}KB)"
                    )
                except Exception as e:
                    logger.warning(f"Failed to evict {path}: {e}")
        except Exception as e:
            logger.warning(f"Cache eviction check failed: {e}")


def main():
    """Entry point for video worker."""
    worker = VideoWorker()
    worker.run()


if __name__ == "__main__":
    main()
