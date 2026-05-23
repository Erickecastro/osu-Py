import pygame
import pygame_gui

from scenes.base_scene import BaseScene
from scenes.gameplay_scene import GameplayScene


class DifficultySelectScene(BaseScene):

    def __init__(self, game, beatmap):

        super().__init__(game)

        self.beatmap = beatmap

        self.buttons = []

        self.create_ui()

    # -------------------------
    # UI
    # -------------------------
    def create_ui(self):

        # limpa referências antigas
        self.buttons.clear()

        y = 150

        for difficulty in self.beatmap["difficulties"]:

            version_name = difficulty["metadata"].get(
                "Version",
                "Unknown"
            )

            od = difficulty["difficulty"].get(
                "OD",
                0
            )

            ar = difficulty["difficulty"].get(
                "AR",
                0
            )

            cs = difficulty["difficulty"].get(
                "CS",
                0
            )

            btn = pygame_gui.elements.UIButton(

                relative_rect=pygame.Rect(
                    (390, y),
                    (500, 50)
                ),

                text=(
                    f"{version_name}  |  "
                    f"CS:{cs}  "
                    f"AR:{ar}  "
                    f"OD:{od}"
                ),

                manager=self.game.ui_manager
            )

            self.buttons.append(
                (btn, difficulty)
            )

            y += 70

    # -------------------------
    # EVENTS
    # -------------------------
    def handle_event(self, event):

        # voltar
        if event.type == pygame.KEYDOWN:

            if event.key == pygame.K_ESCAPE:

                self.game.scene_manager.pop_scene()

        # clique nos botões
        if event.type == pygame_gui.UI_BUTTON_PRESSED:

            for btn, difficulty in self.buttons:

                if event.ui_element == btn:

                    self.game.scene_manager.push_scene(

                        GameplayScene(
                            self.game,
                            difficulty
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

        screen.fill((25, 25, 40))

    # -------------------------
    # DESTROY
    # -------------------------
    def destroy(self):

        for btn, _ in self.buttons:

            if btn.alive():

                btn.kill()

        self.buttons.clear()