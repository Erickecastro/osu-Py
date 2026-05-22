import pygame

from scenes.base_scene import BaseScene
from scenes.gameplay_scene import GameplayScene


class SongSelectScene(BaseScene):

    def __init__(self, game):

        super().__init__(game)

        self.font = pygame.font.SysFont(
            "arial",
            40
        )

    def handle_event(self, event):

        if event.type == pygame.KEYDOWN:

            if event.key == pygame.K_SPACE:

                self.game.scene_manager.set_scene(
                    GameplayScene(self.game)
                )

    def update(self, dt):

        pass

    def render(self, screen):

        screen.fill((40, 40, 60))

        text = self.font.render(
            "Song Select - SPACE para jogar",
            True,
            (255, 255, 255)
        )

        screen.blit(text, (250, 300))