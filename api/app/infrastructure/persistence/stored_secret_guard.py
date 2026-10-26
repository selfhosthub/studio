# api/app/infrastructure/persistence/stored_secret_guard.py

"""Fail-closed check that no write stores a plaintext secret in a JSON value or a secret-named string column."""

import base64
import binascii
import json
import re
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional

from sqlalchemy import JSON, String, Table, Text, event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.types import TypeEngine
from studio_workers.contracts.redaction import REDACTED_PLACEHOLDER, is_sensitive_key

# Item fields that name the sibling value of a name/value pair list item.
PAIR_NAME_FIELDS = ("key", "name", "header")
PAIR_VALUE_FIELD = "value"

# Key names that trip the sensitive-key substring match but never hold a secret value.
ALLOWED_KEYS = frozenset(
    {
        # A UUID reference to a provider_credentials row, not the credential.
        "credential_id",
        # A provider UUID or slug whose credential a step uses, not the credential.
        "credential_provider_id",
        # A model output budget.
        "max_tokens",
        # A model output budget.
        "max_completion_tokens",
        # The trigger auth mode label: none, header, hmac or jwt.
        "webhook_auth_type",
        # Boolean flag a viewer sees in place of a step webhook token.
        "has_webhook_token",
        # The list of parameter paths a step records as secret, not their values.
        "sealed_parameters",
        # The org_secrets type label recorded on a secret's audit events.
        "secret_type",
        # The catalog publisher name kept on an installed workflow.
        "marketplace_author",
        # Storage path a catalog save_binary step writes a file to.
        "file_key",
        # A provider pagination cursor a list node takes.
        "pagetoken",
        # A Typeform response id a node takes.
        "response_token",
        # The workflow step key a run error names.
        "step_key",
        # A field name in output views and key-value lists; credential dicts are sealed whole in secret_data.
        "key",
    }
)

# JSON columns whose content the platform does not author: catalog packages, provider responses and published copy.
UNCHECKED_JSON_COLUMNS = frozenset(
    {
        # Catalog package config: env var names, OAuth URLs and field names.
        ("providers", "config"),
        # Catalog package capabilities.
        ("providers", "capabilities"),
        # Catalog package metadata.
        ("providers", "client_metadata"),
        # Catalog service categories.
        ("provider_services", "categories"),
        # Catalog service schema.
        ("provider_services", "parameter_schema"),
        # Catalog service result schema.
        ("provider_services", "result_schema"),
        # Catalog example placeholders such as sk_test_ values.
        ("provider_services", "example_parameters"),
        # Catalog service transforms and output views.
        ("provider_services", "client_metadata"),
        # Snapshot of a catalog package file.
        ("package_versions", "json_content"),
        # Catalog ComfyUI workflow graph.
        ("comfyui_workflows", "json_content"),
        # Published catalog index.
        ("marketplace_catalogs", "catalog_data"),
        # Published site copy.
        ("site_content", "content"),
        # A provider's response, stored unmodified.
        ("step_executions", "output_data"),
        # A provider's response, stored unmodified.
        ("step_executions", "result"),
        # Values extracted from a provider's response.
        ("step_executions", "extracted_outputs"),
        # A provider's response for one iteration, stored unmodified.
        ("iteration_executions", "result"),
        # A provider's response carried on the job, stored unmodified.
        ("queued_jobs", "output_data"),
        # Step outputs gathered from provider responses.
        ("instances", "output_data"),
    }
)

# JSON columns of run data mapped from trigger payloads and provider responses, checked for the platform's own secret names only.
RUN_DATA_COLUMNS = frozenset(
    {
        # The trigger request body or form values a run starts from.
        ("instances", "input_data"),
        # A step's resolved inputs, which embed upstream outputs.
        ("step_executions", "input_data"),
        # The request a step sent, which embeds upstream outputs.
        ("step_executions", "request_body"),
        # A step's resolved parameters, which embed upstream outputs.
        ("step_executions", "parameters"),
        # Each iteration's resolved parameters, which embed upstream outputs.
        ("step_executions", "iteration_requests"),
        # One iteration's resolved parameters, which embed upstream outputs.
        ("iteration_executions", "parameters"),
        # The job envelope, which embeds resolved parameters.
        ("queued_jobs", "payload"),
    }
)

# Text columns holding a JSON document, checked as JSON.
JSON_TEXT_COLUMNS = frozenset(
    {
        # OAuth flow state, which carries the PKCE code verifier.
        ("oauth_states", "data"),
    }
)

# secret_data columns, which hold nothing but one ciphertext under SEALED_MARKER.
SEALED_COLUMNS = frozenset(
    {("organization_secrets", "secret_data"), ("provider_credentials", "secret_data")}
)

SECRET_COLUMN_WORDS = ("token", "secret", "password", "api_key", "credential")
NON_SECRET_COLUMN_SUFFIXES = ("_hash", "_type", "_id", "_at")
HASHED_PASSWORD = "hashed_password"

# Fernet version byte 0x80 and a zero high timestamp byte encode as gAAAAA.
_FERNET_TEXT = re.compile(r"^gAAAAA[A-Za-z0-9_-]+={0,2}$")
# An HTTP auth scheme word that may lead a template reference.
_AUTH_SCHEME = re.compile(r"^\s*(?:bearer|basic|token|bot)\b", re.I)
_LITERAL = re.compile(r"[A-Za-z0-9]")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_BCRYPT = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")

_FERNET_OVERHEAD = 57
_FERNET_BLOCK = 16


class PlaintextSecretError(RuntimeError):
    """A write would store a secret-class value without encryption."""


def is_ciphertext(value: str) -> bool:
    """Whether value has the structure of a CredentialEncryption (Fernet) token."""
    if not _FERNET_TEXT.match(value):
        return False
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except binascii.Error:
        return False
    body = len(raw) - _FERNET_OVERHEAD
    return body > 0 and body % _FERNET_BLOCK == 0


def is_stored_form(value: str) -> bool:
    """Whether value is ciphertext, a known one-way hash or the redaction marker."""
    return (
        value == REDACTED_PLACEHOLDER
        or is_ciphertext(value)
        or bool(_SHA256_HEX.match(value))
        or bool(_BCRYPT.match(value))
    )


def is_secret_column(column: str) -> bool:
    """Whether a string column's name marks it as holding a secret."""
    name = column.lower()
    if name == HASHED_PASSWORD or name.endswith(NON_SECRET_COLUMN_SUFFIXES):
        return False
    return any(word in name for word in SECRET_COLUMN_WORDS)


def _join(path: str, segment: Any) -> str:
    """JSON path of segment under path."""
    return f"{path}[{segment}]" if isinstance(segment, int) else f"{path}.{segment}"


def _lookup(node: Any, segments: List[Any]) -> Any:
    """Value at segments under node, or None when absent."""
    for seg in segments:
        if isinstance(node, dict) and isinstance(seg, str):
            node = node.get(seg)
        elif isinstance(node, list) and isinstance(seg, int) and 0 <= seg < len(node):
            node = node[seg]
        else:
            return None
    return node


def _sealed_parameter_paths(node: Dict[str, Any], path: str) -> Iterator[str]:
    """Paths of the recorded secret parameters of a step that hold a plaintext string."""
    # Deferred: the security package loads settings, which a bare models import must not need.
    from app.infrastructure.security.step_secrets import step_secret_paths

    params = _lookup(node, ["job", "parameters"])
    for segments in step_secret_paths(node):
        value = _lookup(params, segments)
        if isinstance(value, str) and value and not is_ciphertext(value):
            out = _join(_join(path, "job"), "parameters")
            for seg in segments:
                out = _join(out, seg)
            yield out


def _secret_name(key: str) -> bool:
    """Whether key names a secret by the sensitive-key match, less the allowlist."""
    return is_sensitive_key(key) and key.lower() not in ALLOWED_KEYS


def _run_secret_name(key: str) -> bool:
    """Whether key is a secret name the platform itself writes into a step."""
    # Deferred: the security package loads settings, which a bare models import must not need.
    from app.infrastructure.security.step_secrets import API_SECRET_PARAMETERS, STEP_WEBHOOK_KEYS

    return key in API_SECRET_PARAMETERS or key in STEP_WEBHOOK_KEYS


def _strip_templates(value: str) -> str:
    """value with each {{ ... }} reference, which holds no secret at rest, replaced by a space, in linear time."""
    parts: list[str] = []
    pos = 0
    while (start := value.find("{{", pos)) >= 0 and (end := value.find("}}", start + 2)) >= 0:
        parts += [value[pos:start], " "]
        pos = end + 2
    parts.append(value[pos:])
    return "".join(parts)


def is_template_only(value: str) -> bool:
    """Whether value holds {{ }} references and no literal text but a leading auth scheme word and punctuation."""
    rest = _strip_templates(value)
    return rest != value and not _LITERAL.search(_AUTH_SCHEME.sub("", rest, count=1))


def is_plaintext_secret(key: Any, value: Any, secret_name: Callable[[str], bool] = _secret_name) -> bool:
    """Whether value is a filled string under a secret name that is neither in stored form nor only template references."""
    return (
        isinstance(key, str)
        and isinstance(value, str)
        and bool(value)
        and secret_name(key)
        and not is_stored_form(value)
        and not is_template_only(value)
    )


def is_plaintext_pair(item: Any, secret_name: Callable[[str], bool] = _secret_name) -> bool:
    """Whether item is a name/value pair whose name field holds a secret name and whose value is_plaintext_secret flags."""
    return isinstance(item, dict) and any(
        is_plaintext_secret(item.get(field), item.get(PAIR_VALUE_FIELD), secret_name)
        for field in PAIR_NAME_FIELDS
    )


def named_secret_paths(node: Any, prefix: Optional[List[Any]] = None) -> List[List[Any]]:
    """Segment paths under node of every value is_plaintext_secret flags by its key or is_plaintext_pair by its pair name."""
    base = prefix or []
    out: List[List[Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if is_plaintext_secret(key, value):
                out.append(base + [key])
            elif not isinstance(value, str):
                out.extend(named_secret_paths(value, base + [key]))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            if is_plaintext_pair(item):
                out.append(base + [index, PAIR_VALUE_FIELD])
            out.extend(named_secret_paths(item, base + [index]))
    return out


def _walk(node: Any, path: str, secret_name: Callable[[str], bool]) -> Iterator[str]:
    """Paths under node of a plaintext secret under a secret name, or at a recorded secret parameter."""
    if isinstance(node, dict):
        yield from _sealed_parameter_paths(node, path)
        for key, value in node.items():
            child = _join(path, key)
            if isinstance(value, str):
                if is_plaintext_secret(key, value, secret_name):
                    yield child
            else:
                yield from _walk(value, child, secret_name)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            if is_plaintext_pair(item, secret_name):
                yield _join(_join(path, index), PAIR_VALUE_FIELD)
            yield from _walk(item, _join(path, index), secret_name)


def _sealed_findings(value: Any) -> List[str]:
    """Paths of a secret_data value that is not one ciphertext under SEALED_MARKER."""
    # Deferred: the security package loads settings, which a bare models import must not need.
    from app.infrastructure.security.credential_encryption import SEALED_MARKER

    if not value:
        return []
    if not isinstance(value, dict):
        return ["$"]
    found = [_join("$", k) for k in value if k != SEALED_MARKER]
    sealed = value.get(SEALED_MARKER)
    if SEALED_MARKER in value and not (isinstance(sealed, str) and is_ciphertext(sealed)):
        found.append(_join("$", SEALED_MARKER))
    return found


def find_plaintext_secrets(table: str, column: str, value: Any, is_json: bool) -> List[str]:
    """table.column, with a JSON path for a JSON column, of each plaintext secret value holds."""
    where = f"{table}.{column}"
    if (table, column) in JSON_TEXT_COLUMNS and isinstance(value, str):
        try:
            value, is_json = json.loads(value), True
        except ValueError:
            return [where]
    if is_json:
        if (table, column) in UNCHECKED_JSON_COLUMNS:
            return []
        if (table, column) in SEALED_COLUMNS:
            paths = _sealed_findings(value)
        elif (table, column) in RUN_DATA_COLUMNS:
            paths = list(_walk(value, "$", _run_secret_name))
        else:
            paths = list(_walk(value, "$", _secret_name))
        return [f"{where} at {p}" for p in paths]
    if isinstance(value, str) and value and is_secret_column(column) and not is_stored_form(value):
        return [where]
    return []


def _column_kind(sql_type: TypeEngine[Any]) -> Optional[bool]:
    """True for a JSON type, False for a string type, None for any other."""
    if isinstance(sql_type, JSON):
        return True
    if isinstance(sql_type, (String, Text)):
        return False
    return None


def _raise_on(found: List[str]) -> None:
    """Raise PlaintextSecretError naming every finding."""
    if found:
        raise PlaintextSecretError(
            "Refusing to store a plaintext secret: " + ", ".join(found)
            + ". Seal it through step_secrets, webhook_tokens or seal_secret_data."
        )


def _object_findings(obj: Any, is_new: bool) -> List[str]:
    """Findings for the column attributes of obj that are new or changed in this flush."""
    state = sa_inspect(obj)
    found: List[str] = []
    for prop in state.mapper.column_attrs:
        column = prop.columns[0]
        kind = _column_kind(column.type)
        table = getattr(column, "table", None)
        if kind is None or not isinstance(table, Table):
            continue
        if not is_new and not state.attrs[prop.key].history.has_changes():
            continue
        value = state.dict.get(prop.key)
        if value is not None:
            found.extend(find_plaintext_secrets(table.name, column.name, value, kind))
    return found


def check_flush(session: Session, flush_context: Any, instances: Any) -> None:
    """before_flush listener: refuse a flush that would store a plaintext secret."""
    found: List[str] = []
    for obj in session.new:
        found.extend(_object_findings(obj, True))
    for obj in session.dirty:
        found.extend(_object_findings(obj, False))
    _raise_on(found)


def _named(values: Mapping[Any, Any]) -> Dict[str, Any]:
    """values keyed by column name, with bound parameters unwrapped."""
    return {str(getattr(k, "key", k)): getattr(v, "value", v) for k, v in values.items()}


def _statement_rows(state: ORMExecuteState) -> List[Dict[str, Any]]:
    """The literal column values of a DML statement and its execute parameters."""
    statement = state.statement
    rows: List[Dict[str, Any]] = []
    values = getattr(statement, "_values", None)
    if values:
        rows.append(_named(values))
    for group in getattr(statement, "_multi_values", None) or ():
        rows.extend(_named(row) for row in group if isinstance(row, Mapping))
    params = state.parameters
    if isinstance(params, Mapping):
        rows.append(_named(params))
    elif isinstance(params, list):
        rows.extend(_named(p) for p in params if isinstance(p, Mapping))
    return rows


def check_statement(state: ORMExecuteState) -> None:
    """do_orm_execute listener: refuse an insert or update statement that would store a plaintext secret."""
    if not (state.is_insert or state.is_update):
        return
    table = getattr(state.statement, "table", None)
    if not isinstance(table, Table):
        return
    found: List[str] = []
    for row in _statement_rows(state):
        for name, value in row.items():
            column = table.columns.get(name)
            kind = _column_kind(column.type) if column is not None else None
            if kind is not None and value is not None:
                found.extend(find_plaintext_secrets(table.name, name, value, kind))
    _raise_on(found)


def install_stored_secret_guard() -> None:
    """Register the flush and statement checks on every Session."""
    if not event.contains(Session, "before_flush", check_flush):
        event.listen(Session, "before_flush", check_flush)
    if not event.contains(Session, "do_orm_execute", check_statement):
        event.listen(Session, "do_orm_execute", check_statement)
