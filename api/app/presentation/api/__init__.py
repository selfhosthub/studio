# api/app/presentation/api/__init__.py

"""FastAPI router registration."""

import logging

from fastapi import FastAPI

from app.presentation.api import (
    audit,
    auth,
    comfyui_marketplace,
    docs,
    instances,
    org_files,
    marketplace,
    notifications,
    oauth,
    organization_secrets,
    organizations,
    packages,
    prompts,
    prompts_marketplace,
    providers,
    public,
    queues,
    site_content,
    system_health,
    system_version,
    users,
    worker_credentials,
    worker_jobs,
    workers,
    workflows,
    workflows_marketplace,
)

logger = logging.getLogger(__name__)


def register_routers(app: FastAPI, api_prefix: str = "/api/v1") -> None:
    """Mount all API routers under api_prefix."""
    app.include_router(public.router, prefix=f"{api_prefix}/public", tags=["Public"])

    app.include_router(
        auth.router, prefix=f"{api_prefix}/auth", tags=["Authentication"]
    )
    # organization_secrets must precede organizations: /organizations/secrets vs /organizations/{id}
    app.include_router(
        organization_secrets.router,
        prefix=f"{api_prefix}/organizations",
        tags=["Organization Secrets"],
    )
    app.include_router(
        organizations.router,
        prefix=f"{api_prefix}/organizations",
        tags=["Organizations"],
    )
    app.include_router(users.router, prefix=f"{api_prefix}/users", tags=["Users"])
    # Blueprint routes disabled - feature is being redesigned (coming soon)
    # app.include_router(blueprints.router, prefix=f"{api_prefix}/blueprints", tags=["Blueprints"])
    # workflows_marketplace must precede workflows: avoids /{workflow_id} catch-all
    app.include_router(
        workflows_marketplace.router,
        prefix=f"{api_prefix}/workflows/marketplace",
        tags=["Workflows Marketplace"],
    )
    app.include_router(
        workflows.router, prefix=f"{api_prefix}/workflows", tags=["Workflows"]
    )
    app.include_router(
        instances.router, prefix=f"{api_prefix}/instances", tags=["Instances"]
    )
    app.include_router(
        providers.router, prefix=f"{api_prefix}/providers", tags=["Providers"]
    )
    # Webhooks are mounted separately at /webhooks during app startup
    app.include_router(queues.router, prefix=f"{api_prefix}/queues", tags=["Queues"])
    app.include_router(workers.router, prefix=f"{api_prefix}/workers", tags=["Workers"])
    app.include_router(
        notifications.router,
        prefix=f"{api_prefix}/notifications",
        tags=["Notifications"],
    )
    app.include_router(
        org_files.router, prefix=f"{api_prefix}", tags=["Files"]
    )
    app.include_router(
        system_health.router, prefix=f"{api_prefix}", tags=["Infrastructure"]
    )
    app.include_router(
        system_version.router, prefix=f"{api_prefix}", tags=["System"]
    )
    app.include_router(oauth.router, prefix=f"{api_prefix}/oauth", tags=["OAuth"])
    app.include_router(
        worker_credentials.router,
        prefix=f"{api_prefix}/internal",
        tags=["Worker Internal"],
    )
    app.include_router(
        worker_jobs.router,
        prefix=f"{api_prefix}",  # router already has /internal prefix
        tags=["Worker Jobs"],
    )
    app.include_router(
        site_content.router, prefix=f"{api_prefix}/site-content", tags=["Site Content"]
    )
    app.include_router(
        marketplace.router, prefix=f"{api_prefix}/marketplace", tags=["Marketplace"]
    )
    app.include_router(
        packages.router, prefix=f"{api_prefix}/packages", tags=["Packages"]
    )
    # Blueprint marketplace routes disabled - feature is being redesigned (coming soon)
    # app.include_router(
    #     blueprints_marketplace.router,
    #     prefix=f"{api_prefix}/blueprints/marketplace",
    #     tags=["Blueprints Marketplace"],
    # )
    app.include_router(
        prompts_marketplace.router,
        prefix=f"{api_prefix}/prompts/marketplace",
        tags=["Prompts Marketplace"],
    )
    app.include_router(
        comfyui_marketplace.router,
        prefix=f"{api_prefix}/comfyui/marketplace",
        tags=["ComfyUI Marketplace"],
    )
    app.include_router(
        prompts.router,
        prefix=f"{api_prefix}/prompts",
        tags=["Prompts"],
    )
    app.include_router(audit.router, prefix=f"{api_prefix}/audit", tags=["Audit Logs"])
    app.include_router(docs.router, prefix=f"{api_prefix}/docs", tags=["Documentation"])


__all__ = ["register_routers"]
