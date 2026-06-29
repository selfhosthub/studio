# api/app/infrastructure/auth/jwt.py

"""JWT token generation and validation."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.domain.common.value_objects import Role
from app.infrastructure.logging.request_context import update_request_identity
from app.infrastructure.persistence.database import get_db_session
from app.infrastructure.persistence.models import OrganizationModel, UserModel

SECRET_KEY: str = settings.JWT_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS
WEBHOOK_TOKEN_EXPIRE_HOURS = settings.WEBHOOK_TOKEN_EXPIRE_HOURS

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()

    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # `iat` is set explicitly: token-invalidation checks require it.
    to_encode.update({"exp": expire, "iat": now})

    encoded_jwt: str = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    encoded_jwt: str = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_refresh_token(token: str) -> Dict[str, Any]:
    """Verify a refresh token. Raises HTTPException on invalid/expired/wrong-type tokens."""
    try:
        payload: Dict[str, Any] = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return payload
    except JWTError as e:
        error_msg = str(e).lower()
        if "expired" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_webhook_token(job_id: uuid.UUID) -> str:
    """Issue a short-lived JWT for authenticating inbound job-status webhook callbacks."""
    data: Dict[str, Any] = {
        "sub": str(job_id),
        "type": "webhook",
        "purpose": "job_status",
        "iat": datetime.now(UTC).timestamp(),
    }

    expires_delta = timedelta(hours=WEBHOOK_TOKEN_EXPIRE_HOURS)
    return create_access_token(data, expires_delta)


def verify_token(token: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload


def _iat_is_stale(
    iat: Optional[int],
    password_changed_at: Optional[datetime],
    role_changed_at: Optional[datetime],
    logged_out_at: Optional[datetime],
) -> bool:
    """True if `iat` is older than any invalidation event (or absent).

    Integer-seconds comparison matches JWT's `iat` precision.
    """
    if iat is None:
        return True
    iat_seconds = int(iat)
    for ts in (password_changed_at, role_changed_at, logged_out_at):
        if ts is not None and iat_seconds < int(ts.timestamp()):
            return True
    return False


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Resolve the current user from a JWT, enforcing token-invalidation timestamps and org-active flag."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = verify_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        user_uuid = uuid.UUID(str(user_id))
    except ValueError:
        raise credentials_exception

    row = (
        await session.execute(
            select(
                UserModel.password_changed_at,
                UserModel.role_changed_at,
                UserModel.logged_out_at,
                UserModel.is_active,
                UserModel.organization_id,
                OrganizationModel.is_active,
                OrganizationModel.slug,
                UserModel.role,
                UserModel.username,
                UserModel.email,
                UserModel.first_name,
                UserModel.last_name,
            )
            .join(OrganizationModel, OrganizationModel.id == UserModel.organization_id)
            .where(UserModel.id == user_uuid)
        )
    ).first()

    if row is None:
        raise credentials_exception

    (
        password_changed_at,
        role_changed_at,
        logged_out_at,
        user_is_active,
        organization_id,
        org_is_active,
        org_slug,
        role,
        username,
        email,
        first_name,
        last_name,
    ) = row

    if not user_is_active or not org_is_active:
        # Reuse generic message so a deactivated user/org cannot be distinguished
        # from an invalid token. Forensic detail still lives in audit logs.
        raise credentials_exception

    if _iat_is_stale(
        payload.get("iat"),
        password_changed_at,
        role_changed_at,
        logged_out_at,
    ):
        raise credentials_exception

    # Surface the DB-resolved identity (username + org) to the logging context
    # so log attribution matches the authz source of truth (not the JWT claim).
    update_request_identity(
        username=username, org_id=str(organization_id), org_slug=org_slug
    )

    # role/username/email/first_name/last_name come from the DB (source of
    # truth). Any matching claims still in an already-issued token are ignored.
    return {
        "id": user_id,
        "username": username,
        "email": email,
        "role": role,
        "first_name": first_name,
        "last_name": last_name,
        "org_id": str(organization_id),
        "org_slug": org_slug,
    }


def decode_token(token: str) -> Dict[str, Any]:
    """Verify a JWT and return its payload."""
    if not token:
        raise JWTError("No token provided")

    payload = verify_token(token)
    return payload


async def get_current_user_ws(
    token: Optional[str], session: AsyncSession
) -> Optional[Dict[str, Any]]:
    """WebSocket user resolution - returns None instead of raising on auth failure."""
    if not token:
        return None

    try:
        payload = verify_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            logger.warning("WebSocket token missing user ID")
            return None

        try:
            user_uuid = uuid.UUID(str(user_id))
        except ValueError:
            logger.warning("WebSocket token has malformed user ID")
            return None

        try:
            row = (
                await session.execute(
                    select(
                        UserModel.password_changed_at,
                        UserModel.role_changed_at,
                        UserModel.logged_out_at,
                        UserModel.is_active,
                        UserModel.organization_id,
                        OrganizationModel.is_active,
                        OrganizationModel.slug,
                        UserModel.role,
                        UserModel.username,
                        UserModel.email,
                        UserModel.first_name,
                        UserModel.last_name,
                    )
                    .join(
                        OrganizationModel,
                        OrganizationModel.id == UserModel.organization_id,
                    )
                    .where(UserModel.id == user_uuid)
                )
            ).first()
        except Exception as e:
            logger.warning(f"WebSocket user validation failed: {e}")
            return None

        if row is None:
            logger.warning("WebSocket rejected: user not found")
            return None

        (
            password_changed_at,
            role_changed_at,
            logged_out_at,
            user_is_active,
            organization_id,
            org_is_active,
            org_slug,
            role,
            username,
            email,
            first_name,
            last_name,
        ) = row

        if not user_is_active:
            logger.warning("WebSocket rejected: user inactive")
            return None

        if not org_is_active:
            logger.warning("WebSocket rejected: organization inactive")
            return None

        if _iat_is_stale(
            payload.get("iat"),
            password_changed_at,
            role_changed_at,
            logged_out_at,
        ):
            logger.warning("WebSocket rejected: token issued before invalidation event")
            return None

        update_request_identity(
            username=username, org_id=str(organization_id), org_slug=org_slug
        )

        # role/username/email/first_name/last_name come from the DB (source of
        # truth). Any matching claims still in an old token are ignored.
        return {
            "id": user_id,
            "username": username,
            "email": email,
            "role": role,
            "first_name": first_name,
            "last_name": last_name,
            "org_id": str(organization_id),
            "org_slug": org_slug,
        }
    except JWTError as e:
        # Expired signatures are expected when sessions expire - don't log them.
        error_msg = str(e)
        if "expired" not in error_msg.lower():
            logger.warning(f"WebSocket JWT validation failed: {error_msg}")
        return None


class RoleChecker:
    """FastAPI dependency that enforces allowed roles on an endpoint."""

    def __init__(self, allowed_roles: list[Role]) -> None:
        self.allowed_roles = allowed_roles

    async def __call__(
        self, request: Request, user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:
        user_role = user.get("role")
        if user_role not in self.allowed_roles:
            await self._log_access_denied(user, request)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted",
            )
        return user

    async def _log_access_denied(  # pragma: no cover
        self, user: Dict[str, Any], request: Request
    ) -> None:
        try:
            from app.infrastructure.persistence.database import get_db_session
            from app.infrastructure.repositories.audit_repository import (
                AuditEventRepository,
            )
            from app.application.services.audit_service import AuditService
            from app.domain.audit.models import (
                AuditAction,
                AuditActorType,
                AuditCategory,
                AuditSeverity,
                AuditStatus,
                ResourceType,
            )

            user_id_str = user.get("id") or user.get("sub") or ""
            org_id = user.get("org_id")

            # Resolve through dependency_overrides so tests can substitute the session factory.
            session_dep = request.app.dependency_overrides.get(
                get_db_session, get_db_session
            )
            session: Optional[AsyncSession] = None
            async for session in session_dep():
                assert session is not None
                repo = AuditEventRepository(session)
                svc = AuditService(repo)
                await svc.log_event(
                    actor_id=uuid.UUID(str(user_id_str)) if user_id_str else None,
                    actor_type=AuditActorType(user.get("role", "user")),
                    action=AuditAction.ACCESS_DENIED,
                    resource_type=ResourceType.USER,
                    organization_id=uuid.UUID(org_id) if org_id else None,
                    severity=AuditSeverity.WARNING,
                    category=AuditCategory.SECURITY,
                    status=AuditStatus.FAILED,
                    error_message=f"Role '{user.get('role')}' not in {[str(r) for r in self.allowed_roles]}",
                    metadata={
                        "denial_type": "role",
                        "user_role": str(user.get("role")),
                        "required_roles": [str(r) for r in self.allowed_roles],
                    },
                )
        except Exception as e:
            logger.warning(f"Failed to log access denied audit event: {e}")
