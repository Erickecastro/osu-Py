import pygame
import os
import copy
from bisect import bisect_right

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

        # Aproximação do comportamento do osu! para visibilidade:
        # fade-in durante o approach e fade-out logo após o hit.
        self.hit_fade_out_time = 350  # ms

        self.usable_width = (
            (self.playfield_width * self.scale)
            - (self.safe_margin * 2)
        )

        self.usable_height = (
            (self.playfield_height * self.scale)
            - (self.safe_margin * 2)
        )

        self.find_audio()

        self.slider_multiplier = (
            self.beatmap["difficulty"].get(
                "SliderMultiplier",
                1.4
            )
        )
        self.timing_points = (
            self.beatmap.get("timing_points", [])
        )

        # Pré-computa o intervalo de visibilidade de cada objeto.
        # Isso permite desenhar com alpha/escala sem depender de "sumir instantâneo".
        for note in self.notes:
            note["start_time"] = note["time"] - self.approach_time

            if note["type"] == "slider":
                repeat_count = note.get("repeat_count", 1)
                pixel_length = float(note.get("slider_distance", 0.0))
                span_duration = self._slider_span_duration(
                    note["time"],
                    pixel_length
                )
                note["span_duration"] = span_duration
                note["slider_total_duration"] = (
                    span_duration * repeat_count
                )

                fade_out_end = (
                    note["time"]
                    + note["slider_total_duration"]
                    + self.hit_fade_out_time
                )
                note["end_time"] = fade_out_end
            else:
                note["end_time"] = (
                    note["time"] + self.hit_fade_out_time
                )

    def _clamp01(self, v):
        if v <= 0:
            return 0.0
        if v >= 1:
            return 1.0
        return v

    def _note_alpha(self, note):
        """Alpha suave: fade-in no approach e fade-out no fim do objeto."""
        start = note.get("start_time", note["time"] - self.approach_time)
        hit_time = note["time"]

        # Fade-in até o hit.
        fade_in_len = max(1, hit_time - start)
        alpha_in = (self.current_time - start) / fade_in_len
        alpha_in = self._clamp01(alpha_in)

        # Fade-out depende do tipo.
        if note["type"] == "slider":
            fade_out_start = (
                hit_time + note.get("slider_total_duration", 0.0)
            )
        else:
            fade_out_start = hit_time

        fade_out_end = fade_out_start + self.hit_fade_out_time
        if self.current_time <= fade_out_start:
            alpha_out = 1.0
        elif self.current_time >= fade_out_end:
            alpha_out = 0.0
        else:
            alpha_out = (fade_out_end - self.current_time) / self.hit_fade_out_time

        a = alpha_in * self._clamp01(alpha_out)
        return int(255 * a)

    def _effective_beat_length_at(self, time_ms):
        """
        Retorna a beat length efetiva no `time_ms`,
        considerando TimingPoints base (uninherited) e speed changes (inherited).
        """
        if not self.timing_points:
            return 500.0

        base_tp = None
        inherited_tp = None

        for tp in self.timing_points:
            if tp["time"] > time_ms:
                break
            if tp.get("uninherited", 1) == 1:
                base_tp = tp
            else:
                inherited_tp = tp

        if base_tp is None:
            base_tp = self.timing_points[0]

        base_beat_len = float(base_tp.get("ms_per_beat", 500.0))

        # inherited point: ms_per_beat vem negativo e representa speed multiplier.
        if inherited_tp is None:
            return base_beat_len

        mpb = float(inherited_tp.get("ms_per_beat", 0.0))
        if mpb >= 0:
            return base_beat_len

        sv_mult = -100.0 / mpb if mpb != 0 else 1.0
        if sv_mult <= 0:
            sv_mult = 1.0

        return base_beat_len / sv_mult

    def _slider_span_duration(self, slider_start_time_ms, pixel_length):
        """
        Duração (ms) de 1 span do slider (uma ida), usando fórmula aproximada do osu!.
        total = span_duration * repeat_count
        """
        if pixel_length <= 0:
            return 0.0

        effective_beat_len = self._effective_beat_length_at(slider_start_time_ms)
        denom = max(1e-6, 100.0 * float(self.slider_multiplier))
        beats = pixel_length / denom
        return effective_beat_len * beats

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
                    note.get(
                        "start_time",
                        note["time"] - self.approach_time
                    )
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
                note.get(
                    "end_time",
                    note["time"] + self.hit_fade_out_time
                )
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

    def _slider_point_at_distance(self, points, distance):
        """
        Retorna a posição (x, y) ao longo do path do slider,
        usando distância acumulada em `points`.
        """
        if not points:
            return (0, 0)
        if len(points) == 1:
            return points[0]

        cumulative = [0.0]
        total = 0.0

        for i in range(len(points) - 1):
            dx = points[i + 1][0] - points[i][0]
            dy = points[i + 1][1] - points[i][1]
            seg = (dx * dx + dy * dy) ** 0.5
            total += seg
            cumulative.append(total)

        if total <= 0:
            return points[-1]

        d = max(0.0, min(total, float(distance)))
        idx = bisect_right(cumulative, d) - 1
        idx = max(0, min(idx, len(points) - 2))

        seg_start = cumulative[idx]
        seg_end = cumulative[idx + 1]
        seg_len = max(1e-9, seg_end - seg_start)
        t = (d - seg_start) / seg_len
        t = max(0.0, min(1.0, t))

        x = points[idx][0] + (points[idx + 1][0] - points[idx][0]) * t
        y = points[idx][1] + (points[idx + 1][1] - points[idx][1]) * t

        return (int(round(x)), int(round(y)))

    def _draw_slider(self, screen, slider_points, alpha=255, draw_markers=True):

        if len(slider_points) < 2:
            return

        if alpha <= 0:
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

        a = max(0, min(255, int(alpha)))

        outline_color = (30, 30, 30, int(220 * (a / 255)))
        body_color = (255, 105, 180, a)

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

        if draw_markers:
            head_pos = slider_points[0]
            tail_pos = slider_points[-1]

            pygame.draw.circle(
                screen,
                (0, 150, 255, a),
                head_pos,
                self.scaled_radius
            )
            pygame.draw.circle(
                screen,
                (255, 255, 255, a),
                head_pos,
                self.scaled_radius,
                3
            )
            pygame.draw.circle(
                screen,
                (0, 150, 255, a),
                tail_pos,
                self.scaled_radius
            )
            pygame.draw.circle(
                screen,
                (255, 255, 255, a),
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

        # Camada transparente para permitir alpha real (fade in/out suave).
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)

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

            alpha = self._note_alpha(note)
            if alpha <= 0:
                continue

            # Pop suave conforme chega no hit.
            start = note.get("start_time", note["time"] - self.approach_time)
            fade_in_len = max(1, note["time"] - start)
            alpha_in = self._clamp01(
                (self.current_time - start) / fade_in_len
            )
            hit_scale = 0.90 + 0.10 * alpha_in
            scaled_hit_radius = max(1, int(self.scaled_radius * hit_scale))

            approach_radius = int(
                self.scaled_radius
                + (
                    progress
                    * self.scaled_radius
                    * 2.5
                )
            )

            pygame.draw.circle(

                overlay,

                (255, 255, 255, int(alpha * progress)),

                (scaled_x, scaled_y),

                approach_radius,

                2
            )

            if note["type"] == "circle":

                pygame.draw.circle(

                    overlay,

                    (0, 150, 255, alpha),

                    (scaled_x, scaled_y),

                    scaled_hit_radius
                )

                pygame.draw.circle(

                    overlay,

                    (255, 255, 255, alpha),

                    (scaled_x, scaled_y),

                    scaled_hit_radius,

                    3
                )

            elif note["type"] == "slider":

                slider_points = self._build_slider_points(note)

                self._draw_slider(
                    overlay,
                    slider_points
                    ,
                    alpha=alpha,
                    draw_markers=False
                )

                # Slider ball (move along the slider path).
                time_since_hit = (
                    self.current_time
                    - note["time"]
                )
                span_duration = float(
                    note.get("span_duration", 0.0)
                )
                repeat_count = int(
                    note.get("repeat_count", 1)
                )
                slider_total_duration = float(
                    note.get(
                        "slider_total_duration",
                        span_duration * repeat_count
                    )
                )

                if time_since_hit >= 0 and slider_total_duration > 0:
                    # Total length along the path (one span).
                    total_length = 0.0
                    for i in range(len(slider_points) - 1):
                        dx = slider_points[i + 1][0] - slider_points[i][0]
                        dy = slider_points[i + 1][1] - slider_points[i][1]
                        total_length += (dx * dx + dy * dy) ** 0.5

                    total_length = max(0.0, total_length)
                    within = min(slider_total_duration, time_since_hit)

                    if span_duration <= 0:
                        ball_dist = total_length
                    else:
                        if within >= slider_total_duration:
                            repeat_idx = repeat_count - 1
                            t = 1.0
                        else:
                            repeat_idx = int(within / span_duration)
                            t = (within - repeat_idx * span_duration) / span_duration

                        forward = (repeat_idx % 2 == 0)
                        ball_dist = total_length * (
                            t if forward else (1.0 - t)
                        )

                    ball_pos = self._slider_point_at_distance(
                        slider_points,
                        ball_dist
                    )

                    pygame.draw.circle(
                        overlay,
                        (0, 150, 255, alpha),
                        ball_pos,
                        scaled_hit_radius
                    )
                    pygame.draw.circle(
                        overlay,
                        (255, 255, 255, alpha),
                        ball_pos,
                        scaled_hit_radius,
                        3
                    )

        screen.blit(overlay, (0, 0))

    def destroy(self):

        pygame.mixer.music.stop()

        pygame.mouse.set_visible(True)