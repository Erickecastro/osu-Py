import pygame
import os

from scenes.base_scene import BaseScene


class GameplayScene(BaseScene):

    def __init__(self, game, beatmap):

        super().__init__(game)

        self.beatmap = beatmap
        
        self.font = pygame.font.SysFont("arial", 40)

        self.music_started = False
        self.music_path = None

        self.start_time = None
        self.current_time = 0

        self.notes = beatmap["notes"]

        self.active_notes = []

        self.cs = self.beatmap["difficulty"]["CS"]
        self.ar = self.beatmap["difficulty"]["AR"]

        self.circle_radius = int(
            54.4 - (4.48 * self.cs)
        )

        if self.ar < 5:

            self.approach_time = 1800 - (120 * self.ar)

        else:

            self.approach_time = 1200 - (150 * (self.ar - 5))

        self.find_audio()

    # -------------------------
    # AUDIO
    # -------------------------
    def find_audio(self):

        for file in os.listdir(self.beatmap["path"]):

            if file.endswith(".mp3") or file.endswith(".ogg"):

                self.music_path = os.path.join(
                    self.beatmap["path"],
                    file
                )
                break

    def start_music(self):

        if self.music_path:

            pygame.mixer.music.load(self.music_path)
            pygame.mixer.music.play()

            self.start_time = pygame.time.get_ticks()

    # -------------------------
    # EVENTS
    # -------------------------
    def handle_event(self, event):
        pass

    # -------------------------
    # UPDATE
    # -------------------------
    def update(self, dt):

        if not self.music_started:

            self.start_music()
            self.music_started = True

        if self.start_time is not None:

            self.current_time = pygame.time.get_ticks() - self.start_time

        for note in self.notes:

            if (
                (not note["active"])
                and
                self.current_time >= (
                    note["time"] - self.approach_time
                )
            ):

                note["active"] = True
                self.active_notes.append(note)

        for note in self.active_notes[:]:

            if self.current_time > note["time"] + 1000:  

                self.active_notes.remove(note)

    # -------------------------
    # RENDER
    # -------------------------
    def render(self, screen):

        screen.fill((10, 10, 10))

        # nome da música
        text = self.font.render(
            f"Playing: {self.beatmap['name']}",
            True,
            (255, 255, 255)
        )

        screen.blit(text, (400, 320))

        # tempo atual da música
        time_text = self.font.render(
            f"Time: {self.current_time} ms",
            True,
            (0, 255, 0)
        )

        screen.blit(time_text, (400, 380))

        # playfield original do osu!
        playfield_width = 512
        playfield_height = 384

        # calcula escala proporcional
        scale = 720 / playfield_height

        # centraliza o playfield
        offset_x = (
            1280 - (playfield_width * scale)
        ) / 2

        offset_y = (
            720 - (playfield_height * scale)
        ) / 2

        # desenha notas
        for note in self.active_notes:

            scaled_x = int(
                offset_x + (note["x"] * scale)
            )

            scaled_y = int(
                offset_y + (note["y"] * scale)
            )

            # HIT CIRCLE
            if note["type"] == "circle":

                time_left = note["time"] - self.current_time

                progress = max(
                    0,
                    min(
                        1,
                        time_left / self.approach_time
                    )
                )

                approach_radius = int(
                    self.circle_radius +
                    (progress * self.circle_radius * 3)
                )

                pygame.draw.circle(
                    screen,
                    (255, 255, 255),
                    (scaled_x, scaled_y),
                    approach_radius,
                    3
                )

                pygame.draw.circle(
                    screen,
                    (0, 150, 255),
                    (scaled_x, scaled_y),
                    self.circle_radius
                )

            # SLIDER
            elif note["type"] == "slider":

                time_left = note["time"] - self.current_time

                progress = max(
                    0,
                    min(
                        1,
                        time_left / self.approach_time
                    )
                )

                approach_radius = int(
                    self.circle_radius +
                    (progress * self.circle_radius * 3)
                )

                pygame.draw.circle(
                    screen,
                    (255, 255, 255),
                    (scaled_x, scaled_y),
                    approach_radius,
                    3
                )

                # desenha linhas do slider
                previous_x = scaled_x
                previous_y = scaled_y

                for point in note["curve_points"]:

                    point_x = int(
                        offset_x + (point["x"] * scale)
                    )

                    point_y = int(
                        offset_y + (point["y"] * scale)
                    )

                    pygame.draw.line(
                        screen,
                        (255, 100, 255),
                        (previous_x, previous_y),
                        (point_x, point_y),
                        self.circle_radius * 2
                    )

                    previous_x = point_x
                    previous_y = point_y

                # cabeça do slider
                pygame.draw.circle(
                    screen,
                    (255, 100, 255),
                    (scaled_x, scaled_y),
                    self.circle_radius
                )

                pygame.draw.circle(
                    screen,
                    (255, 255, 255),
                    (scaled_x, scaled_y),
                    self.circle_radius,
                    4
                )