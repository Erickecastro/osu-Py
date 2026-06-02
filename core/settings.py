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


@dataclass
class GameSettings:
    mouse_sensitivity: float = 1.0

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
            )
        )

    def save(self):
        path = settings_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "mouse_sensitivity": round(
                            clamp_sensitivity(self.mouse_sensitivity),
                            3
                        )
                    },
                    indent=2
                ),
                encoding="utf-8"
            )
        except OSError:
            return False
        return True
