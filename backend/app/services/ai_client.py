"""
Async HTTP Client for communicating with the Python LangGraph AI microservice
"""

import asyncio
import html
import logging
import re
from typing import Dict, Any, List, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def sanitize_error_message(text: str, max_length: int = 200) -> str:
    """
    Strip HTML tags, decode HTML entities, normalize whitespace,
    and truncate error string to max_length (~200 characters).
    """
    if not text:
        return ""
    # Strip <script> and <style> tags and their contents
    clean = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    # Strip all other HTML tags
    clean = re.sub(r'<[^>]+>', ' ', clean)
    # Decode HTML entities
    clean = html.unescape(clean)
    # Normalize whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    # Truncate to max_length
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip()
    return clean


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
        context: str = "",
        max_attempts: int = 3
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

        backoff_delay = 1.0

        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    logger.info(f"Dispatching investigation for incident '{incident_id}' to AI service (Attempt {attempt}/{max_attempts})...")
                    response = await client.post(url, json=payload)

                    if response.status_code == 202:
                        try:
                            data = response.json()
                        except Exception:
                            logger.error(f"AI service returned non-JSON HTTP 202 response. Full body:\n{response.text}")
                            clean_err = sanitize_error_message(f"AI service returned non-JSON response: {response.text}", max_length=200)
                            raise RuntimeError(clean_err)

                        if not isinstance(data, dict):
                            logger.error(f"AI service returned non-dict JSON response. Full body:\n{response.text}")
                            clean_err = sanitize_error_message(f"AI service returned non-JSON response: {response.text}", max_length=200)
                            raise RuntimeError(clean_err)

                        ai_inv_id = data.get("investigation_id")
                        if not ai_inv_id:
                            raise ValueError("AI Service responded 202 but did not return an investigation_id")
                        logger.info(f"AI service accepted investigation task: {ai_inv_id}")
                        return ai_inv_id

                    # Handle 400 Bad Request (e.g. missing GOOGLE_API_KEY)
                    if response.status_code == 400:
                        logger.error(f"AI service returned HTTP 400. Full body:\n{response.text}")
                        try:
                            data = response.json()
                            err_msg = data.get("error", "Bad Request from AI Service") if isinstance(data, dict) else response.text
                        except Exception:
                            err_msg = response.text
                        clean_err = sanitize_error_message(f"AI Service configuration error: {err_msg}", max_length=200)
                        raise ValueError(clean_err)

                    # Handle transient server errors (500, 502, 503, 504)
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                        logger.warning(f"AI service returned HTTP {response.status_code}. Retrying in {backoff_delay}s...")
                        await asyncio.sleep(backoff_delay)
                        backoff_delay *= 2
                        continue

                    # Non-2xx response (or retries exhausted)
                    logger.error(f"AI service returned HTTP {response.status_code}. Full body:\n{response.text}")
                    clean_err = sanitize_error_message(f"AI service returned error HTTP {response.status_code}: {response.text}", max_length=200)
                    raise RuntimeError(clean_err)

            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                if attempt < max_attempts:
                    logger.warning(f"Could not connect to AI service at {self.base_url}. Retrying in {backoff_delay}s...")
                    await asyncio.sleep(backoff_delay)
                    backoff_delay *= 2
                else:
                    raise ConnectionError(f"AI Service unreachable at {self.base_url}: {e}")
            except httpx.HTTPStatusError as e:
                logger.error(f"AI service returned error HTTP {e.response.status_code}. Full body:\n{e.response.text}")
                clean_err = sanitize_error_message(f"AI service returned error HTTP {e.response.status_code}: {e.response.text}", max_length=200)
                raise RuntimeError(clean_err)

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
                        try:
                            data = response.json()
                        except Exception:
                            logger.error(f"AI service returned non-JSON HTTP 200 response during polling. Full body:\n{response.text}")
                            clean_err = sanitize_error_message(f"AI service returned non-JSON response: {response.text}", max_length=200)
                            raise RuntimeError(clean_err)

                        if not isinstance(data, dict):
                            logger.error(f"AI service returned non-dict JSON response during polling. Full body:\n{response.text}")
                            clean_err = sanitize_error_message(f"AI service returned non-JSON response: {response.text}", max_length=200)
                            raise RuntimeError(clean_err)

                        # Explicit dict key access
                        status_val = data.get("status")

                        if status_val == "completed":
                            logger.info(f"AI investigation '{ai_investigation_id}' completed successfully.")
                            return data

                        if status_val == "failed":
                            err_list = data.get("errors", ["Unknown error in LangGraph pipeline"])
                            clean_errs = [sanitize_error_message(err, max_length=200) for err in err_list]
                            clean_err = sanitize_error_message(f"AI investigation failed: {'; '.join(clean_errs)}", max_length=200)
                            raise RuntimeError(clean_err)

                        logger.debug(f"AI investigation '{ai_investigation_id}' in progress (Poll {poll}/{max_polls})...")

                    elif response.status_code == 404:
                        logger.error(f"AI service lost investigation state for '{ai_investigation_id}' (404 Not Found). Full body:\n{response.text}")
                        raise RuntimeError(
                            f"AI service lost investigation state for '{ai_investigation_id}' (404 Not Found) - AI service may have restarted."
                        )
                    else:
                        logger.error(f"AI service returned HTTP {response.status_code} during polling. Full body:\n{response.text}")
                        clean_err = sanitize_error_message(f"AI service returned error HTTP {response.status_code}: {response.text}", max_length=200)
                        raise RuntimeError(clean_err)

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning(f"Transient error polling AI service: {e}. Retrying in {poll_interval}s...")

            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"AI investigation '{ai_investigation_id}' timed out after 5 minutes.")



ai_service_client = AIServiceClient()
