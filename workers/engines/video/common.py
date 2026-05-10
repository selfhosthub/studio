# workers/engines/video/common.py

"""Shared video/audio utilities reusable across worker types."""

import os
import subprocess
import tempfile
import logging
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import httpx

from shared.settings import settings
from engines.video.settings import settings as video_settings

logger = logging.getLogger(__name__)


def create_http_client(
    timeout: float = settings.HTTP_VIDEO_DOWNLOAD_TIMEOUT_S,
) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True)


def translate_url_for_docker(url: str) -> str:
    """Rewrite localhost URLs to host.docker.internal so worker containers can reach host API."""
    import re

    # Worker runs in Docker where localhost = the container itself; host.docker.internal
    # resolves to the host machine where the API actually listens.
    pattern = r"^(https?://)(?:localhost|127\.0\.0\.1)(:\d+)?(/.*)?$"
    match = re.match(pattern, url)

    if match:
        scheme = match.group(1)
        port = match.group(2) or ""
        path = match.group(3) or ""
        translated = f"{scheme}host.docker.internal{port}{path}"
        logger.debug(f"Translated URL for Docker: {url} -> {translated}")
        return translated

    return url


def translate_to_internal_endpoint(url: str) -> tuple:
    """Public file URLs (JWT) -> internal endpoint (worker secret).

    Returns (translated_url, is_internal). is_internal=True means add the worker auth header.
    """
    import re

    pattern = r"^(.*)/api/v1/files/([a-f0-9-]+)/download(.*)$"
    match = re.match(pattern, url, re.IGNORECASE)

    if match:
        base = match.group(1)
        file_id = match.group(2)
        suffix = match.group(3)
        internal_url = f"{base}/api/v1/internal/files/{file_id}/download{suffix}"
        logger.debug(f"Translated to internal endpoint: {url} -> {internal_url}")
        return internal_url, True

    return url, False


MAX_DOWNLOAD_SIZE_MB = settings.MAX_DOWNLOAD_SIZE_MB


def download_file(client: httpx.Client, url: str, path: str) -> None:
    """Download URL to path with a size limit."""
    from shared.utils.security import validate_url_scheme

    # SSRF check before translation - localhost/127.0.0.1 get translated, not blocked.
    if url.startswith("http"):
        validate_url_scheme(url)

    translated_url = translate_url_for_docker(url)
    translated_url, needs_worker_auth = translate_to_internal_endpoint(translated_url)

    headers = {}
    if needs_worker_auth:
        worker_secret = settings.WORKER_SHARED_SECRET
        if worker_secret:
            headers["X-Worker-Secret"] = worker_secret
            logger.debug("Adding worker auth header for internal file download")
        else:
            logger.warning(
                "WORKER_SHARED_SECRET not set - internal file download may fail"
            )

    max_bytes = MAX_DOWNLOAD_SIZE_MB * 1024 * 1024
    downloaded = 0

    with client.stream("GET", translated_url, headers=headers) as response:
        response.raise_for_status()
        with open(path, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=settings.HTTP_CHUNK_SIZE):
                downloaded += len(chunk)
                if downloaded > max_bytes:
                    raise ValueError(
                        f"Download exceeds size limit ({MAX_DOWNLOAD_SIZE_MB}MB): {url}"
                    )
                f.write(chunk)

    from shared.utils.redaction import redact_url

    logger.debug(f"Downloaded {redact_url(url)} -> {path} ({downloaded} bytes)")


def get_url_extension(url: str, default: str = ".mp4") -> str:
    clean = url.split("?")[0]
    ext = os.path.splitext(clean)[1]
    return ext if ext else default


def get_ffmpeg_log_level() -> str:
    return video_settings.FFMPEG_LOGGING_LEVEL.lower()


FFMPEG_TIMEOUT = video_settings.FFMPEG_TIMEOUT_SECONDS


def run_ffmpeg(
    cmd: List[str], description: str = "FFmpeg", timeout: Optional[int] = None
) -> subprocess.CompletedProcess:
    """Run an FFmpeg command with timeout; raises RuntimeError on failure."""
    logger.debug(f"Running {description}: {' '.join(cmd)}")
    effective_timeout = timeout or FFMPEG_TIMEOUT

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=effective_timeout
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{description} timed out after {effective_timeout}s")

    if result.returncode != 0:
        logger.error(f"{description} error: {result.stderr}")
        raise RuntimeError(f"{description} failed: {result.stderr[:500]}")

    return result


def get_media_duration(path: str) -> float:
    """Media duration in seconds via ffprobe; raises RuntimeError on failure."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=settings.FFPROBE_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"ffprobe timed out after {settings.FFPROBE_TIMEOUT_S}s for: {path}"
        )

    if result.returncode != 0:
        logger.warning(f"ffprobe failed for {path}: {result.stderr.strip()}")
        raise RuntimeError(f"ffprobe failed (rc={result.returncode}): {path}")

    try:
        return float(result.stdout.strip())
    except ValueError:
        logger.warning(
            f"ffprobe returned unparseable duration for {path}: {result.stdout.strip()!r}"
        )
        raise RuntimeError(f"ffprobe returned unparseable duration for: {path}")


def extract_audio_for_transcription(
    input_path: str,
    output_path: str,
    sample_rate: int = 16000,
) -> None:
    """Extract audio as WAV file suitable for Whisper transcription."""
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        get_ffmpeg_log_level(),
        "-i",
        input_path,
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        output_path,
    ]
    run_ffmpeg(cmd, "Audio extraction")
    logger.debug(f"Extracted audio: {input_path} -> {output_path}")


def burn_subtitles(
    video_path: str,
    ass_path: str,
    output_path: str,
    quality: str = "medium",
) -> None:
    """Burn ASS subtitles into video using the detected hardware encoder."""
    from .utils import get_encode_args, _COMMON_COLOR_ARGS, _COMMON_OUTPUT_ARGS

    escaped_ass = ass_path.replace("\\", "\\\\").replace(":", "\\:")
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        get_ffmpeg_log_level(),
        "-i",
        video_path,
        "-vf",
        f"ass={escaped_ass}",
    ]
    cmd += get_encode_args(quality)
    cmd += _COMMON_COLOR_ARGS
    cmd += _COMMON_OUTPUT_ARGS
    cmd += ["-c:a", "copy", output_path]
    run_ffmpeg(cmd, "Subtitle burn")
    logger.debug(f"Burned subtitles into {output_path}")


def concatenate_videos(
    video_paths: List[str],
    output_path: str,
    temp_dir: str,
    reencode: bool = True,
    output_width: Optional[int] = None,
    output_height: Optional[int] = None,
    quality_settings: Optional[Dict[str, Any]] = None,
    quality: str = "medium",
) -> None:
    """
    Concatenate multiple videos into one.

    Uses the auto-detected hardware encoder for re-encode paths.
    """
    from .utils import get_encode_args, _COMMON_COLOR_ARGS, _COMMON_OUTPUT_ARGS

    # Create concat file
    concat_file = os.path.join(temp_dir, "concat_list.txt")
    with open(concat_file, "w") as f:
        for video_path in video_paths:
            f.write(f"file '{os.path.abspath(video_path)}'\n")

    if reencode:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-loglevel",
            get_ffmpeg_log_level(),
            "-safe",
            "0",
            "-i",
            concat_file,
        ]
        cmd += get_encode_args(quality)
        cmd += _COMMON_COLOR_ARGS
        cmd += _COMMON_OUTPUT_ARGS
        if output_width and output_height:
            cmd += [
                "-s",
                f"{output_width}x{output_height}",
                "-aspect",
                f"{output_width}:{output_height}",
            ]
        cmd += [output_path]
    else:
        # Stream copy
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            get_ffmpeg_log_level(),
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file,
            "-c",
            "copy",
            output_path,
        ]

    run_ffmpeg(cmd, "Video concatenation")

    try:
        os.remove(concat_file)
    except OSError:
        # Narrowed from Exception: only filesystem errors expected from os.remove()
        pass

    logger.debug(f"Concatenated {len(video_paths)} videos -> {output_path}")


# ==============================================================================
# Temporary File Management
# ==============================================================================


class TempFileManager:
    """Manages temporary files with automatic cleanup."""

    def __init__(self, cache_dir: Optional[str] = None, prefix: str = "shs_"):
        if cache_dir:
            self.cache_dir = cache_dir
            self._owns_dir = False
        else:
            self.cache_dir = tempfile.mkdtemp(prefix=prefix)
            self._owns_dir = True

        os.makedirs(self.cache_dir, exist_ok=True)
        self._files: List[str] = []
        self._protected: List[str] = []

    def create_path(self, filename: str) -> str:
        """Create a path for a temp file."""
        path = os.path.join(self.cache_dir, filename)
        self._files.append(path)
        return path

    def track(self, path: str) -> str:
        """Track an existing file for cleanup."""
        self._files.append(path)
        return path

    def protect(self, path: str) -> str:
        """Mark a file as protected (will not be deleted on cleanup)."""
        self._protected.append(path)
        return path

    def cleanup(self) -> None:
        """Remove all tracked files except protected ones."""
        for path in self._files:
            if path in self._protected:
                continue
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"Cleaned up: {path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {path}: {e}")

        if self._owns_dir and os.path.exists(self.cache_dir):
            try:
                os.rmdir(self.cache_dir)
            except OSError:
                # Narrowed from Exception: only filesystem errors expected from os.rmdir()
                pass

    def __enter__(self) -> "TempFileManager":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()


@contextmanager
def temp_file_context(cache_dir: Optional[str] = None, prefix: str = "shs_"):
    manager = TempFileManager(cache_dir=cache_dir, prefix=prefix)
    try:
        yield manager
    finally:
        manager.cleanup()
