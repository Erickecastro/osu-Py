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

            if (not note["active"]) and self.current_time >= note["time"]:

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
        scale = min(
            1280 / playfield_width,
            720 / playfield_height
        )

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

            pygame.draw.circle(
                screen,
                (0, 150, 255),
                (scaled_x, scaled_y),
                30
            )