import pygame
import pygame_gui

from scenes.base_scene import BaseScene
from scenes.difficulty_select_scene import (
    DifficultySelectScene
)


class SongSelectScene(BaseScene):

    def __init__(self, game):

        super().__init__(game)

        self.buttons = []

        self.create_ui()

    # -------------------------
    # UI
    # -------------------------
    def create_ui(self):

        # evita duplicação
        self.destroy()

        # centralização automática
        button_width = 500
        button_height = 55

        x = (
            self.game.WIDTH - button_width
        ) // 2

        y = 120

        beatmaps = self.game.beatmaps

        for beatmap in beatmaps:

            btn = pygame_gui.elements.UIButton(

                relative_rect=pygame.Rect(
                    (x, y),
                    (button_width, button_height)
                ),

                text=beatmap.get("display_name", beatmap["name"]),

                manager=self.game.ui_manager
            )

            self.buttons.append(
                (btn, beatmap)
            )

            y += 70

    # -------------------------
    # EVENTS
    # -------------------------
    def handle_event(self, event):

        # voltar para menu principal
        if event.type == pygame.KEYDOWN:

            if event.key == pygame.K_ESCAPE:

                self.game.scene_manager.pop_scene()

        # clique nos botões
        if event.type == pygame_gui.UI_BUTTON_PRESSED:

            for btn, beatmap in self.buttons:

                if event.ui_element == btn:

                    self.game.scene_manager.push_scene(

                        DifficultySelectScene(
                            self.game,
                            beatmap
                        )
                    )

    # -------------------------
    # UPDATE
    # -------------------------
    def update(self, dt):

        pass

    # -------------------------
    # RENDER
    # -------------------------
    def render(self, screen):

        screen.fill((40, 40, 60))

        # título
        font = pygame.font.SysFont(
            "arial",
            48
        )

        text = font.render(
            "Select Song",
            True,
            (255, 255, 255)
        )

        screen.blit(
            text,
            (
                self.game.WIDTH // 2
                - text.get_width() // 2,
                40
            )
        )

    # -------------------------
    # DESTROY
    # -------------------------
    def destroy(self):

        for btn, _ in self.buttons:

            if btn.alive():

                btn.kill()

        self.buttons.clear()
