"""API router for AI Emoji Sticker Generation API."""
from fastapi import APIRouter

from app.api.models import GenerateRequest, GenerateResponse
from app.logger import setup_logger
from app.services.emoji_pipeline import is_task_running, start_emoji_task


logger = setup_logger()

api_router = APIRouter()


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
