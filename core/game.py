import os

import pygame
import pygame_gui

from core.assets import preload_startup_assets
from core.beatmap_loader import BeatmapLoader
from core.osz_importer import OszImporter
from core.performance import (
    AUTO_FPS_MAX,
    AUTO_FPS_MIN,
    AUTO_FPS_MULTIPLIER,
    DEBUG_PERFORMANCE,
    FULLSCREEN_MODE,
    MAX_FRAME_DT,
    MIXER_BUFFER,
    MIXER_CHANNELS,
    MIXER_FREQUENCY,
    MIXER_SIZE,
    RAW_MOUSE_SENSITIVITY,
    TARGET_FPS,
    USE_BUSY_FRAME_PACER,
    configure_low_latency_environment
)
from core.profiler import FrameProfiler
from core.scene_manager import SceneManager
from core.settings import (
    GameSettings,
    clamp_cursor_scale,
    clamp_gameplay_dim,
    clamp_sensitivity
)
from rendering.cursor import CursorRenderer
from rendering.render_backend import create_render_backend
from scenes.main_menu_scene import MainMenuScene

class Game:

    FPS = TARGET_FPS or AUTO_FPS_MIN

    def __init__(self):

        # -------------------------
        # PYGAME
        # -------------------------
        configure_low_latency_environment()

        pygame.mixer.pre_init(
            frequency=MIXER_FREQUENCY,
            size=MIXER_SIZE,
            channels=MIXER_CHANNELS,
            buffer=MIXER_BUFFER
        )
        pygame.init()
        try:
            pygame.joystick.quit()
        except pygame.error:
            pass

        pygame.mixer.init()
        self._configure_event_filters()
        preload_startup_assets()

        # -------------------------
        # DISPLAY
        # -------------------------
        self.fullscreen = True
        self.window_mode = "unknown"
        self.display_surface = None
        self.opengl_window_active = False
        self.opengl_window_failed = False
        self.opengl_window_status = "not_checked"
        self.opengl_backend_status = "not_checked"

        self.create_window()
        self.display_refresh_rate = self._detect_display_refresh_rate()
        self.FPS = self._resolve_target_fps()

        pygame.display.set_caption("PyOsu")

        # -------------------------
        # CLOCK
        # -------------------------
        self.clock = pygame.time.Clock()
        self.dt = 1.0 / self.FPS
        self.profiler = FrameProfiler(enabled=DEBUG_PERFORMANCE)
        self.settings = GameSettings.load()
        self.mouse_pos = pygame.mouse.get_pos()
        self.raw_mouse_enabled = False
        self.raw_mouse_fallback = False
        self.raw_mouse_sensitivity = clamp_sensitivity(
            self.settings.mouse_sensitivity or RAW_MOUSE_SENSITIVITY
        )
        self.cursor_scale = clamp_cursor_scale(self.settings.cursor_scale)
        self.raw_mouse_preferred = bool(self.settings.raw_mouse_enabled)
        self.tablet_input_enabled = bool(self.settings.tablet_input_enabled)
        if self.tablet_input_enabled and self.raw_mouse_preferred:
            self.raw_mouse_preferred = False
            self.settings.raw_mouse_enabled = False
            self.settings.save()
        if self.tablet_input_enabled or not self.raw_mouse_preferred:
            self._normalize_system_pointer_sensitivity()
        self.block_mouse_buttons_in_gameplay = bool(
            self.settings.block_mouse_buttons_in_gameplay
        )
        self.hit_keys = (
            int(self.settings.hit_key_1),
            int(self.settings.hit_key_2)
        )
        self.gameplay_dim = clamp_gameplay_dim(self.settings.gameplay_dim)
        self.cursor_renderer = CursorRenderer(user_scale=self.cursor_scale)
        self._last_cursor_scene = None
        self.render_backend = None
        self._recreate_render_backend()
        pygame.mouse.set_visible(False)
        pygame.event.set_blocked(pygame.MOUSEMOTION)
        self.mouse_motion_blocked = True
        self.sync_input_mode(self.mouse_pos)

        self.current_menu_music_path = None
        self.current_menu_music_title = None
        self.current_menu_music_timing_points = []
        self.current_menu_music_paused = False
        self.current_selected_osu_file = None

        self.running = True

        # -------------------------
        # UI MANAGER
        # -------------------------
        self.ui_manager = pygame_gui.UIManager(
            (self.WIDTH, self.HEIGHT)
        )

        # -------------------------
        # BEATMAPS
        # -------------------------
        self.beatmap_loader = BeatmapLoader()
        self.osz_importer = OszImporter(self.beatmap_loader)
        self.last_import_result = self.osz_importer.import_pending()

        self.beatmaps = (
            self.beatmap_loader.load_songs()
        )

        # -------------------------
        # SCENE MANAGER
        # -------------------------
        self.scene_manager = SceneManager()

        self.scene_manager.set_scene(
            MainMenuScene(self)
        )

    def _configure_event_filters(self):
        blocked_events = []
        for name in (
            "WINDOWFOCUSLOST",
            "WINDOWFOCUSGAINED",
            "WINDOWENTER",
            "WINDOWLEAVE",
            "WINDOWSHOWN",
            "WINDOWHIDDEN",
            "WINDOWEXPOSED",
            "WINDOWMINIMIZED",
            "WINDOWMAXIMIZED",
            "WINDOWRESTORED",
            "JOYAXISMOTION",
            "JOYBALLMOTION",
            "JOYHATMOTION",
            "JOYBUTTONDOWN",
            "JOYBUTTONUP",
            "JOYDEVICEADDED",
            "JOYDEVICEREMOVED",
            "CONTROLLERAXISMOTION",
            "CONTROLLERBUTTONDOWN",
            "CONTROLLERBUTTONUP",
            "CONTROLLERDEVICEADDED",
            "CONTROLLERDEVICEREMOVED",
            "CONTROLLERDEVICEREMAPPED",
            "FINGERDOWN",
            "FINGERUP",
            "FINGERMOTION",
            "MULTIGESTURE",
        ):
            event_type = getattr(pygame, name, None)
            if event_type is not None:
                blocked_events.append(event_type)

        if blocked_events:
            pygame.event.set_blocked(blocked_events)

    # -------------------------
    # CREATE WINDOW
    # -------------------------
    def _fullscreen_mode(self):
        if FULLSCREEN_MODE in {"exclusive", "desktop", "borderless"}:
            return FULLSCREEN_MODE
        return "desktop"

    def _desktop_size(self):
        getter = getattr(pygame.display, "get_desktop_sizes", None)
        if callable(getter):
            try:
                sizes = getter()
            except (pygame.error, TypeError, ValueError):
                sizes = []
            if sizes:
                width, height = sizes[0]
                if width > 0 and height > 0:
                    return int(width), int(height)

        info = pygame.display.Info()
        width = int(getattr(info, "current_w", 0) or 1280)
        height = int(getattr(info, "current_h", 0) or 720)
        return width, height

    def _env_flag_enabled(self, name):
        value = os.environ.get(name, "")
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _should_use_opengl_window(self):
        if self._env_flag_enabled("PYOSU_DISABLE_OPENGL_WINDOW"):
            self.opengl_window_status = "disabled_window_env"
            return False
        if self._env_flag_enabled("PYOSU_DISABLE_MODERNGL"):
            self.opengl_window_status = "disabled_moderngl_env"
            return False
        if not (
            self._env_flag_enabled("PYOSU_ENABLE_OPENGL_WINDOW")
            or self._env_flag_enabled("PYOSU_FORCE_MODERNGL")
        ):
            self.opengl_window_status = "disabled_window_default"
            return False
        if self.opengl_window_failed and not self._env_flag_enabled("PYOSU_FORCE_MODERNGL"):
            self.opengl_window_status = "previous_failure"
            return False
        try:
            import moderngl  # type: ignore  # noqa: F401
        except ImportError:
            self.opengl_window_status = "missing_moderngl"
            return False
        self.opengl_window_status = "ready"
        return True

    def _configure_opengl_attributes(self):
        attributes = (
            ("GL_CONTEXT_MAJOR_VERSION", 3),
            ("GL_CONTEXT_MINOR_VERSION", 3),
            ("GL_DOUBLEBUFFER", 1),
            ("GL_DEPTH_SIZE", 0),
        )
        for name, value in attributes:
            attr = getattr(pygame, name, None)
            if attr is None:
                continue
            try:
                pygame.display.gl_set_attribute(attr, value)
            except pygame.error:
                pass

    def _create_frame_surface(self, size):
        size = (max(1, int(size[0])), max(1, int(size[1])))
        try:
            return pygame.Surface(size).convert()
        except pygame.error:
            return pygame.Surface(size)

    def create_window(self, force_pygame=False):
        previous_window_mode = getattr(self, "window_mode", "unknown")
        flags = pygame.DOUBLEBUF

        if self.fullscreen:
            flags |= pygame.HWSURFACE
            mode = self._fullscreen_mode()
            if mode == "exclusive":
                flags |= pygame.FULLSCREEN
                size = (0, 0)
                self.window_mode = "exclusive"
            elif mode == "desktop":
                flags |= pygame.FULLSCREEN
                size = self._desktop_size()
                self.window_mode = "desktop"
            else:
                flags |= pygame.NOFRAME
                size = self._desktop_size()
                self.window_mode = "borderless"
        else:
            size = (1280, 720)
            self.window_mode = "windowed"
            if previous_window_mode != "windowed":
                try:
                    pygame.display.quit()
                    pygame.display.init()
                except pygame.error:
                    pass

        self.opengl_window_active = False
        use_opengl = (not force_pygame) and self._should_use_opengl_window()
        if use_opengl:
            attempts = [
                (size, flags | pygame.OPENGL, self.window_mode, "primary")
            ]
            if self.fullscreen and self.window_mode in {"desktop", "exclusive"}:
                attempts.append(
                    (
                        self._desktop_size(),
                        pygame.DOUBLEBUF | pygame.NOFRAME | pygame.OPENGL,
                        "borderless",
                        "borderless_retry"
                    )
                )

            last_error = None
            for attempt_size, attempt_flags, attempt_mode, label in attempts:
                try:
                    self._configure_opengl_attributes()
                    display_surface = pygame.display.set_mode(
                        attempt_size,
                        attempt_flags,
                        vsync=0,
                        depth=32
                    )
                    self.display_surface = display_surface
                    self.opengl_window_active = True
                    self.opengl_window_status = (
                        "active"
                        if label == "primary"
                        else f"active:{label}"
                    )
                    self.window_mode = attempt_mode
                    self.screen = self._create_frame_surface(
                        display_surface.get_size()
                    )
                    pygame.display.set_caption("PyOsu")
                    self.WIDTH = self.screen.get_width()
                    self.HEIGHT = self.screen.get_height()
                    return
                except (pygame.error, TypeError) as exc:
                    last_error = exc
                    try:
                        pygame.display.quit()
                        pygame.display.init()
                    except pygame.error:
                        pass

            self.opengl_window_failed = True
            self.opengl_window_status = (
                f"window_error:{type(last_error).__name__}"
                if last_error is not None
                else "window_error:unknown"
            )

        try:
            self.screen = pygame.display.set_mode(
                size,
                flags,
                vsync=0,
                depth=32
            )
        except TypeError:
            self.screen = pygame.display.set_mode(
                size,
                flags
            )
        self.display_surface = self.screen
        pygame.display.set_caption("PyOsu")

        self.WIDTH = self.screen.get_width()

        self.HEIGHT = self.screen.get_height()

    def _attach_backend_to_current_scene(self):
        scene_manager = getattr(self, "scene_manager", None)
        current_scene = getattr(scene_manager, "current_scene", None)
        if current_scene is not None and hasattr(current_scene, "render_backend"):
            current_scene.render_backend = self.render_backend

    def _recreate_render_backend(self):
        self.render_backend = create_render_backend(
            self.screen,
            present_frame_surface=self.opengl_window_active
        )
        self.opengl_backend_status = "pygame"
        if (
            self.opengl_window_active
            and not bool(getattr(self.render_backend, "_enabled", False))
        ):
            self.opengl_window_failed = True
            self.opengl_backend_status = "backend_disabled"
            self.create_window(force_pygame=True)
            self.render_backend = create_render_backend(
                self.screen,
                present_frame_surface=False
            )
        elif self.opengl_window_active:
            self.opengl_backend_status = "active"
        self._attach_backend_to_current_scene()

    def _fallback_to_pygame_window(self):
        if not self.opengl_window_active:
            return
        self.opengl_window_failed = True
        self.opengl_window_status = "runtime_fallback"
        self.opengl_backend_status = "runtime_fallback"
        self.create_window(force_pygame=True)
        self._recreate_render_backend()
        self.display_refresh_rate = self._detect_display_refresh_rate()
        self.FPS = self._resolve_target_fps()
        self.mouse_pos = self._clamp_mouse_pos(self.mouse_pos)
        self.ui_manager = pygame_gui.UIManager(
            (self.WIDTH, self.HEIGHT)
        )
        self._notify_resize()
        self.sync_input_mode(self.mouse_pos)

    # -------------------------
    # TOGGLE FULLSCREEN
    # -------------------------
    def toggle_fullscreen(self):

        self.fullscreen = not self.fullscreen

        self.create_window()
        self._recreate_render_backend()
        self.display_refresh_rate = self._detect_display_refresh_rate()
        self.FPS = self._resolve_target_fps()
        self.mouse_pos = self._clamp_mouse_pos(self.mouse_pos)

        self.ui_manager = pygame_gui.UIManager(
            (self.WIDTH, self.HEIGHT)
        )

        self._notify_resize()
        self.sync_input_mode(self.mouse_pos)

    def _detect_display_refresh_rate(self):
        rate = 0

        getter = getattr(pygame.display, "get_current_refresh_rate", None)
        if callable(getter):
            try:
                rate = int(round(float(getter())))
            except (pygame.error, TypeError, ValueError):
                rate = 0

        if rate > 0:
            return rate

        rates_getter = getattr(pygame.display, "get_desktop_refresh_rates", None)
        if callable(rates_getter):
            try:
                rates = rates_getter()
            except (pygame.error, TypeError, ValueError):
                rates = []
            try:
                flattened = []
                for item in rates:
                    if isinstance(item, (list, tuple)):
                        flattened.extend(item)
                    else:
                        flattened.append(item)
                valid = [
                    int(round(float(item)))
                    for item in flattened
                    if float(item) > 0
                ]
                if valid:
                    return max(valid)
            except (TypeError, ValueError):
                pass

        return 0

    def _resolve_target_fps(self):
        if TARGET_FPS > 0:
            return max(30, int(TARGET_FPS))

        refresh = self.display_refresh_rate or 60
        target = int(round(refresh * AUTO_FPS_MULTIPLIER))
        return max(AUTO_FPS_MIN, min(AUTO_FPS_MAX, target))

    def _sync_render_backend_target(self):
        backend = getattr(self, "render_backend", None)
        if backend is not None:
            setter = getattr(backend, "set_target_surface", None)
            if callable(setter):
                setter(self.screen)
            else:
                backend.target_surface = self.screen
        self._attach_backend_to_current_scene()

    def _notify_resize(self):
        if hasattr(self.scene_manager, "on_resize"):
            self.scene_manager.on_resize()
            return

        current_scene = self.scene_manager.current_scene

        if current_scene:

            if getattr(current_scene, "uses_ui", True):

                if hasattr(current_scene, "destroy"):

                    current_scene.destroy()

                if hasattr(current_scene, "create_ui"):

                    current_scene.create_ui()

            elif hasattr(current_scene, "on_resize"):

                current_scene.on_resize()

    def _sync_display_size(self):
        display_surface = (
            self.display_surface
            if self.opengl_window_active and self.display_surface is not None
            else self.screen
        )
        size = display_surface.get_size()
        if size == (self.WIDTH, self.HEIGHT):
            return

        self.WIDTH, self.HEIGHT = size
        if self.opengl_window_active:
            self.screen = self._create_frame_surface(size)
        self._sync_render_backend_target()
        self.mouse_pos = self._clamp_mouse_pos(self.mouse_pos)
        self.ui_manager = pygame_gui.UIManager(size)
        self._notify_resize()
        self.sync_input_mode(self.mouse_pos)

    def sync_input_mode(self, pos=None):
        if self.tablet_input_enabled or not self.raw_mouse_preferred:
            self.disable_raw_mouse(recenter=False)
            if pos is not None:
                self.mouse_pos = self._clamp_mouse_pos(pos)
            pygame.mouse.get_rel()
            return

        self.enable_raw_mouse(pos if pos is not None else self.mouse_pos)

    def enable_raw_mouse(self, pos=None):
        if pos is None:
            pos = self.mouse_pos

        self.mouse_pos = self._clamp_mouse_pos(pos)
        self.raw_mouse_fallback = False
        if self.tablet_input_enabled or not self.raw_mouse_preferred:
            self.disable_raw_mouse(recenter=False)
            return

        pygame.event.set_grab(True)

        if hasattr(pygame.mouse, "set_relative_mode"):
            try:
                pygame.mouse.set_relative_mode(True)
                self.raw_mouse_enabled = bool(
                    pygame.mouse.get_relative_mode()
                    if hasattr(pygame.mouse, "get_relative_mode")
                    else True
                )
            except pygame.error:
                self.raw_mouse_enabled = bool(pygame.event.get_grab())
                self.raw_mouse_fallback = self.raw_mouse_enabled
        else:
            self.raw_mouse_enabled = bool(pygame.event.get_grab())
            self.raw_mouse_fallback = self.raw_mouse_enabled

        if not self.raw_mouse_enabled and pygame.event.get_grab():
            self.raw_mouse_enabled = True
            self.raw_mouse_fallback = True

        if self.raw_mouse_enabled:
            pygame.event.set_blocked(pygame.MOUSEMOTION)
            self.mouse_motion_blocked = True
        else:
            pygame.event.set_grab(False)

        pygame.mouse.get_rel()

    def sample_mouse_now(self, pump=False):
        if pump:
            try:
                pygame.event.pump()
            except pygame.error:
                pass

        if self.raw_mouse_enabled:
            rel = pygame.mouse.get_rel()
            if rel != (0, 0):
                self._apply_mouse_delta(rel)
            return self.mouse_pos

        if self.tablet_input_enabled or not self.raw_mouse_preferred:
            self.mouse_pos = self._clamp_mouse_pos(pygame.mouse.get_pos())
            pygame.mouse.get_rel()
            return self.mouse_pos

        rel = pygame.mouse.get_rel()
        if rel != (0, 0):
            self._apply_mouse_delta(rel)
        return self.mouse_pos

    def disable_raw_mouse(self, recenter=True):
        pygame.event.set_blocked(pygame.MOUSEMOTION)
        self.mouse_motion_blocked = True

        if hasattr(pygame.mouse, "set_relative_mode"):
            try:
                pygame.mouse.set_relative_mode(False)
            except pygame.error:
                pass

        pygame.event.set_grab(False)
        self.raw_mouse_enabled = False
        self.raw_mouse_fallback = False

        if recenter:
            try:
                pygame.mouse.set_pos(
                    int(self.mouse_pos[0]),
                    int(self.mouse_pos[1])
                )
            except pygame.error:
                pass

    def _clamp_mouse_pos(self, pos):
        return (
            max(0, min(self.WIDTH - 1, float(pos[0]))),
            max(0, min(self.HEIGHT - 1, float(pos[1])))
        )

    def _apply_mouse_delta(self, rel):
        self.mouse_pos = self._clamp_mouse_pos(
            (
                self.mouse_pos[0] + (rel[0] * self.raw_mouse_sensitivity),
                self.mouse_pos[1] + (rel[1] * self.raw_mouse_sensitivity)
            )
        )

    def _normalize_system_pointer_sensitivity(self):
        self.raw_mouse_sensitivity = 1.0
        if self.settings.mouse_sensitivity != 1.0:
            self.settings.mouse_sensitivity = 1.0
            self.settings.save()

    def set_mouse_sensitivity(self, value):
        if not self.raw_mouse_preferred:
            self._normalize_system_pointer_sensitivity()
            return

        self.raw_mouse_sensitivity = clamp_sensitivity(value)
        self.settings.mouse_sensitivity = self.raw_mouse_sensitivity
        self.settings.save()

    def set_cursor_scale(self, value):
        self.cursor_scale = clamp_cursor_scale(value)
        self.settings.cursor_scale = self.cursor_scale
        self.cursor_renderer.set_user_scale(self.cursor_scale)
        self.settings.save()

    def set_hit_key(self, slot, key):
        key = int(key)
        if slot == 1:
            self.settings.hit_key_1 = key
        else:
            self.settings.hit_key_2 = key
        self.hit_keys = (
            int(self.settings.hit_key_1),
            int(self.settings.hit_key_2)
        )
        self.settings.save()

    def set_raw_mouse_enabled(self, enabled):
        self.raw_mouse_preferred = bool(enabled)
        if self.raw_mouse_preferred:
            self.tablet_input_enabled = False
            self.settings.tablet_input_enabled = False
        else:
            self._normalize_system_pointer_sensitivity()
        self.settings.raw_mouse_enabled = self.raw_mouse_preferred
        self.settings.save()
        self.sync_input_mode(self.mouse_pos)

    def set_tablet_input_enabled(self, enabled):
        self.tablet_input_enabled = bool(enabled)
        if self.tablet_input_enabled:
            self.raw_mouse_preferred = False
            self.settings.raw_mouse_enabled = False
            self._normalize_system_pointer_sensitivity()
        self.settings.tablet_input_enabled = self.tablet_input_enabled
        self.settings.save()
        self.sync_input_mode(self.mouse_pos)

    def set_block_mouse_buttons_in_gameplay(self, enabled):
        self.block_mouse_buttons_in_gameplay = bool(enabled)
        self.settings.block_mouse_buttons_in_gameplay = (
            self.block_mouse_buttons_in_gameplay
        )
        self.settings.save()

    def set_gameplay_dim(self, value):
        self.gameplay_dim = clamp_gameplay_dim(value)
        self.settings.gameplay_dim = self.gameplay_dim
        self.settings.save()

    # -------------------------
    # MAIN LOOP
    # -------------------------
    def run(self):
        while self.running:
            current_scene = self.scene_manager.current_scene
            low_latency_pacing = (
                self.raw_mouse_enabled
                or getattr(current_scene, "prefer_low_latency_pacing", False)
            )
            if USE_BUSY_FRAME_PACER or low_latency_pacing:
                elapsed_ms = self.clock.tick_busy_loop(self.FPS)
            else:
                elapsed_ms = self.clock.tick(self.FPS)
            self.dt = min(MAX_FRAME_DT, elapsed_ms / 1000.0)

            profiler_enabled = self.profiler.enabled
            if profiler_enabled:
                self.profiler.add("pacer", elapsed_ms)
            if profiler_enabled:
                self.profiler.begin_frame()

            # Process events first to get fresh input
            if profiler_enabled:
                self.profiler.start("events")
            self.events()
            if profiler_enabled:
                self.profiler.end("events")

            if profiler_enabled:
                self.profiler.start("update")
            self.update(self.dt)
            if profiler_enabled:
                self.profiler.end("update")

            # Sample mouse right before rendering for freshest position
            self.sample_mouse_now(pump=False)
            if profiler_enabled:
                self.profiler.start("render")
            self.render()
            if profiler_enabled:
                self.profiler.end("render")

            if profiler_enabled:
                current_scene = self.scene_manager.current_scene
                scene_name = (
                    current_scene.__class__.__name__
                    if current_scene is not None
                    else "None"
                )
                self.profiler.end_frame(scene_name, self.clock.get_fps())

        pygame.quit()

    # -------------------------
    # EVENTS
    # -------------------------
    def events(self):
        current_scene = self.scene_manager.current_scene
        uses_ui = getattr(current_scene, "uses_ui", True)
        wants_motion_events = (
            (uses_ui or self.tablet_input_enabled)
            and not self.raw_mouse_enabled
        )
        if wants_motion_events and self.mouse_motion_blocked:
            pygame.event.set_allowed(pygame.MOUSEMOTION)
            self.mouse_motion_blocked = False
        elif not wants_motion_events and not self.mouse_motion_blocked:
            pygame.event.set_blocked(pygame.MOUSEMOTION)
            self.mouse_motion_blocked = True

        self.sample_mouse_now(pump=True)

        for event in pygame.event.get():
            if (
                self.raw_mouse_enabled
                and event.type in (
                    pygame.KEYDOWN,
                    pygame.KEYUP,
                    pygame.MOUSEBUTTONDOWN,
                    pygame.MOUSEBUTTONUP
                )
            ):
                self.sample_mouse_now()

            if not self.raw_mouse_enabled and event.type == pygame.KEYDOWN:
                self.sample_mouse_now()

            if self.tablet_input_enabled and hasattr(event, "pos"):
                self.mouse_pos = event.pos

            event = self._event_with_current_mouse_pos(event)

            # -------------------------
            # QUIT
            # -------------------------
            if event.type == pygame.QUIT:

                self.running = False

            if event.type == pygame.DROPFILE:
                self.import_osz_file(getattr(event, "file", ""))
                continue

            # -------------------------
            # KEYDOWN
            # -------------------------
            if event.type == pygame.KEYDOWN:

                # ALT + F4
                if (
                    event.key == pygame.K_F4
                    and
                    pygame.key.get_mods()
                    & pygame.KMOD_ALT
                ):

                    self.running = False

                # F11 fullscreen
                if event.key == pygame.K_F11:

                    self.toggle_fullscreen()

                if event.key == pygame.K_F3:

                    self.profiler.toggle()

            # -------------------------
            # SCENE EVENTS
            # -------------------------
            self.scene_manager.handle_event(
                event
            )

            # -------------------------
            # UI EVENTS
            # -------------------------
            if uses_ui:
                self.ui_manager.process_events(
                    event
                )

    def _event_with_current_mouse_pos(self, event):
        if event.type not in (
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION
        ):
            return event

        try:
            event_dict = event.dict
        except AttributeError:
            return event

        pos = (
            int(round(self.mouse_pos[0])),
            int(round(self.mouse_pos[1]))
        )
        if event_dict is not None:
            event_dict["pos"] = pos
        try:
            event.pos = pos
        except (AttributeError, TypeError):
            pass
        return event

    def import_osz_file(self, path):
        if not path or not str(path).lower().endswith(".osz"):
            return None

        result = self.osz_importer.import_file(path)
        self.last_import_result = result
        if result.changed:
            self.beatmaps = self.beatmap_loader.load_songs()
            current_scene = self.scene_manager.current_scene
            refresh = getattr(current_scene, "refresh_beatmaps", None)
            if callable(refresh):
                refresh()
        return result

    # -------------------------
    # UPDATE
    # -------------------------
    def update(self, dt):
        current_scene = self.scene_manager.current_scene
        scene_before_update = current_scene

        profiler_enabled = self.profiler.enabled
        if getattr(current_scene, "uses_ui", True):
            if profiler_enabled:
                self.profiler.start("ui_update")
            self.ui_manager.update(dt)
            if profiler_enabled:
                self.profiler.end("ui_update")

        if profiler_enabled:
            self.profiler.start("scene_manager_update")
        self.scene_manager.update(dt)
        if profiler_enabled:
            self.profiler.end("scene_manager_update")

        current_scene = self.scene_manager.current_scene
        scene_changed = (
            current_scene is not scene_before_update
            or bool(getattr(self.scene_manager, "factory_transition_completed", False))
            or current_scene is not self._last_cursor_scene
        )
        suppress_cursor_trail = bool(
            getattr(self.scene_manager, "is_cursor_trail_suppressed", lambda: False)()
        )

        if not getattr(current_scene, "draws_own_cursor", False):
            if profiler_enabled:
                self.profiler.start("cursor_update")
            if scene_changed or suppress_cursor_trail:
                self.cursor_renderer.reset_trail(self.mouse_pos)
            else:
                self.cursor_renderer.update(dt, self.mouse_pos)
            self._last_cursor_scene = current_scene
            if profiler_enabled:
                self.profiler.end("cursor_update")

    # -------------------------
    # RENDER
    # -------------------------
    def render(self):
        current_scene = self.scene_manager.current_scene
        if self.fullscreen:
            self._sync_display_size()

        profiler_enabled = self.profiler.enabled
        clear_for_transition = bool(
            getattr(
                self.scene_manager,
                "should_clear_screen_for_transition",
                lambda: False
            )()
        )
        backend = getattr(self, "render_backend", None)
        if backend is not None:
            begin_frame = getattr(backend, "begin_frame", None)
            if callable(begin_frame):
                begin_frame()
            warm_gpu = getattr(backend, "warm_gpu_surface_cache", None)
            if callable(warm_gpu):
                warm_gpu(max_items=2)

        if clear_for_transition:
            self.screen.fill((0, 0, 0))

        if profiler_enabled:
            self.profiler.start("scene_render")
        self.scene_manager.render(
            self.screen
        )
        if backend is not None and profiler_enabled:
            self.profiler.set_metric("backend", getattr(backend, "name", "pygame"))
            self.profiler.set_metric("gpu", int(bool(getattr(backend, "gpu_available", False))))
            self.profiler.set_metric("batch", getattr(backend, "last_flush_count", 0))
            self.profiler.set_metric("surfaces", getattr(backend, "last_unique_surface_count", 0))
            self.profiler.set_metric("culled", getattr(backend, "last_culled_count", 0))
            self.profiler.set_metric("atlas_pages", getattr(backend, "last_atlas_pages", 0))
            self.profiler.set_metric("atlas_sprites", getattr(backend, "last_atlas_sprites", 0))
            self.profiler.set_metric("atlas_cmds", getattr(backend, "last_atlas_command_count", 0))
            self.profiler.set_metric("atlas_groups", getattr(backend, "last_atlas_group_count", 0))
            self.profiler.set_metric("atlas_runs", getattr(backend, "last_atlas_run_count", 0))
            self.profiler.set_metric("batchable", getattr(backend, "last_batchable_command_count", 0))
            self.profiler.set_metric("gpu_sprites", getattr(backend, "last_gpu_sprite_count", 0))
            self.profiler.set_metric("gpu_flushes", getattr(backend, "last_gpu_flush_count", 0))
            self.profiler.set_metric("gpu_uploads", getattr(backend, "last_gpu_texture_upload_count", 0))
            self.profiler.set_metric("gpu_fallbacks", getattr(backend, "last_gpu_fallback_count", 0))
            self.profiler.set_metric("gpu_prepare", getattr(backend, "last_gpu_prepare_count", 0))
            self.profiler.set_metric("gpu_prepq", getattr(backend, "last_gpu_prepare_pending", 0))
            self.profiler.set_metric("gpu_layers", getattr(backend, "last_present_layer_count", 0))
            self.profiler.set_metric("gpu_sprite_path", int(bool(getattr(backend, "_gpu_sprite_enabled", False))))
            self.profiler.set_metric("opengl_window", int(bool(self.opengl_window_active)))
            self.profiler.set_metric(
                "opengl_status",
                getattr(self, "opengl_window_status", "unknown")
            )
            self.profiler.set_metric(
                "opengl_backend",
                getattr(self, "opengl_backend_status", "unknown")
            )
            self.profiler.set_metric("hz", self.display_refresh_rate or 0)
            self.profiler.set_metric("target", self.FPS)
            self.profiler.set_metric("mode", self.window_mode)
        if profiler_enabled:
            self.profiler.end("scene_render")

        if getattr(current_scene, "uses_ui", True):
            if profiler_enabled:
                self.profiler.start("ui_draw")
            self.ui_manager.draw_ui(
                self.screen
            )
            if profiler_enabled:
                self.profiler.end("ui_draw")

        if profiler_enabled:
            current_scene = self.scene_manager.current_scene
            scene_name = (
                current_scene.__class__.__name__
                if current_scene is not None
                else "None"
            )
            self.profiler.start("debug_render")
            self.profiler.draw_overlay(
                self.screen,
                scene_name,
                self.clock.get_fps()
            )
            self.profiler.end("debug_render")

        if not getattr(current_scene, "draws_own_cursor", False):
            if profiler_enabled:
                self.profiler.start("cursor_draw")
            loading_transition = bool(
                getattr(self.scene_manager, "is_cursor_trail_suppressed", lambda: False)()
            )
            post_present_cursor = bool(
                self.opengl_window_active
                and backend is not None
                and bool(getattr(backend, "present_frame_surface", False))
                and getattr(backend, "_post_present_renderer", None) is not None
            )
            self.cursor_renderer.draw(
                self.screen,
                self.mouse_pos,
                draw_trail=not loading_transition,
                backend=backend,
                post_present=post_present_cursor
            )
            if profiler_enabled:
                self.profiler.end("cursor_draw")

        if backend is not None:
            if profiler_enabled:
                self.profiler.start("backend_present")
            backend.present()
            if profiler_enabled:
                self.profiler.end("backend_present")
                self.profiler.set_metric(
                    "gpu_post",
                    getattr(backend, "last_post_present_count", 0)
                )
                self.profiler.set_metric(
                    "gpu_layers",
                    getattr(backend, "last_present_layer_count", 0)
                )
                self.profiler.set_metric(
                    "gpu_sprites",
                    getattr(backend, "last_gpu_sprite_count", 0)
                )
                self.profiler.set_metric(
                    "gpu_flushes",
                    getattr(backend, "last_gpu_flush_count", 0)
                )
                self.profiler.set_metric(
                    "gpu_uploads",
                    getattr(backend, "last_gpu_texture_upload_count", 0)
                )
                self.profiler.set_metric(
                    "gpu_prepare",
                    getattr(backend, "last_gpu_prepare_count", 0)
                )
                self.profiler.set_metric(
                    "gpu_prepq",
                    getattr(backend, "last_gpu_prepare_pending", 0)
                )
            if (
                self.opengl_window_active
                and not bool(getattr(backend, "_enabled", True))
            ):
                self._fallback_to_pygame_window()

        if profiler_enabled:
            self.profiler.start("flip")
        pygame.display.flip()
        if profiler_enabled:
            self.profiler.end("flip")
