"""API router for AI Emoji Sticker Generation API."""
from typing import Optional

from fastapi import APIRouter

from app.api.models import CallbackPayload, GenerateRequest, GenerateResponse
from app.config import config
from app.logger import setup_logger
from app.services.emoji_pipeline import is_task_running, start_emoji_task


logger = setup_logger()

api_router = APIRouter()

# ---------------------------------------------------------------------------
# Debug: in-memory callback result store (only active when DEBUG_MODE=true)
# ---------------------------------------------------------------------------
_callback_results: dict[str, CallbackPayload] = {}


@api_router.post("/generate", response_model=GenerateResponse)
async def generate_emoji_stickers(
    request: GenerateRequest,
):
    """Submit an async emoji sticker generation request.

    Returns immediately with {code: 0, msg: "ok"}.
    Results are delivered via POST to the callbackUrl.
    """
    # Task ID deduplication
    if is_task_running(request.taskId):
        return GenerateResponse(code=409, msg=f"taskId '{request.taskId}' is already being processed")

    # Validate imageUrl is a valid URL
    if not request.imageUrl.startswith(("http://", "https://")):
        return GenerateResponse(code=400, msg="imageUrl must start with http:// or https://")

    # Start the background pipeline
    logger.info("[API] Starting task {} for imageUrl={}", request.taskId, request.imageUrl)
    start_emoji_task(request.taskId, request.imageUrl, request.callbackUrl)

    return GenerateResponse(code=0, msg="ok")


# ---------------------------------------------------------------------------
# Debug endpoints — only mounted when DEBUG_MODE=true
# ---------------------------------------------------------------------------
if config.debug_mode:

    @api_router.post("/test/callback")
    async def test_callback(payload: CallbackPayload):
        """Receive and store callback results in memory (debug only)."""
        _callback_results[payload.taskId] = payload
        logger.info("[Debug] Stored callback result for taskId={}", payload.taskId)
        return {"success": True, "msg": "ok"}

    @api_router.get("/test/result/{task_id}")
    async def get_test_result(task_id: str) -> Optional[CallbackPayload]:
        """Poll for callback result by taskId (debug only)."""
        result = _callback_results.get(task_id)
        if result is None:
            return {"taskId": task_id, "status": "pending", "msg": "result not ready yet"}
        return result
