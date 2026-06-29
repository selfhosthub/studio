# api/app/application/defaults/notifications.py

"""Defaults for notification delivery."""

# In-app only by default (the bell icon). Email and other channels are opt-in
# per-notification at the command layer, not global - keeps email from being
# accidentally sent to every recipient of every workflow event.
NOTIFICATION_CHANNELS_DEFAULT: list[str] = ["IN_APP"]
