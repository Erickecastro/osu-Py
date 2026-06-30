import os


TARGET_FPS_OVERRIDE = os.environ.get("PYOSU_TARGET_FPS")
TARGET_FPS = int(TARGET_FPS_OVERRIDE) if TARGET_FPS_OVERRIDE else 0
AUTO_FPS_MULTIPLIER = float(os.environ.get("PYOSU_AUTO_FPS_MULTIPLIER", "4.0"))
AUTO_FPS_MIN = int(os.environ.get("PYOSU_AUTO_FPS_MIN", "480"))
AUTO_FPS_MAX = int(os.environ.get("PYOSU_AUTO_FPS_MAX", "1200"))
USE_BUSY_FRAME_PACER = os.environ.get("PYOSU_BUSY_FRAME_PACER", "0") == "1"
DEBUG_PERFORMANCE = os.environ.get("PYOSU_DEBUG_PERFORMANCE", "0") == "1"
MAX_FRAME_DT = 1 / 30
RAW_MOUSE_SENSITIVITY = 1.0
MIXER_FREQUENCY = 44100
MIXER_SIZE = -16
MIXER_CHANNELS = 2
MIXER_BUFFER = 256
AUDIO_OFFSET_MS = float(os.environ.get("PYOSU_AUDIO_OFFSET_MS", "0"))
HIT_ERROR_DISPLAY_OFFSET_MS = float(
    os.environ.get("PYOSU_HIT_ERROR_DISPLAY_OFFSET_MS", "-8")
)


def configure_low_latency_environment():
    os.environ.setdefault("SDL_MOUSE_RELATIVE_MODE_WARP", "0")
    os.environ.setdefault("SDL_MOUSE_RELATIVE_SYSTEM_SCALE", "0")
    os.environ.setdefault("SDL_MOUSE_RELATIVE_MODE_CENTER", "0")
    os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "0")
    os.environ.setdefault("SDL_HINT_FRAMEBUFFER_ACCELERATION", "1")
    os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")
    os.environ.setdefault("SDL_TIMER_RESOLUTION", "1")
    os.environ.setdefault("SDL_MOUSE_TOUCH_EVENTS", "0")
    os.environ.setdefault("SDL_TOUCH_MOUSE_EVENTS", "0")
    os.environ.setdefault("SDL_HINT_RENDER_VSYNC", "0")
    os.environ.setdefault("SDL_HINT_VIDEO_X11_XRANDR", "1")
    os.environ.setdefault("SDL_HINT_VIDEO_X11_XVIDMODE", "1")
    os.environ.setdefault("SDL_HINT_VIDEO_ALLOW_SCREENSAVER", "0")
    os.environ.setdefault("SDL_HINT_IDLE_TIMER_DISABLED", "1")
    os.environ.setdefault("SDL_HINT_THREAD_FORCE_REALTIME_TIME_CRITICAL", "1")
    os.environ.setdefault("SDL_HINT_AUDIO_RESAMPLING_MODE", "0")
    os.environ.setdefault("SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "0")
    os.environ.setdefault("SDL_HINT_MOUSE_DOUBLE_CLICK_RADIUS", "0")
    os.environ.setdefault("SDL_HINT_MOUSE_DOUBLE_CLICK_TIME", "0")
