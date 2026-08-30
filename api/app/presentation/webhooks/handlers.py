# api/app/presentation/webhooks/handlers.py

"""Public token-based incoming webhook endpoints (POST/GET)."""

import logging
from typing import Any, Dict, cast
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.application.services.webhook_service import (
    AUTH_FAILURE_CODES,
    WebhookService,
)
from app.domain.common.exceptions import (
    EntityNotFoundError,
    ValidationError,
)
from app.presentation.api.dependencies import get_webhook_service_public
from app.infrastructure.errors import safe_error_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Webhooks"])


def _status_for(code: Any) -> int:
    """Rejected credentials are 401; every other rejection is a payload problem."""
    if code in AUTH_FAILURE_CODES:
        return status.HTTP_401_UNAUTHORIZED
    return status.HTTP_400_BAD_REQUEST


async def _parse_body(request: Request) -> Dict[str, Any]:
    """Decode a POST body by content type. An unparseable body is rejected, not
    dispatched: a malformed request must not look like an empty one."""
    raw = await request.body()
    if not raw:
        return {}

    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    try:
        if content_type == "application/x-www-form-urlencoded":
            text = raw.decode("utf-8")
            # parse_qsl accepts anything, so a body that is not form-encoded
            # arrives as one garbage key. Require a field separator and reject
            # a JSON document declared as a form.
            if "=" not in text or text.lstrip()[:1] in ("{", "["):
                raise ValueError("body is not form-encoded")
            parsed: Any = dict(parse_qsl(text, keep_blank_values=True))
        else:
            parsed = await request.json()
    except Exception as e:
        logger.warning(f"Failed to parse webhook request body ({content_type}): {e}")
        raise ValidationError(
            message="Request body could not be parsed",
            code="UNPARSEABLE_BODY",
        )

    if not isinstance(parsed, dict):
        logger.warning(f"Webhook request body is {type(parsed).__name__}, not an object")
        raise ValidationError(
            message="Request body must be an object",
            code="BODY_NOT_AN_OBJECT",
        )
    return parsed


async def _handle_webhook(
    token: str,
    request: Request,
    response: Response,
    service: WebhookService,
) -> Dict[str, Any]:
    """Shared POST/GET dispatch. Payload follows n8n convention: {body, query, method}."""
    try:
        method = request.method.upper()

        # Read once: Starlette caches the body, so a signature verifier can see
        # the exact bytes that _parse_body decoded.
        raw_body = await request.body()
        body_data = await _parse_body(request) if method == "POST" else {}
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
            raw_body=raw_body,
        )

        # A handshake is answered in the sender's own shape, not the trigger
        # envelope, and with the 200 those handshakes require.
        if result.get("status") == "handshake":
            response.status_code = status.HTTP_200_OK
            return cast(Dict[str, Any], result["body"])

        return result

    except EntityNotFoundError as e:
        logger.warning(f"Webhook not matched token={token[:8]}...: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )
    except ValidationError as e:
        code = getattr(e, "code", None)
        logger.warning(f"Webhook rejected token={token[:8]}... code={code}: {e}")
        raise HTTPException(
            status_code=_status_for(code),
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
    response: Response,
    service: WebhookService = Depends(get_webhook_service_public),
) -> Dict[str, Any]:
    """POST webhook trigger. Payload: {body, query, method='POST'} + body flattened on top."""
    return await _handle_webhook(token, request, response, service)


@router.get(
    "/incoming/{token}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Handle incoming webhook (GET)",
    description="Trigger a workflow via GET request with query parameters.",
)
async def handle_incoming_webhook_get(
    token: str,
    request: Request,
    response: Response,
    service: WebhookService = Depends(get_webhook_service_public),
) -> Dict[str, Any]:
    """GET webhook trigger. Payload: {body={}, query, method='GET'} + query flattened on top."""
    return await _handle_webhook(token, request, response, service)


@router.post(
    "/trigger/{workflow_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a workflow via API key",
    description="Trigger a workflow with a bearer API key in the Authorization header.",
)
async def handle_api_trigger_endpoint(
    workflow_id: UUID,
    request: Request,
    service: WebhookService = Depends(get_webhook_service_public),
) -> Dict[str, Any]:
    """API trigger. Bearer-key auth; JSON body becomes the instance payload."""
    auth = request.headers.get("authorization", "")
    api_key = auth[7:].strip() if auth[:7].lower() == "bearer " else ""

    try:
        body = await request.body()
        payload = await request.json() if body else {}
    except Exception as e:
        logger.warning(f"Failed to parse API trigger request body as JSON: {e}")
        payload = {}

    try:
        return await service.handle_api_trigger(
            workflow_id,
            api_key,
            payload,
            dict(request.headers),
        )
    except EntityNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_message(e),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=_status_for(getattr(e, "code", None)),
            detail=safe_error_message(e),
        )
