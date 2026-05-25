# workers/engines/comfyui/templates.py

"""ComfyUI workflow template loader and parameter injection.

Templates use ComfyUI's API format (not UI format) - dicts keyed by node ID.
"""

import json
import copy
import random
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)

WORKFLOW_DIR = Path(__file__).parent / "workflows"

AVAILABLE_WORKFLOWS = [
    "comfyui_txt2img",
    "comfyui_txt2img_fp8",
    "comfyui_txt2img_gguf",
    "comfyui_txt2img_flux2",
    "comfyui_txt2img_flux2_9b",
    "comfyui_imgedit",
]

# param_name -> list of (node_id, path_type, path_key) tuples.
# path_type is "inputs" or "widgets_values". width/height fan out across multiple nodes.
WORKFLOW_PARAM_MAPPINGS: Dict[str, Dict[str, List[Tuple[str, str, Any]]]] = {
    "comfyui_txt2img": {
        "prompt": [("6", "inputs", "text")],
        "seed": [("25", "inputs", "noise_seed")],
        # EmptySD3LatentImage (27) and ModelSamplingFlux (30) both need width/height.
        "width": [("27", "inputs", "width"), ("30", "inputs", "width")],
        "height": [("27", "inputs", "height"), ("30", "inputs", "height")],
        "steps": [("17", "inputs", "steps")],
        "batch_size": [("27", "inputs", "batch_size")],
        # FluxGuidance: higher = stricter prompt adherence.
        "guidance": [("26", "inputs", "guidance")],
        # Node 50 ImageScale: upscale output.
        "output_width": [("50", "inputs", "width")],
        "output_height": [("50", "inputs", "height")],
        "upscale_method": [("50", "inputs", "upscale_method")],
    },
    # fp8 and gguf share the simple KSampler graph (UnetLoader + flux1-schnell weights).
    "comfyui_txt2img_fp8": {
        "prompt": [("3", "inputs", "text")],
        "seed": [("6", "inputs", "seed")],
        "steps": [("6", "inputs", "steps")],
        "width": [("5", "inputs", "width")],
        "height": [("5", "inputs", "height")],
        "batch_size": [("5", "inputs", "batch_size")],
        "output_width": [("50", "inputs", "width")],
        "output_height": [("50", "inputs", "height")],
        "upscale_method": [("50", "inputs", "upscale_method")],
    },
    "comfyui_txt2img_gguf": {
        "prompt": [("3", "inputs", "text")],
        "seed": [("6", "inputs", "seed")],
        "steps": [("6", "inputs", "steps")],
        "width": [("5", "inputs", "width")],
        "height": [("5", "inputs", "height")],
        "batch_size": [("5", "inputs", "batch_size")],
        "output_width": [("50", "inputs", "width")],
        "output_height": [("50", "inputs", "height")],
        "upscale_method": [("50", "inputs", "upscale_method")],
    },
    "comfyui_txt2img_flux2": {
        "prompt": [("6", "inputs", "text")],
        "negative_prompt": [("7", "inputs", "text")],
        "seed": [("14", "inputs", "noise_seed")],
        # EmptyFlux2LatentImage (11) and Flux2Scheduler (12) both need width/height.
        "width": [("11", "inputs", "width"), ("12", "inputs", "width")],
        "height": [("11", "inputs", "height"), ("12", "inputs", "height")],
        "steps": [("12", "inputs", "steps")],
        "batch_size": [("11", "inputs", "batch_size")],
        # CFGGuider cfg field receives the guidance param.
        "guidance": [("15", "inputs", "cfg")],
        "output_width": [("50", "inputs", "width")],
        "output_height": [("50", "inputs", "height")],
        "upscale_method": [("50", "inputs", "upscale_method")],
    },
    # 9B reuses the 4B node graph; only UNET weights differ.
    "comfyui_txt2img_flux2_9b": {
        "prompt": [("6", "inputs", "text")],
        "negative_prompt": [("7", "inputs", "text")],
        "seed": [("14", "inputs", "noise_seed")],
        "width": [("11", "inputs", "width"), ("12", "inputs", "width")],
        "height": [("11", "inputs", "height"), ("12", "inputs", "height")],
        "steps": [("12", "inputs", "steps")],
        "batch_size": [("11", "inputs", "batch_size")],
        "guidance": [("15", "inputs", "cfg")],
        "output_width": [("50", "inputs", "width")],
        "output_height": [("50", "inputs", "height")],
        "upscale_method": [("50", "inputs", "upscale_method")],
    },
    "comfyui_imgedit": {
        "image": [("1", "inputs", "image")],
        "prompt": [("6", "inputs", "text")],
        "negative_prompt": [("7", "inputs", "text")],
        "width": [("11", "inputs", "width"), ("12", "inputs", "width")],
        "height": [("11", "inputs", "height"), ("12", "inputs", "height")],
        "steps": [("12", "inputs", "steps")],
        "seed": [("14", "inputs", "noise_seed")],
        # CFGGuider cfg controls edit strength: 1 preserves original, higher follows prompt.
        "cfg": [("15", "inputs", "cfg")],
        "output_width": [("50", "inputs", "width")],
        "output_height": [("50", "inputs", "height")],
        "upscale_method": [("50", "inputs", "upscale_method")],
    },
}

WORKFLOW_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "comfyui_txt2img": {
        "width": 512,
        "height": 512,
        "steps": 1,
        "batch_size": 1,
        "seed": -1,  # -1 = randomize
        "guidance": 3.5,  # 3.5 natural, 7-10 stricter style adherence
        "upscale": True,
        "output_width": 1920,
        "output_height": 1080,
        "upscale_method": "lanczos",
    },
    "comfyui_txt2img_fp8": {
        "width": 512,
        "height": 512,
        "steps": 1,
        "batch_size": 1,
        "seed": -1,
        "upscale": True,
        "output_width": 1920,
        "output_height": 1080,
        "upscale_method": "lanczos",
    },
    "comfyui_txt2img_gguf": {
        "width": 512,
        "height": 512,
        "steps": 1,
        "batch_size": 1,
        "seed": -1,
        "upscale": True,
        "output_width": 1920,
        "output_height": 1080,
        "upscale_method": "lanczos",
    },
    "comfyui_txt2img_flux2": {
        "width": 512,
        "height": 512,
        "steps": 1,
        "batch_size": 1,
        "seed": -1,
        "guidance": 3.5,  # CFGGuider cfg: 3.5 natural, higher = stricter prompt
        "negative_prompt": "",
        "upscale": True,
        "output_width": 1920,
        "output_height": 1080,
        "upscale_method": "lanczos",
    },
    "comfyui_txt2img_flux2_9b": {
        "width": 512,
        "height": 512,
        "steps": 1,
        "batch_size": 1,
        "seed": -1,
        "guidance": 3.5,
        "negative_prompt": "",
        "upscale": True,
        "output_width": 1920,
        "output_height": 1080,
        "upscale_method": "lanczos",
    },
    "comfyui_imgedit": {
        "width": 512,
        "height": 512,
        "steps": 1,
        "seed": -1,
        "negative_prompt": "",
        "cfg": 1,  # 1 preserves original, 3-7 follows edit prompt more
        "upscale": True,
        "output_width": 1920,
        "output_height": 1080,
        "upscale_method": "lanczos",
    },
}


def _calculate_generation_dimensions(
    output_width: int, output_height: int
) -> tuple[int, int]:
    """Smallest gen dims that preserve exact aspect ratio: both multiples of 64, both >= 512.

    Falls back to approximate rounding for non-standard ratios that would produce dims > 2048.
    Examples: 1920x1080 -> 1024x576; 1080x1080 -> 512x512; 800x600 -> 768x576.
    """
    from math import gcd as _gcd

    MIN_DIM = 512
    MAX_DIM = 2048
    ROUND_TO = 64

    g = _gcd(output_width, output_height)
    ratio_w = output_width // g
    ratio_h = output_height // g

    # Smallest scale s where both ratio*s land on 64-boundaries.
    s_w = ROUND_TO // _gcd(ratio_w, ROUND_TO)
    s_h = ROUND_TO // _gcd(ratio_h, ROUND_TO)
    base_s = (s_w * s_h) // _gcd(s_w, s_h)

    s = base_s
    while ratio_w * s < MIN_DIM or ratio_h * s < MIN_DIM:
        s += base_s

    gen_w = ratio_w * s
    gen_h = ratio_h * s

    # Non-standard ratios can blow past MAX_DIM - fall back to approximate.
    if gen_w > MAX_DIM or gen_h > MAX_DIM:
        if output_width >= output_height:
            gen_h = MIN_DIM
            gen_w = round(MIN_DIM * output_width / output_height / ROUND_TO) * ROUND_TO
        else:
            gen_w = MIN_DIM
            gen_h = round(MIN_DIM * output_height / output_width / ROUND_TO) * ROUND_TO
        gen_w = max(gen_w, MIN_DIM)
        gen_h = max(gen_h, MIN_DIM)

    return gen_w, gen_h


def load_workflow_template(workflow_name: str) -> Dict[str, Any]:
    """Load a workflow JSON template by name."""
    if workflow_name not in AVAILABLE_WORKFLOWS:
        raise ValueError(
            f"Unknown workflow: {workflow_name}. "
            f"Available: {', '.join(AVAILABLE_WORKFLOWS)}"
        )

    template_path = WORKFLOW_DIR / f"{workflow_name}.json"

    if not template_path.exists():
        raise FileNotFoundError(
            f"Workflow template not found: {template_path}. "
            f"Please provide the API format JSON file."
        )

    with open(template_path, "r") as f:
        workflow = json.load(f)

    logger.debug(f"Loaded workflow template: {workflow_name}")
    return workflow


def inject_parameters(
    workflow: Dict[str, Any],
    parameters: Dict[str, Any],
    workflow_name: str = "comfyui_txt2img",
) -> Dict[str, Any]:
    """Inject user parameters into a workflow template; returns a new dict."""
    workflow = copy.deepcopy(workflow)

    mappings = WORKFLOW_PARAM_MAPPINGS.get(workflow_name, {})
    defaults = WORKFLOW_DEFAULTS.get(workflow_name, {})

    merged_params = {**defaults, **parameters}

    if merged_params.get("seed", -1) == -1:
        merged_params["seed"] = random.randint(0, 2**32 - 1)
        logger.debug(f"Generated random seed: {merged_params['seed']}")

    out_w = int(merged_params["output_width"])
    out_h = int(merged_params["output_height"])
    if merged_params.get("upscale", False):
        gen_w, gen_h = _calculate_generation_dimensions(out_w, out_h)
        merged_params["width"] = gen_w
        merged_params["height"] = gen_h
        logger.debug(f"Upscale: gen {gen_w}x{gen_h} -> output {out_w}x{out_h}")
    else:
        merged_params["width"] = out_w
        merged_params["height"] = out_h

    for param_name, param_value in merged_params.items():
        if param_name not in mappings:
            continue

        targets = mappings[param_name]
        for node_id, path_type, path_key in targets:
            if node_id not in workflow:
                logger.warning(f"Node {node_id} not found for parameter {param_name}")
                continue

            node = workflow[node_id]

            if path_type == "inputs":
                if "inputs" not in node:
                    node["inputs"] = {}
                node["inputs"][path_key] = param_value
                logger.debug(f"Set {node_id}.inputs.{path_key} = {param_value}")

            else:  # widgets_values
                if "widgets_values" not in node:
                    node["widgets_values"] = []
                while len(node["widgets_values"]) <= path_key:
                    node["widgets_values"].append(None)
                node["widgets_values"][path_key] = param_value
                logger.debug(
                    f"Set {node_id}.widgets_values[{path_key}] = {param_value}"
                )

    return workflow


def get_workflow_defaults(workflow_name: str) -> Dict[str, Any]:
    return WORKFLOW_DEFAULTS.get(workflow_name, {}).copy()


def list_workflows() -> List[str]:
    return AVAILABLE_WORKFLOWS.copy()


def validate_parameters(
    workflow_name: str,
    parameters: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Validate parameters for a workflow; returns (is_valid, error_message)."""
    if workflow_name not in AVAILABLE_WORKFLOWS:
        return False, f"Unknown workflow: {workflow_name}"

    if workflow_name == "comfyui_imgedit":
        if "image" not in parameters or not parameters["image"]:
            return False, "image is required for image editing"
        if "prompt" not in parameters or not parameters["prompt"]:
            return False, "prompt (edit instructions) is required for image editing"
    else:
        if "prompt" not in parameters or not parameters["prompt"]:
            return False, "prompt is required"

    # Coerce strings (form data) before range check.
    try:
        width = int(parameters.get("width", 1024))
    except (ValueError, TypeError):
        return False, f"width must be 256-2048, got {parameters.get('width')}"

    try:
        height = int(parameters.get("height", 1024))
    except (ValueError, TypeError):
        return False, f"height must be 256-2048, got {parameters.get('height')}"

    if width < 256 or width > 2048:
        return False, f"width must be 256-2048, got {width}"

    if height < 256 or height > 2048:
        return False, f"height must be 256-2048, got {height}"

    try:
        steps = int(parameters.get("steps", 4))
    except (ValueError, TypeError):
        return False, f"steps must be 1-50, got {parameters.get('steps')}"

    if steps < 1 or steps > 50:
        return False, f"steps must be 1-50, got {steps}"

    if parameters.get("upscale", False):
        # ImageScale (node 50) is required for upscale.
        try:
            wf = load_workflow_template(workflow_name)
            if "50" not in wf or wf["50"].get("class_type") != "ImageScale":
                return (
                    False,
                    f"Workflow {workflow_name} does not have an ImageScale node (node 50) required for upscale",
                )
        except (ValueError, FileNotFoundError):
            pass

        for dim_name in ("output_width", "output_height"):
            if dim_name in parameters:
                try:
                    val = int(parameters[dim_name])
                except (ValueError, TypeError):
                    return (
                        False,
                        f"{dim_name} must be 256-7680, got {parameters[dim_name]}",
                    )
                if val < 256 or val > 7680:
                    return False, f"{dim_name} must be 256-7680, got {val}"

    return True, None
