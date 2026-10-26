# api/alembic/versions/7bd2534f9bda_seal_run_form_secrets.py

"""seal run form secrets

Revision ID: 7bd2534f9bda
Revises: 2da11a22b9fc
Create Date: 2026-10-21 05:19:36.830159

"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7bd2534f9bda'
down_revision: Union[str, Sequence[str], None] = '2da11a22b9fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

SEALED = "sealed_parameters"
SEALED_PAYLOAD = "_sealed_payload"
SEALED_JSON = "_sealed_json"

Path = List[Union[str, int]]
Schemas = Dict[str, List[Dict[str, Any]]]


def _segments(key: str) -> Path:
    """Segments of a bracket/dot parameter key, list indexes as ints."""
    return [int(p) if p.isdigit() else p for p in re.split(r"\.|\[(\d+)\]", key) if p]


def _under(path: Path, root: Path) -> bool:
    """Whether path lies at or under root."""
    return path[: len(root)] == root


def form_roots(step: Dict[str, Any]) -> Dict[str, Path]:
    """Form-mapped parameter keys of a snapshot step with their paths."""
    mappings: Dict[str, Any] = {}
    for holder in (step, step.get("client_metadata")):
        found = holder.get("input_mappings") if isinstance(holder, dict) else None
        if isinstance(found, dict):
            mappings.update(found)
    return {
        key: _segments(key)
        for key, m in mappings.items()
        if isinstance(m, dict) and (m.get("mappingType") or m.get("mapping_type")) == "form"
    }


def _get(node: Any, path: Path) -> Any:
    """Value at path under node, or None."""
    for seg in path:
        if isinstance(node, dict) and isinstance(seg, str):
            node = node.get(seg)
        elif isinstance(node, list) and isinstance(seg, int) and 0 <= seg < len(node):
            node = node[seg]
        else:
            return None
    return node


def _set(node: Any, path: Path, value: Any) -> Any:
    """Copy of node with value at path, which exists."""
    seg, rest = path[0], path[1:]
    if isinstance(node, list):
        copy = list(node)
        copy[int(seg)] = _set(node[int(seg)], rest, value) if rest else value
        return copy
    return {**node, seg: _set(node[seg], rest, value) if rest else value}


def _is_ciphertext(value: str, encryption: Any) -> bool:
    """Whether value decrypts under the configured key."""
    try:
        encryption.decrypt(value)
        return True
    except ValueError:
        return False


def seal_step(step: Any, schemas: Schemas, encryption: Any) -> Tuple[Any, List[str]]:
    """Step with the secret values under its form roots encrypted and recorded, and the form keys holding one."""
    from app.infrastructure.security.step_secrets import (
        secret_parameter_paths,
        step_secret_paths,
        step_service_id,
    )

    job = step.get("job") if isinstance(step, dict) else None
    if not isinstance(job, dict):
        return step, []
    params = job.get("parameters")
    roots = form_roots(step)
    if not isinstance(params, dict) or not roots:
        return step, []
    recorded = step_secret_paths(step)
    paths: List[Path] = []
    for path in secret_parameter_paths(params, schemas.get(step_service_id(step) or "", [])) + recorded:
        value = _get(params, path)
        if path in paths or not (isinstance(value, str) and value):
            continue
        if any(_under(path, r) for r in roots.values()):
            paths.append(path)
            if not _is_ciphertext(value, encryption):
                params = _set(params, path, encryption.encrypt(value))
    if not paths:
        return step, []
    meta = step.get("client_metadata")
    kept = dict(meta) if isinstance(meta, dict) else {}
    kept[SEALED] = recorded + [p for p in paths if p not in recorded]
    sealed = {**step, "client_metadata": kept, "job": {**job, "parameters": params}}
    return sealed, [k for k, r in roots.items() if any(_under(p, r) for p in paths)]


def _remove(node: Any, path: Path) -> Any:
    """Copy of node without the value at path, when present."""
    seg, rest = path[0], path[1:]
    if isinstance(node, dict) and isinstance(seg, str) and seg in node:
        if not rest:
            return {k: v for k, v in node.items() if k != seg}
        return {**node, seg: _remove(node[seg], rest)}
    if isinstance(node, list) and isinstance(seg, int) and 0 <= seg < len(node):
        copy = list(node)
        copy[seg] = _remove(node[seg], rest) if rest else None
        return copy
    return node


def target_values(steps: Dict[str, Any], form: Dict[str, Any], keys: List[str]) -> Dict[str, List[Tuple[Path, Any]]]:
    """Per node, the parameter paths an __instance_form__ mapping or template fills from a sealed form key, with the value the run used."""
    from app.infrastructure.security.step_secrets import form_template_values

    def lookup(field: str) -> Tuple[bool, Any]:
        key = next((k for k in form if k == field or k.endswith(f".{field}")), None)
        return (key in keys, form[key] if key in keys else None)

    out: Dict[str, List[Tuple[Path, Any]]] = {}
    for step_id, step in steps.items():
        if not isinstance(step, dict):
            continue
        job = step.get("job")
        params = job.get("parameters") if isinstance(job, dict) else None
        if isinstance(params, dict):
            found = form_template_values(params, lookup)
            if found:
                out.setdefault(step_id, []).extend(found)
        mappings: Dict[str, Any] = {}
        for holder in (step.get("client_metadata"), step):
            found = holder.get("input_mappings") if isinstance(holder, dict) else None
            if isinstance(found, dict):
                mappings.update(found)
        for param_key, m in mappings.items():
            if param_key.startswith("_prompt_variable:") or not isinstance(m, dict):
                continue
            if m.get("mappingType") != "mapped" or m.get("stepId") != "__instance_form__":
                continue
            field = str(m.get("outputField") or "")
            key = next((k for k in form if k == field or k.endswith(f".{field}")), None)
            if key in keys and form[key] not in ("", None):
                out.setdefault(step_id, []).append((_segments(param_key), form[key]))
    return out


def seal_target(step: Dict[str, Any], values: List[Tuple[Path, Any]], encryption: Any) -> Dict[str, Any]:
    """Step with each value written sealed at its parameter path, a non-string as the ciphertext of its JSON, and the path recorded."""
    job = step.get("job") if isinstance(step.get("job"), dict) else {}
    params: Any = dict(job.get("parameters") or {}) if isinstance(job, dict) else {}
    meta = step.get("client_metadata")
    kept = dict(meta) if isinstance(meta, dict) else {}
    recorded = [p for p in kept.get(SEALED) or [] if isinstance(p, list)]
    for path, value in values:
        if len(path) == 1 or _get(params, path[:-1]) is not None:
            sealed = encryption.encrypt(value) if isinstance(value, str) else {SEALED_JSON: encryption.encrypt(json.dumps(value))}
            params = _set(params, path, sealed)
            if path not in recorded:
                recorded.append(path)
    kept[SEALED] = recorded
    return {**step, "client_metadata": kept, "job": {**(job if isinstance(job, dict) else {}), "parameters": params}}


def scrub_step_records(bind: Any, instance_id: Any, targets: Dict[str, List[Tuple[Path, Any]]]) -> int:
    """Remove the target paths from the target nodes' step_executions and iteration_executions records; returns step rows updated."""
    updated = 0
    for step_key, values in targets.items():
        paths = [p for p, _ in values]
        rows = bind.execute(
            sa.text(
                "SELECT id, input_data, request_body, parameters, execution_data, iteration_requests "
                "FROM step_executions WHERE instance_id = :i AND step_key = :k"
            ),
            {"i": instance_id, "k": step_key},
        ).fetchall()
        for row in rows:
            row_id, cols = row[0], dict(zip(
                ("input_data", "request_body", "parameters", "execution_data", "iteration_requests"), row[1:]
            ))
            new = dict(cols)
            for path in paths:
                for col in ("request_body", "parameters"):
                    new[col] = _remove(new[col], path)
                for col in ("input_data", "execution_data"):
                    if isinstance(new[col], dict) and "parameters" in new[col]:
                        new[col] = {**new[col], "parameters": _remove(new[col]["parameters"], path)}
                if isinstance(new["iteration_requests"], list):
                    new["iteration_requests"] = [
                        {**r, "params": _remove(r.get("params"), path)} if isinstance(r, dict) else r
                        for r in new["iteration_requests"]
                    ]
            changes = {c: v for c, v in new.items() if v != cols[c]}
            if changes:
                sets = ", ".join(f"{c} = CAST(:{c} AS jsonb)" for c in changes)
                bind.execute(
                    sa.text(f"UPDATE step_executions SET {sets} WHERE id = :id"),
                    {**{c: json.dumps(v) for c, v in changes.items()}, "id": row_id},
                )
                updated += 1
            for it_id, it_params in bind.execute(
                sa.text("SELECT id, parameters FROM iteration_executions WHERE step_id = :s"),
                {"s": row_id},
            ).fetchall():
                cleaned = it_params
                for path in paths:
                    cleaned = _remove(cleaned, path)
                if cleaned != it_params:
                    bind.execute(
                        sa.text("UPDATE iteration_executions SET parameters = CAST(:v AS jsonb) WHERE id = :id"),
                        {"v": json.dumps(cleaned), "id": it_id},
                    )
    return updated


def scrub_input(data: Any, keys: List[str]) -> Any:
    """Input data without the form values at keys or any top-level copy of them."""
    if not isinstance(data, dict) or not isinstance(data.get("form_values"), dict):
        return data
    form = data["form_values"]
    removed = [form[k] for k in keys if k in form and form[k] not in ("", None)]
    if not removed:
        return data
    kept = {k: v for k, v in data.items() if k == "form_values" or v not in removed}
    kept["form_values"] = {k: v for k, v in form.items() if k not in keys}
    return kept


def _load_schemas(bind: Any) -> Schemas:
    """Every installed service's parameter schema, by service id."""
    schemas: Schemas = {}
    for service_id, schema in bind.execute(
        sa.text("SELECT service_id, parameter_schema FROM provider_services")
    ).fetchall():
        if isinstance(schema, str):
            schema = json.loads(schema)
        if isinstance(schema, dict):
            schemas.setdefault(service_id, []).append(schema)
    return schemas


def seal_payload(payload: Any, sealed_steps: Dict[str, Any], keys: List[str]) -> Optional[Dict[str, Any]]:
    """Queued payload without the run form's secret copies, sealed whole when its step records secrets; None when unchanged."""
    from app.infrastructure.security.step_secrets import seal_job_payload

    if not isinstance(payload, dict) or SEALED_PAYLOAD in payload:
        return None
    new = dict(payload)
    if "instance_parameters" in new:
        new["instance_parameters"] = scrub_input(new["instance_parameters"], keys)
    step = new.get("step_config")
    sealed_step = sealed_steps.get(str(new.get("step_id")))
    if isinstance(step, dict) and sealed_step is not None:
        meta = step.get("client_metadata")
        paths = sealed_step["client_metadata"][SEALED]
        new["step_config"] = {**step, "client_metadata": {**(meta if isinstance(meta, dict) else {}), SEALED: paths}}
    if new == payload:
        return None
    return seal_job_payload(new)


def seal_all(bind: Any) -> Dict[str, int]:
    """Seal run form secrets in instance snapshots, including nodes that read them through __instance_form__, and drop their plaintext copies from input data, queued payloads and step records; returns rows updated per table."""
    from app.infrastructure.security.credential_encryption import get_credential_encryption

    encryption = get_credential_encryption()
    schemas = _load_schemas(bind)
    counts = {"instances": 0, "queued_jobs": 0, "step_executions": 0}
    rows = bind.execute(
        sa.text(
            "SELECT id, workflow_snapshot, input_data FROM instances "
            "WHERE workflow_snapshot::text LIKE :p"
        ),
        {"p": '%"form"%'},
    ).fetchall()
    for row_id, snap, input_data in rows:
        if not isinstance(snap, dict) or not isinstance(snap.get("steps"), dict):
            continue
        steps = dict(snap["steps"])
        keys: List[str] = []
        sealed_steps: Dict[str, Any] = {}
        for step_id, step in snap["steps"].items():
            new_step, step_keys = seal_step(step, schemas, encryption)
            if step_keys:
                steps[step_id] = sealed_steps[step_id] = new_step
                keys.extend(f"{step_id}.{k}" for k in step_keys)
        if not keys:
            continue
        form = input_data.get("form_values") if isinstance(input_data, dict) else None
        targets = target_values(steps, form if isinstance(form, dict) else {}, keys)
        for step_id, values in targets.items():
            steps[step_id] = sealed_steps[step_id] = seal_target(steps[step_id], values, encryption)
        counts["step_executions"] += scrub_step_records(bind, row_id, targets)
        new_snap = {**snap, "steps": steps}
        new_input = scrub_input(input_data, keys)
        if new_snap != snap or new_input != input_data:
            bind.execute(
                sa.text(
                    "UPDATE instances SET workflow_snapshot = CAST(:s AS jsonb), "
                    "input_data = CAST(:i AS jsonb) WHERE id = :id"
                ),
                {"s": json.dumps(new_snap), "i": json.dumps(new_input), "id": row_id},
            )
            counts["instances"] += 1
        for job_id, payload in bind.execute(
            sa.text("SELECT id, payload FROM queued_jobs WHERE instance_id = :id"), {"id": row_id}
        ).fetchall():
            if isinstance(payload, str):
                payload = json.loads(payload)
            new = seal_payload(payload, sealed_steps, keys)
            if new is not None:
                bind.execute(
                    sa.text("UPDATE queued_jobs SET payload = CAST(:v AS json) WHERE id = :id"),
                    {"v": json.dumps(new), "id": job_id},
                )
                counts["queued_jobs"] += 1
    return counts


def upgrade() -> None:
    """Encrypt run form values for secret node parameters and drop their plaintext copies."""
    counts = seal_all(op.get_bind())
    logger.info(f"run form secrets sealed: {counts}")


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
