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
