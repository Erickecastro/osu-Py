import os
from pathlib import Path


ASSETS_ROOT = Path("assets")
ACTIVE_SKIN_DIR = Path(
    os.environ.get(
        "PYOSU_SKIN_DIR",
        str(ASSETS_ROOT / "skins" / "default")
    )
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
