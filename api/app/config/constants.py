# api/app/config/constants.py

"""Static constants shared across the app (non-env-tunable)."""

# WebSocket close reasons. All sent with policy-violation close code.
WS_CLOSE_REASON_AUTH_REQUIRED = "Authentication required"
WS_CLOSE_REASON_IDLE = "Idle timeout"
WS_CLOSE_REASON_IP_LIMIT = "IP connection limit exceeded"
WS_CLOSE_REASON_RATE_LIMIT = "Message rate limit exceeded"
WS_CLOSE_REASON_TOTAL_LIMIT = "Server connection limit exceeded"
