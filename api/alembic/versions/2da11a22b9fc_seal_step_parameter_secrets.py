# api/alembic/versions/2da11a22b9fc_seal_step_parameter_secrets.py

"""seal step parameter secrets

Revision ID: 2da11a22b9fc
Revises: 0990a4cbc661
Create Date: 2026-10-21 04:56:55.119051

"""
import json
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa

if TYPE_CHECKING:
    from app.infrastructure.security.credential_encryption import CredentialEncryption


# revision identifiers, used by Alembic.
revision: str = '2da11a22b9fc'
down_revision: Union[str, Sequence[str], None] = '0990a4cbc661'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

API_KEYS = ("webhook_auth_header_value", "webhook_jwt_secret")
META_KEYS = ("webhook_token", "webhook_secret", "webhook_token_hash")
SEALED = "sealed_parameters"
SEALED_PAYLOAD = "_sealed_payload"
SECRET_FORMAT = "password"
SENSITIVE_TOKENS = (
    "secret", "password", "hashed_password", "api_key", "apikey", "api-key", "key",
    "token", "auth_token", "authorization", "bearer", "credential_id", "credential",
    "access_key", "access_token", "refresh_token", "private_key", "secret_key",
    "client_secret", "auth", "aws_secret", "signing_key", "webhook_secret", "encryption_key",
)

_HEADERS = {"headers": {"type": "object", "additionalProperties": {"type": "string"}}}

# Catalog secret marks as of this revision, applied even where the installed schema predates them.
FROZEN_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "shs/discord.discord_send_webhook": {
        "properties": {"webhook_url": {"type": "string", "format": SECRET_FORMAT}}
    },
    "shs/core.http_request": {"properties": _HEADERS},
    "shs/core.call_webhook": {"properties": _HEADERS},
    "shs/core.poll_service": {"properties": _HEADERS},
    "shs/json2video.j2v_render": {
        "properties": {
            "exports": {
                "type": "array",
                "items": {"properties": {"password": {"type": "string", "format": SECRET_FORMAT}}},
            }
        }
    },
}

Path = List[Union[str, int]]
Schemas = Dict[str, List[Dict[str, Any]]]
StepFn = Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]


class LazyEncryption:
    """The configured credential encryption, built on first use."""

    def __init__(self) -> None:
        self._enc: Optional["CredentialEncryption"] = None

    def _get(self) -> "CredentialEncryption":
        if self._enc is None:
            from app.config.settings import settings
            from app.infrastructure.security.credential_encryption import CredentialEncryption

            self._enc = CredentialEncryption(settings.CREDENTIAL_ENCRYPTION_KEY)
        return self._enc

    def encrypt(self, value: str) -> str:
        return self._get().encrypt(value)

    def decrypt(self, value: str) -> str:
        return self._get().decrypt(value)


def _sensitive(key: str) -> bool:
    """Whether key contains a secret-class token."""
    lower = key.lower()
    return any(t in lower for t in SENSITIVE_TOKENS)


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
                if _filled(item) and _sensitive(key):
                    out.append(prefix + [key])
                else:
                    _schema_paths(item, extra, prefix + [key], out)


def secret_paths(params: Dict[str, Any], schemas: Iterable[Dict[str, Any]]) -> List[Path]:
    """Paths in params holding an API-verified auth value or a value a schema marks secret."""
    out: List[Path] = [[k] for k in API_KEYS if _filled(params.get(k))]
    for schema in schemas:
        found: List[Path] = []
        _schema_paths(params, schema, [], found)
        out.extend(p for p in found if p not in out)
    return out


def _get(node: Any, path: Path) -> Tuple[bool, Any]:
    """Whether path exists under node, and its value."""
    for seg in path:
        if isinstance(node, dict) and isinstance(seg, str) and seg in node:
            node = node[seg]
        elif isinstance(node, list) and isinstance(seg, int) and 0 <= seg < len(node):
            node = node[seg]
        else:
            return False, None
    return True, node


def _update(node: Any, path: Path, fn: Callable[[Any, Union[str, int]], Any]) -> Any:
    """Copy of node with fn applied to the parent of path and its last segment."""
    seg, rest = path[0], path[1:]
    if isinstance(node, dict) and isinstance(seg, str):
        if not rest:
            return fn(node, seg)
        return {**node, seg: _update(node[seg], rest, fn)} if seg in node else node
    if isinstance(node, list) and isinstance(seg, int) and 0 <= seg < len(node):
        if not rest:
            return fn(node, seg)
        copy = list(node)
        copy[seg] = _update(node[seg], rest, fn)
        return copy
    return node


def _set(node: Any, path: Path, value: Any) -> Any:
    """Copy of node with value at path."""

    def put(parent: Any, seg: Union[str, int]) -> Any:
        if isinstance(parent, dict):
            return {**parent, seg: value}
        copy = list(parent)
        copy[int(seg)] = value
        return copy

    return _update(node, path, put)


def _remove(node: Any, path: Path) -> Any:
    """Copy of node without the value at path; a list slot is emptied."""

    def drop(parent: Any, seg: Union[str, int]) -> Any:
        if isinstance(parent, dict):
            return {k: v for k, v in parent.items() if k != seg}
        copy = list(parent)
        copy[int(seg)] = None
        return copy

    return _update(node, path, drop)


def _is_ciphertext(value: Any, encryption: Any) -> bool:
    """Whether value decrypts under the configured key."""
    try:
        encryption.decrypt(value)
        return True
    except ValueError:
        return False


def _service_id(step: Dict[str, Any]) -> Optional[str]:
    """Service id of a serialized step."""
    job = step.get("job")
    sid = step.get("service_id") or (job.get("service_id") if isinstance(job, dict) else None)
    return sid if isinstance(sid, str) else None


def _params(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The step's job parameters when a dict."""
    job = step.get("job")
    params = job.get("parameters") if isinstance(job, dict) else None
    return params if isinstance(params, dict) else None


def seal_step(step: Dict[str, Any], schemas: Schemas, encryption: Any) -> Optional[Dict[str, Any]]:
    """Step with its secret parameters encrypted and their paths recorded, or None when nothing changes."""
    params = _params(step)
    meta = step.get("client_metadata")
    if params is None or (isinstance(meta, dict) and SEALED in meta):
        return None
    paths = secret_paths(params, schemas.get(_service_id(step) or "", []))
    if not paths:
        return None
    for path in paths:
        value = _get(params, path)[1]
        if not _is_ciphertext(value, encryption):
            params = _set(params, path, encryption.encrypt(value))
    kept = dict(meta) if isinstance(meta, dict) else {}
    kept[SEALED] = paths
    return {**step, "client_metadata": kept, "job": {**step["job"], "parameters": params}}


def open_step(step: Dict[str, Any], encryption: Any) -> Optional[Dict[str, Any]]:
    """Step with its recorded secret parameters decrypted and the record dropped, or None when there is no record."""
    meta = step.get("client_metadata")
    if not isinstance(meta, dict) or SEALED not in meta:
        return None
    params = _params(step)
    if params is not None:
        for path in meta[SEALED]:
            found, value = _get(params, path)
            if found and _filled(value) and _is_ciphertext(value, encryption):
                params = _set(params, path, encryption.decrypt(value))
        step = {**step, "job": {**step["job"], "parameters": params}}
    return {**step, "client_metadata": {k: v for k, v in meta.items() if k != SEALED}}


def rewrite_steps(steps: Any, fn: StepFn) -> Tuple[Any, bool]:
    """Steps with fn applied to each dict step, and whether any changed."""
    if not isinstance(steps, dict):
        return steps, False
    changed = False
    out: Dict[str, Any] = {}
    for step_id, step in steps.items():
        new = fn(step) if isinstance(step, dict) else None
        if new is not None:
            step, changed = new, True
        out[step_id] = step
    return out, changed


def scrub(params: Any, schemas: Iterable[Dict[str, Any]]) -> Tuple[Any, bool]:
    """Params without API-verified auth values or schema-marked secret values, and whether any were removed."""
    if not isinstance(params, dict):
        return params, False
    paths = secret_paths(params, schemas)
    for path in paths:
        params = _remove(params, path)
    return params, bool(paths)


def load_schemas(bind: Any) -> Schemas:
    """Every installed service's parameter schema plus this revision's frozen catalog marks, by service id."""
    schemas: Schemas = {}
    for service_id, schema in bind.execute(
        sa.text("SELECT service_id, parameter_schema FROM provider_services")
    ).fetchall():
        if isinstance(schema, str):
            schema = json.loads(schema)
        if isinstance(schema, dict):
            schemas.setdefault(service_id, []).append(schema)
    for service_id, schema in FROZEN_SCHEMAS.items():
        schemas.setdefault(service_id, []).append(schema)
    return schemas


def _marks_secret(schema: Any) -> bool:
    """Whether schema marks any value secret."""
    if isinstance(schema, dict):
        if schema.get("format") == SECRET_FORMAT or isinstance(schema.get("additionalProperties"), dict):
            return True
        return any(_marks_secret(v) for v in schema.values())
    if isinstance(schema, list):
        return any(_marks_secret(v) for v in schema)
    return False


def candidates(schemas: Schemas) -> List[str]:
    """LIKE patterns for rows that may hold a step secret: each marked service id, then each API auth key."""
    ids = [sid for sid, items in schemas.items() if any(_marks_secret(s) for s in items)]
    return [f'%"{sid}"%' for sid in sorted(ids)] + [f'%"{k}"%' for k in API_KEYS]


def _like_any(column: str, patterns: List[str]) -> Tuple[str, Dict[str, str]]:
    """SQL OR of column::text LIKE each pattern, with its bind params."""
    binds = {f"p{i}": p for i, p in enumerate(patterns)}
    return "(" + " OR ".join(f"{column}::text LIKE :{k}" for k in binds) + ")", binds


def _key_binds(binds: Dict[str, str]) -> List[str]:
    """Bind names of the API auth key patterns, which candidates puts last."""
    return list(binds)[-len(API_KEYS):]


def rewrite_versions(bind: Any, fn: StepFn, patterns: List[str]) -> int:
    """Apply fn to every step of the workflow_versions rows matching patterns; returns rows updated."""
    where, binds = _like_any("steps", patterns)
    updated = 0
    for row_id, steps in bind.execute(
        sa.text(f"SELECT id, steps FROM workflow_versions WHERE {where}"), binds
    ).fetchall():
        new_steps, changed = rewrite_steps(steps, fn)
        if changed:
            bind.execute(
                sa.text("UPDATE workflow_versions SET steps = CAST(:v AS jsonb) WHERE id = :id"),
                {"v": json.dumps(new_steps), "id": row_id},
            )
            updated += 1
    return updated


def rewrite_snapshots(bind: Any, fn: StepFn, patterns: List[str]) -> int:
    """Apply fn to every step of the instance snapshots matching patterns; returns rows updated."""
    where, binds = _like_any("workflow_snapshot", patterns)
    updated = 0
    for row_id, snap in bind.execute(
        sa.text(f"SELECT id, workflow_snapshot FROM instances WHERE {where}"), binds
    ).fetchall():
        if not isinstance(snap, dict):
            continue
        new_steps, changed = rewrite_steps(snap.get("steps"), fn)
        if changed:
            bind.execute(
                sa.text("UPDATE instances SET workflow_snapshot = CAST(:v AS jsonb) WHERE id = :id"),
                {"v": json.dumps({**snap, "steps": new_steps}), "id": row_id},
            )
            updated += 1
    return updated


def _step_schemas(step: Any, schemas: Schemas) -> List[Dict[str, Any]]:
    """Schemas of a snapshot step's service."""
    return schemas.get(_service_id(step) or "", []) if isinstance(step, dict) else []


def scrub_step_executions(bind: Any, schemas: Schemas, patterns: List[str]) -> int:
    """Remove step secrets from step_executions input_data, request_body, parameters, execution_data and iteration_requests; returns rows updated."""
    snap_where, binds = _like_any("i.workflow_snapshot", patterns)
    columns = ("input_data", "request_body", "parameters", "execution_data", "iteration_requests")
    row_where = " OR ".join(f"se.{c}::text LIKE :{k}" for c in columns for k in _key_binds(binds))
    rows = bind.execute(
        sa.text(
            "SELECT se.id, se.input_data, se.request_body, se.parameters, se.execution_data, "
            "se.iteration_requests, i.workflow_snapshot -> 'steps' -> se.step_key "
            "FROM step_executions se JOIN instances i ON i.id = se.instance_id "
            f"WHERE {snap_where} OR {row_where}"
        ),
        binds,
    ).fetchall()
    updated = 0
    for row_id, input_data, request_body, parameters, execution_data, iteration_requests, step in rows:
        step_schemas = _step_schemas(step, schemas)
        changes: Dict[str, Any] = {}
        for column, holder in (("input_data", input_data), ("execution_data", execution_data)):
            if isinstance(holder, dict):
                cleaned, changed = scrub(holder.get("parameters"), step_schemas)
                if changed:
                    changes[column] = {**holder, "parameters": cleaned}
        for column, value in (("request_body", request_body), ("parameters", parameters)):
            cleaned, changed = scrub(value, step_schemas)
            if changed:
                changes[column] = cleaned
        if isinstance(iteration_requests, list):
            cleaned_requests: List[Any] = []
            for req in iteration_requests:
                if isinstance(req, dict):
                    cleaned, changed = scrub(req.get("params"), step_schemas)
                    if changed:
                        req = {**req, "params": cleaned}
                        changes["iteration_requests"] = cleaned_requests
                cleaned_requests.append(req)
        if changes:
            sets = ", ".join(f"{c} = CAST(:{c} AS jsonb)" for c in changes)
            bind.execute(
                sa.text(f"UPDATE step_executions SET {sets} WHERE id = :id"),
                {**{c: json.dumps(v) for c, v in changes.items()}, "id": row_id},
            )
            updated += 1
    return updated


def scrub_iteration_executions(bind: Any, schemas: Schemas, patterns: List[str]) -> int:
    """Remove step secrets from iteration_executions.parameters; returns rows updated."""
    snap_where, binds = _like_any("i.workflow_snapshot", patterns)
    row_where = " OR ".join(f"ie.parameters::text LIKE :{k}" for k in _key_binds(binds))
    rows = bind.execute(
        sa.text(
            "SELECT ie.id, ie.parameters, i.workflow_snapshot -> 'steps' -> se.step_key "
            "FROM iteration_executions ie "
            "JOIN step_executions se ON se.id = ie.step_id "
            "JOIN instances i ON i.id = ie.instance_id "
            f"WHERE {snap_where} OR {row_where}"
        ),
        binds,
    ).fetchall()
    updated = 0
    for row_id, parameters, step in rows:
        cleaned, changed = scrub(parameters, _step_schemas(step, schemas))
        if changed:
            bind.execute(
                sa.text("UPDATE iteration_executions SET parameters = CAST(:v AS jsonb) WHERE id = :id"),
                {"v": json.dumps(cleaned), "id": row_id},
            )
            updated += 1
    return updated


def seal_payload(payload: Any, schemas: Schemas, encryption: Any) -> Optional[Dict[str, Any]]:
    """Payload without node webhook secrets, sealed whole when its step carries parameter secrets; None when unchanged."""
    if not isinstance(payload, dict) or SEALED_PAYLOAD in payload:
        return None
    step = payload.get("step_config")
    if not isinstance(step, dict):
        return None
    changed = False
    meta = step.get("client_metadata")
    if isinstance(meta, dict) and any(k in meta for k in META_KEYS):
        meta = {k: v for k, v in meta.items() if k not in META_KEYS}
        step = {**step, "client_metadata": meta}
        changed = True
    params = _params(step)
    if params is not None and any(k in params for k in API_KEYS):
        params = {k: v for k, v in params.items() if k not in API_KEYS}
        step = {**step, "job": {**step["job"], "parameters": params}}
        changed = True
    sid = _service_id(step) or payload.get("service_id") or ""
    paths = secret_paths(params or {}, schemas.get(sid, []))
    if paths:
        kept = dict(meta) if isinstance(meta, dict) else {}
        kept[SEALED] = paths
        sealed = {**payload, "step_config": {**step, "client_metadata": kept}}
        return {SEALED_PAYLOAD: encryption.encrypt(json.dumps(sealed))}
    return {**payload, "step_config": step} if changed else None


def seal_queued_jobs(bind: Any, schemas: Schemas, patterns: List[str], encryption: Any) -> int:
    """Seal or scrub every queued job payload that may hold a step secret; returns rows updated."""
    where, binds = _like_any("payload", patterns + [f'%"{k}"%' for k in META_KEYS])
    updated = 0
    for row_id, payload in bind.execute(
        sa.text(f"SELECT id, payload FROM queued_jobs WHERE {where}"), binds
    ).fetchall():
        if isinstance(payload, str):
            payload = json.loads(payload)
        new = seal_payload(payload, schemas, encryption)
        if new is not None:
            bind.execute(
                sa.text("UPDATE queued_jobs SET payload = CAST(:v AS json) WHERE id = :id"),
                {"v": json.dumps(new), "id": row_id},
            )
            updated += 1
    return updated


def open_queued_jobs(bind: Any, encryption: Any) -> int:
    """Unseal every sealed queued job payload; returns rows updated."""
    updated = 0
    for row_id, payload in bind.execute(
        sa.text("SELECT id, payload FROM queued_jobs WHERE payload::text LIKE :p"),
        {"p": f'%"{SEALED_PAYLOAD}"%'},
    ).fetchall():
        if isinstance(payload, str):
            payload = json.loads(payload)
        if isinstance(payload, dict) and SEALED_PAYLOAD in payload:
            bind.execute(
                sa.text("UPDATE queued_jobs SET payload = CAST(:v AS json) WHERE id = :id"),
                {"v": encryption.decrypt(payload[SEALED_PAYLOAD]), "id": row_id},
            )
            updated += 1
    return updated


def seal_all(bind: Any) -> Dict[str, int]:
    """Seal step parameter secrets at rest and scrub them from run records; returns rows updated per table."""
    schemas = load_schemas(bind)
    patterns = candidates(schemas)
    encryption = LazyEncryption()
    return {
        "workflow_versions": rewrite_versions(bind, lambda s: seal_step(s, schemas, encryption), patterns),
        "instances": rewrite_snapshots(bind, lambda s: seal_step(s, schemas, encryption), patterns),
        "step_executions": scrub_step_executions(bind, schemas, patterns),
        "iteration_executions": scrub_iteration_executions(bind, schemas, patterns),
        "queued_jobs": seal_queued_jobs(bind, schemas, patterns, encryption),
    }


def open_all(bind: Any) -> Dict[str, int]:
    """Decrypt recorded step parameter secrets and unseal queued payloads; returns rows updated per table."""
    encryption = LazyEncryption()
    patterns = [f'%"{SEALED}"%']
    return {
        "workflow_versions": rewrite_versions(bind, lambda s: open_step(s, encryption), patterns),
        "instances": rewrite_snapshots(bind, lambda s: open_step(s, encryption), patterns),
        "queued_jobs": open_queued_jobs(bind, encryption),
    }


def upgrade() -> None:
    """Encrypt schema-marked node parameters at rest and scrub node secrets from run records."""
    counts = seal_all(op.get_bind())
    logger.info(f"step parameter secrets sealed: {counts}")


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
