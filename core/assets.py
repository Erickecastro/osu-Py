import os
from pathlib import Path

import pygame


ASSETS_ROOT = Path("assets")
ACTIVE_SKIN_DIR = Path(
    os.environ.get(
        "PYOSU_SKIN_DIR",
        str(ASSETS_ROOT / "skins" / "default")
    )
)

_IMAGE_CACHE = {}


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
