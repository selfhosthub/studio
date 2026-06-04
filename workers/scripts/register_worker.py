#!/usr/bin/env python3
"""
Register Worker with API

Standalone script to register a worker with the Studio API without starting
the full worker process. Useful for RunPod and cloud environments where
you want to re-register a worker without restarting the pod.

Usage:
    python scripts/register_worker.py

Environment Variables:
    SHS_WORKER_SHARED_SECRET: Shared secret for authentication (required)
    SHS_API_BASE_URL: API base URL (default: http://localhost:8000)
    SHS_WORKER_TYPE: Type of worker (default: general)
    SHS_WORKER_NAME: Custom worker name (default: auto-generated)

Exit Codes:
    0: Registration successful
    1: Registration failed (missing secret or API error)
"""
import os
import sys
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

# Configure logging for CLI script
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def register_worker() -> bool:
    """Register this worker with the API."""
    api_base_url = os.getenv("SHS_API_BASE_URL")
    if not api_base_url:
        raise RuntimeError("SHS_API_BASE_URL is required and not set")
    worker_secret = os.getenv("SHS_WORKER_SHARED_SECRET")
    if not worker_secret:
        raise RuntimeError("SHS_WORKER_SHARED_SECRET is required and not set")
    worker_type = os.getenv("SHS_WORKER_TYPE", "general")
    worker_name = os.getenv("SHS_WORKER_NAME", f"{worker_type}-{os.getpid()}")

    # Resolve legacy type alias.
    if worker_type == "orchestrator":
        worker_type = "general"

    # Get queue labels based on worker type
    from shared.worker_types import get_worker_config

    try:
        config = get_worker_config(worker_type)
        queue_labels = config.queue_labels
    except ValueError:
        queue_labels = [f"{worker_type}_jobs"]

    capabilities = {"type": worker_type}

    logger.info("Worker Registration")
    logger.info(f"API URL: {api_base_url}")
    logger.info(f"Worker Type: {worker_type}")
    logger.info(f"Worker Name: {worker_name}")
    logger.info(f"Queue Labels: {queue_labels}")

    try:
        timeout = float(os.getenv("SHS_HTTP_INTERNAL_TIMEOUT_S", "30"))
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{api_base_url}/api/v1/workers/register",
                json={
                    "secret": worker_secret,
                    "name": worker_name,
                    "capabilities": capabilities,
                    "queue_labels": queue_labels,
                },
            )

            if response.status_code == 201:
                data = response.json()
                worker_id = data.get("worker_id")
                logger.info(f"Registration successful! worker_id={worker_id}")
                logger.info(
                    "Worker is now visible in Infrastructure > Worker Heartbeats"
                )
                return True
            else:
                logger.error(
                    f"Registration failed: status={response.status_code}, response={response.text}"
                )
                return False

    except httpx.ConnectError:
        logger.error(f"Could not connect to API at {api_base_url}")
        logger.error("Make sure the API server is running")
        return False
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return False


def main():
    success = register_worker()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
