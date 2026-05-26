import pygame
import os
import copy

from scenes.base_scene import BaseScene


class GameplayScene(BaseScene):

    def __init__(self, game, beatmap):

        super().__init__(game)

        self.game = game
        self.beatmap = beatmap

        # -------------------------
        # CURSOR
        # -------------------------
        pygame.mouse.set_visible(False)

        # -------------------------
        # FONT
        # -------------------------
        self.font = pygame.font.SysFont(
            "arial",
            32
        )

        # -------------------------
        # AUDIO
        # -------------------------
        self.music_started = False
        self.music_path = None

        self.start_time = None
        self.current_time = 0

        # -------------------------
        # NOTES
        # -------------------------
        self.notes = copy.deepcopy(
            beatmap["notes"]
        )

        for note in self.notes:

            note["active"] = False

        self.active_notes = []

        # -------------------------
        # DIFFICULTY
        # -------------------------
        self.cs = self.beatmap[
            "difficulty"
        ]["CS"]

        self.ar = self.beatmap[
            "difficulty"
        ]["AR"]

        # -------------------------
        # CIRCLE SIZE
        # -------------------------
        self.circle_radius = (
            54.4 - (4.48 * self.cs)
        )

        # -------------------------
        # APPROACH RATE
        # -------------------------
        if self.ar < 5:

            self.approach_time = (
                1800 - (120 * self.ar)
            )

        else:

            self.approach_time = (
                1200 - (
                    150 * (self.ar - 5)
                )
            )

        # -------------------------
        # PLAYFIELD
        # -------------------------
        self.playfield_width = 512
        self.playfield_height = 384

        self.playfield_screen_height = (
            self.game.HEIGHT * 0.78
        )

        self.scale = (
            self.playfield_screen_height
            / self.playfield_height
        )

        # centralização
        self.offset_x = (
            self.game.WIDTH
            - (
                self.playfield_width
                * self.scale
            )
        ) / 2

        self.offset_y = (
            self.game.HEIGHT
            - (
                self.playfield_height
                * self.scale
            )
        ) / 2

        # -------------------------
        # NOTE SIZE
        # -------------------------
        self.scaled_radius = int(
            self.circle_radius
            * self.scale
            * 0.80
        )

        if self.scaled_radius < 40:

            self.scaled_radius = 40

        # margem de segurança
        self.safe_margin = (
            self.scaled_radius + 16
        )

        self.usable_width = (
            (self.playfield_width * self.scale)
            - (self.safe_margin * 2)
        )

        self.usable_height = (
            (self.playfield_height * self.scale)
            - (self.safe_margin * 2)
        )

        self.find_audio()

    # -------------------------
    # AUDIO
    # -------------------------
    def find_audio(self):

        if not os.path.exists(
            self.beatmap["path"]
        ):

            return

        for file in os.listdir(
            self.beatmap["path"]
        ):

            if (
                file.endswith(".mp3")
                or
                file.endswith(".ogg")
            ):

                self.music_path = os.path.join(
                    self.beatmap["path"],
                    file
                )

                break

    def start_music(self):

        if (
            self.music_path
            and
            not pygame.mixer.music.get_busy()
        ):

            try:

                pygame.mixer.music.load(
                    self.music_path
                )

                pygame.mixer.music.play()

                self.start_time = (
                    pygame.time.get_ticks()
                )

            except Exception as e:

                print(
                    "Erro ao tocar música:"
                )

                print(e)

    # -------------------------
    # EVENTS
    # -------------------------
    def handle_event(self, event):

        if event.type == pygame.KEYDOWN:

            if event.key == pygame.K_ESCAPE:

                pygame.mixer.music.stop()

                self.game.scene_manager.pop_scene()

    # -------------------------
    # UPDATE
    # -------------------------
    def update(self, dt):

        if not self.music_started:

            self.start_music()

            self.music_started = True

        if self.start_time is not None:

            self.current_time = (
                pygame.time.get_ticks()
                - self.start_time
            )

        # ativa notas
        for note in self.notes:

            if (
                not note["active"]
                and
                self.current_time >= (
                    note["time"]
                    - self.approach_time
                )
            ):

                note["active"] = True

                self.active_notes.append(
                    note
                )

        # remove expiradas
        self.active_notes = [

            note

            for note in self.active_notes

            if (
                self.current_time
                <=
                note["time"] + 1000
            )
        ]

    # -------------------------
    # SCALE POSITION
    # -------------------------
    def scale_position(self, x, y):

        scaled_x = int(
            self.offset_x
            + self.safe_margin
            + (
                (x / 512)
                * self.usable_width
            )
        )

        scaled_y = int(
            self.offset_y
            + self.safe_margin
            + (
                (y / 384)
                * self.usable_height
            )
        )

        return scaled_x, scaled_y

    # -------------------------
    # RENDER
    # -------------------------
    def render(self, screen):

        screen.fill((10, 10, 10))

        # -------------------------
        # TEXT
        # -------------------------
        title = self.beatmap[
            "metadata"
        ].get(
            "Title",
            self.beatmap["name"]
        )

        version = self.beatmap[
            "metadata"
        ].get(
            "Version",
            "Unknown"
        )

        title_text = self.font.render(
            f"{title} [{version}]",
            True,
            (255, 255, 255)
        )

        screen.blit(
            title_text,
            (20, 20)
        )

        time_text = self.font.render(
            f"{self.current_time} ms",
            True,
            (0, 255, 0)
        )

        screen.blit(
            time_text,
            (20, 60)
        )

        # -------------------------
        # PLAYFIELD BORDER
        # -------------------------
        pygame.draw.rect(

            screen,

            (40, 40, 40),

            (
                self.offset_x,
                self.offset_y,
                self.playfield_width
                * self.scale,
                self.playfield_height
                * self.scale
            ),

            3
        )

        # -------------------------
        # DRAW NOTES
        # -------------------------
        for note in self.active_notes:

            scaled_x, scaled_y = (
                self.scale_position(
                    note["x"],
                    note["y"]
                )
            )

            # -------------------------
            # APPROACH CIRCLE
            # -------------------------
            time_left = (
                note["time"]
                - self.current_time
            )

            progress = max(
                0,
                min(
                    1,
                    time_left
                    / self.approach_time
                )
            )

            approach_radius = int(
                self.scaled_radius
                + (
                    progress
                    * self.scaled_radius
                    * 2.5
                )
            )

            pygame.draw.circle(

                screen,

                (255, 255, 255),

                (scaled_x, scaled_y),

                approach_radius,

                2
            )

            # -------------------------
            # HIT CIRCLE
            # -------------------------
            if note["type"] == "circle":

                pygame.draw.circle(

                    screen,

                    (0, 150, 255),

                    (scaled_x, scaled_y),

                    self.scaled_radius
                )

                pygame.draw.circle(

                    screen,

                    (255, 255, 255),

                    (scaled_x, scaled_y),

                    self.scaled_radius,

                    3
                )

            # -------------------------
            # SLIDER
            # -------------------------
            elif note["type"] == "slider":

                slider_points = []

                all_points = [

                    {
                        "x": note["x"],
                        "y": note["y"]
                    }

                ] + note.get("curve_points", [])

                # valida e converte pontos
                for point in all_points:

                    try:

                        point_x, point_y = (
                            self.scale_position(
                                point["x"],
                                point["y"]
                            )
                        )

                        # garante inteiros
                        point_x = int(point_x)
                        point_y = int(point_y)
                        
                        # Proteção contra pontos inválidos
                        # Limita a área visível com margem
                        screen_width = self.game.screen.get_width()
                        screen_height = self.game.screen.get_height()
                        
                        # Aceita pontos um pouco fora da tela (para renderização de linhas)
                        MARGIN = 500
                        if (-MARGIN <= point_x <= screen_width + MARGIN and
                            -MARGIN <= point_y <= screen_height + MARGIN):
                            slider_points.append(
                                (point_x, point_y)
                            )

                    except (ValueError, TypeError, KeyError):

                        continue

                # desenha corpo do slider (apenas se há pontos válidos)
                if len(slider_points) > 1:

                    # largura da linha (aumentada para melhor visibilidade)
                    border_width = max(
                        3,
                        int(self.scaled_radius * 1.8)
                    )

                    body_width = max(
                        2,
                        int(self.scaled_radius * 1.2)
                    )

                    # desenha border (cinza escuro)
                    for i in range(
                        len(slider_points) - 1
                    ):

                        pygame.draw.line(

                            screen,

                            (40, 40, 40),

                            slider_points[i],

                            slider_points[i + 1],

                            border_width
                        )

                    # desenha body (rosa)
                    for i in range(
                        len(slider_points) - 1
                    ):

                        pygame.draw.line(

                            screen,

                            (255, 105, 180),

                            slider_points[i],

                            slider_points[i + 1],

                            body_width
                        )

                # desenha head (início)
                if len(slider_points) > 0:

                    head_pos = slider_points[0]

                    pygame.draw.circle(

                        screen,

                        (0, 150, 255),

                        head_pos,

                        self.scaled_radius
                    )

                    pygame.draw.circle(

                        screen,

                        (255, 255, 255),

                        head_pos,

                        self.scaled_radius,

                        3
                    )

                # desenha tail (fim)
                if len(slider_points) > 0:

                    tail_pos = slider_points[-1]

                    pygame.draw.circle(

                        screen,

                        (0, 150, 255),

                        tail_pos,

                        self.scaled_radius
                    )

                    pygame.draw.circle(

                        screen,

                        (255, 255, 255),

                        tail_pos,

                        self.scaled_radius,

                        3
                    )

    # -------------------------
    # DESTROY
    # -------------------------
    def destroy(self):

        pygame.mixer.music.stop()

        pygame.mouse.set_visible(True)