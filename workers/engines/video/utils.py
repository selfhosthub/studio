# workers/engines/video/utils.py

"""Video Processing Utilities"""

import random
import string
import subprocess
import logging
from typing import Dict, Any, Tuple, List, Optional

from shared.settings import settings
from engines.video.settings import settings as video_settings

logger = logging.getLogger(__name__)


# ==============================================================================
# Encoder Detection
# ==============================================================================


def _encoder_works(name: str) -> bool:
    """Test if an encoder actually works by encoding a single frame.

    Checking ffmpeg -encoders only proves the encoder was compiled in,
    not that the hardware is present (e.g. h264_nvenc listed but no
    NVIDIA GPU). A test encode is definitive.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=black:s=16x16:d=0.04:r=25",
                "-frames:v",
                "1",
                "-c:v",
                name,
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=settings.SUBPROCESS_TIMEOUT_S,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _verify_configured_encoder() -> str:
    """Verify the configured encoder works; logs a warning if not.

    Never substitutes - the operator-configured value is always returned.
    """
    configured = video_settings.FFMPEG_ENCODER
    logger.info(f"FFmpeg encoder: {configured}")
    if not _encoder_works(configured):
        logger.warning(
            f"SHS_FFMPEG_ENCODER={configured} does not work on this machine. "
            f"Jobs will fail until you fix this. Install/repair ffmpeg or "
            f"set SHS_FFMPEG_ENCODER to a working encoder (libx264 is a "
            f"safe CPU baseline)."
        )
    return configured


CONFIGURED_ENCODER = _verify_configured_encoder()


# ==============================================================================
# Encoder-specific quality presets
# ==============================================================================

ENCODER_QUALITY_PRESETS = {
    "libx264": {
        "low": {
            "crf": 23,
            "preset": "ultrafast",
            "threads": 0,
            "bf": 1,
            "subme": 2,
            "me": "dia",
            "ref": 1,
        },
        "medium": {
            "crf": 20,
            "preset": "fast",
            "threads": 0,
            "bf": 2,
            "subme": 6,
            "me": "hex",
            "ref": 2,
        },
        "high": {
            "crf": 18,
            "preset": "medium",
            "threads": 0,
            "bf": 3,
            "subme": 7,
            "me": "hex",
            "ref": 3,
        },
    },
    "h264_nvenc": {
        "low": {"cq": 23, "preset": "p1"},
        "medium": {"cq": 20, "preset": "p4", "tune": "hq", "spatial_aq": 1},
        "high": {
            "cq": 18,
            "preset": "p5",
            "tune": "hq",
            "spatial_aq": 1,
            "b_ref_mode": "middle",
        },
    },
    "h264_videotoolbox": {
        "low": {"q_v": 55},
        "medium": {"q_v": 65},
        "high": {"q_v": 75, "allow_sw": 0},
    },
}

# Back-compat alias.
QUALITY_PRESETS = ENCODER_QUALITY_PRESETS["libx264"]

# Shared colorspace and output args
_COMMON_COLOR_ARGS = [
    "-pix_fmt",
    "yuv420p",
    "-colorspace",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_primaries",
    "bt709",
]

_COMMON_OUTPUT_ARGS = ["-movflags", "+faststart"]


# ==============================================================================
# Encoder argument builders
# ==============================================================================


def _build_encoder_args(encoder: str, settings: Dict[str, Any]) -> List[str]:
    """Build encoder-specific codec + quality args (no color/size args)."""
    args = ["-c:v", encoder]

    if encoder == "libx264":
        args += ["-crf", str(settings["crf"]), "-preset", settings["preset"]]
        if "threads" in settings:
            args += ["-threads", str(settings["threads"])]
        if "bf" in settings:
            args += ["-bf", str(settings["bf"])]
        if "subme" in settings:
            args += ["-subq", str(settings["subme"])]
        if "me" in settings:
            args += ["-me_method", settings["me"]]
        if "ref" in settings:
            args += ["-refs", str(settings["ref"])]

    elif encoder == "h264_nvenc":
        args += ["-cq", str(settings["cq"]), "-preset", settings["preset"]]
        if "tune" in settings:
            args += ["-tune", settings["tune"]]
        if "spatial_aq" in settings:
            args += ["-spatial_aq", str(settings["spatial_aq"])]
        if "b_ref_mode" in settings:
            args += ["-b_ref_mode", settings["b_ref_mode"]]

    elif encoder == "h264_videotoolbox":
        args += ["-q:v", str(settings["q_v"])]
        if "allow_sw" in settings:
            args += ["-allow_sw", str(settings["allow_sw"])]

    else:
        # Unknown encoder - just set codec, let ffmpeg use defaults
        pass

    return args


def get_encode_args(quality: str = "medium") -> List[str]:
    """
    Get full encoder + quality args for the detected encoder.

    Returns args like: ["-c:v", "h264_nvenc", "-cq", "20", "-preset", "p4", ...]
    Does NOT include color, size, or movflags args.
    """
    encoder = CONFIGURED_ENCODER
    presets = ENCODER_QUALITY_PRESETS.get(encoder, ENCODER_QUALITY_PRESETS["libx264"])
    settings = presets.get(quality.lower(), presets["medium"])
    return _build_encoder_args(encoder, settings)


def get_encode_codec_only() -> List[str]:
    """
    Get minimal codec args for the detected encoder (re-encode cases).

    Returns e.g. ["h264_nvenc", "-preset", "p4"] or ["libx264", "-preset", "fast"].
    Used where the caller already has "-c:v" in the command.
    """
    encoder = CONFIGURED_ENCODER
    presets = ENCODER_QUALITY_PRESETS.get(encoder, ENCODER_QUALITY_PRESETS["libx264"])
    settings = presets["medium"]

    if encoder == "libx264":
        return [encoder, "-preset", settings["preset"]]
    elif encoder == "h264_nvenc":
        return [encoder, "-preset", settings["preset"]]
    elif encoder == "h264_videotoolbox":
        return [encoder]
    else:
        return [encoder]


def get_quality_settings(
    quality: str = "medium", encoder: Optional[str] = None
) -> Dict[str, Any]:
    """Get FFmpeg quality settings for the specified quality level and encoder."""
    enc = encoder or CONFIGURED_ENCODER
    presets = ENCODER_QUALITY_PRESETS.get(enc, ENCODER_QUALITY_PRESETS["libx264"])
    return presets.get(quality.lower(), presets["medium"])


def generate_random_filename(length: int = 12, extension: str = ".mp4") -> str:
    chars = string.ascii_letters + string.digits
    name = "".join(random.choice(chars) for _ in range(length))
    return f"{name}{extension}"


def calculate_scale_up_dimensions(
    input_width: int,
    input_height: int,
    output_width: int,
    output_height: int,
    smoothness: float = 1,
) -> Tuple[float, float]:
    """
    Calculate dimensions for scaling up an image prior to resizing.

    Ensures scaled-up dimensions are larger than output dimensions for
    high-quality downscaling. Maintains input aspect ratio.
    """
    largest_dimension = max(input_width, input_height, output_width, output_height)
    scale_factor = max(largest_dimension * 2, largest_dimension * smoothness)

    if input_width > input_height:
        scale_up_width = scale_factor
        scale_up_height = scale_up_width / input_width * input_height
    else:
        scale_up_height = scale_factor
        scale_up_width = scale_up_height / input_height * input_width

    # Ensure both dimensions are larger than output dimensions
    scale_up_width = max(scale_up_width, output_width * 1.01)
    scale_up_height = max(scale_up_height, output_height * 1.01)

    # Maintain aspect ratio
    if scale_up_width / input_width > scale_up_height / input_height:
        scale_up_height = scale_up_width / input_width * input_height
    else:
        scale_up_width = scale_up_height / input_height * input_width

    return scale_up_width, scale_up_height


def scale_down_dimensions_for_cropping(
    input_width: int,
    input_height: int,
    output_width: int,
    output_height: int,
    scale_up_width: float,
    scale_up_height: float,
) -> Tuple[int, int]:
    """
    Determine dimensions for scaling when cropping (cover mode) is enabled.

    For cover mode, the scaled image must be >= output in BOTH dimensions,
    then we crop to fit. We use the LARGER scale factor to ensure coverage.
    """
    # Calculate scale factors needed to cover each output dimension
    scale_for_width = output_width / input_width
    scale_for_height = output_height / input_height

    # For cover mode, use the LARGER scale factor to ensure both dimensions are covered
    scale_factor = max(scale_for_width, scale_for_height)

    scale_down_width = int(input_width * scale_factor)
    scale_down_height = int(input_height * scale_factor)

    # Ensure dimensions are at least as large as output (rounding protection)
    scale_down_width = max(scale_down_width, output_width)
    scale_down_height = max(scale_down_height, output_height)

    return scale_down_width, scale_down_height


def scale_down_dimensions_padding(
    input_width: int,
    input_height: int,
    output_width: int,
    output_height: int,
) -> Tuple[int, int]:
    """
    Determine dimensions for scaling down when padding is enabled.

    Maintains input aspect ratio while fitting within output dimensions.
    """
    input_aspect_ratio = input_width / input_height

    if input_width / input_height > output_width / output_height:
        # Input is wider relative to its height than the output
        scale_down_width = output_width
        scale_down_height = int(output_width / input_aspect_ratio)
    else:
        # Input is taller relative to its width than the output
        scale_down_height = output_height
        scale_down_width = int(output_height * input_aspect_ratio)

    return scale_down_width, scale_down_height


def calculate_pad_position(
    horizontal_position: str,
    vertical_position: str,
    output_width: int,
    output_height: int,
    scale_down_width: int,
    scale_down_height: int,
) -> Tuple[int, int]:
    """Calculate pad x/y positions based on alignment settings."""
    # Vertical position
    if vertical_position == "top":
        pad_y = 0
    elif vertical_position == "middle_top":
        pad_y = max(0, (output_height - scale_down_height) / 4)
    elif vertical_position == "middle":
        pad_y = max(0, (output_height - scale_down_height) / 2)
    elif vertical_position == "middle_bottom":
        pad_y = max(0, 3 * (output_height - scale_down_height) / 4)
    elif vertical_position == "bottom":
        pad_y = max(0, output_height - scale_down_height)
    else:
        pad_y = max(0, (output_height - scale_down_height) / 2)

    # Horizontal position
    if horizontal_position == "left":
        pad_x = 0
    elif horizontal_position == "center_left":
        pad_x = max(0, (output_width - scale_down_width) / 4)
    elif horizontal_position == "center":
        pad_x = max(0, (output_width - scale_down_width) / 2)
    elif horizontal_position == "center_right":
        pad_x = max(0, 3 * (output_width - scale_down_width) / 4)
    elif horizontal_position == "right":
        pad_x = max(0, output_width - scale_down_width)
    else:
        pad_x = max(0, (output_width - scale_down_width) / 2)

    return int(pad_x), int(pad_y)


def build_ffmpeg_quality_args(
    quality: str,
    output_width: int,
    output_height: int,
) -> List[str]:
    """Build FFmpeg quality and output arguments for the detected encoder."""
    args = get_encode_args(quality)
    args += _COMMON_COLOR_ARGS
    args += ["-color_range", "pc"]
    args += _COMMON_OUTPUT_ARGS
    args += [
        "-s",
        f"{output_width}x{output_height}",
        "-aspect",
        f"{output_width}:{output_height}",
    ]
    return args


def build_concat_ffmpeg_args(
    quality: str,
    output_width: int,
    output_height: int,
) -> List[str]:
    """Build FFmpeg arguments for concatenation using the detected encoder."""
    args = get_encode_args(quality)
    args += _COMMON_COLOR_ARGS
    args += _COMMON_OUTPUT_ARGS
    args += [
        "-s",
        f"{output_width}x{output_height}",
        "-aspect",
        f"{output_width}:{output_height}",
    ]
    return args


def ensure_even_dimensions(width: int, height: int) -> Tuple[int, int]:
    """Ensure dimensions are even (required for some codecs)."""
    return width - (width % 2), height - (height % 2)
