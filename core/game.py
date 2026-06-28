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
        self.raw_mouse_sensitivity = clamp_sensitivity(
            self.settings.mouse_sensitivity or RAW_MOUSE_SENSITIVITY
        )
        self.cursor_scale = clamp_cursor_scale(self.settings.cursor_scale)
        self.raw_mouse_preferred = bool(self.settings.raw_mouse_enabled)
        self.tablet_input_enabled = bool(self.settings.tablet_input_enabled)
        self.block_mouse_buttons_in_gameplay = bool(
            self.settings.block_mouse_buttons_in_gameplay
        )
        self.hit_keys = (
            int(self.settings.hit_key_1),
            int(self.settings.hit_key_2)
        )
        self.gameplay_dim = clamp_gameplay_dim(self.settings.gameplay_dim)
        self.cursor_renderer = CursorRenderer(user_scale=self.cursor_scale)
        pygame.mouse.set_visible(False)
        pygame.event.set_blocked(pygame.MOUSEMOTION)
        self.mouse_motion_blocked = True

        self.current_menu_music_path = None
        self.current_menu_music_title = None
        self.current_menu_music_timing_points = []
        self.current_menu_music_paused = False

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
    def create_window(self):
        flags = pygame.DOUBLEBUF

        if self.fullscreen:

            flags |= pygame.FULLSCREEN
            size = (0, 0)

        else:

            size = (1280, 720)

        try:
            self.screen = pygame.display.set_mode(
                size,
                flags,
                vsync=0
            )
        except TypeError:
            self.screen = pygame.display.set_mode(
                size,
                flags
            )

        self.WIDTH = self.screen.get_width()

        self.HEIGHT = self.screen.get_height()

    # -------------------------
    # TOGGLE FULLSCREEN
    # -------------------------
    def toggle_fullscreen(self):

        self.fullscreen = not self.fullscreen

        self.create_window()
        self.display_refresh_rate = self._detect_display_refresh_rate()
        self.FPS = self._resolve_target_fps()
        self.mouse_pos = self._clamp_mouse_pos(self.mouse_pos)

        self.ui_manager = pygame_gui.UIManager(
            (self.WIDTH, self.HEIGHT)
        )

        self._notify_resize()

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
        size = self.screen.get_size()
        if size == (self.WIDTH, self.HEIGHT):
            return

        self.WIDTH, self.HEIGHT = size
        self.mouse_pos = self._clamp_mouse_pos(self.mouse_pos)
        self.ui_manager = pygame_gui.UIManager(size)
        self._notify_resize()

    def enable_raw_mouse(self, pos=None):
        if pos is None:
            pos = self.mouse_pos

        self.mouse_pos = self._clamp_mouse_pos(pos)
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
                self.raw_mouse_enabled = False
                pygame.event.set_grab(False)
        else:
            self.raw_mouse_enabled = False
            pygame.event.set_grab(False)

        if self.raw_mouse_enabled:
            pygame.event.set_blocked(pygame.MOUSEMOTION)
            self.mouse_motion_blocked = True

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
                self._apply_raw_mouse_delta(rel)
            return self.mouse_pos

        self.mouse_pos = pygame.mouse.get_pos()
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

    def _apply_raw_mouse_delta(self, rel):
        if not self.raw_mouse_enabled:
            return

        self.mouse_pos = self._clamp_mouse_pos(
            (
                self.mouse_pos[0] + (rel[0] * self.raw_mouse_sensitivity),
                self.mouse_pos[1] + (rel[1] * self.raw_mouse_sensitivity)
            )
        )

    def set_mouse_sensitivity(self, value):
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
        self.settings.raw_mouse_enabled = self.raw_mouse_preferred
        self.settings.save()
        if not self.raw_mouse_preferred or self.tablet_input_enabled:
            self.disable_raw_mouse(recenter=False)

    def set_tablet_input_enabled(self, enabled):
        self.tablet_input_enabled = bool(enabled)
        self.settings.tablet_input_enabled = self.tablet_input_enabled
        self.settings.save()
        if self.tablet_input_enabled:
            self.disable_raw_mouse(recenter=False)

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
                self.profiler.begin_frame()

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

            if not self.raw_mouse_enabled and hasattr(event, "pos"):
                self.mouse_pos = event.pos

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
        self.sample_mouse_now()
        current_scene = self.scene_manager.current_scene

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
        if not getattr(current_scene, "draws_own_cursor", False):
            if profiler_enabled:
                self.profiler.start("cursor_update")
            self.cursor_renderer.update(dt, self.mouse_pos)
            if profiler_enabled:
                self.profiler.end("cursor_update")

    # -------------------------
    # RENDER
    # -------------------------
    def render(self):
        self.sample_mouse_now()
        current_scene = self.scene_manager.current_scene
        if self.fullscreen:
            self._sync_display_size()

        profiler_enabled = self.profiler.enabled
        if profiler_enabled:
            self.profiler.start("scene_render")
        self.scene_manager.render(
            self.screen
        )
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
            self.profiler.draw_overlay(
                self.screen,
                scene_name,
                self.clock.get_fps()
            )

        if not getattr(current_scene, "draws_own_cursor", False):
            self.sample_mouse_now()
            if profiler_enabled:
                self.profiler.start("cursor_draw")
            self.cursor_renderer.draw(self.screen, self.mouse_pos)
            if profiler_enabled:
                self.profiler.end("cursor_draw")

        if profiler_enabled:
            self.profiler.start("flip")
        pygame.display.flip()
        if profiler_enabled:
            self.profiler.end("flip")
