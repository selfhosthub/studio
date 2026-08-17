# workers/studio_workers/engines/comfyui/model_map.py

"""Rewrite a package's model filenames to the values this ComfyUI accepts.

A package names a model by bare filename. ComfyUI accepts only the names it
reports for the node input being filled, and those carry whatever subfolder the
file sits in (``FLUX1/ae.safetensors``). ComfyUI Manager installs into
subfolders, so the bare name does not resolve on a Manager-installed host.

Resolution is per node input, never global: ComfyUI already restricts each input
to one kind of model, so the same filename under two kinds can never be
confused, and no list of model directories is needed here.

The map is built once, from the first ``/object_info`` that parses, then frozen.
A model added afterwards needs a worker restart.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# (node class, input name) -> the names ComfyUI accepts for it
ModelMap = Dict[Tuple[str, str], List[str]]


class ModelNotFoundError(Exception):
    """A declared model has no usable name on this ComfyUI host."""


def _basename(value: str) -> str:
    return value.rsplit("/", 1)[-1]


def _looks_like_a_file(value: Any) -> bool:
    """A widget option naming a file rather than an arbitrary enum member.

    Model options carry a filename with an extension; sampler and scheduler
    names do not, so they never enter the map.
    """
    return (
        isinstance(value, str)
        and "." in _basename(value)
        and not value.startswith("/")
    )


def build_model_map(object_info: Dict[str, Any]) -> ModelMap:
    """Index the file-shaped options of every node input.

    ``/object_info`` reports what ComfyUI will accept, which is not the same as
    what is on disk: a kind maps to any number of roots via
    ``extra_model_paths.yaml``, and extension filtering and custom-node loaders
    move the two further apart. A model whose node class is not installed is
    absent here, which is correct, because it cannot run.
    """
    index: ModelMap = {}

    for node_class, spec in object_info.items():
        if not isinstance(spec, dict):
            continue
        inputs = spec.get("input") or {}
        declared = {**(inputs.get("required") or {}), **(inputs.get("optional") or {})}
        for input_name, definition in declared.items():
            # A widget definition is [options, config]; enum options are a list.
            if not isinstance(definition, (list, tuple)) or not definition:
                continue
            options = definition[0]
            if not isinstance(options, list):
                continue
            files = [o for o in options if _looks_like_a_file(o)]
            if files:
                index[(node_class, input_name)] = files

    return index


def _subfolder(value: str) -> str:
    """Path in front of the filename, empty when the file sits at the root."""
    return value.rsplit("/", 1)[0] if "/" in value else ""


def _declared_subfolder(declared_directory: str) -> str:
    """The declared path minus its leading kind.

    A package declares ``vae/FLUX1``; ComfyUI reports ``FLUX1/ae.safetensors``,
    named within the ``vae`` kind. The kind is decided by the node and never
    appears in the value.
    """
    parts = declared_directory.strip("/").split("/", 1)
    return parts[1] if len(parts) > 1 else ""


def resolve(
    model_map: ModelMap,
    node_class: str,
    input_name: str,
    filename: str,
    declared_directory: Optional[str] = None,
) -> str:
    """The name to send ComfyUI for a declared filename.

    1. the declared subfolder holds the file, use it
    2. otherwise exactly one file with that name on this input, use it
    3. zero matches, or two-plus with none in the declared subfolder, fail
    """
    wanted = _basename(filename)
    matches = sorted(
        {v for v in model_map.get((node_class, input_name), []) if _basename(v) == wanted}
    )

    if declared_directory:
        target = _declared_subfolder(declared_directory)
        for value in matches:
            if _subfolder(value) == target:
                return value

    if len(matches) == 1:
        return matches[0]

    logger.debug(
        "model %r for %s.%s declared in %r: %d candidates: %s",
        filename,
        node_class,
        input_name,
        declared_directory,
        len(matches),
        matches,
    )
    raise ModelNotFoundError(f"model not found: {filename}")


def resolve_graph_models(
    graph: Dict[str, Any],
    model_map: ModelMap,
    declared_directories: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Rewrite every model filename in a graph to the name ComfyUI accepts.

    Walks the graph rather than a list of known loaders, so a custom node's
    model input resolves the same way a built-in one does. An input ComfyUI does
    not report as file-valued is left untouched.
    """
    directories = declared_directories or {}

    for node in graph.values():
        if not isinstance(node, dict):
            continue
        node_class = node.get("class_type")
        inputs = node.get("inputs")
        if not node_class or not isinstance(inputs, dict):
            continue
        for input_name, value in inputs.items():
            if not isinstance(value, str):
                continue
            if (node_class, input_name) not in model_map:
                continue
            inputs[input_name] = resolve(
                model_map,
                node_class,
                input_name,
                value,
                directories.get(_basename(value)),
            )

    return graph
