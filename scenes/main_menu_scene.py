import pygame
import pygame_gui

from scenes.base_scene import BaseScene
from scenes.song_select_scene import SongSelectScene


class MainMenuScene(BaseScene):

    def __init__(self, game):

        super().__init__(game)

        self.font = pygame.font.SysFont("arial", 60)

        self.play_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((540, 250), (200, 60)),
            text="PLAY",
            manager=self.game.ui_manager
        )

        self.settings_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((540, 330), (200, 60)),
            text="SETTINGS",
            manager=self.game.ui_manager
        )

        self.exit_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((540, 410), (200, 60)),
            text="EXIT",
            manager=self.game.ui_manager
        )

    def handle_event(self, event):

        if event.type == pygame_gui.UI_BUTTON_PRESSED:

            if event.ui_element == self.play_button:

                self.game.scene_manager.set_scene(
                    SongSelectScene(self.game)
                )

            if event.ui_element == self.settings_button:
                print("Settings ainda não implementado")

            if event.ui_element == self.exit_button:
                self.game.running = False

    def update(self, dt):
        pass

    def render(self, screen):

        screen.fill((30, 30, 30))

        title = self.font.render(
            "PyOsu",
            True,
            (255, 255, 255)
        )

        screen.blit(title, (520, 120))
    def destroy(self):

        self.play_button.kill()
        self.settings_button.kill()
        self.exit_button.kill()