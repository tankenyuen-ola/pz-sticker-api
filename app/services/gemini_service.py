"""
Gemini image generation service — adapted from cai-ai-demo for the API service.

Provides generate_structured_output (for review) and generate_image (for sticker generation).
"""
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Tuple, Optional
from pathlib import Path

import aiohttp
from PIL import Image as PILImage

from app.config import config
from app.infra.asset_logging import log_generated_asset
from app.infra.generated_assets import build_local_image_destination
from app.infra.oss_utils import OSSUtils
from app.logger import setup_logger
from app.utils.gemini_generation_config import build_image_generation_config_kwargs

logger = setup_logger(config.log_level)


class GeminiImageService:
    """Gemini image generation service for the AI Emoji API."""

    VALID_ASPECT_RATIOS = [
        "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9",
    ]
    VALID_RESOLUTIONS = ["512", "1K", "2K", "4K"]

    def __init__(self):
        self.api_key = config.gemini_api_key
        self._client = None
        self._oss_utils = OSSUtils()
        if self.api_key:
            self._initialize_client()

    def _initialize_client(self):
        """Initialize the Gemini client."""
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            logger.info("[Gemini] Client initialized successfully")
        except ImportError as e:
            raise ValueError("Missing google-genai dependency") from e

    def _resolve_image_paths(self, image_files: Optional[List[str]]) -> List[str]:
        """Resolve image file paths from input."""
        if not image_files:
            return []
        paths: List[str] = []
        for file_obj in image_files:
            if isinstance(file_obj, str):
                paths.append(file_obj)
            elif hasattr(file_obj, "name"):
                paths.append(file_obj.name)
            elif hasattr(file_obj, "path"):
                paths.append(file_obj.path)
        return paths[:3]

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        """Extract text content from a Gemini response."""
        if hasattr(response, "text") and response.text:
            return response.text
        if hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None)
                if not parts:
                    continue
                for part in parts:
                    text = getattr(part, "text", None)
                    if text:
                        return text
        return ""

    @staticmethod
    def _normalise_structured_payload(payload: Any) -> Dict[str, Any]:
        """Normalize structured output payload to dict."""
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "model_dump"):
            return payload.model_dump()
        if hasattr(payload, "dict"):
            return payload.dict()
        raise ValueError(f"Cannot parse structured response: {type(payload)}")

    async def _generate_content(
        self,
        prompt: str,
        model: str,
        image_files: Optional[List[str]] = None,
        response_schema: Optional[Dict[str, Any]] = None,
        response_mime_type: Optional[str] = None,
    ) -> Any:
        """Core method to generate content from Gemini."""
        if not prompt.strip():
            raise ValueError("Prompt is required")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured")
        if not self._client:
            raise ValueError("Gemini client initialization failed")

        try:
            from google.genai.types import GenerateContentConfig, SafetySetting, HarmCategory, HarmBlockThreshold
        except ImportError as e:
            raise ValueError(f"Missing dependency: {e}") from e

        config_kwargs: Dict[str, Any] = {
            "safety_settings": [
                SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.OFF),
                SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.OFF),
                SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.OFF),
                SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.OFF),
                SafetySetting(category=HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY, threshold=HarmBlockThreshold.OFF),
            ]
        }
        if response_schema is not None:
            config_kwargs["response_mime_type"] = response_mime_type or "application/json"
            config_kwargs["response_schema"] = response_schema

        generation_config = GenerateContentConfig(**config_kwargs)
        parts: List[Any] = [prompt]
        paths = self._resolve_image_paths(image_files)
        if paths:
            for path in paths:
                parts.append(PILImage.open(path))

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._client.models.generate_content(
                model=model,
                contents=parts,
                config=generation_config,
            ),
        )

    async def generate_structured_output(
        self,
        prompt: str,
        image_files: Optional[List[str]] = None,
        model: str = "gemini-2.5-flash",
        response_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate structured JSON output — used for photo review."""
        response = await self._generate_content(
            prompt=prompt,
            model=model,
            image_files=image_files,
            response_schema=response_schema,
            response_mime_type="application/json",
        )

        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return self._normalise_structured_payload(parsed)

        text = self._extract_response_text(response).strip()
        if not text:
            raise ValueError("Gemini returned empty structured content")
        return self._normalise_structured_payload(json.loads(text))

    async def generate_image(
        self,
        prompt: str,
        image_files: Optional[List[str]] = None,
        model: str = "gemini-3-pro-image-preview",
        aspect_ratio: Optional[str] = None,
        resolution: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        seed: Optional[int] = None,
        num_images: int = 1,
        use_sequential_interleaving: bool = False,
    ) -> Tuple[List[Tuple[str, str]], str]:
        """Generate images with Gemini.

        Returns:
            (list of (url_or_path, caption), status_message)
        """
        start_time = time.perf_counter()
        logger.info(
            "[Gemini] Starting generation model=%s prompt_len=%d files=%d",
            model, len(prompt.strip()) if prompt else 0,
            len(image_files) if image_files else 0,
        )

        try:
            if not prompt.strip():
                return [], "Prompt is required"
            if not self.api_key:
                return [], "GEMINI_API_KEY not configured"
            if not self._client:
                return [], "Gemini client initialization failed"

            from google.genai.types import GenerateContentConfig, SafetySetting, HarmCategory, HarmBlockThreshold, ImageConfig

            config_kwargs = build_image_generation_config_kwargs(
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                temperature=temperature,
                top_p=top_p,
                seed=seed,
                valid_aspect_ratios=self.VALID_ASPECT_RATIOS,
                valid_resolutions=self.VALID_RESOLUTIONS,
            )
            image_config_raw = config_kwargs.pop("image_config", None)
            image_config = ImageConfig(**image_config_raw) if image_config_raw else None

            generation_config = GenerateContentConfig(
                safety_settings=[
                    SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.OFF),
                    SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.OFF),
                    SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.OFF),
                    SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.OFF),
                    SafetySetting(category=HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY, threshold=HarmBlockThreshold.OFF),
                ],
                **({"image_config": image_config} if image_config else {}),
                **config_kwargs,
            )

            pil_images = []
            if image_files:
                paths = self._resolve_image_paths(image_files)
                pil_images = [PILImage.open(path) for path in paths]

            # Build contents with sequential interleaving for emoji generation
            if use_sequential_interleaving and len(pil_images) == 2:
                contents = [
                    "[Image 1: Character Reference]",
                    pil_images[0],
                    "[Image 2: Style Reference]",
                    pil_images[1],
                    f"\n{prompt}",
                ]
            elif use_sequential_interleaving and len(pil_images) == 1:
                contents = [
                    "[REFERENCE IMAGE - CHARACTER IDENTITY]: Use this image to preserve the character's identity.",
                    pil_images[0],
                    f"\n{prompt}",
                ]
            else:
                contents = [prompt, *pil_images] if pil_images else [prompt]

            async def _request_once() -> Any:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    lambda: self._client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=generation_config,
                    ),
                )

            responses = []
            requested_images = max(1, int(num_images or 1))
            for _ in range(requested_images):
                responses.append(await _request_once())

            images: List[str] = []
            out_dir = Path("generated")
            out_dir.mkdir(exist_ok=True)

            for response in responses:
                if not hasattr(response, "candidates") or not response.candidates:
                    logger.warning("[Gemini] No candidates in response")
                    return [], "Generation failed: API returned no results"

                candidate = response.candidates[0]
                if hasattr(candidate, "finish_reason") and candidate.finish_reason:
                    finish_reason = str(candidate.finish_reason)
                    logger.warning("[Gemini] Finish reason: {}", finish_reason)
                    if finish_reason in ("IMAGE_SAFETY", "SAFETY"):
                        return [], f"Generation blocked by safety filter: {finish_reason}"

                for candidate in response.candidates:
                    if not (hasattr(candidate, "content") and hasattr(candidate.content, "parts")):
                        continue
                    for part in candidate.content.parts:
                        # Check for file_data with URI
                        if hasattr(part, "file_data") and part.file_data:
                            if hasattr(part.file_data, "file_uri") and part.file_data.file_uri:
                                images.append(part.file_data.file_uri)
                                log_generated_asset(logger, "image", part.file_data.file_uri, provider="gemini", model=model, stage="generated")
                                continue

                        # Check for inline_data (binary blob)
                        if hasattr(part, "inline_data") and part.inline_data:
                            blob = part.inline_data
                            if hasattr(blob, "data") and blob.data:
                                suffix = "edit" if image_files else "image"
                                timestamp = int(time.time() * 1000)
                                filename = f"gemini_{suffix}_{timestamp}_{len(images)+1}.png"

                                try:
                                    if self._oss_utils.is_configured():
                                        uploaded_url = await self._oss_utils.upload_file(
                                            file_content=blob.data,
                                            filename=filename,
                                            path_prefix="gemini/generated",
                                        )
                                        images.append(uploaded_url)
                                        log_generated_asset(logger, "image", uploaded_url, provider="gemini", model=model, stage="uploaded")
                                    else:
                                        filepath = out_dir / filename
                                        filepath.write_bytes(blob.data)
                                        images.append(str(filepath))
                                        log_generated_asset(logger, "image", str(filepath), provider="gemini", model=model, stage="saved_local")
                                except Exception as upload_error:
                                    filepath = out_dir / filename
                                    filepath.write_bytes(blob.data)
                                    images.append(str(filepath))
                                    logger.warning("[Gemini] OSS upload failed ({}), saved locally", upload_error)

            if not images:
                return [], "No images generated"

            duration = time.perf_counter() - start_time
            logger.info("[Gemini] Generated {} images in {:.2f}s", len(images), duration)

            result_items = []
            for i, img_path in enumerate(images):
                result_items.append((img_path, f"Gemini_{i+1}"))

            return result_items, f"Generated {len(images)} images"

        except Exception as e:
            logger.exception("[Gemini] Generation failed: {}", e)
            return [], f"Generation failed: {e}"

    async def download_image_to_local(self, source: str, prefix: str = "gemini_reference", work_dir: str | None = None) -> str:
        """Download a Gemini-generated image to a local file for downstream processing.

        Args:
            source: URL or local path of the image.
            prefix: Filename prefix for the downloaded file.
            work_dir: Optional working directory to save the file into.
                       If provided, files are saved under {work_dir}/ instead of generated/.
        """
        if not source:
            raise ValueError("Image source is empty")

        if not source.startswith(("http://", "https://")):
            return str(Path(source).resolve())

        destination = self._build_local_destination(source, prefix, base_dir=Path(work_dir) if work_dir else None)
        destination.parent.mkdir(parents=True, exist_ok=True)

        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(source) as response:
                response.raise_for_status()
                destination.write_bytes(await response.read())
        return str(destination.resolve())

    @staticmethod
    def _build_local_destination(source: str, prefix: str, base_dir: Path | None = None) -> Path:
        return build_local_image_destination(source, prefix, base_dir=base_dir)

    def is_available(self) -> bool:
        """Check if the service is available."""
        return bool(self.api_key and self._client)
