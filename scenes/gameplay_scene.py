import pygame
import os
import copy

from scenes.base_scene import BaseScene


class GameplayScene(BaseScene):

    MAX_SLIDER_SURFACE_SIZE = 4096
    MAX_SLIDER_POINTS = 4000

    def __init__(self, game, beatmap):

        super().__init__(game)

        self.game = game
        self.beatmap = beatmap

        pygame.mouse.set_visible(False)

        self.font = pygame.font.SysFont(
            "arial",
            32
        )

        self.music_started = False
        self.music_path = None

        self.start_time = None
        self.current_time = 0

        self.notes = copy.deepcopy(
            beatmap["notes"]
        )

        for note in self.notes:
            note["active"] = False

        self.active_notes = []

        self.cs = self.beatmap[
            "difficulty"
        ]["CS"]

        self.ar = self.beatmap[
            "difficulty"
        ]["AR"]

        self.circle_radius = (
            54.4 - (4.48 * self.cs)
        )

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

        self.playfield_width = 512
        self.playfield_height = 384

        self.playfield_screen_height = (
            self.game.HEIGHT * 0.78
        )

        self.scale = (
            self.playfield_screen_height
            / self.playfield_height
        )

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

        self.scaled_radius = int(
            self.circle_radius
            * self.scale
            * 0.80
        )

        if self.scaled_radius < 40:
            self.scaled_radius = 40

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

                print(e)

    def handle_event(self, event):

        if event.type == pygame.KEYDOWN:

            if event.key == pygame.K_ESCAPE:

                pygame.mixer.music.stop()

                self.game.scene_manager.pop_scene()

    def update(self, dt):

        if not self.music_started:

            self.start_music()

            self.music_started = True

        if self.start_time is not None:

            self.current_time = (
                pygame.time.get_ticks()
                - self.start_time
            )

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

        self.active_notes = [

            note

            for note in self.active_notes

            if (
                self.current_time
                <=
                note["time"] + 1000
            )
        ]

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

    def _build_slider_points(self, note):

        all_points = [
            {
                "x": note["x"],
                "y": note["y"]
            }
        ] + note.get("curve_points", [])

        scaled_points = []

        for point in all_points:

            try:

                scaled_x, scaled_y = (
                    self.scale_position(
                        point["x"],
                        point["y"]
                    )
                )

                scaled_points.append(
                    (
                        int(round(scaled_x)),
                        int(round(scaled_y))
                    )
                )

            except:
                continue

        filtered_points = []

        for point in scaled_points:

            if (
                not filtered_points
                or
                point != filtered_points[-1]
            ):

                filtered_points.append(point)

        if len(filtered_points) > self.MAX_SLIDER_POINTS:
            filtered_points = filtered_points[
                ::2
            ]

        return filtered_points

    def _draw_slider(self, screen, slider_points):

        if len(slider_points) < 2:
            return

        min_x = min(p[0] for p in slider_points)
        max_x = max(p[0] for p in slider_points)

        min_y = min(p[1] for p in slider_points)
        max_y = max(p[1] for p in slider_points)

        padding = int(
            self.scaled_radius * 2
        )

        width = int(
            (max_x - min_x)
            + padding * 2
        )

        height = int(
            (max_y - min_y)
            + padding * 2
        )

        if width <= 0 or height <= 0:
            return

        width = min(
            width,
            self.MAX_SLIDER_SURFACE_SIZE
        )

        height = min(
            height,
            self.MAX_SLIDER_SURFACE_SIZE
        )

        try:

            slider_surface = pygame.Surface(
                (width, height),
                pygame.SRCALPHA
            )

        except:
            return

        local_points = []

        for point in slider_points:

            local_x = int(
                point[0]
                - min_x
                + padding
            )

            local_y = int(
                point[1]
                - min_y
                + padding
            )

            if (
                -100 <= local_x <= width + 100
                and
                -100 <= local_y <= height + 100
            ):

                local_points.append(
                    (local_x, local_y)
                )

        outline_radius = int(
            self.scaled_radius * 1.18
        )

        body_radius = int(
            self.scaled_radius * 0.88
        )

        outline_color = (
            30,
            30,
            30,
            220
        )

        body_color = (
            255,
            105,
            180,
            255
        )

        step = 1

        if len(local_points) > 2000:
            step = 2

        for point in local_points[::step]:

            pygame.draw.circle(
                slider_surface,
                outline_color,
                point,
                outline_radius
            )

        for point in local_points[::step]:

            pygame.draw.circle(
                slider_surface,
                body_color,
                point,
                body_radius
            )

        screen.blit(
            slider_surface,
            (
                min_x - padding,
                min_y - padding
            )
        )

        head_pos = slider_points[0]
        tail_pos = slider_points[-1]

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

    def render(self, screen):

        screen.fill((10, 10, 10))

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

        for note in self.active_notes:

            scaled_x, scaled_y = (
                self.scale_position(
                    note["x"],
                    note["y"]
                )
            )

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

            elif note["type"] == "slider":

                slider_points = self._build_slider_points(note)

                self._draw_slider(
                    screen,
                    slider_points
                )

    def destroy(self):

        pygame.mixer.music.stop()

        pygame.mouse.set_visible(True)