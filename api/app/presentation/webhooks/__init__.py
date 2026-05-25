# api/app/presentation/webhooks/__init__.py

"""Incoming webhook handlers for external service integrations."""
from fastapi import APIRouter

from app.presentation.webhooks import handlers

webhook_router = APIRouter()
webhook_router.include_router(handlers.router, prefix="/webhooks")
