# workers/engines/video/normalize.py

"""
Schema Normalization for shs-video

Converts j2v-compatible scenes/elements schema to internal format.
Supports the industry-standard j2v schema format.

Architecture:
- Each element type has a dedicated normalizer class
- Effects are processed through an extensible effects pipeline
- Duration resolution is centralized with j2v semantics

External Schema (j2v-compatible with flat parameters):
{
    "scenes": [
        {
            "duration": -1,  # -1 = auto (sum of element durations)
            "elements": [
                {
                    "type": "image",
                    "src": "https://...",
                    "duration": -1,  # -1 = use default, -2 = match scene
                    "zoom": 10,
                    "position": "center",
                    "resize": "contain"
                },
                {
                    "type": "audio",
                    "src": "https://...",
                    "duration": -1,
                    "volume": 1.0
                }
            ]
        }
    ],
    # Flat output params (not nested)
    "width": 1920,
    "height": 1080,
    "framerate": 24,
    "quality": "medium",
    # Flat defaults
    "default_duration": 5,
    "default_zoom_start": 1.0,
    "default_zoom_end": 1.0,
    "smoothness": 3,
    "padding_color": "black",
    # Flat subtitle params
    "subtitles_enabled": false,
    "subtitles_language": "en",
    "subtitles_style": "standard",
    ...
}
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from engines.video.settings import settings as video_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Duration Resolution (j2v Semantics)
# =============================================================================


class DurationResolver:
    """
    Resolve element duration based on j2v semantics.

    Duration values:
    - > 0: Fixed duration in seconds
    - -1: Use intrinsic duration or default
    - -2: Match parent scene duration
    - '' (empty string): Use default (j2v "cleared" semantics)
    """

    @staticmethod
    def resolve(
        element_duration: Optional[float],
        default_duration: float,
        scene_duration: Optional[float] = None,
    ) -> float:
        # Treat empty string as "use default" (j2v cleared field semantics)
        if element_duration == "" or element_duration is None:
            element_duration = -1

        if element_duration == -2:
            # Match parent scene
            if scene_duration and scene_duration > 0:
                return scene_duration
            return default_duration
        elif element_duration == -1:
            # Use default
            return default_duration
        elif element_duration > 0:
            # Fixed duration
            return element_duration
        else:
            # Invalid - use default
            return default_duration


# =============================================================================
# Position Mapping
# =============================================================================


class PositionMapper:
    """
    Map j2v position strings to horizontal/vertical components.

    j2v uses compound positions like "top-left", "center", "bottom-right"
    Internal format uses separate horizontal_position and vertical_position
    """

    POSITION_MAP = {
        # UI format: vertical-horizontal
        "top-left": ("left", "top"),
        "top-center": ("center", "top"),
        "top-right": ("right", "top"),
        "center-left": ("left", "middle"),
        "center-center": ("center", "middle"),
        "center-right": ("right", "middle"),
        "bottom-left": ("left", "bottom"),
        "bottom-center": ("center", "bottom"),
        "bottom-right": ("right", "bottom"),
        # Legacy j2v format
        "top": ("center", "top"),
        "center": ("center", "middle"),
        "left": ("left", "middle"),
        "right": ("right", "middle"),
        "bottom": ("center", "bottom"),
    }

    @classmethod
    def parse(cls, position: str) -> tuple:
        """Return (horizontal, vertical) for position string."""
        return cls.POSITION_MAP.get(position, ("center", "middle"))


# =============================================================================
# Effects Processing
# =============================================================================


@dataclass
class EffectsConfig:
    """
    Parsed effects configuration for an image element.

    Extensible: Add new effect fields here as they're implemented.
    The FFmpeg filter builder reads from this config.
    """

    # Zoom effects
    zoom_start: float = 1.0  # Starting zoom level (1.0 = no zoom, >1 = zoomed in)
    zoom_end: float = 1.0  # Ending zoom level (same = static, different = animated)
    horizontal_position: str = "center"
    vertical_position: str = "middle"
    resize: str = "contain"  # cover, contain, fill, natural

    # Visual effects (j2v parity)
    flip_horizontal: bool = False
    flip_vertical: bool = False
    fade_in: float = 0  # Duration in seconds
    fade_out: float = 0  # Duration in seconds
    pan: str = ""  # Direction: left, right, up, down, etc.
    rotate: float = 0  # Degrees

    @classmethod
    def from_element(
        cls, element: Dict[str, Any], defaults: Dict[str, Any]
    ) -> "EffectsConfig":
        """
        Create EffectsConfig from element dict with fallback to defaults.

        Reads flat properties (element["zoom"]) or nested effects dict (element["effects"]["zoom"]).
        j2v semantics: empty string or None uses the default; explicit 0 is honored.
        """
        # Support both flat and nested effects
        effects = element.get("effects", {})

        # Helper to get value with j2v semantics (empty string = use default)
        def get_with_default(key: str, nested_key: str, default: Any) -> Any:
            # Check flat property first
            value = element.get(key)
            if value is not None and value != "":
                return value
            # Check nested effects
            value = effects.get(nested_key)
            if value is not None and value != "":
                return value
            # Fall back to defaults
            return default

        # Handle zoom_start/zoom_end
        default_zoom_start = defaults.get("default_zoom_start", 1.0)
        zoom_start = get_with_default("zoom_start", "zoom_start", default_zoom_start)
        zoom_end = get_with_default("zoom_end", "zoom_end", default_zoom_start)
        zoom_start = float(zoom_start) if zoom_start else 1.0
        zoom_end = float(zoom_end) if zoom_end else 1.0

        # Handle positions - separate h/v fields (new) or combined position (legacy)
        h_pos = get_with_default(
            "horizontal_position",
            "horizontal_position",
            defaults.get("horizontal_position", "center"),
        )
        v_pos = get_with_default(
            "vertical_position",
            "vertical_position",
            defaults.get("vertical_position", "middle"),
        )

        # Legacy: if combined "position" field exists, parse it
        position = get_with_default("position", "position", None)
        if position:
            h_pos, v_pos = PositionMapper.parse(position)

        # Handle resize mode
        # cover = scale to fill frame, crop overflow (zoom to fill, cut edges)
        # contain = scale to fit within frame, add letterbox padding
        # fill = stretch to exactly fill frame (may distort aspect ratio)
        # custom = use element's width/height, pad around it
        default_resize = defaults.get("resize", "contain")
        resize = get_with_default("resize", "resize", default_resize)
        if resize not in ("cover", "contain", "fill", "custom"):
            resize = "contain"  # Default to contain for invalid values

        # Visual effects (j2v parity)
        flip_horizontal = get_with_default("flip_horizontal", "flip_horizontal", False)
        flip_vertical = get_with_default("flip_vertical", "flip_vertical", False)
        fade_in = get_with_default("fade_in", "fade_in", 0)
        fade_out = get_with_default("fade_out", "fade_out", 0)
        pan = get_with_default("pan", "pan", "")
        rotate = get_with_default("rotate", "rotate", 0)

        return cls(
            zoom_start=zoom_start,
            zoom_end=zoom_end,
            horizontal_position=h_pos,
            vertical_position=v_pos,
            resize=resize,
            flip_horizontal=bool(flip_horizontal),
            flip_vertical=bool(flip_vertical),
            fade_in=float(fade_in) if fade_in else 0,
            fade_out=float(fade_out) if fade_out else 0,
            pan=str(pan) if pan else "",
            rotate=float(rotate) if rotate else 0,
        )


# =============================================================================
# Element Normalizers
# =============================================================================


@dataclass
class NormalizedElement:
    """Base class for normalized elements."""

    url: str
    duration: float
    element_type: str


@dataclass
class NormalizedImage(NormalizedElement):
    """Normalized image element with effects."""

    element_type: str = field(default="image", init=False)
    effects: EffectsConfig = field(default_factory=EffectsConfig)
    width: Optional[int] = None
    height: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for downstream rendering."""
        return {
            "url": self.url,
            "duration": self.duration,
            "zoom_start": self.effects.zoom_start,
            "zoom_end": self.effects.zoom_end,
            "horizontal_position": self.effects.horizontal_position,
            "vertical_position": self.effects.vertical_position,
            "resize": self.effects.resize,
            "width": self.width,
            "height": self.height,
            # Visual effects (j2v parity)
            "flip_horizontal": self.effects.flip_horizontal,
            "flip_vertical": self.effects.flip_vertical,
            "fade_in": self.effects.fade_in,
            "fade_out": self.effects.fade_out,
            "pan": self.effects.pan,
            "rotate": self.effects.rotate,
        }


@dataclass
class NormalizedAudio(NormalizedElement):
    """Normalized audio element."""

    element_type: str = field(default="audio", init=False)
    volume: float = 1.0
    scene_duration: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "duration": self.duration,
            "volume": self.volume,
            "scene_duration": self.scene_duration,
        }


@dataclass
class NormalizedVideo(NormalizedElement):
    """Normalized video clip element."""

    element_type: str = field(default="video", init=False)
    scene_duration: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "duration": self.duration,
            "scene_duration": self.scene_duration,
        }


class ElementNormalizer(ABC):
    """Base class for element type normalizers."""

    @abstractmethod
    def normalize(
        self,
        element: Dict[str, Any],
        scene_duration: float,
        defaults: Dict[str, Any],
    ) -> NormalizedElement:
        raise NotImplementedError


class ImageNormalizer(ElementNormalizer):
    def normalize(
        self,
        element: Dict[str, Any],
        scene_duration: float,
        defaults: Dict[str, Any],
    ) -> NormalizedImage:
        # Resolve duration (use default_duration from flat schema)
        default_dur = defaults.get(
            "default_duration",
            defaults.get("duration", video_settings.DEFAULT_SCENE_DURATION_S),
        )
        duration = DurationResolver.resolve(
            element.get("duration", -1),
            default_dur,
            scene_duration,
        )

        # Parse effects from flat element properties
        effects = EffectsConfig.from_element(element, defaults)

        # Support both "src" (new schema) and "url" (legacy)
        url: str = element.get("src") or element.get("url") or ""

        return NormalizedImage(
            url=url,
            duration=duration,
            effects=effects,
            width=element.get("width"),
            height=element.get("height"),
        )


class AudioNormalizer(ElementNormalizer):
    def normalize(
        self,
        element: Dict[str, Any],
        scene_duration: float,
        defaults: Dict[str, Any],
    ) -> NormalizedAudio:
        # Support both "src" (new schema) and "url" (legacy)
        url: str = element.get("src") or element.get("url") or ""

        return NormalizedAudio(
            url=url,
            duration=element.get("duration", -1),  # Keep -1 for intrinsic
            volume=element.get("volume", 1.0),
            scene_duration=scene_duration,
        )


class VideoNormalizer(ElementNormalizer):
    def normalize(
        self,
        element: Dict[str, Any],
        scene_duration: float,
        defaults: Dict[str, Any],
    ) -> NormalizedVideo:
        # Support both "src" (new schema) and "url" (legacy)
        url: str = element.get("src") or element.get("url") or ""

        return NormalizedVideo(
            url=url,
            duration=element.get("duration", -1),  # Keep -1 for intrinsic
            scene_duration=scene_duration,
        )


# Registry of element normalizers
ELEMENT_NORMALIZERS: Dict[str, ElementNormalizer] = {
    "image": ImageNormalizer(),
    "audio": AudioNormalizer(),
    "video": VideoNormalizer(),
}


# =============================================================================
# Scene Processing
# =============================================================================


@dataclass
class NormalizedScene:
    """A processed scene with categorized elements."""

    images: List[NormalizedImage] = field(default_factory=list)
    audio_tracks: List[NormalizedAudio] = field(default_factory=list)
    video_clips: List[NormalizedVideo] = field(default_factory=list)
    duration: float = 0.0


def process_scene(
    scene: Dict[str, Any],
    defaults: Dict[str, Any],
) -> NormalizedScene:
    """Process a single scene, normalizing all elements by type."""
    elements = scene.get("elements", [])
    scene_duration = scene.get("duration", -1)

    # First pass: collect images to calculate auto duration if needed
    image_elements = [e for e in elements if e.get("type") == "image"]

    if scene_duration == -1:
        # Auto: sum of image durations
        scene_duration = sum(
            DurationResolver.resolve(
                img.get("duration", -1),
                defaults.get("duration", video_settings.DEFAULT_SCENE_DURATION_S),
                None,
            )
            for img in image_elements
        ) or defaults.get("duration", video_settings.DEFAULT_SCENE_DURATION_S)

    # Second pass: normalize all elements
    result = NormalizedScene(duration=scene_duration)

    for element in elements:
        elem_type = element.get("type")
        normalizer = ELEMENT_NORMALIZERS.get(elem_type)

        if not normalizer:
            logger.warning(f"Unknown element type: {elem_type}, skipping")
            continue

        normalized = normalizer.normalize(element, scene_duration, defaults)

        if isinstance(normalized, NormalizedImage):
            result.images.append(normalized)
        elif isinstance(normalized, NormalizedAudio):
            result.audio_tracks.append(normalized)
        elif isinstance(
            normalized, NormalizedVideo
        ):  # pragma: no branch - covered by test but coverage.py quirk with elif in for
            result.video_clips.append(normalized)

    return result


# =============================================================================
# Main Normalization Entry Point
# =============================================================================


@dataclass
class NormalizedParams:
    images: List[Dict[str, Any]]
    audio_tracks: List[Dict[str, Any]]
    video_clips: List[Dict[str, Any]]
    output_width: int
    output_height: int
    framerate: int
    quality: str
    duration: float
    zoom_start: float  # Default zoom start (1.0 = no zoom)
    zoom_end: float  # Default zoom end (1.0 = no zoom)
    smoothness: int
    padding_color: str
    subtitles: Optional[Dict[str, Any]]
    cache_dir: Optional[str]
    filename: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for passing to processing functions."""
        return {
            "images": self.images,
            "audio_tracks": self.audio_tracks,
            "video_clips": self.video_clips,
            "output_width": self.output_width,
            "output_height": self.output_height,
            "framerate": self.framerate,
            "quality": self.quality,
            "duration": self.duration,
            "zoom_start": self.zoom_start,
            "zoom_end": self.zoom_end,
            "smoothness": self.smoothness,
            "padding_color": self.padding_color,
            "subtitles": self.subtitles,
            "cache_dir": self.cache_dir,
            "filename": self.filename,
        }

    def has_audio(self) -> bool:
        return bool(self.audio_tracks)

    def has_video_clips(self) -> bool:
        return bool(self.video_clips)


def normalize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize parameters from j2v-compatible schema to internal format.

    Accepts scenes[].elements[] (flat params) or images[] (passthrough).
    Flat params (width, default_duration) take precedence over nested (output.width, defaults.duration).
    """
    # Check if already in legacy format (passthrough)
    if "images" in params and "scenes" not in params:
        logger.debug("Using legacy images[] format (passthrough)")
        return params

    # Extract scenes
    scenes = params.get("scenes", [])

    if not scenes:
        # No scenes - check for legacy format one more time
        if "images" in params:
            return params
        raise ValueError("No scenes or images provided")

    # Build defaults dict from flat or nested params
    # Flat params take precedence over nested for forward compatibility
    defaults = _extract_defaults(params)

    # Process all scenes
    all_images: List[Dict[str, Any]] = []
    all_audio: List[Dict[str, Any]] = []
    all_video: List[Dict[str, Any]] = []

    for scene_idx, scene in enumerate(scenes):
        normalized_scene = process_scene(scene, defaults)

        # Convert to dicts and accumulate
        for img in normalized_scene.images:
            all_images.append(img.to_dict())

        for audio in normalized_scene.audio_tracks:
            all_audio.append(audio.to_dict())

        for video in normalized_scene.video_clips:
            all_video.append(video.to_dict())

        logger.debug(
            f"Scene {scene_idx}: {len(normalized_scene.images)} images, "
            f"{len(normalized_scene.audio_tracks)} audio, "
            f"{len(normalized_scene.video_clips)} video"
        )

    # Extract output params (flat or nested)
    output_width = params.get("width", params.get("output", {}).get("width", 1920))
    output_height = params.get("height", params.get("output", {}).get("height", 1080))
    framerate = params.get("framerate", params.get("output", {}).get("framerate", 24))
    quality = params.get("quality", params.get("output", {}).get("quality", "medium"))

    # Extract subtitles (flat or nested)
    subtitles = _extract_subtitles(params)

    # Build result
    result = NormalizedParams(
        images=all_images,
        audio_tracks=all_audio,
        video_clips=all_video,
        output_width=output_width,
        output_height=output_height,
        framerate=framerate,
        quality=quality,
        duration=defaults.get(
            "default_duration", video_settings.DEFAULT_SCENE_DURATION_S
        ),
        zoom_start=defaults.get("default_zoom_start", 1.0),
        zoom_end=defaults.get("default_zoom_end", 1.0),
        smoothness=defaults.get("smoothness", 3),
        padding_color=defaults.get("padding_color", "black"),
        subtitles=subtitles,
        cache_dir=params.get("cache_dir"),
        filename=params.get("filename"),
    )

    logger.debug(
        f"Normalized: {len(all_images)} images, {len(all_audio)} audio, "
        f"{len(all_video)} video from {len(scenes)} scenes"
    )

    return result.to_dict()


def _extract_defaults(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract defaults from flat or nested params.

    Supports both:
    - Flat: default_duration, default_zoom_start, default_zoom_end, smoothness, padding_color
    - Nested: defaults.duration, defaults.zoom_start, defaults.zoom_end, etc.

    j2v semantics: empty string means "not set", use hardcoded default.
    """
    nested = params.get("defaults", {})

    def get_default(flat_key: str, nested_key: str, hardcoded: Any) -> Any:
        """Get value with j2v semantics - empty string means use hardcoded default."""
        value = params.get(flat_key)
        if value is not None and value != "":
            return value
        value = nested.get(nested_key)
        if value is not None and value != "":
            return value
        return hardcoded

    return {
        "default_duration": get_default(
            "default_duration", "duration", video_settings.DEFAULT_SCENE_DURATION_S
        ),
        "default_zoom_start": get_default("default_zoom_start", "zoom_start", 1.0),
        "default_zoom_end": get_default("default_zoom_end", "zoom_end", 1.0),
        "smoothness": get_default(
            "smoothness", "smoothness", video_settings.DEFAULT_SMOOTHNESS
        ),
        "padding_color": get_default("padding_color", "padding_color", "black"),
        "resize": get_default("resize", "resize", "contain"),
    }


def _extract_subtitles(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract subtitle configuration from flat or nested params.

    Sources: "auto" (Whisper), "captions" (manual), "src" (SRT/VTT), "text" (plain).
    Falls back to source="auto" when subtitles_enabled=true (legacy flat flag).
    """
    nested = params.get("subtitles", {})

    # Check source type (new pattern) or legacy enabled flag
    source = params.get("subtitles_source", nested.get("source", ""))

    # Legacy support: subtitles_enabled: true means source=auto
    if not source:
        if params.get("subtitles_enabled", nested.get("enabled", False)):
            source = "auto"
        else:
            return None

    # Base configuration with styling options
    config = {
        "source": source,
        "enabled": True,
        "model": params.get("subtitles_model", nested.get("model", None)),
        "language": params.get("subtitles_language", nested.get("language", "en")),
        "style": params.get("subtitles_style", nested.get("style", "standard")),
        "font_size": params.get("subtitles_font_size", nested.get("font_size", 24)),
        "font_family": params.get(
            "subtitles_font_family", nested.get("font_family", "Luckiest Guy")
        ),
        "font_color": params.get(
            "subtitles_font_color", nested.get("font_color", "FFFFFF")
        ),
        "background_color": params.get(
            "subtitles_background_color", nested.get("background_color", "")
        ),
        "all_caps": params.get("subtitles_all_caps", nested.get("all_caps", False)),
        "position": params.get("subtitles_position", nested.get("position", "bottom")),
        "highlight_color": params.get(
            "subtitles_highlight_color", nested.get("highlight_color", "FFFF00")
        ),
        "outline_color": params.get(
            "subtitles_outline_color", nested.get("outline_color", "000000")
        ),
        "outline_width": params.get(
            "subtitles_outline_width", nested.get("outline_width", 2)
        ),
        "shadow_offset": params.get(
            "subtitles_shadow_offset", nested.get("shadow_offset", 1)
        ),
        "max_words_per_phrase": params.get(
            "subtitles_max_words_per_phrase", nested.get("max_words_per_phrase", 5)
        ),
        "edge_padding": params.get(
            "subtitles_edge_padding", nested.get("edge_padding", 20)
        ),
    }

    # Source-specific data
    if source == "captions":
        config["captions"] = params.get(
            "subtitles_captions", nested.get("captions", [])
        )
    elif source == "src":
        config["src"] = params.get("subtitles_src", nested.get("src", ""))
    elif source == "text":
        config["text"] = params.get("subtitles_text", nested.get("text", ""))

    return config


# =============================================================================
# Utility Functions
# =============================================================================


def has_audio_tracks(params: Dict[str, Any]) -> bool:
    """Check if normalized params contain audio tracks to merge."""
    return bool(params.get("audio_tracks"))


def has_video_clips(params: Dict[str, Any]) -> bool:
    """Check if normalized params contain video clips to concatenate."""
    return bool(params.get("video_clips"))


def get_total_duration(params: Dict[str, Any]) -> float:
    """Calculate total duration from normalized params."""
    total = 0.0
    for img in params.get("images", []):
        total += img.get("duration", 0)
    return total
