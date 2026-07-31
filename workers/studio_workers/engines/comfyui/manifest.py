# workers/studio_workers/engines/comfyui/manifest.py

"""Manifest-driven graph injection for catalog comfyui packages.

A manifest-bearing package (service + parameters + node_mappings + graph)
is the only executable unit: the worker resolves every job to a synced
package and injects parameters from its manifest.
"""

from __future__ import annotations

import copy
import logging
import random
from dataclasses import dataclass, field
from math import gcd
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PackageManifest:
    """Runtime view of one manifest-bearing package."""

    slug: str
    version: str
    service_id: str
    queue: str
    media: str
    graph: Dict[str, Any]
    parameters: Dict[str, Any] = field(default_factory=dict)
    node_mappings: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    models: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    default_model: Optional[str] = None
    generation: Dict[str, Any] = field(default_factory=dict)
    capabilities: Dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_package(cls, package: Dict[str, Any]) -> Optional["PackageManifest"]:
        """Build from a package dict; None when the package carries no manifest."""
        service = package.get("service")
        graph = package.get("graph")
        if not service or not graph or not package.get("node_mappings"):
            return None
        models = {m["id"]: m for m in package.get("models", [])}
        default_model = next(
            (mid for mid, m in models.items() if m.get("default")), None
        )
        return cls(
            slug=package.get("slug", ""),
            version=package.get("version", ""),
            service_id=service["id"],
            queue=service["queue"],
            media=service.get("media", "image"),
            graph=graph,
            parameters=package.get("parameters", {}),
            node_mappings=package["node_mappings"],
            models=models,
            default_model=default_model,
            generation=package.get("generation", {}),
            capabilities=package.get("capabilities", {}),
        )

    def defaults(self) -> Dict[str, Any]:
        return {
            name: spec["default"]
            for name, spec in self.parameters.items()
            if "default" in spec
        }


def _set_path(node: Dict[str, Any], path: str, value: Any) -> None:
    """Set a dotted literal path inside a node spec, creating dicts as needed."""
    keys = path.split(".")
    target = node
    for key in keys[:-1]:
        target = target.setdefault(key, {})
    target[keys[-1]] = value


def _split_dimensions(value: str) -> Tuple[int, int]:
    w, h = value.lower().split("x", 1)
    return int(w), int(h)


def _calculate_generation_dimensions(
    output_width: int,
    output_height: int,
    min_side: int = 512,
    max_side: int = 2048,
    snap: int = 64,
) -> Tuple[int, int]:
    """Smallest gen dims that preserve exact aspect ratio: both multiples of snap, both >= min_side.

    Falls back to approximate rounding for non-standard ratios that would produce dims > max_side.
    Examples: 1920x1080 -> 1024x576; 1080x1080 -> 512x512; 800x600 -> 768x576.
    """
    g = gcd(output_width, output_height)
    ratio_w = output_width // g
    ratio_h = output_height // g

    # Smallest scale s where both ratio*s land on snap-boundaries.
    s_w = snap // gcd(ratio_w, snap)
    s_h = snap // gcd(ratio_h, snap)
    base_s = (s_w * s_h) // gcd(s_w, s_h)

    s = base_s
    while ratio_w * s < min_side or ratio_h * s < min_side:
        s += base_s

    gen_w = ratio_w * s
    gen_h = ratio_h * s

    # Non-standard ratios can blow past max_side - fall back to approximate.
    if gen_w > max_side or gen_h > max_side:
        if output_width >= output_height:
            gen_h = min_side
            gen_w = round(min_side * output_width / output_height / snap) * snap
        else:
            gen_w = min_side
            gen_h = round(min_side * output_height / output_width / snap) * snap
        gen_w = max(gen_w, min_side)
        gen_h = max(gen_h, min_side)

    return gen_w, gen_h


def inject_from_manifest(
    manifest: PackageManifest,
    parameters: Dict[str, Any],
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Inject parameters into the manifest's graph; returns a new dict.

    Merge order is package defaults, then model defaults, then user params;
    seed -1 randomizes; output dims come from explicit
    output_width/output_height (legacy payloads) or the dimensions enum;
    gen dims derive inside the package's generation band.
    """
    workflow = copy.deepcopy(manifest.graph)

    model_entry = manifest.models.get(model, {}) if model else {}
    merged = {**manifest.defaults(), **model_entry.get("defaults", {}), **parameters}

    if merged.get("seed", -1) == -1:
        merged["seed"] = random.randint(0, 2**32 - 1)

    if "output_width" in merged and "output_height" in merged:
        out_w = int(merged["output_width"])
        out_h = int(merged["output_height"])
    else:
        out_w, out_h = _split_dimensions(str(merged.get("dimensions", "1920x1080")))
    merged["output_width"] = out_w
    merged["output_height"] = out_h

    gen = manifest.generation
    if merged.get("upscale", False):
        merged["width"], merged["height"] = _calculate_generation_dimensions(
            out_w,
            out_h,
            min_side=gen.get("min_side", 512),
            max_side=gen.get("max_side", 2048),
            snap=gen.get("snap", 64),
        )
    else:
        merged["width"] = out_w
        merged["height"] = out_h

    for name, value in merged.items():
        for target in manifest.node_mappings.get(name, []):
            node_id = target["node"]
            if node_id not in workflow:
                logger.warning(f"Node {node_id} not found for parameter {name}")
                continue
            _set_path(workflow[node_id], target["path"], value)

    for assignment in model_entry.get("assignments", []):
        node_id = assignment["node"]
        if node_id not in workflow:
            logger.warning(f"Node {node_id} not found for model {model}")
            continue
        _set_path(workflow[node_id], assignment["path"], assignment["value"])

    return workflow


def _option_values(spec: Dict[str, Any]) -> List[Any]:
    return [
        opt["value"] if isinstance(opt, dict) else opt
        for opt in spec.get("options", [])
    ]


def validate_manifest_parameters(
    manifest: PackageManifest,
    parameters: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """Validate user parameters against the manifest's parameter specs."""
    for name, spec in manifest.parameters.items():
        if spec.get("required") and not parameters.get(name):
            return False, f"Parameter '{name}' is required"

    for name, value in parameters.items():
        spec = manifest.parameters.get(name)
        if spec is None:
            continue
        ptype = spec.get("type")
        if ptype in ("integer", "float"):
            try:
                num = int(value) if ptype == "integer" else float(value)
            except (TypeError, ValueError):
                return False, f"Parameter '{name}' must be a number"
            if "min" in spec and num < spec["min"]:
                return False, f"Parameter '{name}' must be >= {spec['min']}"
            if "max" in spec and num > spec["max"]:
                return False, f"Parameter '{name}' must be <= {spec['max']}"
        elif ptype == "enum":
            if value not in _option_values(spec):
                return False, f"Parameter '{name}' has invalid value '{value}'"

    return True, None
