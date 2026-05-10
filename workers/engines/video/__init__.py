# workers/engines/video/__init__.py

"""Video processing for the shs-video provider."""

from .create_video import create_video
from .merge_video_audio import merge_video_audio, burn_subtitles_only
from .utils import (
    CONFIGURED_ENCODER,
    get_quality_settings,
    generate_random_filename,
    calculate_scale_up_dimensions,
    scale_down_dimensions_for_cropping,
    scale_down_dimensions_padding,
    calculate_pad_position,
    build_ffmpeg_quality_args,
    build_concat_ffmpeg_args,
    ensure_even_dimensions,
    get_encode_args,
    get_encode_codec_only,
)
from .normalize import (
    normalize_params,
    has_audio_tracks,
    has_video_clips,
    get_total_duration,
)
from .common import (
    create_http_client,
    download_file,
    get_url_extension,
    get_ffmpeg_log_level,
    run_ffmpeg,
    get_media_duration,
    extract_audio_for_transcription,
    burn_subtitles,
    concatenate_videos,
    TempFileManager,
    temp_file_context,
)

__all__ = [
    "create_video",
    "merge_video_audio",
    "burn_subtitles_only",
    "normalize_params",
    "has_audio_tracks",
    "has_video_clips",
    "get_total_duration",
    "CONFIGURED_ENCODER",
    "get_quality_settings",
    "generate_random_filename",
    "calculate_scale_up_dimensions",
    "scale_down_dimensions_for_cropping",
    "scale_down_dimensions_padding",
    "calculate_pad_position",
    "build_ffmpeg_quality_args",
    "build_concat_ffmpeg_args",
    "ensure_even_dimensions",
    "get_encode_args",
    "get_encode_codec_only",
    "create_http_client",
    "download_file",
    "get_url_extension",
    "get_ffmpeg_log_level",
    "run_ffmpeg",
    "get_media_duration",
    "extract_audio_for_transcription",
    "burn_subtitles",
    "concatenate_videos",
    "TempFileManager",
    "temp_file_context",
]
