"""Background removal utilities for sticker-sheet outputs."""

from __future__ import annotations

from collections import Counter
import io
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageColor

try:
    from rembg import remove as rembg_remove
except ImportError:  # pragma: no cover - depends on runtime environment
    rembg_remove = None

BACKGROUND_REMOVAL_METHODS = ["rembg", "ffmpeg"]
ALPHA_LOW_CUTOFF = 128
ALPHA_HIGH_CUTOFF = 220
EDGE_ANALYSIS_SIMILARITY = 0.14
EDGE_ANALYSIS_BLEND = 0.02
EDGE_RATIO = 0.10
SAMPLE_STEP = 5
EROSION_SIZE = 1
BOXBLUR_SIZE = 1

FFMPEG_PARAMETER_LIMITS = {
    "similarity": {"minimum": 0.05, "maximum": 0.30, "step": 0.01, "default": 0.16},
    "blend": {"minimum": 0.00, "maximum": 0.08, "step": 0.005, "default": 0.02},
    "alpha_low_cutoff": {"minimum": 0, "maximum": 254, "step": 1, "default": 138},
    "alpha_high_cutoff": {"minimum": 1, "maximum": 255, "step": 1, "default": 215},
    "edge_ratio": {"minimum": 0.02, "maximum": 0.30, "step": 0.01, "default": 0.10},
    "sample_step": {"minimum": 1, "maximum": 20, "step": 1, "default": 5},
    "erosion_size": {"minimum": 0, "maximum": 3, "step": 1, "default": 1},
    "boxblur_size": {"minimum": 0, "maximum": 3, "step": 1, "default": 1},
}

FFMPEG_PRESETS = {
    "balanced": {
        "label": "平衡（推荐）",
        "description": "适合大多数表情包，优先兼顾主体保留和背景去除。",
        "values": {
            "similarity": 0.16,
            "blend": 0.02,
            "alpha_low_cutoff": 138,
            "alpha_high_cutoff": 215,
            "edge_ratio": 0.10,
            "sample_step": 5,
            "erosion_size": 1,
            "boxblur_size": 1,
        },
    },
    "aggressive": {
        "label": "强力去边",
        "description": "优先去残边和脏边，适合背景残留明显的图。",
        "values": {
            "similarity": 0.17,
            "blend": 0.015,
            "alpha_low_cutoff": 145,
            "alpha_high_cutoff": 210,
            "edge_ratio": 0.10,
            "sample_step": 5,
            "erosion_size": 1,
            "boxblur_size": 1,
        },
    },
    "extreme": {
        "label": "极限去边",
        "description": "在强力去边基础上把 Alpha Low/High 都拉到 210，可能把主体边缘直接抠没，谨慎使用。",
        "values": {
            "similarity": 0.17,
            "blend": 0.015,
            "alpha_low_cutoff": 210,
            "alpha_high_cutoff": 210,
            "edge_ratio": 0.10,
            "sample_step": 5,
            "erosion_size": 1,
            "boxblur_size": 1,
        },
    },
    "conservative": {
        "label": "保守保主体",
        "description": "优先保留头发、手势、衣角等细节，但可能残留更多边缘。",
        "values": {
            "similarity": 0.11,
            "blend": 0.03,
            "alpha_low_cutoff": 110,
            "alpha_high_cutoff": 230,
            "edge_ratio": 0.10,
            "sample_step": 5,
            "erosion_size": 1,
            "boxblur_size": 1,
        },
    },
}


def get_ffmpeg_preset_values(preset_name: str) -> dict[str, float | int]:
    preset = FFMPEG_PRESETS.get(preset_name) or FFMPEG_PRESETS["balanced"]
    return dict(preset["values"])


def get_ffmpeg_reference_markdown() -> str:
    lines = ["**推荐参数方案参考**"]
    for key in ("balanced", "aggressive", "extreme", "conservative"):
        preset = FFMPEG_PRESETS[key]
        lines.append(f"- `{preset['label']}`: {preset['description']}")
    return "\n".join(lines)


def extract_edge_pixels(image_path: str | Path, edge_ratio: float = 0.1, sample_step: int = 5):
    image = Image.open(image_path).convert("RGB")
    arr = np.array(image)
    height, width = arr.shape[:2]

    edge_x = max(1, int(width * edge_ratio))
    edge_y = max(1, int(height * edge_ratio))

    top = arr[:edge_y, :, :]
    bottom = arr[height - edge_y :, :, :]
    left = arr[edge_y : height - edge_y, :edge_x, :]
    right = arr[edge_y : height - edge_y, width - edge_x :, :]

    edge_pixels = np.concatenate(
        [
            top.reshape(-1, 3),
            bottom.reshape(-1, 3),
            left.reshape(-1, 3),
            right.reshape(-1, 3),
        ]
    )
    return edge_pixels[::sample_step]


def detect_background_rgb_from_edges(
    image_path: str | Path,
    edge_ratio: float = 0.1,
    sample_step: int = 5,
) -> tuple[int, int, int]:
    edge_pixels = extract_edge_pixels(
        image_path,
        edge_ratio=edge_ratio,
        sample_step=sample_step,
    )
    counts = Counter(map(tuple, edge_pixels))
    dominant = counts.most_common(1)[0][0]
    return tuple(int(channel) for channel in dominant[:3])


def rgb_to_ffmpeg_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb[:3]
    return f"0x{r:02X}{g:02X}{b:02X}"


def build_ffmpeg_command(
    input_path: str | Path,
    output_path: str | Path,
    hex_color: str,
    similarity: float,
    blend: float,
    alpha_low_cutoff: int,
    alpha_high_cutoff: int,
    erosion_size: int,
    boxblur_size: int,
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        (
            f"[0:v]colorkey={hex_color}:{similarity}:{blend},format=rgba[ck];"
            "[ck]alphaextract[a];"
            f"[a]erosion={erosion_size},boxblur={boxblur_size},"
            f"lut=y='if(lt(val,{alpha_low_cutoff}),0,if(gt(val,{alpha_high_cutoff}),255,val))'[a2];"
            "[ck][a2]alphamerge"
        ),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(output_path),
    ]


def decontaminate_edge_spill(image: Image.Image, background_rgb: tuple[int, int, int]) -> Image.Image:
    rgba_image = image.convert("RGBA")
    arr = np.array(rgba_image).astype(np.float32)

    alpha = arr[..., 3:4] / 255.0
    bg = np.array(background_rgb, dtype=np.float32).reshape((1, 1, 3))

    partial_mask = (alpha > 0.0) & (alpha < 1.0)
    safe_alpha = np.maximum(alpha, 1e-6)
    corrected_rgb = (arr[..., :3] - bg * (1.0 - alpha)) / safe_alpha
    corrected_rgb = np.clip(corrected_rgb, 0, 255)

    arr[..., :3] = np.where(partial_mask, corrected_rgb, arr[..., :3])

    return Image.fromarray(arr.astype(np.uint8))


def save_rgba_image(image: Image.Image, output_path: str | Path) -> None:
    output_path = Path(output_path)
    if output_path.suffix.lower() == ".webp":
        image.save(output_path, format="WEBP")
        return
    image.save(output_path)


def analyze_transparency(image_path: str | Path) -> dict[str, int | str]:
    image = Image.open(image_path).convert("RGBA")
    alpha = np.array(image)[..., 3]

    transparent_pixels = int(np.sum(alpha == 0))
    translucent_pixels = int(np.sum((alpha > 0) & (alpha < 255)))
    opaque_pixels = int(np.sum(alpha == 255))

    if transparent_pixels or translucent_pixels:
        status = 'Image Contains Transparency'
    else:
        status = 'Image Is Fully Opaque'

    return {
        "status": status,
        "transparent_pixels": transparent_pixels,
        "translucent_pixels": translucent_pixels,
        "opaque_pixels": opaque_pixels,
    }


def format_transparency_check(analysis: dict[str, int | str]) -> str:
    return "\n".join(
        [
            "Transparency Check",
            f'Status: "{analysis["status"]}"',
            f'Transparent pixels: {analysis["transparent_pixels"]}',
            f'Translucent pixels: {analysis["translucent_pixels"]}',
            f'Opaque pixels: {analysis["opaque_pixels"]}',
        ]
    )


def create_transparency_status_visualization(
    input_path: str | Path,
    output_path: str | Path,
    transparency_color: str = "rgb(83, 143, 216)",
    translucency_color: str = "red",
    opacity_color: str = "white",
    display_actual_translucency: bool = True,
) -> None:
    image = Image.open(input_path).convert("RGBA")
    rgba = np.array(image).astype(np.float32)
    alpha = rgba[..., 3]

    transparent_rgb = np.array(ImageColor.getrgb(transparency_color), dtype=np.float32)
    translucent_rgb = np.array(ImageColor.getrgb(translucency_color), dtype=np.float32)
    opaque_rgb = np.array(ImageColor.getrgb(opacity_color), dtype=np.float32)

    output = np.zeros((rgba.shape[0], rgba.shape[1], 3), dtype=np.float32)
    output[:] = transparent_rgb

    opaque_mask = alpha == 255
    translucent_mask = (alpha > 0) & (alpha < 255)

    output[opaque_mask] = opaque_rgb
    if display_actual_translucency:
        translucency_factor = (alpha[translucent_mask] / 255.0).reshape(-1, 1)
        output[translucent_mask] = (
            translucency_factor * translucent_rgb
            + (1.0 - translucency_factor) * transparent_rgb
        )
    else:
        output[translucent_mask] = translucent_rgb

    Image.fromarray(np.clip(output, 0, 255).astype(np.uint8)).save(output_path)


def remove_background_ffmpeg(
    input_path: str | Path,
    output_path: str | Path,
    similarity: float = EDGE_ANALYSIS_SIMILARITY,
    blend: float = EDGE_ANALYSIS_BLEND,
    alpha_low_cutoff: int = ALPHA_LOW_CUTOFF,
    alpha_high_cutoff: int = ALPHA_HIGH_CUTOFF,
    edge_ratio: float = EDGE_RATIO,
    sample_step: int = SAMPLE_STEP,
    erosion_size: int = EROSION_SIZE,
    boxblur_size: int = BOXBLUR_SIZE,
) -> None:
    background_rgb = detect_background_rgb_from_edges(
        input_path,
        edge_ratio=edge_ratio,
        sample_step=sample_step,
    )
    hex_color = rgb_to_ffmpeg_hex(background_rgb)

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        tmp_png = Path(tmp.name)
        subprocess.run(
            build_ffmpeg_command(
                input_path,
                tmp_png,
                hex_color,
                similarity,
                blend,
                alpha_low_cutoff,
                alpha_high_cutoff,
                erosion_size,
                boxblur_size,
            ),
            check=True,
        )
        with Image.open(tmp_png) as image:
            cleaned_image = decontaminate_edge_spill(image, background_rgb)
            save_rgba_image(cleaned_image, output_path)


def remove_background(
    input_path: str | Path,
    output_path: str | Path,
    method: str = "ffmpeg",
    ffmpeg_params: dict | None = None,
) -> None:
    """Remove background with the selected method and save the result as WEBP."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if method == "ffmpeg":
        remove_background_ffmpeg(input_path, output_path, **(ffmpeg_params or {}))
        return
    if method != "rembg":
        raise ValueError(f"不支持的抠图算法: {method}")

    if rembg_remove is None:
        raise ImportError("rembg 未安装，请先安装 requirements.txt 中的 rembg 依赖")

    with input_path.open("rb") as source_file:
        input_bytes = source_file.read()

    output_bytes = rembg_remove(input_bytes)
    with Image.open(io.BytesIO(output_bytes)) as image:
        image.save(output_path, format="WEBP")
