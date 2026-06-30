import json
import os
from dataclasses import dataclass
from pathlib import Path


def settings_path():
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "PyOsu" / "settings.json"
    return Path("settings.json")


def clamp_sensitivity(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 1.0
    return max(0.40, min(2.00, value))


def clamp_cursor_scale(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 1.0
    return max(0.50, min(2.00, value))


def clamp_gameplay_dim(value):
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError):
        value = 94
    return max(0, min(100, value))


def _coerce_key(value, default):
    try:
        key = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(0, key)


@dataclass
class GameSettings:
    mouse_sensitivity: float = 1.0
    cursor_scale: float = 1.0
    hit_key_1: int = 122  # pygame.K_z
    hit_key_2: int = 120  # pygame.K_x
    raw_mouse_enabled: bool = True
    tablet_input_enabled: bool = False
    block_mouse_buttons_in_gameplay: bool = False
    gameplay_dim: int = 94

    @classmethod
    def load(cls):
        path = settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()

        return cls(
            mouse_sensitivity=clamp_sensitivity(
                data.get("mouse_sensitivity", 1.0)
            ),
            cursor_scale=clamp_cursor_scale(data.get("cursor_scale", 1.0)),
            hit_key_1=_coerce_key(data.get("hit_key_1", 122), 122),
            hit_key_2=_coerce_key(data.get("hit_key_2", 120), 120),
            raw_mouse_enabled=bool(data.get("raw_mouse_enabled", True)),
            tablet_input_enabled=bool(data.get("tablet_input_enabled", False)),
            block_mouse_buttons_in_gameplay=bool(
                data.get("block_mouse_buttons_in_gameplay", False)
            ),
            gameplay_dim=clamp_gameplay_dim(data.get("gameplay_dim", 94))
        )

    def save(self):
        path = settings_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                {
                    "mouse_sensitivity": round(
                        clamp_sensitivity(self.mouse_sensitivity),
                        3
                    ),
                    "cursor_scale": round(
                        clamp_cursor_scale(self.cursor_scale),
                        3
                    ),
                    "hit_key_1": _coerce_key(self.hit_key_1, 122),
                    "hit_key_2": _coerce_key(self.hit_key_2, 120),
                    "raw_mouse_enabled": bool(self.raw_mouse_enabled),
                    "tablet_input_enabled": bool(self.tablet_input_enabled),
                    "block_mouse_buttons_in_gameplay": bool(
                        self.block_mouse_buttons_in_gameplay
                    ),
                    "gameplay_dim": clamp_gameplay_dim(self.gameplay_dim)
                },
                indent=2
            )
            temp_path = path.with_name(f"{path.name}.tmp")
            temp_path.write_text(payload, encoding="utf-8")
            temp_path.replace(path)
        except OSError:
            return False
        return True
