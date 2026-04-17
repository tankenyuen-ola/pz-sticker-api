"""Helpers for immediate generated-asset URL logging."""

from __future__ import annotations

from typing import Any


def log_generated_asset(logger: Any, asset_type: str, url: str, **context: Any) -> None:
    """Log a generated asset URL/path in a consistent single-line format."""
    if not url:
        return

    context_parts = [f"{key}={value}" for key, value in context.items() if value is not None and value != ""]
    suffix = f" {' '.join(context_parts)}" if context_parts else ""
    logger.info(f"[Asset] type={asset_type} url={url}{suffix}")
