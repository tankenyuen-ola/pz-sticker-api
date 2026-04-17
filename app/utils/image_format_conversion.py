from __future__ import annotations

from pathlib import Path

from PIL import Image


SUPPORTED_IMAGE_FORMATS = {
    "png": "PNG",
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "webp": "WEBP",
}


def convert_image_format(source_path: str | Path, output_path: str | Path, target_format: str) -> str:
    normalized = target_format.lower()
    if normalized not in SUPPORTED_IMAGE_FORMATS:
        raise ValueError(f"不支持的目标格式: {target_format}")

    with Image.open(source_path) as image:
        if normalized in {"jpg", "jpeg"}:
            if image.mode not in {"RGB", "L"}:
                flattened = Image.new("RGB", image.size, (255, 255, 255))
                flattened.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
                image = flattened
            else:
                image = image.convert("RGB")
        elif normalized == "png":
            if image.mode not in {"RGBA", "RGB", "L", "LA"}:
                image = image.convert("RGBA")
        elif normalized == "webp" and image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

        save_format = SUPPORTED_IMAGE_FORMATS[normalized]
        image.save(output_path, format=save_format, quality=95 if save_format in {"JPEG", "WEBP"} else None)
    return str(output_path)


def build_image_conversion_links_text(gallery_items: list[tuple[str, str]]) -> str:
    lines = ["🔗 转换后的图片链接：", ""]
    for path, caption in gallery_items:
        lines.append(f"{caption}:")
        lines.append(path)
        lines.append("")
    return "\n".join(lines).strip()
