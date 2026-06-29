# api/app/application/event_handlers/organization_handler.py

"""Side effects of organization lifecycle events (workspace dirs, .org-info)."""

import logging

from app.domain.common.events import OrganizationCreatedEvent, OrganizationUpdatedEvent
from app.infrastructure.storage.workspace import (
    ensure_org_workspace,
    get_workspace_path,
    write_org_info,
)

logger = logging.getLogger(__name__)


async def handle_organization_created(event: OrganizationCreatedEvent) -> None:
    try:
        logger.info(
            f"Handling OrganizationCreatedEvent for org {event.organization_id}"
        )
        name = event.data.get("name") if event.data else None
        slug = event.data.get("slug") if event.data else None
        ensure_org_workspace(event.organization_id, name=name, slug=slug)
        logger.info(
            f"Created workspace directories for organization {event.organization_id}"
        )
    except Exception as e:
        logger.error(
            f"Failed to create workspace directories for organization {event.organization_id}: {e}",
        )
        # Swallow: workspace creation failure must not block org creation -
        # directories can be created later via the sync command.


async def handle_organization_updated(event: OrganizationUpdatedEvent) -> None:
    try:
        name = event.data.get("name") if event.data else None
        slug = event.data.get("slug") if event.data else None
        if not name or not slug:
            return

        workspace_path = get_workspace_path()
        org_dir = workspace_path / "orgs" / str(event.organization_id)
        if org_dir.exists():
            write_org_info(org_dir, name, slug)
            logger.info(f"Updated .org-info for organization {event.organization_id}")
    except Exception as e:
        logger.error(
            f"Failed to update .org-info for organization {event.organization_id}: {e}",
        )


EVENT_HANDLERS = {
    OrganizationCreatedEvent: handle_organization_created,
    OrganizationUpdatedEvent: handle_organization_updated,
}
