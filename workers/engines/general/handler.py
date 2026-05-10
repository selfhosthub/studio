# workers/engines/general/handler.py

"""General-purpose step executor worker."""

import time
import logging
from typing import Dict, Any
import httpx

logger = logging.getLogger(__name__)

from shared.utils import (
    WorkerBase,
    create_job_client,
)
from shared.utils.result_publisher import ResultPublisher
from shared.utils.credential_client import CredentialClient
from shared.settings import settings
from shared.worker_types import get_worker_config

from engines.general.executor import JobExecutor


class StepExecutor(WorkerBase):
    def __init__(self, worker_type: str = "general"):
        config = get_worker_config(worker_type)

        super().__init__(
            worker_type=config.type_id,
            queue_labels=config.queue_labels,
            capabilities=config.capabilities,
        )

        self.queue_name = config.queue_name

        # Job client initialized after registration so we have real worker_id from the API.
        self.job_client = None
        self.result_publisher = ResultPublisher(token_getter=self.get_token)
        self.credential_client = CredentialClient()
        self.http_client = httpx.Client(timeout=settings.HTTP_HANDLER_TIMEOUT_S)

        self.executor = JobExecutor(
            http_client=self.http_client,
            credential_client=self.credential_client,
            token_getter=self.get_token,
        )

    def process_jobs(self):
        """Main worker loop."""
        logger.debug("=" * 60)
        logger.info(f"🔄 {self.worker_type.upper()} Worker Started (Step Executor)")
        logger.debug("=" * 60)
        logger.info(f"Monitoring queue: {self.queue_name}")
        logger.debug(
            f"Capabilities: {', '.join(self.capabilities.get('services', []))}"
        )
        logger.debug("Press Ctrl+C to stop")

        self.job_client = create_job_client(
            worker_id=self.worker_id or self.worker_name,
            token_getter=self.get_token,
        )

        if self.worker_token:
            logger.debug(f"✅ Using JWT auth (worker_id: {self.worker_id})")
        elif self.worker_id:
            logger.debug(
                f"✅ Using registered worker_id: {self.worker_id} (legacy mode)"
            )
        else:
            logger.warning(
                "⚠️  Not registered - job claims may fail. Waiting for registration..."
            )

        try:
            while self.running:
                job = self.job_client.claim_job(
                    self.queue_name, timeout=settings.JOB_CLAIM_TIMEOUT_S
                )

                if job is None:
                    sleep_duration = self.job_client.get_sleep_duration()
                    if sleep_duration > 0:
                        time.sleep(sleep_duration)
                    continue

                self._process_step_job(job)

        finally:
            self.http_client.close()
            self.job_client.close()
            self.result_publisher.close()

    def _process_step_job(self, job: Dict[str, Any]):
        job_id = job.get("job_id", "unknown")
        step_config = job["step_config"]
        instance_parameters = job.get("instance_parameters", {})
        previous_results = job.get("previous_step_results", {})
        credential_id = job.get("credential_id")
        workflow_name = job.get("workflow_name", "Unknown")
        provider_id = job.get("provider_id")
        service_id = job.get("service_id")
        iteration_index = job.get("iteration_index")

        self.set_busy(job_id)

        logger.debug("=" * 60)
        logger.info(f"📨 Processing Step (job {job_id})", extra={"job_id": job_id})
        logger.debug(f"   Workflow: {workflow_name}")
        logger.debug(f"   Step Name: {step_config.get('name', 'Unnamed')}")
        logger.debug("=" * 60)

        step_start_time = time.time()
        try:
            orchestrator_hints = step_config.get("orchestrator_hints", {})

            # Legacy step_type field kept for backward compat.
            step_type = step_config.get("step_type") or step_config.get("type", "task")
            should_pause = (
                orchestrator_hints.get("pauses", False) or step_type == "webhook"
            )

            if should_pause:
                # Pause status is contract-driven from catalog.orchestrator_hints.pause_status.
                # Worker stays agnostic - adding a new pause type is a pure catalog edit.
                pause_status = orchestrator_hints.get("pause_status")
                if not pause_status:
                    raise ValueError(
                        f"Step declares pauses={orchestrator_hints.get('pauses')!r} "
                        f"but orchestrator_hints.pause_status is missing - "
                        f"every pause-shaped service must declare pause_status."
                    )
                wait_for = orchestrator_hints.get("wait_for", "webhook_callback")

                logger.info(f"→ Step requires pausing, waiting for: {wait_for}")

                self.result_publisher.publish_step_result(
                    status=pause_status,
                    result={
                        "wait_for": wait_for,
                        "webhook_config": step_config.get("webhook_config", {}),
                    },
                    job_id=job_id,
                )

                logger.info(f"✓ Step paused ({pause_status})")
                return  # Job resumes after callback.

            if orchestrator_hints.get("stops_workflow"):
                logger.info("-> Step stops workflow execution")

                stop_result = {
                    "stopped": True,
                    "reason": step_config.get("job", {})
                    .get("parameters", {})
                    .get("reason", "Stopped by step"),
                }

                self.result_publisher.publish_step_result(
                    status="STOPPED",
                    result=stop_result,
                    job_id=job_id,
                )

                logger.info("Workflow stopped")
                return

            polling_config = job.get("polling")
            auth_config = job.get("auth_config")
            local_worker = job.get("local_worker")
            post_processing_config = job.get("post_processing")
            result_schema = job.get("result_schema")
            org_settings = job.get("org_settings", {})
            # API-prebuilt wire envelope for HTTP-provider jobs; core services don't need it.
            http_request = job.get("http_request")
            # Catalog handler-selector list. dispatch=["http_request"] routes core services
            # like core.call_webhook through the generic outbound-HTTP handler.
            dispatch = job.get("dispatch")

            # Persist input BEFORE execution so it's visible if the worker stalls/dies.
            self.result_publisher.publish_step_result(
                status="PROCESSING", job_id=job_id
            )

            result, _ = self.executor.execute(
                step_config=step_config,
                instance_parameters=instance_parameters,
                previous_results=previous_results,
                credential_id=credential_id,
                polling_config=polling_config,
                auth_config=auth_config,
                provider_id=provider_id,
                service_id=service_id,
                local_worker=local_worker,
                post_processing_config=post_processing_config,
                result_schema=result_schema,
                org_settings=org_settings,
                iteration_index=iteration_index,
                http_request=http_request,
                dispatch=dispatch,
                job_id=job_id,
            )

            # Local-worker jobs are queued to a GPU worker that publishes COMPLETED itself.
            if isinstance(result, dict) and result.get("status") == "QUEUED":
                logger.info(f"→ Step queued to local worker: {result.get('queue')}")
                return

            # Storage preserves the full replayable payload (regen/rerun/audit depend on it).
            # Redaction happens at egress (logs, responses, telemetry).
            if not self.result_publisher.publish_step_result(
                status="COMPLETED", result=result, job_id=job_id
            ):
                logger.critical(
                    "Failed to publish step result after retries - job will be orphaned"
                )

            step_duration_ms = int((time.time() - step_start_time) * 1000)
            logger.info(
                f"Step completed (job {job_id}, {step_duration_ms}ms)",
                extra={
                    "job_id": job_id,
                    "service_id": service_id,
                    "duration_ms": step_duration_ms,
                },
            )

        except Exception as e:
            error_msg = str(e)
            step_duration_ms = int((time.time() - step_start_time) * 1000)
            logger.error(
                f"Step failed (job {job_id}, {step_duration_ms}ms): {error_msg}",
                extra={
                    "job_id": job_id,
                    "service_id": service_id,
                    "duration_ms": step_duration_ms,
                    "error": error_msg,
                },
            )

            if not self.result_publisher.publish_step_result(
                status="FAILED", error=error_msg, job_id=job_id
            ):
                logger.critical(
                    "Failed to publish step result after retries - job will be orphaned"
                )

        finally:
            self.set_idle()


# Back-compat alias.
WorkflowOrchestrator = StepExecutor


def main():
    executor = StepExecutor()
    executor.run()


if __name__ == "__main__":
    main()
