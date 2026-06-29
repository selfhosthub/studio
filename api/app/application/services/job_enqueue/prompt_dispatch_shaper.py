# api/app/application/services/job_enqueue/prompt_dispatch_shaper.py

"""Prompt dispatch shaper - provider-neutral messages → per-dialect wire params.

Prompts assemble to a neutral ``[{role, content}]`` list (role in
system/user/assistant) long before the step's endpoint is resolved. Each
provider dialect places that content differently on the wire (anthropic and
gemini hoist system to a top-level param; gemini renames assistant→model and
wraps content in parts). This module does the logic half of that adaptation:
it parses the neutral list into ``{system, turns}`` and injects ready-made
``_*`` parameters that the service's declarative ``request_transform.body``
then places. Placement stays config; logic stays here.

Keying rule: the shaper branches on the service-declared ``wire_dialect``
(``openai`` | ``anthropic`` | ``gemini``), never on provider name - any
future OpenAI-compatible provider is pure config. Gated on
``prompt_shape == "chat"`` (explicit opt-in, no magic detection).

Empties are omitted Python-side: when there is no system text the ``_*``
system key is simply not set, and the transform's ``is defined`` guard maps
that to the ``__omit__`` sentinel. Never ``… or '__omit__'`` in config - that
would drop legitimate falsy values like ``top_p=0.0``.

Shaping errors are deliberate enqueue-blocking validation failures
(BusinessRuleViolation - author-visible verbatim), not swallowed
envelope-build failures: a malformed prompt must fail at shape time with an
actionable message, not as a provider 400 at fire time.
"""

from typing import Any, Dict, List, Optional, Tuple

from app.domain.common.exceptions import BusinessRuleViolation

PROMPT_SHAPE_CHAT = "chat"
_DIALECTS = ("openai", "anthropic", "gemini")
_NEUTRAL_ROLES = ("system", "user", "assistant")


def _invalid(message: str) -> BusinessRuleViolation:
    return BusinessRuleViolation(message=message, code="PROMPT_SHAPE_INVALID")


def _validate_neutral_messages(messages: Any) -> List[Dict[str, Any]]:
    """Validate the neutral message list shape; returns it typed."""
    if not isinstance(messages, list) or not messages:
        raise _invalid(
            "Chat prompt shaping requires a non-empty 'messages' list of "
            "{role, content} entries. Bind a prompt or author messages on the step."
        )
    for entry in messages:
        if not isinstance(entry, dict) or "role" not in entry or "content" not in entry:
            raise _invalid(
                "Each chat message must be an object with 'role' and 'content'."
            )
        if entry["role"] not in _NEUTRAL_ROLES:
            raise _invalid(
                f"Unknown chat message role '{entry['role']}'. "
                "Allowed roles: system, user, assistant."
            )
    return messages


def _split_system(
    messages: List[Dict[str, Any]],
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Split a leading system message off the neutral list.

    The domain invariant (≤1 system chunk, must lead) already rejected
    misplaced system content at prompt save; a system entry surviving past
    index 0 here means hand-authored step messages - reject it the same way
    rather than coercing.
    """
    system_text: Optional[str] = None
    turns = messages
    if messages and messages[0]["role"] == "system":
        content = messages[0]["content"]
        if not isinstance(content, str):
            raise _invalid("System message content must be a string.")
        system_text = content.strip() or None
        turns = messages[1:]
    for entry in turns:
        if entry["role"] == "system":
            raise _invalid(
                "A system message is only allowed as the first message. "
                "Move system content to the System field / system parameter."
            )
    if not turns:
        raise _invalid(
            "Chat prompt has no user/assistant messages. Every dialect "
            "requires at least one conversation turn."
        )
    return system_text, turns


def _require_string_contents(turns: List[Dict[str, Any]]) -> None:
    for entry in turns:
        if not isinstance(entry["content"], str):
            raise _invalid(
                "Prompt shaping supports string message content only "
                "(vision/tool content blocks are not shaped)."
            )


def _shape_anthropic(parameters: Dict[str, Any]) -> Dict[str, Any]:
    messages = _validate_neutral_messages(parameters.get("messages"))
    system_text, turns = _split_system(messages)
    shaped = dict(parameters)
    # The native "system" string field remains a valid authoring channel; a
    # prompt-level system chunk takes precedence when both are set.
    if system_text is None:
        native = parameters.get("system")
        if isinstance(native, str) and native.strip():
            system_text = native.strip()
    if system_text is not None:
        shaped["_system_text"] = system_text
    shaped["_turns"] = turns
    return shaped


def _shape_openai(parameters: Dict[str, Any]) -> Dict[str, Any]:
    # system-as-role is wire-valid anywhere in the list on this dialect, so
    # the neutral list is already the wire list - validate shape, pass through.
    messages = _validate_neutral_messages(parameters.get("messages"))
    shaped = dict(parameters)
    shaped["_openai_messages"] = messages
    return shaped


def _merge_adjacent_gemini(contents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge adjacent same-role contents (gemini's alternation constraint)."""
    merged: List[Dict[str, Any]] = []
    for entry in contents:
        if merged and merged[-1]["role"] == entry["role"]:
            merged[-1]["parts"][0]["text"] += "\n\n" + entry["parts"][0]["text"]
        else:
            merged.append(entry)
    return merged


def _shape_gemini(parameters: Dict[str, Any]) -> Dict[str, Any]:
    shaped = dict(parameters)

    neutral = parameters.get("messages")
    contents = parameters.get("contents")
    if neutral is None and isinstance(contents, list):
        if all(isinstance(c, dict) and "parts" in c for c in contents) and contents:
            # Native gemini contents (parts-shaped) - already wire-shaped;
            # pass through with the native systemInstruction, if any.
            shaped["_gemini_contents"] = contents
            system_instruction = parameters.get("systemInstruction")
            if isinstance(system_instruction, dict) and system_instruction.get(
                "parts"
            ):
                shaped["_gemini_system"] = system_instruction
            return shaped
        # A shared prompt bound to the contents parameter resolves to the
        # neutral [{role, content}] list - shape it like messages.
        neutral = contents

    messages = _validate_neutral_messages(neutral)
    system_text, turns = _split_system(messages)
    _require_string_contents(turns)

    wire_contents = [
        {
            "role": "model" if t["role"] == "assistant" else "user",
            "parts": [{"text": t["content"]}],
        }
        for t in turns
    ]
    shaped["_gemini_contents"] = _merge_adjacent_gemini(wire_contents)
    if system_text is not None:
        shaped["_gemini_system"] = {"parts": [{"text": system_text}]}
    return shaped


def shape_prompt_parameters(
    service_metadata: Optional[Dict[str, Any]],
    parameters: Dict[str, Any],
) -> Dict[str, Any]:
    """Inject dialect-specific ``_*`` params for chat-shaped services.

    Returns ``parameters`` unchanged (same object) when the service does not
    declare ``prompt_shape == "chat"``; otherwise returns a shallow copy with
    the dialect's ``_*`` keys added. Never mutates the input.

    Raises:
        BusinessRuleViolation: misconfigured/unknown ``wire_dialect``, or
            neutral input that cannot be shaped (empty turns, misplaced
            system, non-string content).
    """
    meta = service_metadata or {}
    if meta.get("prompt_shape") != PROMPT_SHAPE_CHAT:
        return parameters

    dialect = meta.get("wire_dialect")
    if dialect == "anthropic":
        shaped = _shape_anthropic(parameters)
    elif dialect == "openai":
        shaped = _shape_openai(parameters)
    elif dialect == "gemini":
        shaped = _shape_gemini(parameters)
    else:
        raise _invalid(
            f"Service declares prompt_shape='chat' but wire_dialect={dialect!r} "
            f"is not one of {_DIALECTS}. Fix the service config."
        )
    return shaped
