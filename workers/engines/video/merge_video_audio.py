# workers/engines/video/merge_video_audio.py

"""Merge video + audio with optional subtitle generation. Internal post-processing utility.

Subtitle pipeline runs Phase 1 → Phase 2 → Phase 3:
1. Merge video + audio streams (locks final timing).
2. Whisper transcribes the MERGED audio so timestamps match the final video.
3. Burn ASS subtitles into the merged video.

This order is required: loop_video, audio mixing, and -shortest all alter the
final timeline relative to the raw audio.
"""

import os
import logging
from typing import Dict, Any, Optional

from .common import (
    create_http_client,
    download_file,
    get_url_extension,
    get_ffmpeg_log_level,
    get_media_duration,
    extract_audio_for_transcription,
    burn_subtitles,
    run_ffmpeg,
    TempFileManager,
)
from .utils import generate_random_filename
from .subtitle_utils import (
    transcribe_audio,
    generate_ass_subtitles,
    generate_ass_from_captions,
    align_transcription_words,
    fetch_and_parse_subtitle_file,
    auto_time_text,
)

logger = logging.getLogger(__name__)


def merge_video_audio(params: Dict[str, Any]) -> Dict[str, Any]:
    """Merge video with audio track, optionally adding subtitles."""
    video_url = params.get("video_url")
    video_path = params.get("video_path")
    audio_url = params.get("audio_url")
    audio_path = params.get("audio_path")
    output_path = params.get("output_path")
    cache_dir = params.get("cache_dir")

    add_subtitles = params.get("subtitles", False)
    audio_volume = params.get("audio_volume", 1.0)
    video_audio_volume = params.get("video_audio_volume", 0.0)
    loop_video = params.get("loop_video", False)

    temp = TempFileManager(cache_dir=cache_dir, prefix="shs_merge_audio_")

    if not output_path:
        output_path = temp.create_path(generate_random_filename())

    temp.protect(output_path)

    logger.debug(f"Merging video with audio -> {output_path}")

    http_client = create_http_client()

    try:
        if video_url and not video_path:
            ext = get_url_extension(video_url, ".mp4")
            video_path = temp.create_path(f"input_video{ext}")
            download_file(http_client, video_url, video_path)

        # /orgs/... is a workspace virtual path - resolve to filesystem.
        if audio_url and audio_url.startswith("/orgs/") and not audio_path:
            from shared.settings import settings as _settings
            from shared.utils.security import validate_virtual_path

            resolved = validate_virtual_path(audio_url, _settings.WORKSPACE_ROOT)
            if os.path.exists(resolved):
                audio_path = resolved
                logger.debug(f"Resolved virtual audio path: {audio_url} → {audio_path}")

        if audio_url and not audio_path:
            ext = get_url_extension(audio_url, ".mp3")
            audio_path = temp.create_path(f"input_audio{ext}")
            download_file(http_client, audio_url, audio_path)

        if not video_path or not os.path.exists(video_path):
            raise ValueError("Video file not found")
        if not audio_path or not os.path.exists(audio_path):
            raise ValueError("Audio file not found")

        merged_path = output_path
        if add_subtitles:
            # Merge to temp first; subtitles burn from the merged file in step 3.
            merged_path = temp.create_path("merged_temp.mp4")

        _merge_streams(
            video_path=video_path,
            audio_path=audio_path,
            output_path=merged_path,
            audio_volume=audio_volume,
            video_audio_volume=video_audio_volume,
            loop_video=loop_video,
        )

        if add_subtitles:
            ass_path = _process_subtitles(
                params=params,
                video_path=merged_path,
                temp=temp,
            )

            if ass_path:
                burn_subtitles(merged_path, ass_path, output_path)

        duration = get_media_duration(output_path)

        logger.debug(f"Merge complete: {output_path} ({duration:.1f}s)")

        return {
            "success": True,
            "output_path": output_path,
            "duration": duration,
            "has_subtitles": add_subtitles,
        }

    finally:
        http_client.close()
        temp.cleanup()


def _merge_streams(
    video_path: str,
    audio_path: str,
    output_path: str,
    audio_volume: float = 1.0,
    video_audio_volume: float = 0.0,
    loop_video: bool = False,
) -> None:
    """Merge video and audio streams with volume control.

    loop_video uses -stream_loop -1 + an explicit -t at audio duration so the
    merged file has no silent video tail (would shift subtitles when concatenated).
    -stream_loop is incompatible with -c:v copy, so the video is re-encoded.
    """

    from .utils import get_encode_codec_only

    video_codec = get_encode_codec_only() if loop_video else ["copy"]

    # Explicit -t is more reliable than -shortest, which overshoots by ~2s
    # due to encoder buffering.
    audio_duration = None
    if loop_video:
        try:
            audio_duration = get_media_duration(audio_path)
        except (RuntimeError, OSError) as e:
            logger.warning(f"Cannot probe audio duration for loop cap: {e}")

    if video_audio_volume > 0:
        # Mix original video audio with the new audio track.
        filter_complex = (
            f"[0:a]volume={video_audio_volume}[va];"
            f"[1:a]volume={audio_volume}[aa];"
            f"[va][aa]amix=inputs=2:duration=shortest[a]"
        )
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            get_ffmpeg_log_level(),
        ]
        if loop_video:
            ffmpeg_cmd += ["-stream_loop", "-1"]
        ffmpeg_cmd += (
            [
                "-i",
                video_path,
                "-i",
                audio_path,
                "-filter_complex",
                filter_complex,
                "-map",
                "0:v",
                "-map",
                "[a]",
                "-c:v",
            ]
            + video_codec
            + [
                "-c:a",
                "aac",
            ]
        )
        if audio_duration:
            ffmpeg_cmd += ["-t", str(audio_duration)]
        else:
            ffmpeg_cmd += ["-shortest"]
        ffmpeg_cmd += [output_path]
    else:
        # Replace audio entirely.
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            get_ffmpeg_log_level(),
        ]
        if loop_video:
            ffmpeg_cmd += ["-stream_loop", "-1"]
        ffmpeg_cmd += (
            [
                "-i",
                video_path,
                "-i",
                audio_path,
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-c:v",
            ]
            + video_codec
            + [
                "-c:a",
                "aac",
            ]
        )
        if audio_duration:
            ffmpeg_cmd += ["-t", str(audio_duration)]
        else:
            ffmpeg_cmd += ["-shortest"]
        ffmpeg_cmd += [output_path]

        if audio_volume != 1.0:
            idx = ffmpeg_cmd.index("-c:a")
            ffmpeg_cmd.insert(idx, f"volume={audio_volume}")
            ffmpeg_cmd.insert(idx, "-af")

    run_ffmpeg(ffmpeg_cmd, "Audio merge")


def _process_subtitles(
    params: Dict[str, Any],
    video_path: str,
    temp: TempFileManager,
) -> Optional[str]:
    """Dispatch to the right subtitle source handler; returns path to .ass or None.

    Sources: auto (Whisper + karaoke), captions (manual array), src (SRT/VTT URL),
    text (plain text auto-timed to video duration).
    """
    sub_config = params.get("subtitles", {})
    if isinstance(sub_config, dict):
        source = sub_config.get("source", "auto")
    else:
        # Legacy boolean - treat as auto.
        source = "auto"

    # Flat-param fallback.
    if not source or source == "":
        source = params.get("subtitles_source", "auto")

    ass_path = temp.create_path("subtitles.ass")

    def get_param(key: str, default: Any) -> Any:
        flat_val = params.get(key)
        if flat_val is not None:
            return flat_val
        if isinstance(sub_config, dict):
            return sub_config.get(key, default)
        return default

    style_params = {
        "all_caps": get_param("all_caps", False),
        "font_size": get_param("font_size", 24),
        "font_family": get_param("font_family", "Luckiest Guy"),
        "font_color": get_param("font_color", "FFFFFF"),
        "highlight_color": get_param("highlight_color", "FFFF00"),
        "outline_color": get_param("outline_color", "000000"),
        "outline_width": get_param("outline_width", 2),
        "shadow_offset": get_param("shadow_offset", 1),
        "background_color": get_param("background_color", ""),
        "position": get_param("position", "bottom"),
        "edge_padding": get_param("edge_padding", 20),
        "max_words_per_phrase": get_param("max_words_per_phrase", 5),
    }

    logger.debug(f"Processing subtitles with source: {source}")

    if source == "auto":
        return _process_subtitles_auto(params, video_path, ass_path, style_params, temp)

    elif source == "captions":
        return _process_subtitles_captions(params, sub_config, ass_path, style_params)

    elif source == "src":
        return _process_subtitles_src(params, sub_config, ass_path, style_params)

    elif source == "text":
        return _process_subtitles_text(
            params, sub_config, video_path, ass_path, style_params
        )

    else:
        logger.warning(f"Unknown subtitle source: {source}")
        return None


def _process_subtitles_auto(
    params: Dict[str, Any],
    video_path: str,
    ass_path: str,
    style_params: Dict[str, Any],
    temp: TempFileManager,
) -> str:
    """Whisper auto-transcription with karaoke highlighting."""
    logger.debug("Generating subtitles via Whisper transcription...")

    # 16kHz mono WAV is what Whisper expects.
    wav_path = temp.create_path("audio_for_stt.wav")
    extract_audio_for_transcription(video_path, wav_path)

    sub_config = params.get("subtitles", {})
    language = params.get(
        "language",
        sub_config.get("language", "en") if isinstance(sub_config, dict) else "en",
    )

    transcription = transcribe_audio(
        audio_path=wav_path,
        language=language,
        model_name=sub_config.get("model") or "small",
    )

    # Forced alignment overrides Whisper words with known-correct narration text.
    narration_text = (
        sub_config.get("narration_text", "") if isinstance(sub_config, dict) else ""
    )
    if narration_text:
        logger.debug("Applying forced alignment with narration text")
        transcription = align_transcription_words(transcription, narration_text)

    generate_ass_subtitles(
        transcription=transcription,
        output_path=ass_path,
        params=style_params,
    )

    return ass_path


def _process_subtitles_captions(
    params: Dict[str, Any],
    sub_config: Dict[str, Any],
    ass_path: str,
    style_params: Dict[str, Any],
) -> Optional[str]:
    """Manual captions array."""
    logger.debug("Generating subtitles from manual captions...")

    captions = params.get("captions", [])
    if not captions and isinstance(sub_config, dict):
        captions = sub_config.get("captions", [])

    if not captions:
        logger.warning("No captions provided for source=captions")
        return None

    generate_ass_from_captions(
        captions=captions,
        output_path=ass_path,
        params=style_params,
    )

    return ass_path


def _process_subtitles_src(
    params: Dict[str, Any],
    sub_config: Dict[str, Any],
    ass_path: str,
    style_params: Dict[str, Any],
) -> Optional[str]:
    """External SRT/VTT file URL."""
    logger.debug("Generating subtitles from external file...")

    src_url = params.get("src", "")
    if not src_url and isinstance(sub_config, dict):
        src_url = sub_config.get("src", "")

    if not src_url:
        logger.warning("No src URL provided for source=src")
        return None

    try:
        captions = fetch_and_parse_subtitle_file(src_url)

        if not captions:
            logger.warning(f"No captions parsed from: {src_url}")
            return None

        generate_ass_from_captions(
            captions=captions,
            output_path=ass_path,
            params=style_params,
        )

        return ass_path

    except Exception as e:
        logger.error(f"Failed to process subtitle file: {e}")
        return None


def _process_subtitles_text(
    params: Dict[str, Any],
    sub_config: Dict[str, Any],
    video_path: str,
    ass_path: str,
    style_params: Dict[str, Any],
) -> Optional[str]:
    """Plain text auto-timed across video duration."""
    logger.debug("Generating subtitles from plain text...")

    text = params.get("text", "")
    if not text and isinstance(sub_config, dict):
        text = sub_config.get("text", "")

    if not text:
        logger.warning("No text provided for source=text")
        return None

    try:
        duration = get_media_duration(video_path)
    except (RuntimeError, OSError) as e:
        logger.warning(f"Could not determine video duration for text timing: {e}")
        return None

    if duration <= 0:
        logger.warning("Video duration is 0 - cannot time text subtitles")
        return None

    max_words = (
        sub_config.get("max_words_per_phrase", 5) if isinstance(sub_config, dict) else 5
    )
    captions = auto_time_text(text, duration, words_per_caption=int(max_words))

    if not captions:
        logger.warning("No captions generated from text")
        return None

    generate_ass_from_captions(
        captions=captions,
        output_path=ass_path,
        params=style_params,
    )

    return ass_path


def burn_subtitles_only(params: Dict[str, Any]) -> Dict[str, Any]:
    """Burn subtitles into a video file with no audio merge."""
    video_path = params.get("video_path")
    output_path = params.get("output_path")
    cache_dir = params.get("cache_dir")

    if not video_path or not os.path.exists(video_path):
        raise ValueError("Video file not found for subtitle burning")

    temp = TempFileManager(cache_dir=cache_dir, prefix="shs_burn_subs_")

    if not output_path:
        output_path = temp.create_path(generate_random_filename())

    temp.protect(output_path)

    logger.debug(f"Burning subtitles into video -> {output_path}")

    try:
        ass_path = _process_subtitles(
            params=params,
            video_path=video_path,
            temp=temp,
        )

        if not ass_path:
            logger.warning("No subtitles generated, copying video as-is")
            import shutil

            shutil.copy2(video_path, output_path)
        else:
            burn_subtitles(video_path, ass_path, output_path)

        duration = get_media_duration(output_path)

        logger.debug(f"Subtitle burn complete: {output_path} ({duration:.1f}s)")

        return {
            "success": True,
            "output_path": output_path,
            "duration": duration,
            "has_subtitles": bool(ass_path),
        }

    finally:
        temp.cleanup()
