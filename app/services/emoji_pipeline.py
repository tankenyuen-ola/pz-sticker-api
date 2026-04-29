"""
Emoji sticker generation pipeline — the core orchestration.

Steps:
1. Download imageUrl -> local file
2. Gemini Review (structured output)
3. Gemini Webtoon Reference generation
4. Gemini 3x 4-sticker sheet generation (with fixed seed)
5. Chroma-key cutout (ffmpeg balanced preset)
6. Smart crop (512x512 individual stickers)
7. PNG -> WebP conversion
8. Upload WebP to OSS -> get CDN URL
9. Send callback with emojiList
"""
from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

from app.api.callback import send_callback
from app.api.models import CallbackData, CallbackPayload, EmojiItem
from app.config import config
from app.infra.oss_utils import OSSUtils
from app.logger import setup_logger
from app.prompts.emoji_meme_prompts import (
    DEFAULT_SHEET_PROMPTS,
    EMOJI_MODE_SHEET,
    LABEL_ACTION_DESCRIPTIONS,
    LABEL_VERIFY_PROMPT,
    REVIEW_PROMPT,
    REVIEW_RESPONSE_SCHEMA,
    WEBTOON_REFERENCE_PROMPT,
    _DEFAULT_SHEETS,
    _SHEET_STYLE_NO_REF,
    get_default_sheet_prompts,
)
from app.services.gemini_service import GeminiImageService
from app.services.image_utils import cleanup_task_dir, download_image, png_to_webp
from app.utils.background_removal import get_ffmpeg_preset_values, remove_background
from app.utils.smart_crop import smart_crop_sticker_sheet

logger = setup_logger()

# ---------------------------------------------------------------------------
# Theme mapping: Chinese label -> English API key
# ---------------------------------------------------------------------------
EMOJI_THEME_MAP: dict[str, str] = {
    "你好": "hello",
    "鼓掌": "clap",
    "喜欢": "like",
    "害羞": "shy",
    "呜呜呜": "crying",
    "生气": "angry",
    "色咪咪": "flirty",
    "要抱抱": "hug",
    "谢谢老板": "thank_you_boss",
    "加油": "cheer_up",
    "飞吻": "flying_kiss",
    "晚安": "good_night",
}

# Emotion labels per sheet (matches _DEFAULT_SHEETS order)
SHEET_EMOTION_LABELS: list[list[str]] = [
    list(_DEFAULT_SHEETS[0][1]),  # ["你好", "鼓掌", "喜欢", "害羞"]
    list(_DEFAULT_SHEETS[1][1]),  # ["呜呜呜", "生气", "色咪咪", "要抱抱"]
    list(_DEFAULT_SHEETS[2][1]),  # ["谢谢老板", "加油", "飞吻", "晚安"]
]

# Error code -> English msg mapping for callbacks
_ERROR_MESSAGES: dict[int, str] = {
    0: "ok",
    1001: "unsafe content detected",
    1002: "public figure identified",
    1003: "no human face detected",
    1004: "multiple faces detected",
    1005: "abnormal lighting detected",
    1006: "face not centered or cropped",
    1007: "face heavily occluded",
    1008: "face angle or expression abnormal",
    9999: "internal error",
}

# Fixed generation parameters for the API
_GENERATION_MODEL = "gemini-3-pro-image-preview"
_REVIEW_MODEL = "gemini-2.5-flash"
_LABEL_VERIFY_MODEL = "gemini-3-flash-preview"
_SHEET_ASPECT_RATIO = "1:1"
_WEBTOON_ASPECT_RATIO = "2:3"
_RESOLUTION = "1K"
_TEMPERATURE = 0.6
_TOP_P = 0.95

# Label verification schema builder


def _build_label_verify_schema(candidate_labels: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "top_left": {"type": "string", "enum": candidate_labels},
            "top_right": {"type": "string", "enum": candidate_labels},
            "bottom_left": {"type": "string", "enum": candidate_labels},
            "bottom_right": {"type": "string", "enum": candidate_labels},
        },
        "required": ["top_left", "top_right", "bottom_left", "bottom_right"],
    }


async def verify_sheet_labels(
    gemini_service: GeminiImageService,
    sheet_image_path: str,
    candidate_labels: list[str],
    task_id: str,
    sheet_label: str,
) -> list[str] | None:
    """Use Flash to verify emotion labels for a 2x2 sticker sheet.

    Returns:
        Reordered labels in [top_left, top_right, bottom_left, bottom_right] order,
        or None if verification fails (caller should fallback to positional labels).
    """
    try:
        label_descriptions = "\n".join(
            f"- {label}: {LABEL_ACTION_DESCRIPTIONS.get(label, 'unknown')}"
            for label in candidate_labels
        )
        prompt = LABEL_VERIFY_PROMPT.format(label_descriptions=label_descriptions, count=len(candidate_labels))
        schema = _build_label_verify_schema(candidate_labels)

        result = await gemini_service.generate_structured_output(
            prompt=prompt,
            image_files=[sheet_image_path],
            model=_LABEL_VERIFY_MODEL,
            response_schema=schema,
        )

        logger.info(
            "[Pipeline] Task {}: {} label verification raw result: {}",
            task_id, sheet_label, result,
        )

        verified = [result.get(k, "") for k in ("top_left", "top_right", "bottom_left", "bottom_right")]

        # Validate: must be a permutation of candidate_labels
        if sorted(verified) == sorted(candidate_labels) and all(verified):
            logger.info(
                "[Pipeline] Task {}: {} label verification: positional={} → verified={}",
                task_id, sheet_label, candidate_labels, verified,
            )
            return verified

        logger.warning(
            "[Pipeline] Task {}: {} label verification returned invalid permutation: {} (expected one of {}), falling back to positional",
            task_id, sheet_label, verified, candidate_labels,
        )
        return None
    except Exception as exc:
        logger.warning(
            "[Pipeline] Task {}: {} label verification failed: {} (type={}), falling back to positional",
            task_id, sheet_label, exc, type(exc).__name__,
        )
        return None

# ---------------------------------------------------------------------------
# Task tracking
# ---------------------------------------------------------------------------
_emoji_api_tasks: dict[str, asyncio.Task] = {}


def is_task_running(task_id: str) -> bool:
    """Check if a task is currently running."""
    return task_id in _emoji_api_tasks and not _emoji_api_tasks[task_id].done()


def start_emoji_task(task_id: str, image_url: str, callback_url: str) -> None:
    """Start a background emoji generation task."""
    task = asyncio.create_task(
        _run_emoji_pipeline(task_id, image_url, callback_url)
    )
    _emoji_api_tasks[task_id] = task


async def _run_emoji_pipeline(task_id: str, image_url: str, callback_url: str) -> None:
    """Run the full emoji generation pipeline with 3-minute hard timeout."""
    try:
        await asyncio.wait_for(
            _execute_pipeline(task_id, image_url, callback_url),
            timeout=180,  # 3 minutes
        )
    except asyncio.TimeoutError:
        logger.error("[Pipeline] Task {} timed out after 180s", task_id)
        await send_callback(callback_url, CallbackPayload(
            taskId=task_id,
            errorCode=9999,
            msg="generation timeout",
            data=CallbackData(),
        ))
    except Exception as exc:
        logger.exception("[Pipeline] Task {} failed: {}", task_id, exc)
        await send_callback(callback_url, CallbackPayload(
            taskId=task_id,
            errorCode=9999,
            msg=f"internal error: {exc}",
            data=CallbackData(),
        ))
    finally:
        _emoji_api_tasks.pop(task_id, None)
        # Cleanup working directory
        try:
            cleanup_task_dir(task_id)
        except Exception:
            pass


async def _execute_pipeline(task_id: str, image_url: str, callback_url: str) -> None:
    """Execute the full pipeline (no timeout wrapper — caller handles that)."""
    gemini_service = GeminiImageService()
    oss_utils = OSSUtils()

    # Set up working directory for this task
    task_dir = config.work_dir / "ai_emoji" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    logger.info("[Pipeline] Starting task {} with imageUrl={}", task_id, image_url)

    # ── Step 1: Download user photo ──────────────────────────────────────
    input_photo_path = task_dir / "input_photo.jpg"
    await download_image(image_url, str(input_photo_path))

    # ── Step 2: Gemini Review ─────────────────────────────────────────────
    logger.info("[Pipeline] Task {}: Running photo review...", task_id)
    review_result = await gemini_service.generate_structured_output(
        prompt=REVIEW_PROMPT,
        image_files=[str(input_photo_path)],
        model=_REVIEW_MODEL,
        response_schema=REVIEW_RESPONSE_SCHEMA,
    )

    if not review_result.get("result"):
        # Review failed — extract error code and send callback
        try:
            status_code = int(review_result.get("status_code", "9999"))
        except (ValueError, TypeError):
            status_code = 9999
        reason_code = str(review_result.get("reason") or "AiErrorCodeInternalError")
        error_msg = _ERROR_MESSAGES.get(status_code, "review failed")
        logger.info("[Pipeline] Task {}: Review failed [{}·{}]: {}", task_id, status_code, reason_code, error_msg)
        await send_callback(callback_url, CallbackPayload(
            taskId=task_id,
            errorCode=status_code,
            msg=error_msg,
            data=CallbackData(),
        ), no_retry=True)
        return

    logger.info("[Pipeline] Task {}: Review passed", task_id)

    # ── Step 3: Generate Webtoon Reference ────────────────────────────────
    logger.info("[Pipeline] Task {}: Generating webtoon reference...", task_id)
    reference_items, reference_status = await gemini_service.generate_image(
        WEBTOON_REFERENCE_PROMPT,
        image_files=[str(input_photo_path)],
        model=_GENERATION_MODEL,
        aspect_ratio=_WEBTOON_ASPECT_RATIO,
        resolution=_RESOLUTION,
        use_sequential_interleaving=True,
    )
    if not reference_items:
        await send_callback(callback_url, CallbackPayload(
            taskId=task_id,
            errorCode=9999,
            msg=f"webtoon reference generation failed: {reference_status}",
            data=CallbackData(),
        ))
        return

    reference_source = reference_items[0][0]
    webtoon_ref_path = await gemini_service.download_image_to_local(
        reference_source,
        prefix=f"emoji_api_{task_id}_webtoon_ref",
        work_dir=str(task_dir),
    )
    logger.info("[Pipeline] Task {}: Webtoon reference generated: {}", task_id, webtoon_ref_path)

    # ── Step 4-6: Generate 3 sticker sheets with fixed seed ───────────────
    # Fixed seed: random on first, reused for sheets 2 & 3
    actual_seed = random.randint(0, 2147483647)
    logger.info("[Pipeline] Task {}: Using fixed seed {} for all sheets", task_id, actual_seed)

    sheet_prompts = get_default_sheet_prompts(has_style_image=False)
    all_sticker_paths: list[tuple[str, str]] = []  # [(chinese_label, png_path)]

    for sheet_index, sheet_prompt in enumerate(sheet_prompts):
        sheet_label = f"sheet_{sheet_index + 1}"
        logger.info("[Pipeline] Task {}: Generating {}...", task_id, sheet_label)

        gallery_items, status_msg = await gemini_service.generate_image(
            sheet_prompt,
            image_files=[webtoon_ref_path],
            model=_GENERATION_MODEL,
            aspect_ratio=_SHEET_ASPECT_RATIO,
            resolution=_RESOLUTION,
            temperature=_TEMPERATURE,
            top_p=_TOP_P,
            seed=actual_seed,
            use_sequential_interleaving=True,
        )

        if not gallery_items:
            logger.warning("[Pipeline] Task {}: {} generation failed: {}", task_id, sheet_label, status_msg)
            continue

        # Download generated sheet image
        sheet_image_url = gallery_items[0][0]
        sheet_local_path = await gemini_service.download_image_to_local(
            sheet_image_url,
            prefix=f"emoji_api_{task_id}_{sheet_label}",
            work_dir=str(task_dir),
        )

        # Verify emotion labels using Flash (before cutout)
        emotion_labels = SHEET_EMOTION_LABELS[sheet_index] if sheet_index < len(SHEET_EMOTION_LABELS) else None
        if emotion_labels:
            verified_labels = await verify_sheet_labels(
                gemini_service, sheet_local_path, emotion_labels, task_id, sheet_label,
            )
            if verified_labels:
                if verified_labels != emotion_labels:
                    positions = ["top-left", "top-right", "bottom-left", "bottom-right"]
                    diffs = [
                        f"{positions[pos]}: {old} → {new}"
                        for pos, (old, new) in enumerate(zip(emotion_labels, verified_labels))
                        if old != new
                    ]
                    logger.warning(
                        "[Pipeline] Task {}: {} label verification swapped: {}",
                        task_id, sheet_label, "; ".join(diffs),
                    )
                emotion_labels = verified_labels

        # Step 5: Chroma-key cutout
        cutout_path = task_dir / "cutout" / f"{sheet_label}.webp"
        cutout_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            ffmpeg_params = get_ffmpeg_preset_values("balanced")
            await asyncio.to_thread(
                remove_background,
                sheet_local_path,
                str(cutout_path),
                "ffmpeg",
                ffmpeg_params,
            )
            logger.info("[Pipeline] Task {}: Cutout done for {}", task_id, sheet_label)
        except Exception as exc:
            logger.error("[Pipeline] Task {}: Cutout failed for {}: {}", task_id, sheet_label, exc)
            continue

        # Step 6: Smart crop
        smart_crop_dir = task_dir / "smart_crop" / sheet_label
        try:
            crop_paths = await asyncio.to_thread(
                smart_crop_sticker_sheet,
                str(cutout_path),
                str(smart_crop_dir),
                target_size=512,
                expected_stickers=4,
                emotion_labels=emotion_labels,
            )
            logger.info("[Pipeline] Task {}: Smart crop done for {}: {} stickers", task_id, sheet_label, len(crop_paths))
        except Exception as exc:
            logger.error("[Pipeline] Task {}: Smart crop failed for {}: {}", task_id, sheet_label, exc)
            continue

        # Collect sticker paths with their Chinese labels
        if emotion_labels:
            for i, crop_path in enumerate(crop_paths):
                label = emotion_labels[i] if i < len(emotion_labels) else f"sticker_{i+1}"
                all_sticker_paths.append((label, crop_path))
        else:
            for i, crop_path in enumerate(crop_paths):
                all_sticker_paths.append((f"sticker_{sheet_label}_{i+1}", crop_path))

    if not all_sticker_paths:
        await send_callback(callback_url, CallbackPayload(
            taskId=task_id,
            errorCode=9999,
            msg="all sticker sheet generations failed",
            data=CallbackData(),
        ))
        return

    # ── Step 7-8: Convert to WebP + Upload to OSS ────────────────────────
    webp_dir = task_dir / "webp"
    webp_dir.mkdir(parents=True, exist_ok=True)

    emoji_list: list[EmojiItem] = []

    for chinese_label, png_path in all_sticker_paths:
        english_theme = EMOJI_THEME_MAP.get(chinese_label, chinese_label)

        # Step 7: PNG -> WebP
        webp_path = webp_dir / f"{english_theme}.webp"
        try:
            png_to_webp(png_path, str(webp_path))
        except Exception as exc:
            logger.error("[Pipeline] Task {}: WebP conversion failed for {}: {}", task_id, english_theme, exc)
            continue

        # Step 8: Upload to OSS
        try:
            with open(webp_path, "rb") as f:
                webp_content = f.read()
            cdn_url = await oss_utils.upload_file(
                file_content=webp_content,
                filename=f"{english_theme}.webp",
                path_prefix=f"ai_emoji/{task_id}",
            )
            emoji_list.append(EmojiItem(theme=english_theme, url=cdn_url))
            logger.info("[Pipeline] Task {}: Uploaded {} -> {}", task_id, english_theme, cdn_url)
        except Exception as exc:
            logger.error("[Pipeline] Task {}: OSS upload failed for {}: {}", task_id, english_theme, exc)
            continue

    if not emoji_list:
        await send_callback(callback_url, CallbackPayload(
            taskId=task_id,
            errorCode=9999,
            msg="all WebP uploads failed",
            data=CallbackData(),
        ))
        return

    # ── Step 9: Send success callback ─────────────────────────────────────
    logger.info("[Pipeline] Task {}: Pipeline complete, {} stickers generated", task_id, len(emoji_list))
    await send_callback(callback_url, CallbackPayload(
        taskId=task_id,
        errorCode=0,
        msg="ok",
        data=CallbackData(emojiList=emoji_list),
    ))
