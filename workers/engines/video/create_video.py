# workers/engines/video/create_video.py

"""
Create Video from Images

Creates video from array of images with zoom/pan effects.

Features:
- Zoom in/out effects (Ken Burns style)
- Position control (horizontal/vertical)
- Crop or letterbox modes
- Quality presets
- Per-image parameter overrides
"""

import math
import os
import shutil
import logging
from typing import Dict, Any, List, Optional
import httpx
from PIL import Image

from .common import (
    create_http_client,
    download_file,
    get_url_extension,
    get_ffmpeg_log_level,
    run_ffmpeg,
    get_media_duration,
    TempFileManager,
)
from .utils import (
    generate_random_filename,
    calculate_scale_up_dimensions,
    scale_down_dimensions_for_cropping,
    scale_down_dimensions_padding,
    calculate_pad_position,
    build_ffmpeg_quality_args,
    build_concat_ffmpeg_args,
    ensure_even_dimensions,
)
from shared.utils.security import validate_padding_color

logger = logging.getLogger(__name__)


# Pan effect: fraction of image dimension used as max pan distance
PAN_DISTANCE_FACTOR = 0.3
# Extended frame count multiplier for pan easing (ensures pan is still
# visibly moving at clip end rather than reaching its final position)
EXTENDED_FRAMES_MULTIPLIER = 1.25


def create_video(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create video from images with zoom/pan effects."""
    images = params.get("images", [])
    if not images:
        raise ValueError("No images provided")

    # Global parameters (can be overridden per-image)
    output_width = params.get("output_width", 1920)
    output_height = params.get("output_height", 1080)
    framerate = params.get("framerate", 24)
    quality = params.get("quality", "medium")
    from shared.settings import settings as _settings
    from engines.video.settings import settings as _video_settings

    default_duration = params.get("duration", _video_settings.DEFAULT_SCENE_DURATION_S)
    default_smoothness = params.get("smoothness", _video_settings.DEFAULT_SMOOTHNESS)
    default_resize = params.get("resize", "contain")
    default_h_pos = params.get("horizontal_position", "center")
    default_v_pos = params.get("vertical_position", "middle")
    default_padding_color = validate_padding_color(params.get("padding_color", "black"))

    # Ensure even dimensions
    output_width, output_height = ensure_even_dimensions(output_width, output_height)

    # Initialize temp file manager
    cache_dir = params.get("cache_dir")
    temp = TempFileManager(cache_dir=cache_dir, prefix="shs_create_video_")

    # Determine output path: explicit path > custom filename > auto-generated
    output_path = params.get("output_path")
    if not output_path:
        custom_filename = params.get("filename")
        if custom_filename:
            # Use custom filename (ensure .mp4 extension)
            if not custom_filename.endswith(".mp4"):
                custom_filename = f"{custom_filename}.mp4"
            output_path = temp.create_path(custom_filename)
        else:
            output_path = temp.create_path(generate_random_filename())

    # Protect output from cleanup
    temp.protect(output_path)

    logger.debug(f"Creating video: {len(images)} images -> {output_path}")
    logger.debug(
        f"Output: {output_width}x{output_height} @ {framerate}fps, quality={quality}"
    )

    # Build concat file list
    concat_list_path = temp.create_path("concat_list.txt")
    clip_paths: List[str] = []
    http_client = create_http_client(timeout=float(_settings.HTTP_DOWNLOAD_TIMEOUT_S))

    try:
        with open(concat_list_path, "w") as concat_file:
            for idx, image_data in enumerate(images):
                clip_path = _process_image_to_clip(
                    image_data=image_data,
                    idx=idx,
                    output_width=output_width,
                    output_height=output_height,
                    framerate=framerate,
                    quality=quality,
                    default_duration=default_duration,
                    default_smoothness=default_smoothness,
                    default_resize=default_resize,
                    default_h_pos=default_h_pos,
                    default_v_pos=default_v_pos,
                    default_padding_color=default_padding_color,
                    temp=temp,
                    http_client=http_client,
                )
                clip_paths.append(clip_path)
                concat_file.write(f"file '{os.path.abspath(clip_path)}'\n")

        # Concatenate all clips
        if len(clip_paths) == 1:
            shutil.move(clip_paths[0], output_path)
        else:
            _concatenate_videos(
                concat_list_path=concat_list_path,
                output_path=output_path,
                output_width=output_width,
                output_height=output_height,
                quality=quality,
            )

        # Get video info
        duration = get_media_duration(output_path)
        frame_count = int(duration * framerate)

        logger.debug(
            f"Video created: {output_path} ({duration:.1f}s, {frame_count} frames)"
        )

        return {
            "success": True,
            "output_path": output_path,
            "duration": duration,
            "frame_count": frame_count,
        }

    finally:
        http_client.close()
        temp.cleanup()


def _process_image_to_clip(
    image_data: Dict[str, Any],
    idx: int,
    output_width: int,
    output_height: int,
    framerate: int,
    quality: str,
    default_duration: int,
    default_smoothness: int,
    default_resize: str,
    default_h_pos: str,
    default_v_pos: str,
    default_padding_color: str,
    temp: TempFileManager,
    http_client: httpx.Client,
) -> str:
    """Process a single image into a video clip with effects."""
    # Get image URL
    image_url = (
        image_data.get("url")
        or image_data.get("src")
        or image_data.get("cached_input_file")
    )
    if not image_url:
        raise ValueError(f"Image {idx} missing url")

    # Per-image overrides
    resize = _get_value(image_data.get("resize"), default_resize)
    duration = _get_value(image_data.get("duration"), default_duration)
    fps = _get_value(image_data.get("fps"), framerate)
    padding_color = validate_padding_color(
        _get_value(image_data.get("padding_color"), default_padding_color)
    )
    smoothness = _get_value(image_data.get("smoothness"), default_smoothness)
    h_pos = _get_value(image_data.get("horizontal_position"), default_h_pos)
    v_pos = _get_value(image_data.get("vertical_position"), default_v_pos)

    # Zoom parameters (1.0 = no zoom, >1 = zoomed in)
    zoom_start = image_data.get("zoom_start", 1.0)
    zoom_end = image_data.get("zoom_end", 1.0)

    # Visual effects (j2v parity)
    flip_horizontal = image_data.get("flip_horizontal", False)
    flip_vertical = image_data.get("flip_vertical", False)
    fade_in = image_data.get("fade_in", 0)
    fade_out = image_data.get("fade_out", 0)
    pan = image_data.get("pan", "")
    rotate = image_data.get("rotate", 0)

    # Handle local file vs URL
    if image_url.startswith(("http://", "https://")):
        ext = get_url_extension(image_url, ".jpg")
        image_path = temp.create_path(f"image_{idx}{ext}")
        download_file(http_client, image_url, image_path)
    else:
        # Virtual paths start with /orgs/ and need WORKSPACE_ROOT prepended
        if image_url.startswith("/orgs/"):
            from shared.settings import settings as _s
            from shared.utils.security import validate_virtual_path

            image_path = validate_virtual_path(image_url, _s.WORKSPACE_ROOT)
        else:
            image_path = image_url

    # Always auto-detect source dimensions from image file
    with Image.open(image_path) as img:
        input_width, input_height = img.size
    logger.debug(f"Source image {idx} dimensions: {input_width}x{input_height}")

    # For custom mode, use user-specified output dimensions
    target_width = image_data.get("width", -1)
    target_height = image_data.get("height", -1)
    if resize == "custom" and target_width > 0 and target_height > 0:
        logger.debug(f"Custom output dimensions: {target_width}x{target_height}")

    # Generate clip path
    clip_path = temp.create_path(f"clip_{idx}_{quality}.mp4")

    # Calculate aspect ratios
    input_aspect_ratio = input_width / input_height
    output_aspect_ratio = output_width / output_height

    logger.debug(
        f"Input: {input_width}x{input_height}, Output: {output_width}x{output_height}"
    )
    logger.debug(f"Input AR: {input_aspect_ratio}, Output AR: {output_aspect_ratio}")
    logger.debug(
        f"resize={resize}, duration={duration}, fps={fps}, zoom_start={zoom_start}, zoom_end={zoom_end}"
    )

    final_filter = _build_filter_chain(
        input_width=input_width,
        input_height=input_height,
        output_width=output_width,
        output_height=output_height,
        target_width=target_width,
        target_height=target_height,
        input_aspect_ratio=input_aspect_ratio,
        output_aspect_ratio=output_aspect_ratio,
        duration=duration,
        fps=fps,
        zoom_start=zoom_start,
        zoom_end=zoom_end,
        smoothness=smoothness,
        resize=resize,
        h_pos=h_pos,
        v_pos=v_pos,
        padding_color=padding_color,
        # Visual effects (j2v parity)
        flip_horizontal=flip_horizontal,
        flip_vertical=flip_vertical,
        fade_in=fade_in,
        fade_out=fade_out,
        pan=pan,
        rotate=rotate,
    )

    logger.debug(f"final_filter: {final_filter}")

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        get_ffmpeg_log_level(),
        "-loop",
        "1",
        "-i",
        image_path,
        "-vf",
        final_filter,
        "-t",
        str(duration),
        "-framerate",
        str(fps),
        *build_ffmpeg_quality_args(quality, output_width, output_height),
        clip_path,
    ]

    run_ffmpeg(ffmpeg_cmd, f"Image {idx} clip generation")
    logger.debug(f"  Clip {idx}: {duration}s")

    return clip_path


def _build_filter_chain(
    input_width: int,
    input_height: int,
    output_width: int,
    output_height: int,
    target_width: int,
    target_height: int,
    input_aspect_ratio: float,
    output_aspect_ratio: float,
    duration: int,
    fps: int,
    zoom_start: float,
    zoom_end: float,
    smoothness: int,
    resize: str,
    h_pos: str,
    v_pos: str,
    padding_color: str,
    # Visual effects (j2v parity)
    flip_horizontal: bool = False,
    flip_vertical: bool = False,
    fade_in: float = 0,
    fade_out: float = 0,
    pan: str = "",
    rotate: float = 0,
) -> str:
    """Build FFmpeg filter chain with visual effects."""
    # Ensure zoom values are numeric
    try:
        zoom_start = float(zoom_start) if zoom_start not in (None, "", "None") else 1.0
    except (TypeError, ValueError):
        zoom_start = 1.0
    try:
        zoom_end = float(zoom_end) if zoom_end not in (None, "", "None") else 1.0
    except (TypeError, ValueError):
        zoom_end = 1.0

    # Initialize filter strings
    scale_up_filter = ""
    zoom_filter = ""
    scale_down_filter = ""
    crop_filter = ""
    pad_filter = ""

    # FILTER: SCALE UP
    scale_up_width, scale_up_height = calculate_scale_up_dimensions(
        input_width, input_height, output_width, output_height, smoothness
    )
    scale_up_filter = f"scale={int(scale_up_width)}:{int(scale_up_height)}"

    logger.debug(f"Scale UP: {scale_up_width}x{scale_up_height}")

    if input_aspect_ratio == output_aspect_ratio:
        # MATCHING ASPECT RATIOS
        zoom_filter = (
            _build_zoom_filter_matching_ar(zoom_start, zoom_end, duration, fps, pan)
            or ""
        )
        scale_down_width = output_width
        scale_down_height = output_height
    else:
        # MISMATCHED ASPECT RATIOS
        zoom_filter = (
            _build_zoom_filter_mismatched_ar(zoom_start, zoom_end, duration, fps, pan)
            or ""
        )

        if resize == "cover":
            # COVER MODE: scale to fill frame, crop overflow
            scale_down_width, scale_down_height = scale_down_dimensions_for_cropping(
                input_width,
                input_height,
                output_width,
                output_height,
                scale_up_width,
                scale_up_height,
            )
            crop_filter = f"crop={int(output_width)}:{int(output_height)}"
            logger.debug(f"Crop: {output_width}x{output_height}")
        elif resize == "fill":
            # FILL MODE: stretch to exactly fill frame (may distort aspect ratio)
            scale_down_width = output_width
            scale_down_height = output_height
            logger.debug(f"Fill (stretch): {output_width}x{output_height}")
        elif resize == "custom":
            # CUSTOM MODE: use element's target width/height, pad around it
            # If output dimensions specified, use them; otherwise use source dimensions
            if target_width > 0 and target_height > 0:
                scale_down_width = int(target_width)
                scale_down_height = int(target_height)
            else:
                # No custom dimensions - use source dimensions (true "natural" behavior)
                scale_down_width = int(input_width)
                scale_down_height = int(input_height)
            logger.debug(f"Custom: {scale_down_width}x{scale_down_height}")

            # Add padding to center element in output frame
            pad_x, pad_y = calculate_pad_position(
                h_pos,
                v_pos,
                output_width,
                output_height,
                scale_down_width,
                scale_down_height,
            )
            pad_filter = f"pad={int(output_width)}:{int(output_height)}:{pad_x}:{pad_y}:{padding_color}"
        else:
            # CONTAIN MODE: scale to fit within frame, add letterbox padding
            scale_down_width, scale_down_height = scale_down_dimensions_padding(
                input_width, input_height, output_width, output_height
            )
            scale_down_width = int(scale_down_width)
            scale_down_height = int(scale_down_height)

            pad_x, pad_y = calculate_pad_position(
                h_pos,
                v_pos,
                output_width,
                output_height,
                scale_down_width,
                scale_down_height,
            )

            logger.debug(f"Pad X: {pad_x}, Pad Y: {pad_y}")
            pad_filter = f"pad={int(output_width)}:{int(output_height)}:{pad_x}:{pad_y}:{padding_color}"

    # Scale down filter (always applied after zoom)
    scale_down_filter = f"scale={int(scale_down_width)}:{int(scale_down_height)}"

    # Visual effects filters (j2v parity)
    flip_filter = ""
    if flip_horizontal and flip_vertical:
        flip_filter = "hflip,vflip"
    elif flip_horizontal:
        flip_filter = "hflip"
    elif flip_vertical:
        flip_filter = "vflip"

    rotate_filter = ""
    if rotate and rotate != 0:
        try:
            angle_rad = float(rotate) * math.pi / 180
            # c=none means transparent fill for rotated corners
            rotate_filter = f"rotate={angle_rad}:c=none"
        except (TypeError, ValueError):
            pass

    fade_in_filter = ""
    fade_out_filter = ""
    if fade_in and fade_in > 0:
        fade_in_filter = f"fade=t=in:st=0:d={float(fade_in)}"
    if fade_out and fade_out > 0:
        fade_start = max(0, float(duration) - float(fade_out))
        fade_out_filter = f"fade=t=out:st={fade_start}:d={float(fade_out)}"

    # Build filter chain in order:
    # 1. scale_up - enlarge for quality
    # 2. zoom - Ken Burns effect
    # 3. scale_down - fit to output
    # 4. flip - horizontal/vertical flip
    # 5. rotate - rotation angle
    # 6. crop/pad - aspect ratio adjustment
    # 7. format/color - output format
    # 8. fade - fade in/out effects (last)
    filters = [
        scale_up_filter,
        zoom_filter,
        scale_down_filter,
        flip_filter,
        rotate_filter,
        crop_filter,
        pad_filter,
        "format=yuv420p",
        "setrange=full",
        "eq=contrast=1.1",
        fade_in_filter,
        fade_out_filter,
    ]

    return ",".join(f for f in filters if f)


def _build_zoom_filter_matching_ar(
    zoom_start: float, zoom_end: float, duration: int, fps: int, pan: str = ""
) -> Optional[str]:
    """Build zoom filter for matching aspect ratios with optional pan.

    zoom_start/zoom_end: 1.0 = no zoom, >1 = zoomed in.
    pan: direction string (left, right, up, down, diagonals).
    """
    # No zoom animation and no pan = no filter needed
    if zoom_start == zoom_end == 1.0 and not pan:
        return None

    total_frames = duration * fps

    # Get pan expressions
    x_expr, y_expr = _get_pan_expressions(pan, total_frames)

    # Static zoom (no animation) - used for pan-only or static headroom
    # IMPORTANT: fps parameter must match output fps, otherwise zoompan's internal
    # frame counter (on) won't sync with the actual video frames, causing freeze at end
    if zoom_start == zoom_end:
        return f"zoompan=z={zoom_start}:d=1:fps={fps}:x='{x_expr}':y='{y_expr}'"

    # Zoom animation
    if zoom_end > zoom_start:  # Zoom in
        zoom_factor = (zoom_end - zoom_start) / total_frames - 0.001

        logger.debug(
            f"ZOOM IN: start={zoom_start}, end={zoom_end}, factor={zoom_factor}"
        )

        return (
            f"zoompan=z='if(eq(pzoom,{zoom_end}),{zoom_start},min({zoom_end},pzoom+{zoom_factor}))':d=1:"
            f"fps={fps}:"
            f"x='{x_expr}':"
            f"y='{y_expr}'"
        )
    else:  # Zoom out
        zoom_factor = (zoom_start - zoom_end) / total_frames - 0.001

        logger.debug(
            f"ZOOM OUT: start={zoom_start}, end={zoom_end}, factor={zoom_factor}"
        )

        return (
            f"zoompan=z='if(eq(pzoom,{zoom_end}),{zoom_start},max({zoom_end},pzoom-{zoom_factor}))':d=1:"
            f"fps={fps}:"
            f"x='{x_expr}':"
            f"y='{y_expr}'"
        )


def _build_zoom_filter_mismatched_ar(
    zoom_start: float, zoom_end: float, duration: int, fps: int, pan: str = ""
) -> Optional[str]:
    """Build zoom filter for mismatched aspect ratios with optional pan.

    zoom_start/zoom_end: 1.0 = no zoom, >1 = zoomed in.
    pan: direction string (left, right, up, down, diagonals).
    """
    # No zoom animation and no pan = no filter needed
    if zoom_start == zoom_end == 1.0 and not pan:
        return None

    total_frames = duration * fps

    # Get pan expressions
    x_expr, y_expr = _get_pan_expressions(pan, total_frames)

    # Static zoom (no animation) - used for pan-only or static headroom
    # IMPORTANT: fps parameter must match output fps, otherwise zoompan's internal
    # frame counter (on) won't sync with the actual video frames, causing freeze at end
    if zoom_start == zoom_end:
        return f"zoompan=z={zoom_start}:d=1:fps={fps}:x='{x_expr}':y='{y_expr}'"

    # Zoom animation
    if zoom_end > zoom_start:  # Zoom in
        zoom_factor = (zoom_end - zoom_start) / total_frames - 0.001

        logger.debug(
            f"ZOOM IN (mismatched): start={zoom_start}, end={zoom_end}, factor={zoom_factor}"
        )

        return (
            f"zoompan=z='if(eq(pzoom,{zoom_end}),{zoom_start},min({zoom_end},pzoom+{zoom_factor}))':d=1:"
            f"fps={fps}:"
            f"x='{x_expr}':"
            f"y='{y_expr}'"
        )
    else:  # Zoom out
        zoom_factor = (zoom_start - zoom_end) / total_frames - 0.001

        logger.debug(
            f"ZOOM OUT (mismatched): start={zoom_start}, end={zoom_end}, factor={zoom_factor}"
        )

        return (
            f"zoompan=z='if(eq(pzoom,{zoom_end}),{zoom_start},max({zoom_end},pzoom-{zoom_factor}))':d=1:"
            f"fps={fps}:"
            f"x='{x_expr}':"
            f"y='{y_expr}'"
        )


def _get_pan_expressions(pan: str, total_frames: int) -> tuple:
    """
    Get x and y expressions for pan direction.

    Pan directions:
    - left: Camera pans left (content moves right)
    - right: Camera pans right (content moves left)
    - up: Camera pans up (content moves down)
    - down: Camera pans down (content moves up)
    - Diagonals: Combine horizontal and vertical

    Returns (x_expr, y_expr) for zoompan filter.

    Uses ease-out curve (quadratic) to make motion decelerate smoothly
    at the end, avoiding the jarring "freeze" effect.
    """
    # Default: centered (no pan)
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"

    if not pan:
        return center_x, center_y

    pan_dist = PAN_DISTANCE_FACTOR

    # Calculate expressions based on direction
    # IMPORTANT: We intentionally make the animation take LONGER than the clip
    # so the pan is still moving when the clip ends. This avoids the jarring
    # "freeze" effect where the pan stops but the video continues.
    extended_frames = int(total_frames * EXTENDED_FRAMES_MULTIPLIER)
    progress = f"(on/{extended_frames})"

    # Horizontal pan expressions
    # Use fixed iw/2 for pan distance (not iw/zoom) so pan speed is constant
    # even when zoom is changing. This prevents acceleration during zoom out.
    pan_left_x = f"iw/2-(iw/zoom/2)+((iw/2)*{pan_dist}*{progress})"  # Move view left (x increases)
    pan_right_x = f"iw/2-(iw/zoom/2)-((iw/2)*{pan_dist}*{progress})"  # Move view right (x decreases)

    # Vertical pan expressions
    pan_up_y = (
        f"ih/2-(ih/zoom/2)+((ih/2)*{pan_dist}*{progress})"  # Move view up (y increases)
    )
    pan_down_y = f"ih/2-(ih/zoom/2)-((ih/2)*{pan_dist}*{progress})"  # Move view down (y decreases)

    pan_map = {
        "left": (pan_left_x, center_y),
        "right": (pan_right_x, center_y),
        "up": (center_x, pan_up_y),
        "down": (center_x, pan_down_y),
        "top-left": (pan_left_x, pan_up_y),
        "top-right": (pan_right_x, pan_up_y),
        "bottom-left": (pan_left_x, pan_down_y),
        "bottom-right": (pan_right_x, pan_down_y),
    }

    return pan_map.get(pan, (center_x, center_y))


def _concatenate_videos(
    concat_list_path: str,
    output_path: str,
    output_width: int,
    output_height: int,
    quality: str,
) -> None:
    """Concatenate videos using FFmpeg concat demuxer."""
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
        concat_list_path,
        *build_concat_ffmpeg_args(quality, output_width, output_height),
        output_path,
    ]
    run_ffmpeg(cmd, "Video concatenation")


def _get_value(image_val: Any, default_val: Any) -> Any:
    """Get value with fallback."""
    if image_val is not None:
        return image_val
    return default_val
