# api/app/infrastructure/security/step_secrets.py

"""Stored, run, job and viewer forms of a node's secrets: its Wait for Webhook token and signing secret, and the job parameters its service schema marks secret."""

import json
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from studio_workers.contracts.redaction import is_sensitive_key

from app.infrastructure.security.credential_encryption import (
    CredentialEncryption,
    get_credential_encryption,
)
from app.infrastructure.persistence.stored_secret_guard import (
    PAIR_NAME_FIELDS,
    PAIR_VALUE_FIELD,
    named_secret_paths,
)
from app.infrastructure.security.worker_enrollment import hash_secret

STEP_WEBHOOK_TOKEN = "webhook_token"
STEP_WEBHOOK_SECRET = "webhook_secret"
STEP_WEBHOOK_TOKEN_HASH = "webhook_token_hash"
STEP_WEBHOOK_KEYS = (STEP_WEBHOOK_TOKEN, STEP_WEBHOOK_SECRET, STEP_WEBHOOK_TOKEN_HASH)
_ENCRYPTED_META_KEYS = (STEP_WEBHOOK_TOKEN, STEP_WEBHOOK_SECRET)

# Wait for Webhook auth values the API verifies itself, secret whatever the installed schema says.
API_SECRET_PARAMETERS = ("webhook_auth_header_value", "webhook_jwt_secret")

# Schema format that marks a parameter value secret.
SECRET_FORMAT = "password"

# client_metadata key listing the parameter paths that hold a secret value; doubles as the configured flag.
SEALED_PARAMETERS = "sealed_parameters"

# Key of a queued job payload stored as one ciphertext.
SEALED_PAYLOAD = "_sealed_payload"

# Key of a sealed non-string parameter value, holding the ciphertext of its JSON.
SEALED_JSON = "_sealed_json"

# A {{ __instance_form__.field }} reference inside a parameter string.
FORM_TEMPLATE = re.compile(r"\{\{\s*__instance_form__\.([^\s.}]+)\s*\}\}")

Segment = Union[str, int]
Path = List[Segment]
Section = Dict[str, Any]
Cipher = Callable[[str], str]


def hash_step_webhook_token(token: str) -> str:
    """Lookup form of a step webhook token, stored beside its ciphertext."""
    return hash_secret(token)


def _filled(value: Any) -> bool:
    """Whether value is a non-empty string."""
    return isinstance(value, str) and bool(value)


def _schema_paths(value: Any, schema: Any, prefix: Path, out: List[Path]) -> None:
    """Append the path of every filled string under value that schema marks secret."""
    if not isinstance(schema, dict):
        return
    if isinstance(value, str):
        if value and schema.get("format") == SECRET_FORMAT:
            out.append(prefix)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _schema_paths(item, schema.get("items"), prefix + [index], out)
    elif isinstance(value, dict):
        props = schema.get("properties") or {}
        extra = schema.get("additionalProperties")
        for key, item in value.items():
            if key in props:
                _schema_paths(item, props[key], prefix + [key], out)
            elif isinstance(extra, dict):
                if _filled(item) and is_sensitive_key(key):
                    out.append(prefix + [key])
                else:
                    _schema_paths(item, extra, prefix + [key], out)


def secret_parameter_paths(
    parameters: Mapping[str, Any], schemas: Iterable[Mapping[str, Any]]
) -> List[Path]:
    """Paths of the filled values in parameters that any of schemas marks secret, that name an API-verified auth value, or whose key the stored-secret guard calls secret."""
    out: List[Path] = [[k] for k in API_SECRET_PARAMETERS if _filled(parameters.get(k))]
    for schema in schemas:
        found: List[Path] = []
        _schema_paths(dict(parameters), dict(schema), [], found)
        out.extend(p for p in found if p not in out)
    out.extend(p for p in named_secret_paths(dict(parameters)) if p not in out)
    return out


def _get(container: Any, path: Path) -> Tuple[bool, Any]:
    """Whether path exists in container, and its value."""
    node = container
    for seg in path:
        if isinstance(node, dict) and isinstance(seg, str) and seg in node:
            node = node[seg]
        elif isinstance(node, list) and isinstance(seg, int) and 0 <= seg < len(node):
            node = node[seg]
        else:
            return False, None
    return True, node


def _update(container: Any, path: Path, fn: Callable[[Any, Segment], Any]) -> Any:
    """Copy of container with fn applied to the parent of path and the last segment; unchanged when the parent is missing."""
    seg, rest = path[0], path[1:]
    if isinstance(container, dict) and isinstance(seg, str):
        if not rest:
            return fn(container, seg)
        if seg not in container:
            return container
        return {**container, seg: _update(container[seg], rest, fn)}
    if isinstance(container, list) and isinstance(seg, int) and 0 <= seg < len(container):
        if not rest:
            return fn(container, seg)
        copy = list(container)
        copy[seg] = _update(container[seg], rest, fn)
        return copy
    return container


def _set(container: Any, path: Path, value: Any) -> Any:
    """Copy of container with value at path, when its parent exists."""

    def put(parent: Any, seg: Segment) -> Any:
        if isinstance(parent, dict):
            return {**parent, seg: value}
        copy = list(parent)
        copy[int(seg)] = value
        return copy

    return _update(container, path, put)


def _remove(container: Any, path: Path) -> Any:
    """Copy of container without the value at path; a list slot is emptied, not removed."""

    def drop(parent: Any, seg: Segment) -> Any:
        if isinstance(parent, dict):
            return {k: v for k, v in parent.items() if k != seg}
        copy = list(parent)
        copy[int(seg)] = None
        return copy

    return _update(container, path, drop)


def _map_values(container: Any, paths: Iterable[Path], cipher: Cipher) -> Any:
    """Copy of container with each filled string at paths passed through cipher."""
    for path in paths:
        found, value = _get(container, path)
        if found and _filled(value):
            container = _set(container, path, cipher(value))
    return container


def without_secret_values(parameters: Any, paths: Iterable[Path]) -> Any:
    """Copy of parameters with the value at each path removed."""
    for path in paths:
        parameters = _remove(parameters, path)
    return parameters


def with_secret_values(parameters: Any, source: Any, paths: Iterable[Path]) -> Any:
    """Copy of parameters with each path it lacks filled from source."""
    for path in paths:
        if not _get(parameters, path)[0]:
            found, value = _get(source, path)
            if found:
                parameters = _set(parameters, path, value)
    return parameters


def _pair_names(item: Any) -> Optional[Tuple[Any, ...]]:
    """The name fields of a pair list item, or None when item is not a dict."""
    return tuple(item.get(f) for f in PAIR_NAME_FIELDS) if isinstance(item, dict) else None


def _pair_target(params: Any, stored: Any, path: Path, taken: List[Path]) -> Optional[Path]:
    """Where a stored secret at path goes in params: path itself when it is no pair value, else the value path of the first untaken incoming item with the stored pair's name, or None."""
    if len(path) < 2 or path[-1] != PAIR_VALUE_FIELD or not isinstance(path[-2], int):
        return path
    names = _pair_names(_get(stored, path[:-1])[1])
    items = _get(params, path[:-2])[1]
    if names is None or not isinstance(items, list):
        return None
    for index, item in enumerate(items):
        target = path[:-2] + [index, PAIR_VALUE_FIELD]
        if _pair_names(item) == names and target not in taken:
            return target
    return None


def keep_parameter_secrets(
    incoming: Dict[str, Any],
    stored: Dict[str, Any],
    paths: Iterable[Path],
    can_manage_secrets: bool,
) -> Dict[str, Any]:
    """Incoming parameters with stored secrets restored: always for a non-manager, a pair value into the incoming item with its name, and for a manager when a top-level one is absent."""
    params = dict(incoming)
    if not can_manage_secrets:
        for key in API_SECRET_PARAMETERS:
            params.pop(key, None)
    taken: List[Path] = []
    for path in paths:
        found, value = _get(stored, path)
        if not found:
            continue
        if can_manage_secrets:
            if len(path) == 1 and not _get(params, path)[0]:
                params = _set(params, path, value)
            continue
        target = _pair_target(params, stored, path, taken)
        if target is not None:
            taken.append(target)
            params = _set(params, target, value)
    return params


def step_secret_paths(step: Any) -> List[Path]:
    """Parameter paths a serialized step records as holding a secret."""
    meta = step.get("client_metadata") if isinstance(step, dict) else None
    paths = meta.get(SEALED_PARAMETERS) if isinstance(meta, dict) else None
    if not isinstance(paths, list):
        return []
    return [list(p) for p in paths if isinstance(p, list) and p]


def step_service_id(step: Any) -> Optional[str]:
    """Service id of a serialized step, at step or job level."""
    if not isinstance(step, dict):
        return None
    job = step.get("job")
    sid = step.get("service_id") or (job.get("service_id") if isinstance(job, dict) else None)
    return sid if isinstance(sid, str) and sid else None


def _params(step: Section) -> Optional[Dict[str, Any]]:
    """The step's job parameters when present as a dict."""
    job = step.get("job")
    params = job.get("parameters") if isinstance(job, dict) else None
    return params if isinstance(params, dict) else None


def _with_params(step: Section, params: Dict[str, Any]) -> Section:
    """Copy of step with its job parameters replaced."""
    return {**step, "job": {**step["job"], "parameters": params}}


def _with_paths(step: Section, paths: List[Path]) -> Section:
    """Copy of step recording paths, or recording none when there are none."""
    meta = step.get("client_metadata")
    kept = {k: v for k, v in meta.items() if k != SEALED_PARAMETERS} if isinstance(meta, dict) else {}
    if paths:
        kept[SEALED_PARAMETERS] = paths
    return {**step, "client_metadata": kept}


def mark_step_secrets(
    steps: Dict[str, Any], schemas: Mapping[str, Sequence[Mapping[str, Any]]]
) -> Dict[str, Any]:
    """Copy of plaintext steps each recording which parameter paths its service's schemas mark secret."""
    marked: Dict[str, Any] = {}
    for step_id, step in steps.items():
        if isinstance(step, dict):
            sid = step_service_id(step)
            paths = secret_parameter_paths(_params(step) or {}, schemas.get(sid or "", []))
            if paths or step_secret_paths(step):
                step = _with_paths(step, paths)
        marked[step_id] = step
    return marked


def _apply(section: Section, keys: Iterable[str], cipher: Cipher) -> Section:
    """Copy of section with each non-empty string under keys passed through cipher."""
    out = dict(section)
    for key in keys:
        if _filled(out.get(key)):
            out[key] = cipher(out[key])
    return out


def _map_steps(
    steps: Dict[str, Any],
    meta_fn: Callable[[Section], Section],
    step_fn: Callable[[Section], Section],
) -> Dict[str, Any]:
    """Copy of steps with meta_fn applied to webhook metadata and step_fn to each step recording parameter secrets."""
    mapped: Dict[str, Any] = {}
    for step_id, step in steps.items():
        if isinstance(step, dict):
            meta = step.get("client_metadata")
            if isinstance(meta, dict) and any(k in meta for k in STEP_WEBHOOK_KEYS):
                step = {**step, "client_metadata": meta_fn(meta)}
            if step_secret_paths(step):
                step = step_fn(step)
        mapped[step_id] = step
    return mapped


def _cipher_params(step: Section, cipher: Cipher) -> Section:
    """Copy of step with its recorded parameter secrets passed through cipher."""
    params = _params(step)
    if params is None:
        return step
    return _with_params(step, _map_values(params, step_secret_paths(step), cipher))


def _drop_params(step: Section, keep_paths: bool) -> Section:
    """Copy of step without its recorded parameter secret values, keeping the path record when keep_paths."""
    paths = step_secret_paths(step)
    if not paths:
        return step
    params = _params(step)
    if params is not None:
        step = _with_params(step, without_secret_values(params, paths))
    return step if keep_paths else _with_paths(step, [])


def _drop_api_secrets(step: Section) -> Section:
    """Copy of step without API-verified auth values, recorded or not."""
    params = _params(step)
    if params is None or not any(k in params for k in API_SECRET_PARAMETERS):
        return step
    return _with_params(
        step, {k: v for k, v in params.items() if k not in API_SECRET_PARAMETERS}
    )


def _open_params(step: Section) -> Section:
    """Copy of step with its recorded parameter secrets decrypted, sealed non-string values restored."""
    params = _params(step)
    if params is None:
        return step
    encryption = get_credential_encryption()
    paths = step_secret_paths(step)
    params = _map_values(params, paths, _decrypt_or_keep(encryption))
    for path in paths:
        value = _get(params, path)[1]
        if isinstance(value, dict) and list(value) == [SEALED_JSON] and isinstance(value[SEALED_JSON], str):
            params = _set(params, path, json.loads(encryption.decrypt(value[SEALED_JSON])))
    return _with_params(step, params)


def _decrypt_or_keep(encryption: CredentialEncryption) -> Cipher:
    """Decrypt a value, keeping one that is not ciphertext."""

    def cipher(value: str) -> str:
        try:
            return encryption.decrypt(value)
        except ValueError:
            return value

    return cipher


def _seal_meta(meta: Section, encryption: CredentialEncryption) -> Section:
    """Encrypted token and secret plus the token's lookup hash; a supplied hash is never trusted."""
    sealed = _apply(
        {k: v for k, v in meta.items() if k != STEP_WEBHOOK_TOKEN_HASH},
        _ENCRYPTED_META_KEYS,
        encryption.encrypt,
    )
    token = meta.get(STEP_WEBHOOK_TOKEN)
    if isinstance(token, str) and token:
        sealed[STEP_WEBHOOK_TOKEN_HASH] = hash_step_webhook_token(token)
    return sealed


def _open_meta(meta: Section, encryption: CredentialEncryption) -> Section:
    """Decrypted token and secret with the lookup hash removed."""
    return _apply(
        {k: v for k, v in meta.items() if k != STEP_WEBHOOK_TOKEN_HASH},
        _ENCRYPTED_META_KEYS,
        encryption.decrypt,
    )


def _without_meta(meta: Section) -> Section:
    """Metadata without any webhook token, secret or token hash."""
    return {k: v for k, v in meta.items() if k not in STEP_WEBHOOK_KEYS}


def seal_step_secrets(steps: Dict[str, Any]) -> Dict[str, Any]:
    """Marked steps in their stored form: webhook token, secret and recorded parameter secrets encrypted, token hash added."""
    return _map_steps(
        steps,
        lambda meta: _seal_meta(meta, get_credential_encryption()),
        lambda step: _cipher_params(step, get_credential_encryption().encrypt),
    )


def open_step_secrets(steps: Dict[str, Any]) -> Dict[str, Any]:
    """Stored steps in their domain form: secrets decrypted, token hash removed."""
    return _map_steps(
        steps,
        lambda meta: _open_meta(meta, get_credential_encryption()),
        _open_params,
    )


def snapshot_step_secrets(steps: Dict[str, Any]) -> Dict[str, Any]:
    """Domain steps in their run snapshot form: no webhook token or secret, parameter secrets encrypted."""
    return _map_steps(
        steps,
        _without_meta,
        lambda step: _cipher_params(step, get_credential_encryption().encrypt),
    )


def drop_step_secrets(steps: Dict[str, Any]) -> Dict[str, Any]:
    """Steps without any webhook token, secret, token hash, parameter secret or path record."""
    dropped = _map_steps(steps, _without_meta, lambda step: _drop_params(step, False))
    return {k: _drop_api_secrets(v) if isinstance(v, dict) else v for k, v in dropped.items()}


def strip_step_secrets(
    steps: Dict[str, Any], flag_token: bool = False
) -> Dict[str, Any]:
    """Copy of steps for a viewer without secret client_metadata or parameter values; flag_token keeps has_webhook_token and the path record as configured flags."""
    stripped: Dict[str, Any] = {}
    for step_id, step in steps.items():
        if isinstance(step, dict):
            step = _drop_api_secrets(_drop_params(step, flag_token))
            meta = step.get("client_metadata")
            if isinstance(meta, dict):
                kept = {k: v for k, v in meta.items() if not is_sensitive_key(k)}
                if flag_token and meta.get(STEP_WEBHOOK_TOKEN):
                    kept["has_webhook_token"] = True
                step = {**step, "client_metadata": kept}
        stripped[step_id] = step
    return stripped


def _under(path: Path, roots: Iterable[Path]) -> bool:
    """Whether path lies at or under any of roots."""
    return any(path[: len(root)] == root for root in roots)


def seal_form_parameters(
    step: Section, roots: Sequence[Path], schemas: Sequence[Mapping[str, Any]]
) -> Tuple[Section, List[Path]]:
    """Snapshot step with the secret values written under the run form's roots encrypted and recorded, and the roots that hold one."""
    params = _params(step)
    if params is None:
        return step, []
    recorded = step_secret_paths(step)
    paths: List[Path] = []
    for path in secret_parameter_paths(params, schemas) + recorded:
        if path not in paths and _under(path, roots) and _filled(_get(params, path)[1]):
            paths.append(path)
    if not paths:
        return step, []
    step = _with_params(step, _map_values(params, paths, get_credential_encryption().encrypt))
    step = _with_paths(step, recorded + [p for p in paths if p not in recorded])
    return step, [root for root in roots if any(_under(p, [root]) for p in paths)]


def seal_value(value: Any) -> Any:
    """Stored form of a secret parameter value: a string's ciphertext, or a wrapper holding the ciphertext of any other value's JSON."""
    encrypt = get_credential_encryption().encrypt
    return encrypt(value) if isinstance(value, str) else {SEALED_JSON: encrypt(json.dumps(value))}


def form_template_values(params: Any, lookup: Callable[[str], Tuple[bool, Any]]) -> List[Tuple[Path, Any]]:
    """Paths of parameter strings referencing a form field lookup finds, each rendered as the run renders it: a whole reference as the value, an embedded one as its text."""
    out: List[Tuple[Path, Any]] = []

    def walk(value: Any, path: Path) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, path + [key])
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, path + [index])
        elif isinstance(value, str) and "__instance_form__" in value and "[*]" not in value:
            whole = FORM_TEMPLATE.fullmatch(value.strip())
            if whole:
                found, resolved = lookup(whole.group(1))
                if found:
                    out.append((path, resolved))
                return
            hits: List[bool] = []

            def render(match: "re.Match[str]") -> str:
                found, resolved = lookup(match.group(1))
                hits.append(found)
                return str(resolved) if found else match.group(0)

            rendered = FORM_TEMPLATE.sub(render, value)
            if any(hits):
                out.append((path, rendered))

    walk(params, [])
    return out


def seal_parameter_values(step: Section, values: Sequence[Tuple[Path, Any]]) -> Section:
    """Copy of a snapshot step with each value written sealed at its parameter path and the path recorded."""
    job = step.get("job")
    params: Any = dict(_params(step) or {})
    recorded = step_secret_paths(step)
    written: List[Path] = []
    for path, value in values:
        updated = _set(params, path, seal_value(value))
        if _get(updated, path)[0]:
            params = updated
            written.append(path)
    if not written:
        return step
    step = {**step, "job": {**(job if isinstance(job, dict) else {}), "parameters": params}}
    return _with_paths(step, recorded + [p for p in written if p not in recorded])


def opened_parameters(step: Any) -> Optional[Dict[str, Any]]:
    """A snapshot step's job parameters with its recorded secrets decrypted, or None when it has none."""
    if not isinstance(step, dict):
        return None
    return _params(open_step_parameters(step))


def open_step_parameters(step: Dict[str, Any]) -> Dict[str, Any]:
    """One snapshot step with its recorded parameter secrets decrypted for a run."""
    if not step_secret_paths(step):
        return step
    return _open_params(step)


def seal_job_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """A job payload whose step records parameter secrets as one ciphertext; any other payload as is."""
    if not payload or not step_secret_paths(payload.get("step_config")):
        return payload
    return {SEALED_PAYLOAD: get_credential_encryption().encrypt(json.dumps(payload))}


def open_job_payload(stored: Dict[str, Any]) -> Dict[str, Any]:
    """Plaintext of a stored job payload."""
    if not stored or SEALED_PAYLOAD not in stored:
        return stored
    return json.loads(get_credential_encryption().decrypt(stored[SEALED_PAYLOAD]))
