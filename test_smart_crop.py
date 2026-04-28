"""Standalone test for sticker smart_crop bottom margin.

Usage:
  # Test with a single sticker image (no grid detection, just extract + margin)
  python test_smart_crop.py path/to/sticker.png

  # Test with a 2x2 sticker sheet
  python test_smart_crop.py path/to/sheet.png --sheet

  # Test with a generated task directory (finds sheets automatically)
  python test_smart_crop.py work_dir/ai_emoji/{taskId}

Output:
  - Prints bottom margin measurements for each sticker
  - Saves cropped stickers to a test_output/ directory
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image
from app.utils.smart_crop import (
    detect_sticker_contours,
    extract_sticker,
    smart_crop_sticker_sheet,
)


def measure_bottom_margin(image_path: str) -> dict:
    """Measure the bottom transparent margin of a PNG image."""
    img = Image.open(image_path).convert("RGBA")
    alpha = img.split()[3]
    width, height = img.size

    # Find the lowest non-transparent pixel
    bottom_y = 0
    for y in range(height - 1, -1, -1):
        row = alpha.crop((0, y, width, y + 1))
        if row.getextrema()[1] > 0:  # Has non-transparent pixel
            bottom_y = y
            break

    bottom_margin = height - 1 - bottom_y
    return {
        "width": width,
        "height": height,
        "content_bottom_y": bottom_y,
        "bottom_margin_px": bottom_margin,
    }


def test_single_sticker(image_path: str, output_dir: Path, target_size: int = 512):
    """Test extract_sticker on a single sticker image (no grid)."""
    img = Image.open(image_path).convert("RGBA")
    print(f"\n--- Single sticker test: {image_path} ---")
    print(f"  Source: {img.width}x{img.height}")

    # Use the full image as a single contour
    from app.utils.smart_crop import ContourInfo

    contour = ContourInfo(
        x=0, y=0, width=img.width, height=img.height, area=img.width * img.height
    )

    result = extract_sticker(img, contour, all_contours=None, target_size=target_size)

    output_path = output_dir / f"single_{Path(image_path).stem}.png"
    result.save(output_path, format="PNG")

    info = measure_bottom_margin(str(output_path))
    print(f"  Output: {info['width']}x{info['height']}")
    print(f"  Content bottom Y: {info['content_bottom_y']} px")
    print(f"  Bottom margin: {info['bottom_margin_px']} px")
    print(f"  Saved: {output_path}")

    return info


def test_sheet(image_path: str, output_dir: Path, target_size: int = 512):
    """Test smart_crop_sticker_sheet on a 2x2 sticker sheet."""
    print(f"\n--- Sheet test: {image_path} ---")

    # Detect contours first for info
    contours = detect_sticker_contours(image_path)
    print(f"  Detected {len(contours)} contours")

    # Run full smart_crop pipeline
    sheet_dir = output_dir / f"sheet_{Path(image_path).stem}"
    sheet_dir.mkdir(parents=True, exist_ok=True)

    paths = smart_crop_sticker_sheet(
        input_path=image_path,
        output_dir=sheet_dir,
        target_size=target_size,
        expected_stickers=4,
    )

    print(f"\n  Cropped {len(paths)} stickers:")
    for i, p in enumerate(paths, 1):
        info = measure_bottom_margin(p)
        status = "OK" if info["bottom_margin_px"] == 52 else "MISMATCH"
        print(
            f"    [{i}] {Path(p).name}: "
            f"content_bottom={info['content_bottom_y']}px, "
            f"bottom_margin={info['bottom_margin_px']}px "
            f"{'✓' if status == 'OK' else '✗ NOT 52px'}"
        )

    return paths


def test_task_dir(task_dir: str, output_dir: Path, target_size: int = 512):
    """Find and test all sheet images in a task directory."""
    task_path = Path(task_dir)
    if not task_path.exists():
        print(f"Directory not found: {task_dir}")
        return

    # Find sheet images (typically named sheet_*.png or *_sheet.png)
    sheet_files = list(task_path.glob("sheet_*.png")) + list(
        task_path.glob("*_sheet.png")
    )

    # Also try any PNG if no sheet files found
    if not sheet_files:
        sheet_files = list(task_path.glob("*.png"))

    if not sheet_files:
        print(f"No PNG images found in {task_dir}")
        return

    print(f"Found {len(sheet_files)} images in {task_dir}")
    for f in sorted(sheet_files):
        test_sheet(str(f), output_dir, target_size)


def main():
    parser = argparse.ArgumentParser(description="Test sticker smart_crop bottom margin")
    parser.add_argument("input", help="Image path or task directory")
    parser.add_argument(
        "--sheet", action="store_true", help="Treat input as 2x2 sticker sheet"
    )
    parser.add_argument(
        "--output",
        default="test_output",
        help="Output directory (default: test_output)",
    )
    parser.add_argument(
        "--size", type=int, default=512, help="Target size (default: 512)"
    )

    args = parser.parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input)

    if input_path.is_dir():
        test_task_dir(str(input_path), output_dir, args.size)
    elif args.sheet:
        test_sheet(str(input_path), output_dir, args.size)
    else:
        test_single_sticker(str(input_path), output_dir, args.size)

    print(f"\n--- Summary ---")
    print(f"Output saved to: {output_dir}/")
    print(f"Expected bottom margin: 52px")


if __name__ == "__main__":
    main()
