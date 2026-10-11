"""
Async HTTP Client for communicating with the Python LangGraph AI microservice
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIServiceClient:
    """Handles communication and status polling with ai-service"""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.AI_SERVICE_URL).rstrip("/")
        self.timeout = httpx.Timeout(45.0, connect=5.0)

    async def trigger_investigation(
        self,
        incident_id: str,
        logs: List[str],
        alerts: Optional[List[str]] = None,
        context: str = ""
    ) -> str:
        """
        Trigger 6-step LangGraph multi-agent investigation in ai-service
        Returns ai_investigation_id
        """
        url = f"{self.base_url}/api/investigate"
        payload = {
            "incident_id": incident_id,
            "logs": logs,
            "alerts": alerts or [],
            "context": context
        }

        max_attempts = 3
        backoff_delay = 1.0

        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    logger.info(f"Dispatching investigation for incident '{incident_id}' to AI service (Attempt {attempt}/{max_attempts})...")
                    response = await client.post(url, json=payload)

                    if response.status_code == 202:
                        data = response.json()
                        ai_inv_id = data.get("investigation_id")
                        if not ai_inv_id:
                            raise ValueError("AI Service responded 202 but did not return an investigation_id")
                        logger.info(f"AI service accepted investigation task: {ai_inv_id}")
                        return ai_inv_id

                    # Handle 400 Bad Request (e.g. missing GOOGLE_API_KEY)
                    if response.status_code == 400:
                        err_msg = response.json().get("error", "Bad Request from AI Service")
                        raise ValueError(f"AI Service configuration error: {err_msg}")

                    # Handle transient server errors (500, 503, 429)
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                        logger.warning(f"AI service returned HTTP {response.status_code}. Retrying in {backoff_delay}s...")
                        await asyncio.sleep(backoff_delay)
                        backoff_delay *= 2
                        continue

                    response.raise_for_status()

            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                if attempt < max_attempts:
                    logger.warning(f"Could not connect to AI service at {self.base_url}. Retrying in {backoff_delay}s...")
                    await asyncio.sleep(backoff_delay)
                    backoff_delay *= 2
                else:
                    raise ConnectionError(f"AI Service unreachable at {self.base_url}: {e}")
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"AI service returned error HTTP {e.response.status_code}: {e.response.text}")

        raise RuntimeError("Failed to trigger investigation after maximum retries.")

    async def poll_investigation_result(
        self,
        ai_investigation_id: str,
        max_polls: int = 150,
        poll_interval: float = 2.0
    ) -> Dict[str, Any]:
        """
        Poll ai-service until investigation workflow is completed.
        Overall timeout capped at max_polls * poll_interval (default 5 minutes).
        """
        url = f"{self.base_url}/api/investigate/{ai_investigation_id}"

        for poll in range(1, max_polls + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url)

                    if response.status_code == 200:
                        data = response.json()
                        if not isinstance(data, dict):
                            raise RuntimeError(f"Expected JSON dictionary from AI service, got {type(data)}")

                        # Explicit dict key access
                        status_val = data.get("status")

                        if status_val == "completed":
                            logger.info(f"AI investigation '{ai_investigation_id}' completed successfully.")
                            return data

                        if status_val == "failed":
                            err_list = data.get("errors", ["Unknown error in LangGraph pipeline"])
                            raise RuntimeError(f"AI investigation failed: {'; '.join(err_list)}")

                        logger.debug(f"AI investigation '{ai_investigation_id}' in progress (Poll {poll}/{max_polls})...")

                    elif response.status_code == 404:
                        raise RuntimeError(
                            f"AI service lost investigation state for '{ai_investigation_id}' (404 Not Found) - AI service may have restarted."
                        )
                    else:
                        logger.warning(f"Unexpected status HTTP {response.status_code} while polling AI service")

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning(f"Transient error polling AI service: {e}. Retrying in {poll_interval}s...")

            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"AI investigation '{ai_investigation_id}' timed out after 5 minutes.")


ai_service_client = AIServiceClient()
