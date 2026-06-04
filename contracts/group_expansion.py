# contracts/group_expansion.py

"""
Group expansion - template fan-out via circular array pull.

Authors declare a group spec - a template with ``repeat: N`` and
``elements[]`` where each element carries parallel arrays (e.g.
``src: [a, b, c]``). The expander produces N concrete items by pulling
index ``i mod len(array)`` from each array, then (for video groups)
calculates auto-durations and sequential start times.

Pure data transformation - no FFmpeg, no file I/O, no provider-specific
networking. The output shape ``{duration, elements}`` is what today's
callers (json2video request body + shs-video render pipeline) consume;
the mechanism doesn't name that abstraction layer.

Lives in ``contracts/`` because both the API (at enqueue time, when
building HTTP requests for general-worker jobs) and workers (shs-video
at render time) need it. API importing from ``workers/shared/`` would
be a layering inversion.

Renamed 2026-04-18 from ``scene_assembly.py`` with ``scene_group``/
``scene_count`` keys. "Scene" was json2video-domain vocabulary leaking
into platform code; the mechanism is domain-neutral and now named that
way. Hard rename - no dual-tag recognition, pre-MVP so nothing deployed
to be compatible with.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

AUTO_DURATION_PADDING_S = 0.1


def expand_groups(items: List[Any]) -> List[Any]:
    """Walk a list, expanding any ``{type: "item_group"}`` entries in place.

    Non-group entries pass through unchanged. Returns a new list when
    any expansion happens; returns the input identity otherwise so
    callers can detect the no-op via ``result is items``.

    Caller guarantees ``items`` is a list - validate upstream.
    """
    has_groups = any(
        isinstance(item, dict) and item.get("type") == "item_group" for item in items
    )
    if not has_groups:
        return items
    expanded: List[Any] = []
    for item in items:
        if isinstance(item, dict) and item.get("type") == "item_group":
            expanded.extend(expand_group(item))
        else:
            expanded.append(item)
    logger.debug(f"Expanded {len(items)} entries into {len(expanded)} after groups")
    return expanded


def expand_group(
    group_spec: Dict[str, Any],
    default_duration: float = 5.0,
) -> List[Dict[str, Any]]:
    """Expand one group spec into N concrete items.

    Each iteration produces one item containing all elements pulled via
    circular-array indexing. Auto-duration divides audio duration
    across images when image duration is -1 (video-specific convenience;
    no-op if no image/audio elements present).
    """
    elements = group_spec.get("elements", [])
    raw_repeat = group_spec.get("repeat", 0)

    try:
        total_groups = int(raw_repeat) if raw_repeat else 0
    except (ValueError, TypeError):
        total_groups = 0

    if total_groups <= 0:
        for elem in elements:
            src = elem.get("src", [])
            elem_count = _safe_int(elem.get("count", 1))
            if isinstance(src, list) and src and elem_count > 0:
                inferred = len(src) // elem_count
                if inferred > total_groups:
                    total_groups = inferred
        if total_groups <= 0:
            total_groups = 1
        logger.debug(
            f"repeat not set (raw={raw_repeat!r}), "
            f"inferred {total_groups} from element arrays"
        )

    items: List[Dict[str, Any]] = []

    for group_idx in range(total_groups):
        group_elements: List[Dict[str, Any]] = []
        for elem in elements:
            pulled = pull_from_circular_stack(elem, group_idx, total_groups)
            group_elements.extend(pulled)

        _apply_auto_duration(group_elements, default_duration)
        _apply_start_times(group_elements)

        items.append(
            {
                "duration": group_spec.get("duration", -1),
                "elements": group_elements,
            }
        )

    logger.debug(f"Expanded group into {len(items)} items (repeat={total_groups})")

    return items


def pull_from_circular_stack(
    element_template: Dict[str, Any],
    group_idx: int,
    total_groups: int = 1,
) -> List[Dict[str, Any]]:
    # Non-array src (static elements) returns [element_template] as-is.
    src = element_template.get("src")
    raw_count = element_template.get("count", 1)
    try:
        count = int(raw_count)
    except (ValueError, TypeError):
        count = 0
        logger.warning(f"  count={raw_count!r} is not a valid integer")

    if not isinstance(src, list):
        return [dict(element_template)]

    if not src:
        return []

    if count <= 0 and total_groups > 0:
        count = max(1, len(src) // total_groups)
        logger.debug(
            f"    Inferred count={count} from "
            f"{len(src)} items / {total_groups} groups"
        )

    durations = element_template.get("durations", [])
    start = (group_idx * count) % len(src)
    pulled_elements: List[Dict[str, Any]] = []

    for j in range(count):
        idx = (start + j) % len(src)
        elem: Dict[str, Any] = {
            k: v
            for k, v in element_template.items()
            if k not in ("src", "count", "durations")
        }

        # Resolve src item: may be a string URL or a DownloadedFileContract dict.
        src_item = src[idx]
        if isinstance(src_item, dict):
            elem["src"] = src_item.get("url", "")
        else:
            elem["src"] = src_item

        if durations:
            elem["_duration"] = durations[idx % len(durations)]

        # Handle array-valued properties (circular stack for zoom, etc.)
        for key in list(elem.keys()):
            val = elem[key]
            if isinstance(val, list) and key not in ("src", "durations"):
                elem[key] = val[idx % len(val)]

        pulled_elements.append(elem)

    total_needed = group_idx * count + count
    if total_needed > len(src):
        logger.debug(
            f"Circular stack wrapping: {len(src)} items for pull "
            f"starting at {start} (count={count})"
        )

    return pulled_elements


def _apply_auto_duration(
    elements: List[Dict[str, Any]],
    default_duration: float,
) -> None:
    """Calculate image durations from audio when image duration is -1.

    Uses pre-computed ``_duration`` from ``durations`` array (set by
    ``pull_from_circular_stack``). No ffprobe - callers that need
    ffprobe fallback apply it after this function.

    Strips ``_duration`` from all elements after processing.
    Modifies elements in place.
    """
    image_elements = [e for e in elements if e.get("type") == "image"]
    audio_elements = [e for e in elements if e.get("type") == "audio"]

    needs_auto = any(
        e.get("duration") == -1 or e.get("duration") is None for e in image_elements
    )

    if needs_auto and audio_elements and image_elements:
        audio_duration = audio_elements[0].get("_duration", 0)
        if isinstance(audio_duration, (int, float)) and audio_duration > 0:
            per_image = (audio_duration + AUTO_DURATION_PADDING_S) / len(image_elements)
            for e in image_elements:
                if e.get("duration") == -1 or e.get("duration") is None:
                    e["duration"] = per_image
            logger.debug(
                f"Auto-duration: {audio_duration:.2f}s / "
                f"{len(image_elements)} images = {per_image:.3f}s each"
            )
    elif needs_auto and not audio_elements:
        for e in image_elements:
            if e.get("duration") == -1 or e.get("duration") is None:
                e["duration"] = default_duration
        logger.debug(f"No audio in group, using default_duration={default_duration}s")

    for e in elements:
        e.pop("_duration", None)


def _apply_start_times(elements: List[Dict[str, Any]]) -> None:
    """Set sequential start times for elements with calculated durations.

    Elements of the same type play sequentially - each starts after
    the previous one ends. Modifies elements in place.
    """
    cumulative = 0.0
    for elem in elements:
        duration = elem.get("duration")
        if not isinstance(duration, (int, float)) or duration <= 0:
            continue
        elem["start"] = round(cumulative, 3)
        cumulative += duration


def _safe_int(value: Any) -> int:
    """Convert to int. Non-numeric values become 0."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0
