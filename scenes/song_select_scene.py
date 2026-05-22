import pygame
import pygame_gui

from scenes.base_scene import BaseScene
from scenes.gameplay_scene import GameplayScene


class SongSelectScene(BaseScene):

    def __init__(self, game):

        super().__init__(game)

        self.buttons = []
        self.selected_map = None

        self.create_ui()

    def create_ui(self):

        y = 100

        beatmaps = self.game.beatmaps

        for beatmap in beatmaps:

            btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect((450, y), (400, 50)),
                text=beatmap["name"],
                manager=self.game.ui_manager
            )

            self.buttons.append((btn, beatmap))

            y += 70

    def handle_event(self, event):

        if event.type == pygame_gui.UI_BUTTON_PRESSED:

            for btn, beatmap in self.buttons:

                if event.ui_element == btn:

                    self.selected_map = beatmap

                    self.game.scene_manager.set_scene(
                        GameplayScene(self.game)
                    )

    def update(self, dt):
        pass

    def render(self, screen):

        screen.fill((40, 40, 60))

    def destroy(self):

        for btn, _ in self.buttons:
            btn.kill()