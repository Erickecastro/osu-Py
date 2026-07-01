import os
from pathlib import Path

import pygame

from core.utils import application_path, resource_path


def _resolve_env_path(relative_path):
    path = Path(relative_path)
    if path.is_absolute():
        return path

    normalized = relative_path.replace("\\", "/")
    if normalized == "assets" or normalized.startswith("assets/"):
        return Path(resource_path(relative_path))

    return Path(application_path(relative_path))


ASSETS_ROOT = Path(resource_path("assets"))
ACTIVE_SKIN_DIR = _resolve_env_path(
    os.environ.get(
        "PYOSU_SKIN_DIR",
        str(ASSETS_ROOT / "skins" / "default")
    )
)

_IMAGE_CACHE = {}

_STARTUP_PRELOADS = (
    ("cursor.png", "cursor"),
    ("cursortrail.png", "cursor"),
    ("Osu!_Logo_2016.svg.png",),
    ("menu-bg.jpg",),
    ("main-menu-buttons.png",),
    ("button.png",),
    ("menu-snow.png", "menu"),
    ("snow.png", "menu"),
    ("menu-button-background.png", "songselect_cards"),
    ("songselect-back-button.png",),
    ("songselect-top-band.png",),
    ("star.png",),
    ("results-menu.png",),
    ("scorebar-colour.png", "HP"),
    ("spinner-approachcircle.png", "spinner"),
    ("spinner-circle.png", "spinner"),
)


def asset_path(filename, *legacy_parts):
    skin_path = ACTIVE_SKIN_DIR / filename
    if skin_path.exists():
        return skin_path

    if legacy_parts:
        legacy_path = ASSETS_ROOT.joinpath(*legacy_parts, filename)
        if legacy_path.exists():
            return legacy_path

    root_path = ASSETS_ROOT / filename
    if root_path.exists():
        return root_path

    return skin_path


def _resolved_key(path):
    try:
        return str(path.resolve())
    except (OSError, RuntimeError):
        return str(path)


def scale_image_high_quality(image, target_size):
    """
    Scale an image to target size with MAXIMUM possible quality!
    Uses multi-pass scaling for optimal results both up and down.
    """
    target_w, target_h = target_size
    
    if image.get_width() == target_w and image.get_height() == target_h:
        return image
    
    # First ensure we're working with an alpha surface for best results
    scaled = image.convert_alpha()
    current_w, current_h = scaled.get_size()
    
    # Multi-step scaling approach (always use power-of-2 steps for quality)
    while True:
        if current_w == target_w and current_h == target_h:
            break
            
        # Calculate next size
        next_w, next_h = target_w, target_h
        
        # For upscaling: go in smaller steps for better results
        if target_w > current_w * 1.1 or target_h > current_h * 1.1:
            next_w = min(int(current_w * 1.3), target_w)
            next_h = min(int(current_h * 1.3), target_h)
        # For downscaling: also use smaller steps
        elif target_w < current_w * 0.9 or target_h < current_h * 0.9:
            next_w = max(int(current_w * 0.8), target_w)
            next_h = max(int(current_h * 0.8), target_h)
        
        # Use smoothscale for the best possible quality
        scaled = pygame.transform.smoothscale(scaled, (next_w, next_h))
        current_w, current_h = next_w, next_h
        
        # Break if we've reached the target
        if current_w == target_w and current_h == target_h:
            break
            
    # Final smoothscale to exact target size to ensure perfection
    scaled = pygame.transform.smoothscale(scaled, (target_w, target_h))
    return scaled


def load_image(filename, *legacy_parts, alpha=True):
    path = asset_path(filename, *legacy_parts)
    if not path.exists():
        return None

    key = (_resolved_key(path), bool(alpha))
    cached = _IMAGE_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        image = pygame.image.load(str(path))
        image = image.convert_alpha() if alpha else image.convert()
    except pygame.error:
        return None

    _IMAGE_CACHE[key] = image
    return image


def preload_startup_assets():
    for parts in _STARTUP_PRELOADS:
        load_image(*parts)
