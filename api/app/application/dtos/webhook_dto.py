# api/app/application/dtos/webhook_dto.py

"""DTOs for managing workflow webhook configurations (not incoming payloads)."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateWebhookRequest(BaseModel):
    workflow_id: UUID
    method: Literal["POST", "GET"] = "POST"
    auth_type: Literal["none", "header", "jwt"] = "none"
    auth_header_name: Optional[str] = Field(
        None,
        description="Header name for header auth (e.g., 'X-API-Key')",
    )
    auth_header_value: Optional[str] = Field(
        None,
        description="Header value for header auth",
    )
    jwt_secret: Optional[str] = Field(
        None,
        description="JWT signing secret for jwt auth (HS256)",
    )
    enable_signature_verification: bool = Field(
        False,
        description="Enable HMAC signature verification",
    )


class UpdateWebhookRequest(BaseModel):
    method: Optional[Literal["POST", "GET"]] = None
    auth_type: Optional[Literal["none", "header", "jwt"]] = None
    auth_header_name: Optional[str] = None
    auth_header_value: Optional[str] = None
    jwt_secret: Optional[str] = None
    regenerate_token: bool = Field(
        False,
        description="Regenerate the webhook token (invalidates old URLs)",
    )
    regenerate_secret: bool = Field(
        False,
        description="Regenerate the HMAC signing secret",
    )


class WebhookResponse(BaseModel):
    workflow_id: UUID
    webhook_url: str = Field(
        ...,
        description="Full URL for triggering the workflow via webhook",
    )
    webhook_token: str = Field(
        ...,
        description="Secure token (included in URL)",
    )
    method: str = Field(
        ...,
        description="HTTP method (POST or GET)",
    )
    auth_type: str = Field(
        ...,
        description="Authentication type: none, header, or jwt",
    )
    auth_header_name: Optional[str] = Field(
        None,
        description="Header name for header auth",
    )
    has_signature_secret: bool = Field(
        ...,
        description="Whether HMAC signature verification is enabled",
    )
    signature_secret: Optional[str] = Field(
        None,
        description="HMAC signing secret (only returned on create/regenerate)",
    )
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ListWebhooksResponse(BaseModel):
    items: List[WebhookResponse]
    total: int
    skip: int
    limit: int
