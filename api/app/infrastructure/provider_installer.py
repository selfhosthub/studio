# api/app/infrastructure/provider_installer.py

"""Installs providers from the unified single-file format into the database. Always upserts - the package file is the source of truth."""

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.provider.models import (
    PackageSource,
    PackageType,
    ProviderStatus,
    ProviderType,
    ServiceType,
)
from app.infrastructure.errors import safe_error_message
from app.infrastructure.persistence.models import (
    ProviderModel,
    ProviderServiceModel,
)
from app.infrastructure.services.package_version_service import PackageVersionService

logger = logging.getLogger(__name__)


@dataclass
class InstallResult:

    package_name: str
    version: str
    provider_id: uuid.UUID
    provider_name: str
    services_installed: list[str] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class ProviderInstaller:
    """Reads unified single-file provider JSON, upserts provider + service rows, and records a package-version snapshot."""

    async def install_from_path(
        self,
        package_path: str | Path,
        session: AsyncSession,
        created_by: uuid.UUID,
        provider_type_override: str | None = None,
        source: PackageSource = PackageSource.LOCAL,
    ) -> InstallResult:
        """Install from a unified JSON file or a directory containing exactly one."""
        package_path = Path(package_path)

        # Allow callers to pass either the JSON file directly or a directory
        # containing exactly one provider .json (the studio-cat/providers
        # layout uses flat files, but uploaded packages land in a temp dir).
        if package_path.is_dir():
            json_files = list(package_path.glob("*.json"))
            if len(json_files) != 1:
                return InstallResult(
                    package_name=package_path.name,
                    version="",
                    provider_id=uuid.uuid4(),
                    provider_name=package_path.name,
                    success=False,
                    error=f"Expected exactly one .json file in {package_path}, found {len(json_files)}",
                )
            package_path = json_files[0]

        provider_data = self._load_json(package_path)

        if provider_type_override:
            provider_data["provider_type"] = provider_type_override

        try:
            slug = provider_data["slug"]
            version = provider_data.get("version", "1.0.0")
        except KeyError as e:
            missing = e.args[0] if e.args else "unknown"
            allowed = {"slug", "version", "name", "provider_type"}
            field_name = missing if missing in allowed else "required"
            return InstallResult(
                package_name=package_path.stem,
                version="",
                provider_id=uuid.uuid4(),
                provider_name=package_path.stem,
                success=False,
                error=f"Package is missing the '{field_name}' field.",
            )

        # Snapshot stores the unified content directly. No more
        # {manifest, provider, adapter_config, services} envelope.
        json_content = provider_data
        source_hash = PackageVersionService.compute_source_hash(json_content)

        logger.info(f"Installing provider: {slug} v{version}")

        try:
            provider_id = await self._upsert_provider(
                session,
                provider_data,
                version,
                source_hash,
                created_by,
            )

            services_installed = []
            for service_slug, service_data in provider_data.get("services", {}).items():
                # service_id has provider.service shape for global uniqueness.
                full_service_id = f"{slug}.{service_slug}"
                await self._upsert_service(
                    session,
                    provider_id,
                    full_service_id,
                    service_data,
                    version,
                    created_by,
                )
                services_installed.append(full_service_id)

            await PackageVersionService.record_version(
                session=session,
                package_type=PackageType.PROVIDER,
                slug=slug,
                version=version,
                json_content=json_content,
                source_hash=source_hash,
                created_by=created_by,
                source=source,
            )

            logger.info(
                f"✅ Installed {slug} v{version}: {len(services_installed)} services"
            )

            return InstallResult(
                package_name=slug,
                version=version,
                provider_id=provider_id,
                provider_name=provider_data.get("name", slug),
                services_installed=services_installed,
                success=True,
            )
        except Exception as e:
            logger.exception(f"Failed to install {slug}")
            return InstallResult(
                package_name=slug,
                version=version,
                provider_id=uuid.uuid4(),
                provider_name=provider_data.get("name", slug),
                success=False,
                error=safe_error_message(e),
            )

    def _load_json(self, path: Path) -> dict[str, Any]:
        with open(path, "r") as f:
            return json.load(f)

    async def _upsert_provider(
        self,
        session: AsyncSession,
        provider_data: dict[str, Any],
        version: str,
        source_hash: str,
        created_by: uuid.UUID,
    ) -> uuid.UUID:
        """Upsert a provider row; maps unified-file content to model fields.

        source_hash is accepted for call-site compatibility but is recomputed by the shared installer helper.
        """
        del source_hash  # recomputed in the helper

        from app.application.services.versioned_installer import install_versioned

        def apply_provider_content(row: ProviderModel, data: dict[str, Any]) -> None:
            # Normalize provider_type → enum NAME (uppercase)
            raw_type = (data.get("provider_type") or "API").upper()
            valid_types = {t.name for t in ProviderType}
            row.provider_type = ProviderType[
                raw_type if raw_type in valid_types else "API"
            ]
            # Normalize status - accept "ACTIVE"/"INACTIVE" and "active"/"inactive"
            raw_status = (data.get("status") or "ACTIVE").lower()
            row.status = (
                ProviderStatus.INACTIVE
                if raw_status == "inactive"
                else ProviderStatus.ACTIVE
            )

            # config column: auth + adapter_config + local_worker, read by
            # step_endpoint_resolver.py at runtime.
            config: dict[str, Any] = {}
            if "auth" in data:
                config["auth"] = data["auth"]
            if "oauth" in data:
                config["oauth"] = data["oauth"]
                config["oauth_provider"] = data["oauth"].get("oauth_provider")
            if "local_worker" in data:
                config["local_worker"] = data["local_worker"]
            adapter_block: dict[str, Any] = {}
            if "default_headers" in data:
                adapter_block["default_headers"] = data["default_headers"]
            if "default_queue" in data:
                adapter_block["default_queue"] = data["default_queue"]
            if adapter_block:
                config["adapter_config"] = adapter_block
            row.config = config

            # client_metadata: display + marketplace fields the UI reads back.
            client_metadata = {
                "credential_schema": data.get("credential_schema"),
                "documentation_url": data.get("documentation_url", ""),
                "icon_url": data.get("icon_url", ""),
                "package_version": data["version"],
                "slug": data["slug"],
                "tier": data.get("tier", "basic"),
                "category": data.get("category", "core"),
                "credential_provider": data.get("credential_provider"),
                "requires": data.get("requires", []),
                "services_preview": data.get("services_preview", []),
            }
            if "field_type_mapping" in data:
                client_metadata["field_type_mapping"] = data["field_type_mapping"]
            row.client_metadata = client_metadata

            row.name = data["name"]
            row.description = data.get("description", "")
            row.endpoint_url = data.get("base_url") or ""
            # capabilities column is unused by runtime code;
            # keep as empty dict so existing index queries don't break.
            row.capabilities = {}

        outcome = await install_versioned(
            session,
            ProviderModel,
            type_name="provider",
            content=provider_data,
            apply_content=apply_provider_content,
            extra_insert_fields={"created_by": created_by},
        )
        return outcome.row_id

    async def _upsert_service(
        self,
        session: AsyncSession,
        provider_id: uuid.UUID,
        full_service_id: str,
        service_data: dict[str, Any],
        version: str,
        created_by: uuid.UUID,
    ) -> uuid.UUID:

        ui_hints = service_data.get("ui_hints") or {}
        ui_categories = ui_hints.get("categories") or []
        categories = [c.lower() for c in ui_categories] if ui_categories else ["core"]

        try:
            service_type = ServiceType(categories[0])
        except ValueError:
            service_type = ServiceType.CORE

        # services inherit their parent provider's version via the UUID
        # input - `service.{provider}.{service}@{version}` - so two
        # versions of the same provider have distinct service rows.
        service_uuid = uuid.uuid5(
            uuid.NAMESPACE_DNS, f"service.{full_service_id}@{version}"
        )

        # client_metadata absorbs the unified file's per-service fields that
        # don't have a dedicated column on ProviderServiceModel. The runtime
        # consumers (step_endpoint_resolver, generic_http_adapter, worker
        # handler) read from this dict.
        svc_client_metadata = {
            "endpoint": service_data.get("path", "/"),
            "endpoint_url": service_data.get("endpoint_url"),
            "method": service_data.get("method", "POST"),
            "requires_credentials": service_data.get("requires_credentials", True),
            "post_processing": service_data.get("post_processing"),
            "polling": service_data.get("polling"),
            "parameter_mapping": service_data.get("parameter_mapping"),
            "request_transform": service_data.get("request_transform"),
            "ui_hints": service_data.get("ui_hints"),
            "orchestrator_hints": service_data.get("orchestrator_hints"),
            "output_view": service_data.get("output_view"),
            "iterable": service_data.get("iterable", True),
            "queue": service_data.get("queue"),
            # Worker-side handler selector: "http_request" routes through the
            # generic outbound-HTTP handler; additional handlers can be listed
            # here without code changes.
            "dispatch": service_data.get("dispatch"),
        }

        result = await session.execute(
            select(ProviderServiceModel).where(
                ProviderServiceModel.provider_id == provider_id,
                ProviderServiceModel.service_id == full_service_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.display_name = service_data.get("display_name", full_service_id)
            existing.service_type = service_type
            existing.categories = categories
            existing.description = service_data.get("description", "")
            existing.endpoint = service_data.get("path", "")
            existing.parameter_schema = service_data.get("parameter_schema", {})
            existing.result_schema = service_data.get("result_schema", {})
            existing.example_parameters = service_data.get("example_parameters", {})
            existing.is_active = service_data.get("is_active", True)
            existing.client_metadata = svc_client_metadata
            existing.version = version
            await session.flush()
            return existing.id

        service = ProviderServiceModel(
            id=service_uuid,
            provider_id=provider_id,
            service_id=full_service_id,
            display_name=service_data.get("display_name", full_service_id),
            service_type=service_type,
            categories=categories,
            description=service_data.get("description", ""),
            endpoint=service_data.get("path", ""),
            parameter_schema=service_data.get("parameter_schema", {}),
            result_schema=service_data.get("result_schema", {}),
            example_parameters=service_data.get("example_parameters", {}),
            is_active=service_data.get("is_active", True),
            client_metadata=svc_client_metadata,
            version=version,
            created_by=created_by,
        )
        session.add(service)
        await session.flush()
        return service.id


async def install_all_providers(
    providers_dir: str | Path, session: AsyncSession, created_by: uuid.UUID
) -> list[InstallResult]:
    """Install every provider JSON file found in the given directory."""
    providers_dir = Path(providers_dir)
    installer = ProviderInstaller()
    results: list[InstallResult] = []
    for json_file in sorted(providers_dir.glob("*.json")):
        result = await installer.install_from_path(json_file, session, created_by)
        results.append(result)
    return results
