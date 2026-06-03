import os


TARGET_FPS = int(os.environ.get("PYOSU_TARGET_FPS", "1000"))
USE_BUSY_FRAME_PACER = os.environ.get("PYOSU_BUSY_FRAME_PACER", "0") == "1"
MAX_FRAME_DT = 1 / 30
RAW_MOUSE_SENSITIVITY = 1.0
MIXER_FREQUENCY = 44100
MIXER_SIZE = -16
MIXER_CHANNELS = 2
MIXER_BUFFER = 256


def configure_low_latency_environment():
    os.environ.setdefault("SDL_MOUSE_RELATIVE_MODE_WARP", "0")
    os.environ.setdefault("SDL_MOUSE_RELATIVE_SYSTEM_SCALE", "0")
    os.environ.setdefault("SDL_MOUSE_RELATIVE_MODE_CENTER", "0")
