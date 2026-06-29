# api/app/application/services/image_presets.py

"""Image style preset loader and applier - wraps positive prompts and merges negatives."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_presets_cache: Optional[Dict[str, Any]] = None


def _load_presets() -> Dict[str, Any]:
    global _presets_cache
    if _presets_cache is None:
        presets_path = Path(__file__).parent.parent / "data" / "image_presets.json"
        if presets_path.exists():
            with open(presets_path) as f:
                data = json.load(f)
                _presets_cache = data.get("styles", {})
                logger.info(
                    f"Loaded {len(_presets_cache) if _presets_cache else 0} image style presets"
                )
        else:
            _presets_cache = {}
            logger.warning(f"Image presets not found: {presets_path}")
    return _presets_cache if _presets_cache is not None else {}


def apply_image_presets(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve named style presets in `parameters['styles']` into actual
    prompt text and merge their negatives.

    Merge modes:
      nested  (default): later styles wrap earlier; last style's negative wins.
      stacked: first style is outermost (dominant); first style's negative wins.
      blended: linear concatenation; all style negatives merged.
      minimal: same wrapping as nested but no style negatives - user's only.
    """
    style_names = parameters.get("styles", [])
    if not style_names:
        return parameters

    if isinstance(style_names, str):
        style_names = [style_names]

    style_names = [s for s in style_names if s]
    if not style_names:
        return parameters

    styles = _load_presets()
    params = parameters.copy()

    merge_mode = params.get("style_merge", "nested")
    if merge_mode not in ("nested", "stacked", "blended", "minimal"):
        logger.warning(
            f"Unknown style_merge mode '{merge_mode}', defaulting to 'nested'"
        )
        merge_mode = "nested"

    # Strip orchestration-only params before forwarding to workers.
    if "style_merge" in params:
        del params["style_merge"]
    if "merge_preset_negatives" in params:
        del params["merge_preset_negatives"]

    user_prompt = params.get("prompt", "")
    user_negative = params.get("negative_prompt", "")

    # List prompts (iteration workflows): recurse per item.
    if isinstance(user_prompt, list):
        styled_prompts = []
        for single_prompt in user_prompt:
            single_params = params.copy()
            single_params["prompt"] = single_prompt
            styled_single = apply_image_presets(single_params)
            styled_prompts.append(styled_single.get("prompt", single_prompt))
        params["prompt"] = styled_prompts
        del params["styles"]
        return params

    valid_styles = []
    for style_name in style_names:
        if style_name in styles:
            valid_styles.append((style_name, styles[style_name]))
        else:
            logger.warning(f"Unknown image style preset: {style_name}")

    if not valid_styles:
        return parameters

    if merge_mode == "blended":
        current_prompt = _apply_blended(user_prompt, valid_styles)
        style_negatives = [s[1].get("negative_prompt", "") for s in valid_styles]
        style_negatives = [n for n in style_negatives if n]
    elif merge_mode == "stacked":
        # Reverse so first style is the outermost wrapper.
        current_prompt = _apply_wrapped(user_prompt, list(reversed(valid_styles)))
        first_negative = valid_styles[0][1].get("negative_prompt", "")
        style_negatives = [first_negative] if first_negative else []
    else:
        current_prompt = _apply_wrapped(user_prompt, valid_styles)
        if merge_mode == "minimal":
            style_negatives = []
        else:
            last_negative = valid_styles[-1][1].get("negative_prompt", "")
            style_negatives = [last_negative] if last_negative else []

    # Collapse 2+ consecutive dots/commas/whitespace into one.
    current_prompt = re.sub(r"\.(\s*\.)+", ".", current_prompt)
    current_prompt = re.sub(r",(\s*,)+", ",", current_prompt)
    current_prompt = re.sub(r"\s+", " ", current_prompt)
    current_prompt = current_prompt.strip()

    params["prompt"] = current_prompt

    negatives = []
    if user_negative:
        negatives.append(user_negative)
    negatives.extend(style_negatives)

    if negatives:
        params["negative_prompt"] = ", ".join(negatives)

    style_names_applied = [s[0] for s in valid_styles]
    neg_count = len(style_negatives)
    neg_status = f"{neg_count} style negative(s)" if neg_count else "no style negatives"
    logger.debug(
        f"Applied {len(valid_styles)} style(s) [{merge_mode}] ({neg_status}): {', '.join(style_names_applied)}"
    )

    del params["styles"]

    return params


def _apply_wrapped(user_prompt: str, style_list: list) -> str:
    """Each style wraps the previous result via its positive_prompt template."""
    current = user_prompt
    for _, style in style_list:
        wrapper = style.get("positive_prompt", "{prompt}")
        current = wrapper.replace("{prompt}", current)
    return current


def _apply_blended(user_prompt: str, style_list: list) -> str:
    """Linear concatenation: all prefixes, user prompt, all suffixes."""
    prefixes = []
    suffixes = []

    for _, style in style_list:
        wrapper = style.get("positive_prompt", "{prompt}")
        if "{prompt}" in wrapper:
            parts = wrapper.split("{prompt}", 1)
            prefix = parts[0].strip()
            suffix = parts[1].strip() if len(parts) > 1 else ""
            if prefix:
                prefixes.append(prefix)
            if suffix:
                suffixes.append(suffix)
        else:
            # No placeholder - treat entire wrapper as prefix.
            if wrapper.strip():
                prefixes.append(wrapper.strip())

    parts = prefixes + [user_prompt] + suffixes
    return " ".join(p for p in parts if p)
