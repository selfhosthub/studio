# api/app/infrastructure/provider_installer.py

"""Installs providers from the unified single-file format into the database. Always upserts - the parsed package dict is the source of truth."""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.sources import DEFAULT_TIER
from app.domain.common.value_objects import OperationalStatus, Visibility
from app.domain.provider.models import (
    PackageType,
    ProviderType,
    ServiceType,
)
from app.infrastructure.errors import safe_error_message
from app.infrastructure.persistence.models import (
    ProviderModel,
    ProviderServiceModel,
)
from app.infrastructure.services.package_version_service import PackageVersionService
from contracts.webhook_completion import audit_provider_webhook_completion

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
    """Takes a parsed unified provider dict, upserts provider + service rows, and records a package-version snapshot."""

    async def install_from_data(
        self,
        provider_data: dict[str, Any],
        session: AsyncSession,
        created_by: uuid.UUID,
        provider_type_override: str | None = None,
        *,
        allow_reserved: bool = False,
        visibility_on_insert: Visibility | None = None,
    ) -> InstallResult:
        """Install a provider from an already-parsed unified dict.

        The shared core behind the /upload and /install-from-url routes, the
        catalog installer, and the seeder - validate + persist with no file or
        URL coupling.
        """
        if provider_type_override:
            provider_data["provider_type"] = provider_type_override

        # No source path here; name error results off the dict's own fields.
        fallback_name = (
            provider_data.get("slug") or provider_data.get("name") or "unknown"
        )
        try:
            slug = provider_data["slug"]
            version = provider_data.get("version", "1.0.0")
        except KeyError as e:
            missing = e.args[0] if e.args else "unknown"
            allowed = {"slug", "version", "name", "provider_type"}
            field_name = missing if missing in allowed else "required"
            return InstallResult(
                package_name=fallback_name,
                version="",
                provider_id=uuid.uuid4(),
                provider_name=fallback_name,
                success=False,
                error=f"Package is missing the '{field_name}' field.",
            )

        # A service that opts into webhook completion mode must declare every
        # required webhook_completion path; a half-built block would silently
        # strand the step. Fail the install loudly instead (invariant in
        # docs/plans/leonardo-webhook-listen-mode.md S13.4).
        webhook_issues = audit_provider_webhook_completion(provider_data)
        if webhook_issues:
            return InstallResult(
                package_name=slug,
                version=version,
                provider_id=uuid.uuid4(),
                provider_name=provider_data.get("name", slug),
                success=False,
                error="Invalid webhook_completion config: " + "; ".join(webhook_issues),
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
                visibility_on_insert=visibility_on_insert,
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
                allow_reserved=allow_reserved,
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

    async def _upsert_provider(
        self,
        session: AsyncSession,
        provider_data: dict[str, Any],
        version: str,
        source_hash: str,
        created_by: uuid.UUID,
        *,
        visibility_on_insert: Visibility | None = None,
    ) -> uuid.UUID:
        """Upsert a provider row; maps unified-file content to model fields.

        source_hash is accepted for call-site compatibility but is recomputed by the shared installer helper.
        """
        del source_hash  # recomputed in the helper

        from app.application.services.versioned_installer import install_versioned

        def apply_provider_content(row: ProviderModel, data: dict[str, Any]) -> None:
            # Normalize provider_type → enum NAME (uppercase). Required by the
            # provider schema; an unknown value is a hard error, not silently
            # coerced to API.
            raw_type = data["provider_type"].upper()
            valid_types = {t.name for t in ProviderType}
            if raw_type not in valid_types:
                raise ValueError(
                    f"provider '{data['slug']}': unknown provider_type "
                    f"'{data['provider_type']}' (expected one of {sorted(valid_types)})"
                )
            row.provider_type = ProviderType[raw_type]
            # Normalize operational_status - accept "ACTIVE"/"INACTIVE" and
            # "active"/"inactive". visibility is left to its column default
            # (PUBLIC) on insert and preserved as-is on re-install upsert.
            raw_status = (data.get("status") or "ACTIVE").lower()
            row.operational_status = (
                OperationalStatus.INACTIVE
                if raw_status == "inactive"
                else OperationalStatus.ACTIVE
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
                "tier": data.get("tier", DEFAULT_TIER),
                "category": data["category"],
                "credential_provider": data.get("credential_provider"),
                "requires": data.get("requires", []),
                "services_preview": data.get("services_preview", []),
            }
            if "field_type_mapping" in data:
                client_metadata["field_type_mapping"] = data["field_type_mapping"]
            # Provider-level webhook envelope (inbound callback shape + auth),
            # resolvable pre-demux from credential->provider. Service-level
            # webhook_completion (the asset shape) is persisted per-service.
            if "webhook_completion" in data:
                client_metadata["webhook_completion"] = data["webhook_completion"]
            row.client_metadata = client_metadata

            row.name = data["name"]
            row.description = data.get("description", "")
            row.endpoint_url = data.get("base_url") or ""
            # capabilities column is unused by runtime code;
            # keep as empty dict so existing index queries don't break.
            row.capabilities = {}

        extra_insert_fields: dict[str, Any] = {"created_by": created_by}
        if visibility_on_insert is not None:
            extra_insert_fields["visibility"] = visibility_on_insert

        outcome = await install_versioned(
            session,
            ProviderModel,
            type_name="provider",
            content=provider_data,
            apply_content=apply_provider_content,
            extra_insert_fields=extra_insert_fields,
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
            # Service-authored notice shown in the UI when an array is mapped to a
            # non-iterable service (which handles arrays internally).
            "array_mapping_notice": service_data.get("array_mapping_notice"),
            "supports_image_presets": service_data.get(
                "supports_image_presets", False
            ),
            "queue": service_data.get("queue"),
            # Worker-side handler selector: "http_request" routes through the
            # generic outbound-HTTP handler; additional handlers can be listed
            # here without code changes.
            "dispatch": service_data.get("dispatch"),
            # Per-step completion mode + the declared callback paths the inbound
            # webhook handler reads to match an id and locate the result assets.
            "completion_modes": service_data.get("completion_modes"),
            "webhook_completion": service_data.get("webhook_completion"),
            # Chat prompt shaping: prompt_shape="chat" opts the service into
            # the dispatch shaper; wire_dialect (openai|anthropic|gemini) is
            # the only key the shaper branches on - never provider name.
            "prompt_shape": service_data.get("prompt_shape"),
            "wire_dialect": service_data.get("wire_dialect"),
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
            existing.custom_ui = service_data.get("custom_ui", False)
            existing.custom_output = service_data.get("custom_output", False)
            existing.parameter_title = service_data.get("parameter_title")
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
            custom_ui=service_data.get("custom_ui", False),
            custom_output=service_data.get("custom_output", False),
            parameter_title=service_data.get("parameter_title"),
            client_metadata=svc_client_metadata,
            version=version,
            created_by=created_by,
        )
        session.add(service)
        await session.flush()
        return service.id
