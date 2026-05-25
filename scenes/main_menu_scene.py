import pygame
import pygame_gui

from scenes.base_scene import BaseScene
from scenes.song_select_scene import SongSelectScene

class MainMenuScene(BaseScene):

    def __init__(self, game):

        super().__init__(game)

        self.font = pygame.font.SysFont("arial", 60)

        self.play_button = None
        self.settings_button = None
        self.exit_button = None

        self.create_ui()

    # -------------------------
    # UI
    # -------------------------
    def create_ui(self):

        # Limpar botões antigos
        self.destroy()

        # Dimensões dos botões
        button_width = 200
        button_height = 60
        button_spacing = 20

        # Calcular posição X centralizada
        button_x = (self.game.WIDTH - button_width) // 2

        # Calcular posição Y centralizada
        total_buttons_height = (button_height * 3) + (button_spacing * 2)
        button_y = (self.game.HEIGHT - total_buttons_height) // 2

        self.play_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((button_x, button_y), (button_width, button_height)),
            text="PLAY",
            manager=self.game.ui_manager
        )

        self.settings_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((button_x, button_y + button_height + button_spacing), (button_width, button_height)),
            text="SETTINGS",
            manager=self.game.ui_manager
        )

        self.exit_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((button_x, button_y + (button_height + button_spacing) * 2), (button_width, button_height)),
            text="EXIT",
            manager=self.game.ui_manager
        )

    def handle_event(self, event):

        if event.type == pygame_gui.UI_BUTTON_PRESSED:

            if event.ui_element == self.play_button:

                self.game.scene_manager.push_scene(
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

        # Centralizar título horizontalmente
        title_x = (self.game.WIDTH - title.get_width()) // 2
        title_y = 60

        screen.blit(title, (title_x, title_y))
    def destroy(self):

        if self.play_button:
            self.play_button.kill()
            self.play_button = None

        if self.settings_button:
            self.settings_button.kill()
            self.settings_button = None

        if self.exit_button:
            self.exit_button.kill()
            self.exit_button = None