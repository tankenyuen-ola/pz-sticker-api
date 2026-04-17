"""Smart crop utilities for extracting individual stickers from 4-sticker sheets."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class ContourInfo:
    """Information about a detected contour."""
    x: int
    y: int
    width: int
    height: int
    area: float


def detect_sticker_contours(
    image_path: str | Path,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.45,
) -> List[ContourInfo]:
    """
    Detect sticker contours in an image with transparent background.
    
    Args:
        image_path: Path to the image file (should have alpha channel)
        min_area_ratio: Minimum contour area as ratio of image area
        max_area_ratio: Maximum contour area as ratio of image area
        
    Returns:
        List of ContourInfo objects, sorted by area (largest first)
    """
    try:
        import cv2
    except ImportError:
        logger.error("OpenCV (cv2) is required for smart crop functionality")
        raise ImportError("OpenCV is required. Install with: pip install opencv-python")
    
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    # Load image with alpha channel
    img = Image.open(image_path).convert("RGBA")
    img_array = np.array(img)
    
    height, width = img_array.shape[:2]
    total_area = height * width
    min_area = total_area * min_area_ratio
    max_area = total_area * max_area_ratio
    
    # Extract alpha channel
    alpha = img_array[:, :, 3]
    
    # Create binary mask: non-transparent pixels
    # Use a threshold to handle partial transparency
    _, binary_mask = cv2.threshold(alpha, 10, 255, cv2.THRESH_BINARY)
    
    # Apply morphological operations to clean up noise
    kernel = np.ones((5, 5), np.uint8)
    binary_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, kernel)
    binary_mask = cv2.morphologyEx(binary_mask, cv2.MORPH_OPEN, kernel)
    
    # Find contours
    contours, _ = cv2.findContours(
        binary_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )
    
    contour_infos = []
    for contour in contours:
        area = cv2.contourArea(contour)
        
        # Filter by area
        if area < min_area or area > max_area:
            continue
        
        x, y, w, h = cv2.boundingRect(contour)
        contour_infos.append(ContourInfo(
            x=x,
            y=y,
            width=w,
            height=h,
            area=area
        ))
    
    # Sort by area (largest first)
    contour_infos.sort(key=lambda c: c.area, reverse=True)
    
    logger.info(
        f"Detected {len(contour_infos)} valid contours in {image_path} "
        f"(total contours: {len(contours)})"
    )
    
    return contour_infos


def _calculate_non_overlapping_crop(
    contour: ContourInfo,
    all_contours: List[ContourInfo],
    image_width: int,
    image_height: int,
    padding_ratio: float = 0.05,
) -> Tuple[int, int, int, int]:
    """
    Calculate crop region for a sticker that avoids overlapping with other stickers.
    
    The strategy is to expand the bounding box with padding, but clip any expansion
    that would intersect with neighboring stickers' bounding boxes.
    
    Args:
        contour: Target contour to crop
        all_contours: All detected contours
        image_width: Image width
        image_height: Image height
        padding_ratio: Desired padding ratio
        
    Returns:
        Tuple of (left, top, right, bottom) for safe crop region
    """
    # Calculate desired padding
    desired_padding_x = int(contour.width * padding_ratio)
    desired_padding_y = int(contour.height * padding_ratio)
    
    # Start with desired crop region
    left = max(0, contour.x - desired_padding_x)
    top = max(0, contour.y - desired_padding_y)
    right = min(image_width, contour.x + contour.width + desired_padding_x)
    bottom = min(image_height, contour.y + contour.height + desired_padding_y)
    
    # Check for overlaps with other contours and clip if necessary
    for other in all_contours:
        if other is contour:
            continue
        
        # Check if this other contour's bounding box overlaps with our desired crop
        # Expand other contour's box slightly to avoid edge cases
        safety_margin = 5  # pixels
        other_left = other.x - safety_margin
        other_top = other.y - safety_margin
        other_right = other.x + other.width + safety_margin
        other_bottom = other.y + other.height + safety_margin
        
        # If there's overlap, clip our crop region
        # Overlap on the left side
        if other_right > left and other_right < (contour.x + contour.width):
            left = max(left, other_right)
        
        # Overlap on the top side
        if other_bottom > top and other_bottom < (contour.y + contour.height):
            top = max(top, other_bottom)
        
        # Overlap on the right side
        if other_left < right and other_left > contour.x:
            right = min(right, other_left)
        
        # Overlap on the bottom side
        if other_top < bottom and other_top > contour.y:
            bottom = min(bottom, other_top)
    
    # Ensure minimum crop size (at least the contour itself)
    left = min(left, contour.x)
    top = min(top, contour.y)
    right = max(right, contour.x + contour.width)
    bottom = max(bottom, contour.y + contour.height)
    
    return (left, top, right, bottom)


def extract_sticker(
    image: Image.Image,
    contour: ContourInfo,
    all_contours: List[ContourInfo] | None = None,
    target_size: int = 512,
    padding_ratio: float = 0.05,
) -> Image.Image:
    """
    Extract a sticker from an image based on its contour and center it on a canvas.
    
    This function analyzes all contours to ensure the crop region doesn't overlap
    with adjacent stickers, then extracts with transparent padding and resizes to target.
    
    Args:
        image: Source PIL Image with alpha channel
        contour: ContourInfo defining the sticker bounding box
        all_contours: All detected contours (for overlap avoidance). If None, uses simple padding.
        target_size: Output canvas size (target_size x target_size)
        padding_ratio: Padding ratio around the sticker (0.05 = 5%)
        
    Returns:
        PIL Image of size (target_size, target_size) with centered sticker
    """
    # Calculate crop region
    if all_contours and len(all_contours) > 1:
        # Use non-overlapping crop calculation
        left, top, right, bottom = _calculate_non_overlapping_crop(
            contour, all_contours, image.width, image.height, padding_ratio
        )
    else:
        # Simple padding mode (single sticker or no contour info)
        padding_x = int(contour.width * padding_ratio)
        padding_y = int(contour.height * padding_ratio)
        left = max(0, contour.x - padding_x)
        top = max(0, contour.y - padding_y)
        right = min(image.width, contour.x + contour.width + padding_x)
        bottom = min(image.height, contour.y + contour.height + padding_y)
    
    # Crop the sticker region
    sticker_crop = image.crop((left, top, right, bottom))
    
    # Calculate scaling to fit within target size while maintaining aspect ratio
    crop_width = right - left
    crop_height = bottom - top
    
    # Leave some margin for the target canvas
    available_size = int(target_size * 0.85)  # 85% of canvas
    
    scale = min(
        available_size / crop_width,
        available_size / crop_height
    )
    
    new_width = int(crop_width * scale)
    new_height = int(crop_height * scale)
    
    # Resize the sticker
    sticker_resized = sticker_crop.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS
    )
    
    # Create new transparent canvas
    canvas = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    
    # Calculate position to center the sticker
    paste_x = (target_size - new_width) // 2
    paste_y = (target_size - new_height) // 2
    
    # Paste the sticker onto the canvas
    canvas.paste(sticker_resized, (paste_x, paste_y), sticker_resized)
    
    return canvas


def smart_crop_sticker_sheet(
    input_path: str | Path,
    output_dir: str | Path,
    target_size: int = 512,
    expected_stickers: int = 4,
    emotion_labels: List[str] | None = None,
) -> List[str]:
    """
    Smart crop a 4-sticker sheet into individual sticker images.
    
    Args:
        input_path: Path to the input sticker sheet image
        output_dir: Directory to save the output images
        target_size: Output canvas size for each sticker
        expected_stickers: Expected number of stickers (default 4)
        emotion_labels: List of emotion names for renaming (e.g., ["你好", "鼓掌", "喜欢", "害羞"])
        
    Returns:
        List of paths to the generated sticker images
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Starting smart crop for {input_path}")
    
    # Detect contours
    contours = detect_sticker_contours(input_path)
    
    if not contours:
        logger.warning(f"No contours detected in {input_path}")
        return []
    
    # Load the source image
    source_image = Image.open(input_path).convert("RGBA")
    
    # Take the top N contours (expected stickers)
    # If we have more than expected, take the largest ones
    # If we have fewer, we'll return what we have
    selected_contours = contours[:expected_stickers]
    
    if len(contours) < expected_stickers:
        logger.warning(
            f"Expected {expected_stickers} stickers but only found {len(contours)} "
            f"in {input_path}"
        )
    elif len(contours) > expected_stickers:
        logger.info(
            f"Found {len(contours)} contours, using top {expected_stickers} largest"
        )
    
    # Sort contours by position (top-to-bottom, left-to-right)
    # This ensures consistent naming: top-left, top-right, bottom-left, bottom-right
    selected_contours.sort(key=lambda c: (c.y, c.x))
    
    output_paths = []
    base_name = input_path.stem
    
    for index, contour in enumerate(selected_contours, start=1):
        try:
            # Extract and center the sticker with non-overlapping crop
            sticker_image = extract_sticker(
                source_image,
                contour,
                all_contours=selected_contours,  # Pass all contours for overlap avoidance
                target_size=target_size
            )
            
            # Determine output filename
            if emotion_labels and index <= len(emotion_labels):
                # Use emotion label for naming
                emotion_name = emotion_labels[index - 1]
                output_filename = f"{emotion_name}.png"
            else:
                # Fallback to generic naming
                output_filename = f"{base_name}_sticker_{index}.png"
            
            output_path = output_dir / output_filename
            sticker_image.save(output_path, format="PNG")
            
            output_paths.append(str(output_path))
            logger.info(
                f"Saved sticker {index}/{len(selected_contours)}: {output_path} "
                f"(contour: {contour.width}x{contour.height} at {contour.x},{contour.y})"
            )
            
        except Exception as e:
            logger.error(f"Failed to extract sticker {index}: {e}")
            # Continue with other stickers
    
    logger.info(
        f"Smart crop completed: {len(output_paths)}/{len(selected_contours)} "
        f"stickers saved to {output_dir}"
    )
    
    return output_paths


def analyze_sticker_layout(
    contours: List[ContourInfo],
) -> dict:
    """
    Analyze the layout of detected contours to verify it's a 2x2 grid.
    
    Args:
        contours: List of detected contours
        
    Returns:
        Dictionary with layout analysis results
    """
    if len(contours) != 4:
        return {
            "is_valid_2x2": False,
            "reason": f"Expected 4 contours, found {len(contours)}",
            "rows": None,
            "cols": None,
        }
    
    # Sort contours by position (top-to-bottom, left-to-right)
    # First by y (row), then by x (column)
    sorted_contours = sorted(contours, key=lambda c: (c.y, c.x))
    
    # Check if they form a rough 2x2 grid
    # In a 2x2 grid, we expect 2 distinct y-positions and 2 distinct x-positions
    y_positions = sorted(set(c.y for c in contours))
    x_positions = sorted(set(c.x for c in contours))
    
    # Group by rows (similar y positions)
    y_tolerance = max(c.height for c in contours) * 0.5
    rows = []
    current_row = []
    current_y = None
    
    for contour in sorted_contours:
        if current_y is None or abs(contour.y - current_y) > y_tolerance:
            if current_row:
                rows.append(current_row)
            current_row = [contour]
            current_y = contour.y
        else:
            current_row.append(contour)
    
    if current_row:
        rows.append(current_row)
    
    is_valid_2x2 = len(rows) == 2 and all(len(row) == 2 for row in rows)
    
    return {
        "is_valid_2x2": is_valid_2x2,
        "reason": None if is_valid_2x2 else f"Layout is {len(rows)} rows instead of 2",
        "rows": rows,
        "contours": sorted_contours,
    }
