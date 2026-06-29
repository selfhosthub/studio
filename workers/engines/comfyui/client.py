# workers/engines/comfyui/client.py

"""Synchronous HTTP client for ComfyUI's REST API."""

import os
import time
import logging
import uuid
from typing import Dict, Any, List, Optional

from shared.settings import settings
from engines.comfyui.settings import settings as comfyui_settings

import httpx

logger = logging.getLogger(__name__)


class ComfyUIClient:
    """Synchronous client for ComfyUI REST API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        timeout: float = comfyui_settings.COMFYUI_CLIENT_TIMEOUT_S,
    ):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)
        self.client_id = str(uuid.uuid4())

    def close(self):
        self.client.close()

    def health_check(self) -> bool:
        try:
            response = self.client.get(
                f"{self.base_url}/system_stats",
                timeout=settings.HEALTH_CHECK_TIMEOUT_S,
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    def queue_prompt(self, workflow: Dict[str, Any]) -> str:
        """Submit workflow to ComfyUI; returns prompt_id."""
        payload = {
            "prompt": workflow,
            "client_id": self.client_id,
        }

        response = self.client.post(
            f"{self.base_url}/prompt",
            json=payload,
        )

        # 400 carries ComfyUI's structured error details - surface them.
        if response.status_code == 400:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", "")
                node_errors = error_data.get("node_errors", {})

                details = []
                if error_msg:
                    details.append(error_msg)

                for node_id, node_error in node_errors.items():
                    errors = node_error.get("errors", [])
                    for err in errors:
                        err_msg = err.get("message", str(err))
                        details.append(f"Node {node_id}: {err_msg}")

                if details:
                    raise RuntimeError(
                        f"ComfyUI rejected workflow: {'; '.join(details)}"
                    )
                else:
                    raise RuntimeError(f"ComfyUI rejected workflow: {error_data}")
            except RuntimeError:
                raise
            except (ValueError, KeyError, TypeError):
                raise RuntimeError(f"ComfyUI rejected workflow: {response.text}")

        response.raise_for_status()

        data = response.json()
        prompt_id = data.get("prompt_id")

        if not prompt_id:
            raise ValueError(f"No prompt_id in response: {data}")

        logger.debug(f"Queued prompt: {prompt_id}")
        return prompt_id

    def get_history(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get execution history for a prompt; None if not found."""
        response = self.client.get(f"{self.base_url}/history/{prompt_id}")
        response.raise_for_status()

        data = response.json()
        return data.get(prompt_id)

    def wait_for_completion(
        self,
        prompt_id: str,
        timeout: int = comfyui_settings.COMFYUI_JOB_TIMEOUT_S,
        poll_interval: float = comfyui_settings.COMFYUI_POLL_INTERVAL_S,
    ) -> Dict[str, Any]:
        """Poll until execution completes or times out; raises on failure."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            history = self.get_history(prompt_id)

            if history is not None:
                status = history.get("status", {})
                status_str = status.get("status_str", "")

                match status_str:
                    case "success":
                        logger.debug(f"Prompt {prompt_id} completed successfully")
                        return history

                    case "error":
                        messages = status.get("messages", [])
                        error_details = []
                        for msg in messages:
                            if isinstance(msg, list) and len(msg) >= 2:
                                error_details.append(str(msg[1]))
                        error_msg = (
                            "; ".join(error_details)
                            if error_details
                            else "Unknown error"
                        )
                        raise RuntimeError(f"ComfyUI execution failed: {error_msg}")

                    case _:
                        logger.debug(
                            f"Prompt {prompt_id} status: {status_str} - waiting"
                        )

            time.sleep(poll_interval)

        raise TimeoutError(f"ComfyUI execution timed out after {timeout}s")

    def get_output_images(self, prompt_id: str) -> List[Dict[str, Any]]:
        """Image info dicts from a completed execution: [{filename, subfolder, type}, ...]."""
        history = self.get_history(prompt_id)
        if not history:
            return []

        outputs = history.get("outputs", {})
        images = []

        for node_id, node_output in outputs.items():
            for image in node_output.get("images", []):
                images.append(
                    {
                        "filename": image["filename"],
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    }
                )

        return images

    def download_image(
        self,
        filename: str,
        output_dir: str,
        subfolder: str = "",
        image_type: str = "output",
    ) -> str:
        """Download a generated image; returns local path."""
        params = {
            "filename": filename,
            "type": image_type,
        }
        if subfolder:
            params["subfolder"] = subfolder

        max_download_mb = settings.MAX_DOWNLOAD_SIZE_MB
        max_bytes = max_download_mb * 1024 * 1024

        os.makedirs(output_dir, exist_ok=True)
        local_path = os.path.join(output_dir, filename)
        downloaded = 0

        with self.client.stream(
            "GET", f"{self.base_url}/view", params=params
        ) as response:
            response.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=settings.HTTP_CHUNK_SIZE):
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise RuntimeError(
                            f"ComfyUI output exceeds size limit ({max_download_mb}MB): {filename}"
                        )
                    f.write(chunk)

        logger.debug(f"Downloaded image: {local_path} ({downloaded} bytes)")
        return local_path

    def get_queue_status(self) -> Dict[str, Any]:
        response = self.client.get(f"{self.base_url}/queue")
        response.raise_for_status()
        return response.json()

    def interrupt_execution(self) -> bool:
        try:
            response = self.client.post(f"{self.base_url}/interrupt")
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to interrupt: {e}")
            return False

    def upload_image(
        self,
        image_path: str,
        subfolder: str = "",
        image_type: str = "input",
        overwrite: bool = True,
    ) -> str:
        """Upload via /upload/image - works for local and remote servers (no fs access)."""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        filename = os.path.basename(image_path)

        with open(image_path, "rb") as f:
            files = {
                "image": (filename, f, "image/png"),
            }
            data = {
                "type": image_type,
                "overwrite": "true" if overwrite else "false",
            }
            if subfolder:
                data["subfolder"] = subfolder

            response = self.client.post(
                f"{self.base_url}/upload/image",
                files=files,
                data=data,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to upload image: {response.status_code} - {response.text}"
            )

        result = response.json()
        # ComfyUI returns {"name": "filename.png", "subfolder": "", "type": "input"}.
        uploaded_name = result.get("name", filename)

        logger.debug(f"Uploaded image to ComfyUI: {uploaded_name}")
        return uploaded_name
