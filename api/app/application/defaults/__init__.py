# api/app/application/defaults/__init__.py

"""Single authority for user-facing response and command defaults - values
assigned when the caller omits them. Operational env-tunable values (pool
sizes, timeouts, pagination limits) live in configuration; if a default
is already owned there, reference it instead of duplicating here."""

from app.application.defaults.forms import (
    FORM_FIELD_TYPE_DEFAULT,
    FORM_FIELD_REQUIRED_DEFAULT,
)
from app.application.defaults.notifications import (
    NOTIFICATION_CHANNELS_DEFAULT,
)

__all__ = [
    "FORM_FIELD_TYPE_DEFAULT",
    "FORM_FIELD_REQUIRED_DEFAULT",
    "NOTIFICATION_CHANNELS_DEFAULT",
]
