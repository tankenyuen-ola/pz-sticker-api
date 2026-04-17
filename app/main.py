"""AI Emoji Sticker Generation API — FastAPI entry point."""
import uvicorn
from fastapi import FastAPI

from app.config import config
from app.logger import setup_logger
from app.api.router import api_router

logger = setup_logger(config.log_level)

app = FastAPI(
    title="AI Emoji Sticker Generation API",
    version="1.0.0",
    docs_url="/docs" if config.debug_mode else None,
)

app.include_router(api_router, prefix="/api/ai_emoji")


@app.get("/health")
async def health():
    return {"status": "ok", "env": config.app_env}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=config.app_host,
        port=config.app_port,
        reload=config.debug_mode,
    )
