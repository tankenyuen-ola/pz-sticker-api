"""Pydantic models for the AI Emoji Sticker Generation API."""
from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional


# --- Request ---

class GenerateRequest(BaseModel):
    """Request body for POST /api/ai_emoji/v1/generate."""
    imageUrl: str = Field(..., description="User photo URL (HTTPS preferred)")
    taskId: str = Field(
        ...,
        description="Caller-provided unique task identifier (alphanumeric + underscore, max 64 chars)",
        pattern=r"^[a-zA-Z0-9_]{1,64}$",
    )
    callbackUrl: str = Field(..., description="HTTPS URL to receive results via POST callback")


class GenerateResponse(BaseModel):
    """Immediate response after submitting a generation request."""
    code: int = Field(..., description="0 = accepted, non-zero = error")
    msg: str = Field(..., description="Status message")


# --- Callback ---

class EmojiItem(BaseModel):
    """One sticker in the callback result."""
    theme: str = Field(..., description="English theme name, e.g. 'hello', 'thank_you_boss'")
    url: str = Field(..., description="CDN URL of the WebP sticker image")


class CallbackData(BaseModel):
    """Data payload for the callback."""
    emojiList: List[EmojiItem] = Field(default_factory=list, description="List of generated sticker items")


class CallbackPayload(BaseModel):
    """Payload sent to the callbackUrl via POST."""
    taskId: str = Field(..., description="The task ID from the original request")
    errorCode: int = Field(..., description="0 = success, 1001-1008 = review failure, 9999 = internal error")
    msg: str = Field(..., description="English status message")
    data: CallbackData = Field(default_factory=CallbackData, description="Result data (empty on failure)")
