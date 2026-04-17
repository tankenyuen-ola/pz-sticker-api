from __future__ import annotations


def build_image_generation_config_kwargs(
    *,
    aspect_ratio: str | None,
    resolution: str | None,
    temperature: float | None,
    top_p: float | None,
    seed: int | None = None,
    valid_aspect_ratios: list[str] | tuple[str, ...] = (),
    valid_resolutions: list[str] | tuple[str, ...] = (),
) -> dict:
    kwargs: dict = {}
    image_config: dict = {}

    if aspect_ratio and aspect_ratio in valid_aspect_ratios:
        image_config["aspect_ratio"] = aspect_ratio
    if resolution and resolution in valid_resolutions:
        image_config["image_size"] = resolution
    if image_config:
        kwargs["image_config"] = image_config

    if temperature is not None and 0 <= temperature <= 2:
        kwargs["temperature"] = float(temperature)
    if top_p is not None and 0 <= top_p <= 1:
        kwargs["top_p"] = float(top_p)
    if seed is not None and isinstance(seed, int) and seed >= 0:
        kwargs["seed"] = int(seed)

    return kwargs
