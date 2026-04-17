"""
Application configuration for AI Emoji API service.
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class Config:
    """All configuration from environment variables."""

    @property
    def app_env(self) -> str:
        return os.getenv("APP_ENV", "development")

    @property
    def app_port(self) -> int:
        return int(os.getenv("APP_PORT", "8188"))

    @property
    def app_host(self) -> str:
        return os.getenv("APP_HOST", "0.0.0.0")

    @property
    def debug_mode(self) -> bool:
        return os.getenv("DEBUG_MODE", "false").lower() == "true"

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO")

    @property
    def work_dir(self) -> Path:
        return Path(os.getenv("WORK_DIR", "./work_dir"))

    # Gemini
    @property
    def gemini_api_key(self) -> Optional[str]:
        return os.getenv("GEMINI_API_KEY")

    # Alibaba Cloud OSS
    @property
    def oss_access_key_id(self) -> str:
        return os.getenv("OSS_ACCESS_KEY_ID", "")

    @property
    def oss_access_key_secret(self) -> str:
        return os.getenv("OSS_ACCESS_KEY_SECRET", "")

    @property
    def oss_endpoint(self) -> str:
        return os.getenv("OSS_ENDPOINT", "oss-ap-southeast-1.aliyuncs.com")

    @property
    def oss_bucket_name(self) -> str:
        return os.getenv("OSS_BUCKET_NAME", "recommend-sg")

    @property
    def oss_signed_url_expires(self) -> int:
        """Signed URL expiration in seconds (default: 3600 = 1 hour)."""
        return int(os.getenv("OSS_SIGNED_URL_EXPIRES", "3600"))

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a given provider."""
        key_map = {
            "gemini": "GEMINI_API_KEY",
        }
        env_key = key_map.get(provider.lower())
        return os.getenv(env_key) if env_key else None


config = Config()
