# api/app/domain/prompt/models.py

"""Prompt domain models.

A prompt is an ordered list of text chunks with optional variable bindings. Chunks
with a variable are skipped when the variable resolves empty. Text is rendered with
Jinja2 ({{ var }}, {% if %}, filters). today_date / today_datetime are auto-injected.
"""

import uuid
from datetime import UTC, datetime
from typing import Dict, List, Optional

import jinja2
from jinja2.sandbox import SandboxedEnvironment
from pydantic import BaseModel, Field

from app.domain.common.base_entity import AggregateRoot
from app.domain.common.exceptions import BusinessRuleViolation
from app.domain.common.value_objects import (
    PromptPublishStatus,
    PromptScope,
    PromptSource,
    Visibility,
)

# Sandboxed: chunk.text is user-authored template source, so unsandboxed rendering
# is SSTI/RCE. No autoescape (plain text, not HTML); undefined renders empty, not raise.
_jinja_env = SandboxedEnvironment(
    autoescape=False,
    undefined=jinja2.Undefined,
    keep_trailing_newline=True,
)

# ISO-639-1 → display name. Mirrors the canonical openai_tts.language enum
# across the bundled provider packages; extend in lockstep so workflow
# mappings stay 1:1.
_LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "hi": "Hindi",
    "tr": "Turkish",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
}


def _language_name_filter(value: object) -> str:
    """ISO-639-1 → display name; passes through unknowns."""
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    return _LANGUAGE_NAMES.get(value, value)


_jinja_env.filters["language_name"] = _language_name_filter


class PromptChunk(BaseModel):
    """A single text chunk in a prompt."""

    text: str
    variable: Optional[str] = None
    order: int = 0
    role: Optional[str] = None  # "system" | "user" | "assistant"; None → "user"


def validate_chunk_roles(chunks: List[PromptChunk]) -> None:
    """Enforce the system-chunk invariant: at most one ``system`` chunk, and it
    must be the leading chunk (lowest ``order``).

    Every provider dialect has exactly one system slot, so a duplicate or
    mid-conversation system chunk can never be shaped onto the wire - reject it
    here (fail loud) instead of coercing. Called from ``Prompt.create()`` /
    ``Prompt.update()`` (builder save, importer, marketplace install) and the
    seeder, which writes rows without a ``Prompt`` aggregate.
    """
    ordered = sorted(chunks, key=lambda c: c.order)
    system_positions = [
        i for i, chunk in enumerate(ordered) if (chunk.role or "user") == "system"
    ]
    if len(system_positions) > 1:
        raise BusinessRuleViolation(
            message=(
                "A prompt may contain at most one [system] chunk. "
                "Merge the system content into a single leading chunk."
            ),
            code="PROMPT_MULTIPLE_SYSTEM_CHUNKS",
        )
    if system_positions and system_positions[0] != 0:
        raise BusinessRuleViolation(
            message=(
                "The [system] chunk must be the first chunk of the prompt. "
                "System content belongs in the System field, before any "
                "[user]/[assistant] messages."
            ),
            code="PROMPT_SYSTEM_CHUNK_NOT_LEADING",
        )


class PromptVariable(BaseModel):
    """A configurable variable within a prompt."""

    name: str
    label: str
    type: str = "string"  # "string" | "enum" | "number"
    options: Optional[List[str]] = None
    # Display labels paralleling options (matches the provider-schema enumNames convention).
    option_labels: Optional[List[str]] = None
    default: Optional[str] = None
    # required=True surfaces the var as required in the form schema AND makes
    # assemble() raise on empty values. Optional vars retain chunk-drops-on-empty.
    required: bool = False


class RequiredPromptVariableError(ValueError):
    """Raised by Prompt.assemble() when required variables resolve empty. `missing` lists the offending names."""

    def __init__(self, missing: List[str]) -> None:
        self.missing = missing
        joined = ", ".join(missing)
        super().__init__(f"Required prompt variable(s) not provided: {joined}")


class Prompt(AggregateRoot):
    """A reusable, configurable text block for LLM steps. Org-scoped; custom or marketplace-sourced."""

    organization_id: uuid.UUID
    name: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=3)
    description: Optional[str] = None
    category: str = "general"
    chunks: List[PromptChunk] = Field(default_factory=list)
    variables: List[PromptVariable] = Field(default_factory=list)
    is_enabled: bool = True
    source: PromptSource = PromptSource.CUSTOM
    created_by: Optional[uuid.UUID] = None
    scope: PromptScope = PromptScope.ORGANIZATION
    publish_status: Optional[PromptPublishStatus] = None
    # Cross-org marketplace visibility (super_admin-controlled). Default private.
    visibility: Visibility = Visibility.PRIVATE

    @classmethod
    def create(
        cls,
        organization_id: uuid.UUID,
        name: str,
        slug: str,
        description: Optional[str] = None,
        category: str = "general",
        chunks: Optional[List[PromptChunk]] = None,
        variables: Optional[List[PromptVariable]] = None,
        source: PromptSource = PromptSource.CUSTOM,
        created_by: Optional[uuid.UUID] = None,
        scope: PromptScope = PromptScope.ORGANIZATION,
    ) -> "Prompt":
        validate_chunk_roles(chunks or [])
        return cls(
            organization_id=organization_id,
            name=name,
            slug=slug,
            description=description,
            category=category,
            chunks=chunks or [],
            variables=variables or [],
            is_enabled=True,
            source=source,
            created_by=created_by,
            scope=scope,
            publish_status=None,
        )

    def validate_can_be_deleted(self, actor_id: Optional[uuid.UUID] = None) -> None:
        """Raises if the prompt is pending publish approval and the actor is not
        its creator (only the owner may delete a pending submission — an admin
        declines via reject, not delete)."""
        if self.publish_status == PromptPublishStatus.PENDING and actor_id != self.created_by:
            raise BusinessRuleViolation(
                message="Cannot delete a prompt pending publish approval. Reject it first.",
                code="PROMPT_PENDING_APPROVAL",
                context={"prompt_id": str(self.id)},
            )

    def request_publish(self) -> None:
        if self.scope != PromptScope.PERSONAL:
            raise BusinessRuleViolation(
                message="Only personal prompts can be published to the organization",
                code="NOT_PERSONAL_SCOPE",
                context={"prompt_id": str(self.id), "scope": self.scope.value},
            )
        if self.publish_status == PromptPublishStatus.PENDING:
            raise BusinessRuleViolation(
                message="Publish request already pending",
                code="ALREADY_PENDING",
                context={"prompt_id": str(self.id)},
            )
        self.publish_status = PromptPublishStatus.PENDING
        self.updated_at = datetime.now(UTC)

    def approve_publish(self) -> None:
        if self.publish_status != PromptPublishStatus.PENDING:
            raise BusinessRuleViolation(
                message="Only pending prompts can be approved",
                code="NOT_PENDING",
                context={"prompt_id": str(self.id)},
            )
        self.scope = PromptScope.ORGANIZATION
        self.publish_status = None
        self.updated_at = datetime.now(UTC)

    def reject_publish(self) -> None:
        if self.publish_status != PromptPublishStatus.PENDING:
            raise BusinessRuleViolation(
                message="Only pending prompts can be rejected",
                code="NOT_PENDING",
                context={"prompt_id": str(self.id)},
            )
        self.publish_status = PromptPublishStatus.REJECTED
        self.updated_at = datetime.now(UTC)

    def set_visibility(self, new_visibility: Visibility) -> Visibility:
        """Transition cross-org marketplace visibility. Returns the previous
        value (for audit). Authorization (super_admin-only) is enforced at the
        API boundary; this only mutates state."""
        old_visibility = self.visibility
        self.visibility = new_visibility
        self.updated_at = datetime.now(UTC)
        return old_visibility

    @staticmethod
    def _builtin_variables() -> Dict[str, str]:
        now = datetime.now(UTC)
        return {
            "today_date": now.strftime("%Y-%m-%d"),
            "today_datetime": now.strftime("%Y-%m-%d %H:%M UTC"),
        }

    def assemble(self, variable_values: Dict[str, str]) -> List[Dict[str, str]]:
        """Assemble [{role, content}] messages from chunks. Variable resolution: builtins → variable defaults → variable_values.

        Chunks bound to an empty variable are skipped (unless required, see below).
        Consecutive chunks with the same role are merged into a single message.

        Built-ins: today_date (YYYY-MM-DD), today_datetime (YYYY-MM-DD HH:MM UTC). Both overridable.
        """
        merged: Dict[str, str] = self._builtin_variables()
        for var in self.variables:
            if var.default:
                merged[var.name] = var.default
        merged.update(variable_values)

        # Required-var guard. Silently dropping the chunk that uses an empty
        # required var would yield a malformed prompt and hallucinated output.
        # UI forms block this, but API-direct callers also go through here.
        missing = [v.name for v in self.variables if v.required and not merged.get(v.name)]
        if missing:
            raise RequiredPromptVariableError(missing)

        sorted_chunks = sorted(self.chunks, key=lambda c: c.order)

        role_lines: List[tuple[str, str]] = []
        for chunk in sorted_chunks:
            if chunk.variable:
                value = merged.get(chunk.variable, "")
                if not value:
                    continue
            role = chunk.role or "user"
            template = _jinja_env.from_string(chunk.text)
            text = template.render(merged)
            role_lines.append((role, text))

        messages: List[Dict[str, str]] = []
        for role, text in role_lines:
            if messages and messages[-1]["role"] == role:
                messages[-1]["content"] += "\n\n" + text
            else:
                messages.append({"role": role, "content": text})

        return messages

    def update(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        chunks: Optional[List[PromptChunk]] = None,
        variables: Optional[List[PromptVariable]] = None,
        is_enabled: Optional[bool] = None,
    ) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if category is not None:
            self.category = category
        if chunks is not None:
            validate_chunk_roles(chunks)
            self.chunks = chunks
        if variables is not None:
            self.variables = variables
        if is_enabled is not None:
            self.is_enabled = is_enabled
        self.updated_at = datetime.now(UTC)
