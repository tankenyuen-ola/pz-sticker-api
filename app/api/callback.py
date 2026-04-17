"""Callback client with exponential backoff retry."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from app.api.models import CallbackPayload
from app.logger import setup_logger

logger = setup_logger()

# Retry delays: 2s, 4s, 8s (3 retries after the initial attempt)
_RETRY_DELAYS = [2, 4, 8]
_PER_ATTEMPT_TIMEOUT = 10  # seconds


async def send_callback(callback_url: str, payload: CallbackPayload) -> bool:
    """Send callback payload to the callbackUrl with exponential backoff retry.

    Total attempts: 1 immediate + 3 retries = 4 attempts.
    Delays between retries: 2s, 4s, 8s.

    Returns:
        True if at least one attempt got a 2xx response, False otherwise.
    """
    payload_dict = payload.model_dump()
    last_error: str = ""

    # Initial attempt (no delay)
    success, last_error = await _attempt_callback(callback_url, payload_dict, attempt=0)
    if success:
        return True

    # Retry up to 3 times with exponential backoff
    for retry_index, delay in enumerate(_RETRY_DELAYS, start=1):
        logger.info(
            "[Callback] Retry {}/3 for taskId={} after {:.0f}s delay",
            retry_index, payload.taskId, delay,
        )
        await asyncio.sleep(delay)
        success, last_error = await _attempt_callback(callback_url, payload_dict, attempt=retry_index)
        if success:
            return True

    logger.error(
        "[Callback] All 4 attempts failed for taskId={} to {}. Last error: {}",
        payload.taskId, callback_url, last_error,
    )
    return False


async def _attempt_callback(
    callback_url: str,
    payload_dict: dict[str, Any],
    attempt: int,
) -> tuple[bool, str]:
    """Make a single callback attempt.

    Returns:
        (success, error_message)
    """
    timeout = aiohttp.ClientTimeout(total=_PER_ATTEMPT_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                callback_url,
                json=payload_dict,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if 200 <= resp.status < 300:
                    logger.info(
                        "[Callback] Attempt {} succeeded for taskId={} (HTTP {})",
                        attempt, payload_dict.get("taskId", "?"), resp.status,
                    )
                    return True, ""
                else:
                    body = await resp.text()
                    error_msg = f"HTTP {resp.status}: {body[:200]}"
                    logger.warning(
                        "[Callback] Attempt {} failed for taskId={}: {}",
                        attempt, payload_dict.get("taskId", "?"), error_msg,
                    )
                    return False, error_msg
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "[Callback] Attempt {} exception for taskId={}: {}",
            attempt, payload_dict.get("taskId", "?"), error_msg,
        )
        return False, error_msg
