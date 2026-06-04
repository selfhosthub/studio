# api/app/infrastructure/auth/worker_jwt.py

"""Worker JWTs - short-lived tokens refreshed via heartbeat to avoid per-claim DB lookups."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import Header, HTTPException, status
import jwt
from jwt.exceptions import PyJWTError as JWTError

from app.config.settings import settings

# Shared secret with user JWTs; could split into WORKER_JWT_SECRET for isolation.
SECRET_KEY: str = settings.JWT_SECRET_KEY
ALGORITHM = "HS256"

# Short-lived: workers must heartbeat (~60s) to stay active.
WORKER_TOKEN_EXPIRE_MINUTES = settings.WORKER_TOKEN_EXPIRE_MINUTES

logger = logging.getLogger(__name__)


def create_worker_token(
    worker_id: str,
    queue_labels: List[str],
    capabilities: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Issue a worker JWT carrying its queue labels and capabilities."""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=WORKER_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": worker_id,
        "type": "worker",
        "queue_labels": queue_labels,
        "capabilities": capabilities or {},
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    encoded_jwt: str = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_worker_token(token: str) -> Dict[str, Any]:
    """Verify a worker JWT. Raises HTTPException for invalid/expired/wrong-type tokens."""
    try:
        payload: Dict[str, Any] = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != "worker":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type - expected worker token",
            )

        worker_id = payload.get("sub")
        if worker_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid worker token - missing worker_id",
            )

        return {
            "worker_id": worker_id,
            "queue_labels": payload.get("queue_labels", []),
            "capabilities": payload.get("capabilities", {}),
            "exp": payload.get("exp"),
            "iat": payload.get("iat"),
        }

    except JWTError as e:
        error_msg = str(e).lower()
        if "expired" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Worker token expired. Send heartbeat to refresh.",
            )
        logger.warning(f"Worker JWT validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker token",
        )


def get_worker_from_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """FastAPI dependency: extract and validate worker JWT from `Authorization: Bearer <token>`."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <token>",
        )

    token = parts[1]
    return verify_worker_token(token)


def refresh_worker_token(
    current_token: str,
    new_expires_delta: Optional[timedelta] = None,
) -> str:
    """Re-issue a worker JWT with the same claims but a new expiration."""
    payload = verify_worker_token(current_token)

    return create_worker_token(
        worker_id=payload["worker_id"],
        queue_labels=payload["queue_labels"],
        capabilities=payload["capabilities"],
        expires_delta=new_expires_delta,
    )
