"""Standalone test for Flash-based sticker label verification.

Usage (inside Docker container):
  python test_label_verify.py work_dir/ai_emoji/{taskId}

Requires .env with GEMINI_API_KEY configured.
"""
import asyncio
import sys
from pathlib import Path

from app.services.gemini_service import GeminiImageService
from app.prompts.emoji_meme_prompts import SHEET_EMOTION_LABELS

_LABEL_VERIFY_PROMPT = """You are classifying Chibi sticker emotions from a 2x2 sticker sheet image.

The image contains 4 stickers arranged in a 2x2 grid:
- Top-left quadrant
- Top-right quadrant
- Bottom-left quadrant
- Bottom-right quadrant

Assign each quadrant the MOST FITTING label from this exact list:
{labels}

RULES:
- Each label MUST be used exactly once.
- Match based on the character's facial expression, gesture, and body language.
- Do NOT invent new labels. Only use the {count} labels provided above."""


def _build_schema(candidate_labels: list[str]) -> dict:
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


async def test_sheet(image_path: str, sheet_index: int) -> None:
    service = GeminiImageService()
    labels = SHEET_EMOTION_LABELS[sheet_index]
    prompt = _LABEL_VERIFY_PROMPT.format(labels=labels, count=len(labels))
    schema = _build_schema(list(labels))

    result = await service.generate_structured_output(
        prompt=prompt,
        image_files=[image_path],
        model="gemini-2.5-flash",
        response_schema=schema,
    )

    positional = list(labels)
    verified = [result.get(k, "?") for k in ("top_left", "top_right", "bottom_left", "bottom_right")]

    print(f"\n=== Sheet {sheet_index + 1} ===")
    print(f"Positional labels: {positional}")
    print(f"Flash labels:      {verified}")
    print(f"Match: {'✅' if positional == verified else '❌'}")
    if positional != verified:
        for i, key in enumerate(("top_left", "top_right", "bottom_left", "bottom_right")):
            status = "✅" if positional[i] == verified[i] else "❌ SWAPPED"
            print(f"  {key:15s}: {positional[i]} → {verified[i]} {status}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python test_label_verify.py <task_dir>")
        print("Example: python test_label_verify.py work_dir/ai_emoji/test_male_1")
        sys.exit(1)

    task_dir = Path(sys.argv[1])
    if not task_dir.exists():
        print(f"Directory not found: {task_dir}")
        sys.exit(1)

    # Find sheet images (original generated images, not cutout)
    sheet_files = sorted(task_dir.glob("emoji_api_*_sheet_*"))
    if not sheet_files:
        # Fallback: try cutout images
        sheet_files = sorted((task_dir / "cutout").glob("sheet_*")) if (task_dir / "cutout").exists() else []

    if not sheet_files:
        print(f"No sheet images found in {task_dir}")
        print(f"  Looking for: emoji_api_*_sheet_* or cutout/sheet_*")
        sys.exit(1)

    print(f"Found {len(sheet_files)} sheet image(s) in {task_dir}:")
    for f in sheet_files:
        print(f"  {f}")

    for sheet_index, sheet_file in enumerate(sheet_files[:3]):
        await test_sheet(str(sheet_file), sheet_index)


if __name__ == "__main__":
    asyncio.run(main())
