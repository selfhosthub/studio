# api/alembic/versions/35979a8bd84b_seal_templated_and_pair_step_secrets.py

"""seal templated and pair step secrets

Revision ID: 35979a8bd84b
Revises: 7bd2534f9bda
Create Date: 2026-10-21 15:12:44.140497

"""
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35979a8bd84b'
down_revision: Union[str, Sequence[str], None] = '7bd2534f9bda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

SEALED = "sealed_parameters"
SEALED_PAYLOAD = "_sealed_payload"
# LIKE patterns of rows that may hold a secret beside a template or in a name/value pair.
CANDIDATE_BINDS = {"tpl": "%{{%", "pair": '%"value"%'}

Path = List[Union[str, int]]
StepPaths = Dict[str, List[Path]]
Cipher = Callable[[str], str]


def _candidate(column: str) -> str:
    """SQL condition matching rows of column that may hold a templated or pair secret."""
    return f"({column}::text LIKE :tpl OR {column}::text LIKE :pair)"


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


def seal_step(step: Dict[str, Any], encrypt: Cipher) -> Tuple[Dict[str, Any], List[Path]]:
    """Step with each plaintext value the guard names secret in its parameters encrypted and recorded, and those paths."""
    from app.infrastructure.persistence.stored_secret_guard import named_secret_paths
    from app.infrastructure.security.step_secrets import step_secret_paths

    params = _get(step, ["job", "parameters"])
    if not isinstance(params, dict):
        return step, []
    paths = named_secret_paths(params)
    if not paths:
        return step, []
    for path in paths:
        params = _set(params, path, encrypt(_get(params, path)))
    recorded = step_secret_paths(step)
    meta = step.get("client_metadata")
    kept = dict(meta) if isinstance(meta, dict) else {}
    kept[SEALED] = recorded + [p for p in paths if p not in recorded]
    return {**step, "client_metadata": kept, "job": {**step["job"], "parameters": params}}, paths


def seal_steps(steps: Any, encrypt: Cipher) -> Tuple[Any, StepPaths]:
    """Steps with seal_step applied to each, and the paths sealed per step."""
    if not isinstance(steps, dict):
        return steps, {}
    out: Dict[str, Any] = {}
    sealed: StepPaths = {}
    for step_id, step in steps.items():
        new, paths = seal_step(step, encrypt) if isinstance(step, dict) else (step, [])
        out[step_id] = new
        if paths:
            sealed[step_id] = paths
    return out, sealed


def _scrubbed(cols: Dict[str, Any], paths: List[Path]) -> Dict[str, Any]:
    """Step record columns without the values at paths."""
    from app.infrastructure.security.step_secrets import without_secret_values

    new = dict(cols)
    for col in ("request_body", "parameters"):
        if isinstance(new[col], dict):
            new[col] = without_secret_values(new[col], paths)
    for col in ("input_data", "execution_data"):
        if isinstance(new[col], dict) and isinstance(new[col].get("parameters"), dict):
            new[col] = {**new[col], "parameters": without_secret_values(new[col]["parameters"], paths)}
    if isinstance(new["iteration_requests"], list):
        new["iteration_requests"] = [
            {**r, "params": without_secret_values(r["params"], paths)}
            if isinstance(r, dict) and isinstance(r.get("params"), dict) else r
            for r in new["iteration_requests"]
        ]
    return new


def scrub_records(bind: Any, instance_id: Any, sealed: StepPaths) -> int:
    """Remove the sealed paths from the instance's step and iteration records; returns rows updated."""
    from app.infrastructure.security.step_secrets import without_secret_values

    columns = ("input_data", "request_body", "parameters", "execution_data", "iteration_requests")
    updated = 0
    for step_key, paths in sealed.items():
        rows = bind.execute(
            sa.text(f"SELECT id, {', '.join(columns)} FROM step_executions WHERE instance_id = :i AND step_key = :k"),
            {"i": instance_id, "k": step_key},
        ).fetchall()
        for row in rows:
            cols = dict(zip(columns, row[1:]))
            changes = {c: v for c, v in _scrubbed(cols, paths).items() if v != cols[c]}
            if changes:
                sets = ", ".join(f"{c} = CAST(:{c} AS jsonb)" for c in changes)
                bind.execute(
                    sa.text(f"UPDATE step_executions SET {sets} WHERE id = :id"),
                    {**{c: json.dumps(v) for c, v in changes.items()}, "id": row[0]},
                )
                updated += 1
            for it_id, it_params in bind.execute(
                sa.text("SELECT id, parameters FROM iteration_executions WHERE step_id = :s"), {"s": row[0]}
            ).fetchall():
                if isinstance(it_params, dict):
                    cleaned = without_secret_values(it_params, paths)
                    if cleaned != it_params:
                        bind.execute(
                            sa.text("UPDATE iteration_executions SET parameters = CAST(:v AS jsonb) WHERE id = :id"),
                            {"v": json.dumps(cleaned), "id": it_id},
                        )
                        updated += 1
    return updated


def seal_payload(payload: Any, encrypt: Cipher) -> Optional[Dict[str, Any]]:
    """Queued payload whose step parameters hold a guard-named plaintext secret, with the paths recorded and the payload sealed whole; None when unchanged."""
    from app.infrastructure.security.step_secrets import seal_job_payload

    if not isinstance(payload, dict) or SEALED_PAYLOAD in payload:
        return None
    step = payload.get("step_config")
    if not isinstance(step, dict):
        return None
    marked, paths = seal_step(step, encrypt)
    if not paths:
        return None
    return seal_job_payload({**payload, "step_config": {**step, "client_metadata": marked["client_metadata"]}})


def seal_all(bind: Any) -> Dict[str, int]:
    """Seal node secrets typed beside a template or held in a name/value pair, and drop their plaintext copies; returns rows updated per table."""
    from app.infrastructure.security.credential_encryption import get_credential_encryption

    encrypt = get_credential_encryption().encrypt
    counts = {"workflow_versions": 0, "instances": 0, "step_records": 0, "queued_jobs": 0}
    for row_id, steps in bind.execute(
        sa.text(f"SELECT id, steps FROM workflow_versions WHERE {_candidate('steps')}"), CANDIDATE_BINDS
    ).fetchall():
        new_steps, sealed = seal_steps(steps, encrypt)
        if sealed:
            bind.execute(
                sa.text("UPDATE workflow_versions SET steps = CAST(:v AS jsonb) WHERE id = :id"),
                {"v": json.dumps(new_steps), "id": row_id},
            )
            counts["workflow_versions"] += 1
    for row_id, snap in bind.execute(
        sa.text(f"SELECT id, workflow_snapshot FROM instances WHERE {_candidate('workflow_snapshot')}"),
        CANDIDATE_BINDS,
    ).fetchall():
        if not isinstance(snap, dict):
            continue
        new_steps, sealed = seal_steps(snap.get("steps"), encrypt)
        if sealed:
            bind.execute(
                sa.text("UPDATE instances SET workflow_snapshot = CAST(:v AS jsonb) WHERE id = :id"),
                {"v": json.dumps({**snap, "steps": new_steps}), "id": row_id},
            )
            counts["instances"] += 1
            counts["step_records"] += scrub_records(bind, row_id, sealed)
    for job_id, payload in bind.execute(
        sa.text(f"SELECT id, payload FROM queued_jobs WHERE {_candidate('payload')}"), CANDIDATE_BINDS
    ).fetchall():
        new = seal_payload(json.loads(payload) if isinstance(payload, str) else payload, encrypt)
        if new is not None:
            bind.execute(
                sa.text("UPDATE queued_jobs SET payload = CAST(:v AS json) WHERE id = :id"),
                {"v": json.dumps(new), "id": job_id},
            )
            counts["queued_jobs"] += 1
    return counts


def upgrade() -> None:
    """Encrypt node parameter secrets typed beside a template or held in a name/value pair, and drop their plaintext copies."""
    counts = seal_all(op.get_bind())
    logger.info(f"templated and pair step secrets sealed: {counts}")


def downgrade() -> None:
    raise NotImplementedError('Downgrades are not supported. Redeploy the previous major image.')
