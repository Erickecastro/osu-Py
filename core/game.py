import os

import pygame
import pygame_gui

from core.beatmap_loader import BeatmapLoader
from core.scene_manager import SceneManager
from scenes.main_menu_scene import MainMenuScene

class Game:

    FPS = 1000

    def __init__(self):

        # -------------------------
        # PYGAME
        # -------------------------
        os.environ.setdefault("SDL_MOUSE_RELATIVE_MODE_WARP", "0")
        os.environ.setdefault("SDL_MOUSE_RELATIVE_SYSTEM_SCALE", "0")
        os.environ.setdefault("SDL_MOUSE_RELATIVE_MODE_CENTER", "0")

        pygame.mixer.pre_init(
            frequency=44100,
            size=-16,
            channels=2,
            buffer=256
        )
        pygame.init()

        pygame.mixer.init()

        # -------------------------
        # DISPLAY
        # -------------------------
        self.fullscreen = True

        self.create_window()

        pygame.display.set_caption("PyOsu")

        # -------------------------
        # CLOCK
        # -------------------------
        self.clock = pygame.time.Clock()
        self.mouse_pos = pygame.mouse.get_pos()
        self.raw_mouse_enabled = False
        self.raw_mouse_sensitivity = 1.0

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

        self.ui_manager = pygame_gui.UIManager(
            (self.WIDTH, self.HEIGHT)
        )

        current_scene = (
            self.scene_manager.current_scene
        )

        if current_scene:

            if hasattr(current_scene, "destroy"):

                current_scene.destroy()

            if hasattr(current_scene, "create_ui"):

                current_scene.create_ui()

    def enable_raw_mouse(self, pos=None):
        if pos is None:
            pos = self.mouse_pos

        self.mouse_pos = self._clamp_mouse_pos(pos)
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

        pygame.mouse.get_rel()

    def disable_raw_mouse(self):
        pygame.event.set_allowed(pygame.MOUSEMOTION)

        if hasattr(pygame.mouse, "set_relative_mode"):
            try:
                pygame.mouse.set_relative_mode(False)
            except pygame.error:
                pass

        pygame.event.set_grab(False)
        self.raw_mouse_enabled = False

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

    # -------------------------
    # MAIN LOOP
    # -------------------------
    def run(self):

        while self.running:

            dt = self.clock.tick_busy_loop(
                self.FPS
            ) / 1000

            self.events()

            self.update(dt)

            self.render()

        pygame.quit()

    # -------------------------
    # EVENTS
    # -------------------------
    def events(self):
        current_scene = self.scene_manager.current_scene
        uses_ui = getattr(current_scene, "uses_ui", True)

        if self.raw_mouse_enabled:
            self._apply_raw_mouse_delta(
                pygame.mouse.get_rel()
            )

        for event in pygame.event.get():
            if not self.raw_mouse_enabled and hasattr(event, "pos"):
                self.mouse_pos = event.pos

            # -------------------------
            # QUIT
            # -------------------------
            if event.type == pygame.QUIT:

                self.running = False

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

        if not self.raw_mouse_enabled:
            self.mouse_pos = pygame.mouse.get_pos()

    # -------------------------
    # UPDATE
    # -------------------------
    def update(self, dt):
        current_scene = self.scene_manager.current_scene

        if getattr(current_scene, "uses_ui", True):
            self.ui_manager.update(dt)

        self.scene_manager.update(dt)

    # -------------------------
    # RENDER
    # -------------------------
    def render(self):
        current_scene = self.scene_manager.current_scene
        if self.raw_mouse_enabled:
            self._apply_raw_mouse_delta(
                pygame.mouse.get_rel()
            )
        else:
            self.mouse_pos = pygame.mouse.get_pos()

        self.scene_manager.render(
            self.screen
        )

        if getattr(current_scene, "uses_ui", True):
            self.ui_manager.draw_ui(
                self.screen
            )

        pygame.display.flip()
