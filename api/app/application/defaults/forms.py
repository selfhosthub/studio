# api/app/application/defaults/forms.py

"""Defaults for workflow-form field configuration."""

from typing import Literal

# Changing this default flips the fresh-state rendering of every unspecified
# form field across the app.
FORM_FIELD_TYPE_DEFAULT: Literal["text"] = "text"

# Required-by-default is the safer fallback when an author forgets to declare
# optionality. Flipping to False would silently weaken required-field
# enforcement across every workflow.
FORM_FIELD_REQUIRED_DEFAULT: bool = True
