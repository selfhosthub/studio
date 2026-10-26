# api/app/domain/organization/slug.py

"""Generated organization slugs: a name-derived base plus a random base36 suffix."""

import re
import secrets
import string

SLUG_MAX_LENGTH = 32
SLUG_BASE_MAX_LENGTH = 15
SLUG_SUFFIX_LENGTH = 4
SLUG_FALLBACK_BASE = "org"

_SUFFIX_ALPHABET = string.ascii_lowercase + string.digits


def slug_base(name: str) -> str:
    """Lowercase hyphenated base of a name, at most 15 chars, cut on a word boundary when one exists."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if len(base) > SLUG_BASE_MAX_LENGTH:
        head = base[:SLUG_BASE_MAX_LENGTH]
        if base[SLUG_BASE_MAX_LENGTH] != "-" and "-" in head:
            head = head[: head.rfind("-")]
        base = head.rstrip("-")
    return base or SLUG_FALLBACK_BASE


def random_suffix() -> str:
    """Four random lowercase base36 characters."""
    return "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(SLUG_SUFFIX_LENGTH))


def generate_org_slug(name: str) -> str:
    """Slug of the form <base>-<suffix> for a new organization."""
    return f"{slug_base(name)}-{random_suffix()}"
