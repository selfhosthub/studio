# api/app/presentation/webhooks/handlers.py

"""Public token-based incoming webhook endpoints (POST/GET)."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.services.webhook_service import WebhookService
from app.domain.common.exceptions import (
    EntityNotFoundError,
    ValidationError,
)
from app.presentation.api.dependencies import get_webhook_service_public
from app.infrastructure.errors import safe_error_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Webhooks"])


async def _handle_webhook(
    token: str,
    request: Request,
    service: WebhookService,
) -> Dict[str, Any]:
    """Shared POST/GET dispatch. Payload follows n8n convention: {body, query, method}."""
    try:
        method = request.method.upper()

        if method == "POST":
            try:
                body = await request.body()
                if body:
                    body_data = await request.json()
                else:
                    body_data = {}
            except Exception as e:
                # Log so malformed webhook payloads are visible - non-JSON bodies otherwise silently become {}
                logger.warning(f"Failed to parse webhook request body as JSON: {e}")
                body_data = {}
            query_data = dict(request.query_params)
        else:
            body_data = {}
            query_data = dict(request.query_params)

        payload = {
            "body": body_data,
            "query": query_data,
            "method": method,
        }

        # Flatten body/query to top level so workflows expecting flat payload still work
        if body_data:
            payload.update(body_data)
        elif query_data:
            payload.update(query_data)

        headers = dict(request.headers)

        result = await service.handle_incoming_webhook_by_token(
            token=token,
            payload=payload,
            headers=headers,
        )

        return result

    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_message(e),
        )


@router.post(
    "/incoming/{token}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Handle incoming webhook (POST)",
    description="Trigger a workflow via POST request with JSON body.",
)
async def handle_incoming_webhook_post(
    token: str,
    request: Request,
    service: WebhookService = Depends(get_webhook_service_public),
) -> Dict[str, Any]:
    """POST webhook trigger. Payload: {body, query, method='POST'} + body flattened on top."""
    return await _handle_webhook(token, request, service)


@router.get(
    "/incoming/{token}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Handle incoming webhook (GET)",
    description="Trigger a workflow via GET request with query parameters.",
)
async def handle_incoming_webhook_get(
    token: str,
    request: Request,
    service: WebhookService = Depends(get_webhook_service_public),
) -> Dict[str, Any]:
    """GET webhook trigger. Payload: {body={}, query, method='GET'} + query flattened on top."""
    return await _handle_webhook(token, request, service)
