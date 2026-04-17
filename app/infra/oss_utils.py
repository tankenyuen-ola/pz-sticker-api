"""
阿里云 OSS 工具类
"""
import os
import asyncio
from typing import Optional

import oss2
from app.config import config
from app.logger import setup_logger

logger = setup_logger(config.log_level)


class OSSUtils:
    """阿里云 OSS 工具类"""

    def __init__(self):
        self.oss_bucket: Optional[oss2.Bucket] = None
        self._init_bucket()

    def _init_bucket(self):
        """初始化 OSS Bucket"""
        if not (config.oss_access_key_id and
                config.oss_access_key_secret and
                config.oss_endpoint and
                config.oss_bucket_name):
            logger.warning("OSS 配置不完整，跳过初始化")
            return

        try:
            auth = oss2.Auth(config.oss_access_key_id, config.oss_access_key_secret)
            print("Initializing OSS Bucket...", config.oss_access_key_id)

            # 处理代理配置：通过环境变量方式，让 requests 自动使用代理
            if config.app_env in ("local", "development"):
                http_proxy = os.getenv("http_proxy")
                https_proxy = os.getenv("https_proxy") or http_proxy

                if http_proxy or https_proxy:
                    if http_proxy:
                        os.environ["HTTP_PROXY"] = http_proxy
                    if https_proxy:
                        os.environ["HTTPS_PROXY"] = https_proxy
                    logger.info(
                        f"OSS 使用环境变量代理: HTTP={http_proxy}, HTTPS={https_proxy}"
                    )
                else:
                    logger.warning(
                        "app.env=local 但未设置 http_proxy/https_proxy 环境变量, 跳过代理配置"
                    )

            # 初始化 Bucket，这里不再传 session，使用默认 session（会读取 HTTP(S)_PROXY）
            self.oss_bucket = oss2.Bucket(
                auth,
                config.oss_endpoint,
                config.oss_bucket_name,
            )
            logger.info("OSS Bucket 初始化成功")
        except Exception as e:
            # 使用 exception 可以打印堆栈
            logger.exception(f"OSS Bucket 初始化失败: {e}")

    async def upload_file(self, file_content: bytes, filename: str, path_prefix: str = "") -> str:
        """
        上传文件到阿里云 OSS 并返回签名 URL（1小时过期）

        Args:
            file_content: 文件内容
            filename: 文件名
            path_prefix: 路径前缀，例如 "ai_emoji/task_001"

        Returns:
            签名 URL（默认1小时有效期）
        """
        if not self.oss_bucket:
            raise ValueError("OSS 未配置或初始化失败")

        try:
            # 构建 OSS 路径
            object_name = f"{path_prefix.rstrip('/')}/{filename}" if path_prefix else filename
            object_name = object_name.lstrip('/')  # 确保不以 / 开头

            # 使用 run_in_executor 在异步环境中运行同步的 OSS put_object
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, self.oss_bucket.put_object, object_name, file_content
            )

            # 生成签名 URL（默认1小时过期）
            expires = config.oss_signed_url_expires
            signed_url = self.oss_bucket.sign_url('GET', object_name, expires)

            logger.info(f"OSS 上传成功: {object_name}, 签名URL有效期={expires}s")
            return signed_url

        except Exception as e:
            logger.error(f"OSS 上传失败: {str(e)}")
            raise

    def is_configured(self) -> bool:
        """检查 OSS 是否已配置"""
        return self.oss_bucket is not None
