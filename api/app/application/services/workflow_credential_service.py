# api/app/application/services/workflow_credential_service.py

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel

from app.domain.prompt.models import PromptSource
from app.domain.prompt.repository import PromptRepository
from app.domain.provider.models import CredentialType, ProviderStatus
from app.domain.provider.repository import (
    ProviderCredentialRepository,
    ProviderRepository,
    ProviderServiceRepository,
)

# ── DTOs ────────────────────────────────────────────────────────────────────


class CredentialIssue(BaseModel):
    """Details about a credential issue for a workflow step."""

    step_id: str
    step_name: str
    provider_id: str
    provider_name: str
    status: str  # "not_connected", "reauthorize_required", "inactive", "not_selected"
    message: str
    action_url: str


class CredentialCheckResult(BaseModel):
    """Result of a workflow credential readiness check."""

    ready: bool
    issues: List[CredentialIssue]


# ── Service ─────────────────────────────────────────────────────────────────


class WorkflowCredentialService:
    """Stateless - repositories injected per-call from the FastAPI endpoint."""

    async def check_workflow_credentials(
        self,
        workflow_id: UUID,
        organization_id: UUID,
        steps: Dict[str, Dict[str, Any]],
        provider_repo: ProviderRepository,
        credential_repo: ProviderCredentialRepository,
        service_repo: ProviderServiceRepository,
        prompt_repo: Optional[PromptRepository] = None,
    ) -> CredentialCheckResult:
        issues: List[CredentialIssue] = []

        for step_id, step_config in steps.items():
            issue = await self._check_step(
                step_id=step_id,
                step_config=step_config,
                workflow_id=workflow_id,
                organization_id=organization_id,
                provider_repo=provider_repo,
                credential_repo=credential_repo,
                service_repo=service_repo,
            )
            if issue is not None:
                issues.append(issue)

            # Check for missing/disabled AI agent prompts
            if prompt_repo:
                prompt_issues = await self._check_step_prompts(
                    step_id=step_id,
                    step_config=step_config,
                    workflow_id=workflow_id,
                    prompt_repo=prompt_repo,
                )
                issues.extend(prompt_issues)

        return CredentialCheckResult(ready=len(issues) == 0, issues=issues)

    # ── private helpers ─────────────────────────────────────────────────

    async def _check_step(
        self,
        step_id: str,
        step_config: Dict[str, Any],
        workflow_id: UUID,
        organization_id: UUID,
        provider_repo: ProviderRepository,
        credential_repo: ProviderCredentialRepository,
        service_repo: ProviderServiceRepository,
    ) -> CredentialIssue | None:
        """Return a CredentialIssue for a single step, or None if OK."""

        # Skip disabled steps
        execution_mode = (
            step_config.get("execution_mode")
            if step_config
            else getattr(step_config, "execution_mode", None)
        )
        if execution_mode in ("skip", "stop"):
            return None

        # Step level takes precedence over job level.
        provider_id = self._extract_provider_id(step_config)
        if provider_id is None:
            return None

        step_name = (
            step_config.get("name", step_id)
            if step_config
            else getattr(step_config, "name", step_id)
        )

        provider = await provider_repo.get_by_id(provider_id)
        provider_name = provider.name if provider else str(provider_id)

        # Check if provider is uninstalled (soft-deleted)
        if provider and provider.status == ProviderStatus.INACTIVE:
            return CredentialIssue(
                step_id=step_id,
                step_name=step_name,
                provider_id=str(provider_id),
                provider_name=provider_name,
                status="provider_not_installed",
                message=f"{provider_name} is not installed",
                action_url="/providers/marketplace",
            )

        # Check service-level requires_credentials flag
        if await self._service_opts_out_of_credentials(step_config, service_repo):
            return None

        # Skip providers that have no credential schema (e.g. internal/Core)
        if provider:
            credential_schema = provider.client_metadata.get("credential_schema")
            if not credential_schema or credential_schema == {}:
                return None

        # Resolve credential
        job = (
            step_config.get("job") if step_config else getattr(step_config, "job", None)
        )
        credential_id_str = (
            job.get("credential_id")
            if isinstance(job, dict)
            else getattr(job, "credential_id", None)
        )

        if credential_id_str:
            credential = await self._get_credential_by_id(
                credential_id_str, credential_repo
            )
        else:
            # No credential explicitly selected - check if any default exists
            credential = await credential_repo.get_default_credential(
                organization_id=organization_id,
                provider_id=provider_id,
            )
            if credential:
                return CredentialIssue(
                    step_id=step_id,
                    step_name=step_name,
                    provider_id=str(provider_id),
                    provider_name=provider_name,
                    status="not_selected",
                    message=f"No credential selected for {provider_name} in this step",
                    action_url=f"/workflows/{workflow_id}/edit",
                )

        if not credential:
            return CredentialIssue(
                step_id=step_id,
                step_name=step_name,
                provider_id=str(provider_id),
                provider_name=provider_name,
                status="not_connected",
                message=f"No credentials configured for {provider_name}",
                action_url=f"/providers/{provider_id}/credentials",
            )

        if not credential.is_active:
            return CredentialIssue(
                step_id=step_id,
                step_name=step_name,
                provider_id=str(provider_id),
                provider_name=provider_name,
                status="inactive",
                message=f"Credentials for {provider_name} are disabled",
                action_url=f"/providers/{provider_id}/credentials",
            )

        # OAuth2 refresh-token check
        if credential.credential_type == CredentialType.OAUTH2:
            refresh_token = credential.credentials.get("refresh_token")
            if not refresh_token:
                return CredentialIssue(
                    step_id=step_id,
                    step_name=step_name,
                    provider_id=str(provider_id),
                    provider_name=provider_name,
                    status="reauthorize_required",
                    message=f"OAuth authorization expired for {provider_name}. Please reconnect.",
                    action_url=f"/providers/{provider_id}/credentials",
                )

        return None

    async def _check_step_prompts(
        self,
        step_id: str,
        step_config: Dict[str, Any],
        workflow_id: UUID,
        prompt_repo: PromptRepository,
    ) -> List[CredentialIssue]:
        """Return CredentialIssues for missing or disabled AI agent prompts in a step."""

        # Skip disabled steps
        execution_mode = (
            step_config.get("execution_mode")
            if step_config
            else getattr(step_config, "execution_mode", None)
        )
        if execution_mode in ("skip", "stop"):
            return []

        step_name = (
            step_config.get("name", step_id)
            if step_config
            else getattr(step_config, "name", step_id)
        )

        issues: List[CredentialIssue] = []
        input_mappings = (
            step_config.get("input_mappings", {})
            if step_config
            else getattr(step_config, "input_mappings", {})
        ) or {}

        for _param_key, mapping in input_mappings.items():
            if not isinstance(mapping, dict):
                continue
            if mapping.get("mappingType") != "prompt":
                continue

            prompt_id_str = mapping.get("promptId")
            if not prompt_id_str:
                issues.append(
                    CredentialIssue(
                        step_id=step_id,
                        step_name=step_name,
                        provider_id="",
                        provider_name="AI Agent Prompt",
                        status="prompt_missing",
                        message="No AI agent prompt selected",
                        action_url=f"/workflows/{workflow_id}/edit",
                    )
                )
                continue

            try:
                prompt_id = (
                    UUID(prompt_id_str)
                    if isinstance(prompt_id_str, str)
                    else prompt_id_str
                )
            except (ValueError, TypeError):
                issues.append(
                    CredentialIssue(
                        step_id=step_id,
                        step_name=step_name,
                        provider_id="",
                        provider_name="AI Agent Prompt",
                        status="prompt_missing",
                        message="AI agent prompt has an invalid ID",
                        action_url=f"/workflows/{workflow_id}/edit",
                    )
                )
                continue

            prompt = await prompt_repo.get_by_id(prompt_id)
            if not prompt:
                issues.append(
                    CredentialIssue(
                        step_id=step_id,
                        step_name=step_name,
                        provider_id="",
                        provider_name="AI Agent Prompt",
                        status="prompt_missing",
                        message="AI agent prompt not found (may have been deleted)",
                        action_url=f"/workflows/{workflow_id}/edit",
                    )
                )
            elif prompt.source == PromptSource.UNINSTALLED:
                issues.append(
                    CredentialIssue(
                        step_id=step_id,
                        step_name=step_name,
                        provider_id="",
                        provider_name=f"Prompt: {prompt.name}",
                        status="prompt_missing",
                        message=f'AI agent prompt "{prompt.name}" has been uninstalled',
                        action_url="/prompts/marketplace",
                    )
                )
            elif not prompt.is_enabled:
                issues.append(
                    CredentialIssue(
                        step_id=step_id,
                        step_name=step_name,
                        provider_id="",
                        provider_name=f"Prompt: {prompt.name}",
                        status="prompt_missing",
                        message=f'AI agent prompt "{prompt.name}" is disabled',
                        action_url=f"/workflows/{workflow_id}/edit",
                    )
                )

        return issues

    # ── tiny helpers ────────────────────────────────────────────────────

    @staticmethod
    def _extract_provider_id(step_config: Dict[str, Any]) -> UUID | None:
        """Pull provider_id from step-level or job-level config."""
        provider_id_str = (
            step_config.get("provider_id")
            if step_config
            else getattr(step_config, "provider_id", None)
        )
        job = (
            step_config.get("job") if step_config else getattr(step_config, "job", None)
        )
        if not provider_id_str and job:
            provider_id_str = (
                job.get("provider_id")
                if isinstance(job, dict)
                else getattr(job, "provider_id", None)
            )
        if not provider_id_str:
            return None
        try:
            return (
                UUID(provider_id_str)
                if isinstance(provider_id_str, str)
                else provider_id_str
            )
        except (ValueError, TypeError):
            return None

    @staticmethod
    async def _service_opts_out_of_credentials(
        step_config: Dict[str, Any],
        service_repo: ProviderServiceRepository,
    ) -> bool:
        """Return True if the provider service declares requires_credentials=False."""
        service_id_str = (
            step_config.get("service_id")
            if step_config
            else getattr(step_config, "service_id", None)
        )
        job = (
            step_config.get("job") if step_config else getattr(step_config, "job", None)
        )
        if not service_id_str and job:
            service_id_str = (
                job.get("service_id")
                if isinstance(job, dict)
                else getattr(job, "service_id", None)
            )
        if not service_id_str:
            return False

        provider_service = await service_repo.get_by_service_id(
            service_id_str, skip=0, limit=1
        )
        if provider_service:
            requires_creds = provider_service.client_metadata.get(
                "requires_credentials", True
            )
            if requires_creds is False:
                return True
        return False

    @staticmethod
    async def _get_credential_by_id(credential_id_str, credential_repo):
        """Safely fetch a credential by its ID string."""
        try:
            credential_id = (
                UUID(credential_id_str)
                if isinstance(credential_id_str, str)
                else credential_id_str
            )
            return await credential_repo.get_by_id(credential_id)
        except (ValueError, TypeError):
            return None
