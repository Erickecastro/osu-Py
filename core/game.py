import pygame
import pygame_gui

from core.beatmap_loader import BeatmapLoader
from core.scene_manager import SceneManager

from scenes.main_menu_scene import MainMenuScene


class Game:

    FPS = 144

    def __init__(self):

        # -------------------------
        # PYGAME
        # -------------------------
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

        if self.fullscreen:

            self.screen = pygame.display.set_mode(
                (0, 0),
                pygame.FULLSCREEN
            )

        else:

            self.screen = pygame.display.set_mode(
                (1280, 720)
            )

        self.WIDTH = self.screen.get_width()

        self.HEIGHT = self.screen.get_height()

    # -------------------------
    # TOGGLE FULLSCREEN
    # -------------------------
    def toggle_fullscreen(self):

        self.fullscreen = not self.fullscreen

        self.create_window()

        # recria UI manager
        self.ui_manager = pygame_gui.UIManager(
            (self.WIDTH, self.HEIGHT)
        )

        # recria UI da cena atual
        current_scene = (
            self.scene_manager.current_scene
        )

        if current_scene:

            if hasattr(current_scene, "destroy"):

                current_scene.destroy()

            if hasattr(current_scene, "create_ui"):

                current_scene.create_ui()

    # -------------------------
    # MAIN LOOP
    # -------------------------
    def run(self):

        while self.running:

            dt = self.clock.tick(
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

        for event in pygame.event.get():

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
            self.ui_manager.process_events(
                event
            )

    # -------------------------
    # UPDATE
    # -------------------------
    def update(self, dt):

        self.ui_manager.update(dt)

        self.scene_manager.update(dt)

    # -------------------------
    # RENDER
    # -------------------------
    def render(self):

        self.scene_manager.render(
            self.screen
        )

        self.ui_manager.draw_ui(
            self.screen
        )

        pygame.display.flip()