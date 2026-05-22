import pygame
import pygame_gui
from core.beatmap_loader import BeatmapLoader

from core.scene_manager import SceneManager
from scenes.main_menu_scene import MainMenuScene


class Game:

    WIDTH = 1280
    HEIGHT = 720
    FPS = 144

    def __init__(self):

        pygame.init()

        from core.beatmap_loader import BeatmapLoader
        
        self.beatmap_loader = BeatmapLoader()
        self.beatmaps = self.beatmap_loader.load_songs()
        self.screen = pygame.display.set_mode(
            (self.WIDTH, self.HEIGHT)
        )

        pygame.display.set_caption("PyOsu")

        self.clock = pygame.time.Clock()

        self.running = True

        self.ui_manager = pygame_gui.UIManager(
            (self.WIDTH, self.HEIGHT)
        )

        self.beatmap_loader = BeatmapLoader()
        self.beatmaps = self.beatmap_loader.load_songs()
        self.scene_manager = SceneManager()

        self.scene_manager.set_scene(
            MainMenuScene(self)
        )

    def run(self):

        while self.running:

            dt = self.clock.tick(self.FPS) / 1000

            self.events()

            self.update(dt)

            self.render()

        pygame.quit()

    def events(self):

        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                self.running = False

            self.ui_manager.process_events(event)

            self.scene_manager.handle_event(event)

    def update(self, dt):

        self.ui_manager.update(dt)

        self.scene_manager.update(dt)

    def render(self):

        self.scene_manager.render(self.screen)

        self.ui_manager.draw_ui(self.screen)

        pygame.display.flip()