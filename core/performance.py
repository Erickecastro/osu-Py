import os


TARGET_FPS = int(os.environ.get("PYOSU_TARGET_FPS", "480"))
USE_BUSY_FRAME_PACER = os.environ.get("PYOSU_BUSY_FRAME_PACER", "0") == "1"
DEBUG_PERFORMANCE = os.environ.get("PYOSU_DEBUG_PERFORMANCE", "0") == "1"
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
    os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "0")
    os.environ.setdefault("SDL_HINT_FRAMEBUFFER_ACCELERATION", "1")
    os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")
