"""Image download and conversion utilities for the AI Emoji API."""
from __future__ import annotations

import shutil
from pathlib import Path

import aiohttp
from PIL import Image

from app.config import config
from app.logger import setup_logger

logger = setup_logger()


async def download_image(image_url: str, save_path: str | Path, timeout: int = 30) -> str:
    """Download an image from a URL to a local file path.

    Args:
        image_url: HTTP(S) URL to download.
        save_path: Local file path to save the image.
        timeout: Download timeout in seconds.

    Returns:
        The resolved absolute path of the saved file.
    """
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    client_timeout = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=client_timeout) as session:
        async with session.get(image_url) as resp:
            if resp.status != 200:
                raise ValueError(f"Failed to download image: HTTP {resp.status}")
            content = await resp.read()

    save_path.write_bytes(content)
    logger.info("[ImageUtils] Downloaded {} -> {} ({} bytes)", image_url, save_path, len(content))
    return str(save_path.resolve())


def png_to_webp(source_path: str | Path, output_path: str | Path, quality: int = 95) -> str:
    """Convert a PNG image to WebP format.

    Args:
        source_path: Path to the source PNG image.
        output_path: Path for the output WebP file.
        quality: WebP quality (0-100, default 95).

    Returns:
        The path of the output WebP file.
    """
    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.save(output_path, format="WEBP", quality=quality)

    logger.debug("[ImageUtils] Converted {} -> {}", source_path, output_path)
    return str(output_path)


def cleanup_task_dir(task_id: str) -> None:
    """Delete the working directory for a completed task.

    Args:
        task_id: The task identifier.
    """
    task_dir = config.work_dir / "ai_emoji" / task_id
    if task_dir.exists():
        shutil.rmtree(task_dir, ignore_errors=True)
        logger.info("[ImageUtils] Cleaned up task directory: {}", task_dir)
