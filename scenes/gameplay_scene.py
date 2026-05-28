import pygame
import os
import copy
from bisect import bisect_right

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

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

        combo_colors = (
            self.beatmap.get("combo_colors")
            or self.beatmap["difficulty"].get("combo_colors")
            or [
                (233, 182, 29),
                (89, 80, 203),
                (66, 198, 221),
                (224, 73, 73)
            ]
        )

        if not combo_colors:
            combo_colors = [
                (233, 182, 29),
                (89, 80, 203),
                (66, 198, 221),
                (224, 73, 73)
            ]

        self.active_notes = []
        self.circle_surface_cache = {}
        self.slider_surface_cache = {}

        current_combo_color = 0
        current_combo_count = 0

        for note_index, note in enumerate(self.notes):
            note["active"] = False
            note["hit_index"] = note_index + 1

            if note.get("new_combo") or current_combo_count == 0:
                if current_combo_count != 0:
                    offset = note.get("combo_offset", 0)
                    current_combo_color = (
                        current_combo_color + offset + 1
                    ) % len(combo_colors)
                current_combo_count = 1
            else:
                current_combo_count += 1

            note["combo_index"] = current_combo_count
            note["combo_color"] = combo_colors[
                current_combo_color
            ]

        self.cs = self.beatmap[
            "difficulty"
        ]["CS"]

        self.ar = self.beatmap[
            "difficulty"
        ]["AR"]

        self.od = self.beatmap[
            "difficulty"
        ].get(
            "OD",
            5
        )

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

        self.slider_head_radius = int(
            self.scaled_radius
        )

        self.slider_path_radius = int(
            self.scaled_radius * 1.22
        )

        self.safe_margin = (
            max(
                self.slider_head_radius,
                self.slider_path_radius
            ) + 16
        )

        # Aproximação do comportamento do osu! para visibilidade:
        # fade-in durante o approach e fade-out logo após o hit.
        self.hit_fade_out_time = 350  # ms
        self.miss_fade_out_time = 90  # ms
        self.miss_pop_duration = 112  # ms
        self.hit_number_fade_out_time = 140  # ms
        self.hit_explosion_duration = 300  # ms

        self.usable_width = (
            (self.playfield_width * self.scale)
            - (self.safe_margin * 2)
        )

        self.usable_height = (
            (self.playfield_height * self.scale)
            - (self.safe_margin * 2)
        )

        self.object_scale = min(
            self.usable_width / self.playfield_width,
            self.usable_height / self.playfield_height
        )
        self.object_offset_x = (
            self.offset_x
            + self.safe_margin
            + (
                self.usable_width
                - (self.playfield_width * self.object_scale)
            ) / 2
        )
        self.object_offset_y = (
            self.offset_y
            + self.safe_margin
            + (
                self.usable_height
                - (self.playfield_height * self.object_scale)
            ) / 2
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

        self.hit_window_300 = max(20, 80 - (6 * self.od))
        self.hit_window_100 = max(20, 140 - (8 * self.od))
        self.hit_window_50 = max(20, 200 - (10 * self.od))

        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.hit_counts = {
            300: 0,
            100: 0,
            50: 0,
            0: 0
        }
        self.judged_objects = 0
        self.judgable_objects = len(self.notes)

        # Pré-computa o intervalo de visibilidade de cada objeto.
        # Isso permite desenhar com alpha/escala sem depender de "sumir instantâneo".
        for render_index, note in enumerate(self.notes):
            note["render_index"] = render_index
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

        self._precache_slider_surfaces()

        self.circle_number_font = pygame.font.SysFont(
            "arial",
            32,
            bold=True
        )

        self.cursor_history = []
        self.cursor_pos = pygame.mouse.get_pos()
        self.last_cursor_pos = self.cursor_pos
        self.cursor_trail_emit_timer = 0.0
        self.cursor_tail_duration = 0.285  # seconds
        self.cursor_tail_emit_interval = 0.012  # seconds
        self.cursor_tail_min_distance = 2.0
        self.cursor_tail_max_points = 8
        self.cursor_image = self._load_cursor_asset(
            "cursor.png",
            0.92
        )
        self.cursor_trail_image = self._load_cursor_asset(
            "cursortrail.png",
            1.16
        )
        self.circle_number_font = pygame.font.SysFont(
            "arial",
            28,
            bold=True
        )
        
        self.miss_indicators = []
        self.miss_indicator_delay = 25  # ms before the X appears
        self.miss_indicator_duration = 520  # ms X stays visible

    def _accuracy(self):
        total_hits = sum(self.hit_counts.values())
        if total_hits <= 0:
            return 100.0

        weighted = (
            (self.hit_counts[300] * 300)
            + (self.hit_counts[100] * 100)
            + (self.hit_counts[50] * 50)
        )

        return (weighted / (total_hits * 300)) * 100.0

    def _add_hit_result(self, note, result):
        note["judged"] = True
        note["active"] = True
        note["hit_result"] = result
        note["hit_time"] = self.current_time
        self.judged_objects += 1
        self.hit_counts[result] += 1

        if note["type"] == "slider":
            note["head_hit"] = result > 0
            note["head_hit_result"] = result
            note["head_hit_time"] = self.current_time

        if result == 0:
            miss_fade_end = self.current_time + self.miss_fade_out_time
            miss_pop_end = self.current_time + self.miss_pop_duration
            self.miss_indicators.append({
                "pos": self.scale_position(
                    note["x"],
                    note["y"]
                ),
                "show_time": miss_fade_end + self.miss_indicator_delay,
                "start_time": self.current_time
            })
            note["fade_out_start"] = self.current_time
            note["fade_out_duration"] = self.miss_fade_out_time
            note["miss_pop_start"] = self.current_time
            if note["type"] == "slider":
                slider_end = (
                    note["time"]
                    + note.get("slider_total_duration", 0.0)
                )
                note["end_time"] = max(
                    miss_pop_end,
                    slider_end + self.hit_fade_out_time
                )
            else:
                note["end_time"] = miss_pop_end
            self.combo = 0
            return

        if note["type"] == "circle":
            note["fade_out_start"] = self.current_time
            note["end_time"] = self.current_time + self.hit_fade_out_time

        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)

        combo_bonus = max(0, self.combo - 1) * result // 25
        self.score += result + combo_bonus

    def _hit_result_for_delta(self, delta):
        delta = abs(delta)
        if delta <= self.hit_window_300:
            return 300
        if delta <= self.hit_window_100:
            return 100
        if delta <= self.hit_window_50:
            return 50
        return None

    def _try_hit_at(self, pos):
        best_note = None
        best_result = None
        best_delta = None

        for note in self.active_notes:
            if note.get("judged"):
                continue

            if note["type"] == "circle":
                delta = self.current_time - note["time"]
                result = self._hit_result_for_delta(delta)
                if result is None:
                    continue

                scaled_x, scaled_y = self.scale_position(
                    note["x"],
                    note["y"]
                )
                dx = pos[0] - scaled_x
                dy = pos[1] - scaled_y
                distance = (dx * dx + dy * dy) ** 0.5

                if distance > self.scaled_radius:
                    continue

            elif note["type"] == "slider":
                if note.get("head_hit"):
                    continue

                delta = self.current_time - note["time"]
                result = self._hit_result_for_delta(delta)
                if result is None:
                    continue

                scaled_x, scaled_y = self.scale_position(
                    note["x"],
                    note["y"]
                )
                dx = pos[0] - scaled_x
                dy = pos[1] - scaled_y
                distance = (dx * dx + dy * dy) ** 0.5

                if distance > self.scaled_radius:
                    continue

            else:
                continue

            abs_delta = abs(delta)
            if best_delta is None or abs_delta < best_delta:
                best_note = note
                best_result = result
                best_delta = abs_delta

        if best_note is None:
            return False

        self._add_hit_result(best_note, best_result)
        return True

    def _clamp01(self, v):
        if v <= 0:
            return 0.0
        if v >= 1:
            return 1.0
        return v

    def _ease_out_cubic(self, v):
        v = self._clamp01(v)
        return 1.0 - ((1.0 - v) ** 3)

    def _fade_in_progress(self, note):
        start = note.get("start_time", note["time"] - self.approach_time)
        hit_time = note["time"]
        approach_len = max(1, hit_time - start)
        fade_in_len = max(120, min(260, approach_len * 0.28))

        return self._ease_out_cubic(
            (self.current_time - start) / fade_in_len
        )

    def _slider_reveal_progress(self, note):
        start = note.get("start_time", note["time"] - self.approach_time)
        hit_time = note["time"]
        approach_len = max(1, hit_time - start)
        reveal_len = max(180, min(420, approach_len * 0.38))

        return self._ease_out_cubic(
            (self.current_time - start) / reveal_len
        )

    def _note_alpha(self, note):
        """Alpha suave: fade-in no approach e fade-out no fim do objeto."""
        hit_time = note["time"]

        # Fade-in até o hit.
        alpha_in = self._fade_in_progress(note)

        if note["type"] == "slider":
            fade_out_start = (
                hit_time + note.get("slider_total_duration", 0.0)
            )
            fade_out_duration = self.hit_fade_out_time
        else:
            fade_out_start = note.get("fade_out_start")
            if fade_out_start is None and note.get("hit_result") is None:
                fade_out_start = self.current_time + 1
                fade_out_duration = self.hit_fade_out_time
            else:
                fade_out_start = (
                    fade_out_start
                    if fade_out_start is not None
                    else hit_time
                )
                fade_out_duration = note.get(
                    "fade_out_duration",
                    self.hit_fade_out_time
                )

        fade_out_duration = max(1, fade_out_duration)
        fade_out_end = fade_out_start + fade_out_duration
        if self.current_time <= fade_out_start:
            alpha_out = 1.0
        elif self.current_time >= fade_out_end:
            alpha_out = 0.0
        else:
            alpha_out = (fade_out_end - self.current_time) / fade_out_duration

        a = alpha_in * self._clamp01(alpha_out)
        return int(255 * a)

    def _slider_ball_alpha(self, note):
        time_since_hit = self.current_time - note["time"]
        if time_since_hit < 0:
            return 0

        slider_total_duration = float(
            note.get("slider_total_duration", 0.0)
        )
        if slider_total_duration <= 0:
            return 0

        slider_end = note["time"] + slider_total_duration
        if self.current_time <= slider_end:
            return 255

        fade_progress = (
            self.current_time - slider_end
        ) / max(1, self.hit_fade_out_time)
        return int(255 * (1.0 - self._clamp01(fade_progress)))

    def _combo_number_alpha(self, note, base_alpha):
        base_alpha = max(0, min(255, int(base_alpha)))

        if note["type"] == "slider":
            hit_result = note.get("head_hit_result")
            hit_time = note.get("head_hit_time")
        else:
            hit_result = note.get("hit_result")
            hit_time = note.get("hit_time")

        if hit_result is None or hit_time is None:
            return base_alpha

        elapsed = self.current_time - hit_time
        fade_duration = (
            self.miss_pop_duration
            if hit_result == 0
            else self.hit_number_fade_out_time
        )
        progress = self._clamp01(
            elapsed / max(1, fade_duration)
        )
        return int(base_alpha * (1.0 - progress))

    def _miss_pop_alpha(self, note):
        pop_start = note.get("miss_pop_start")
        if pop_start is None:
            return 0

        elapsed = self.current_time - pop_start
        progress = self._clamp01(
            elapsed / max(1, self.miss_pop_duration)
        )
        eased = progress * progress * progress * (
            progress * (progress * 6.0 - 15.0) + 10.0
        )
        return int(255 * (1.0 - eased))

    def _aa_circle_surface(
        self,
        radius,
        fill_color=None,
        outline_color=None,
        outline_width=0
    ):
        radius = max(1, int(round(radius)))
        outline_width = max(0, int(round(outline_width)))

        fill_key = None
        if fill_color is not None:
            fill_key = tuple(fill_color[:3])

        outline_key = None
        if outline_color is not None and outline_width > 0:
            outline_key = tuple(outline_color[:3])

        key = (radius, fill_key, outline_key, outline_width)
        cached = self.circle_surface_cache.get(key)
        if cached is not None:
            return cached

        aa_scale = 3
        padding = max(4, outline_width + 2)
        size = (radius + padding) * 2
        high_size = size * aa_scale
        high_radius = radius * aa_scale
        high_padding = padding * aa_scale
        high_center = (
            high_radius + high_padding,
            high_radius + high_padding
        )

        high_surface = pygame.Surface(
            (high_size, high_size),
            pygame.SRCALPHA
        )

        if fill_key is not None:
            pygame.draw.circle(
                high_surface,
                (*fill_key, 255),
                high_center,
                high_radius
            )

        if outline_key is not None:
            pygame.draw.circle(
                high_surface,
                (*outline_key, 255),
                high_center,
                high_radius,
                max(1, outline_width * aa_scale)
            )

        surface = pygame.transform.smoothscale(
            high_surface,
            (size, size)
        )
        self.circle_surface_cache[key] = surface

        return surface

    def _blit_centered(self, target, surface, center, alpha=255):
        alpha = max(0, min(255, int(alpha)))
        if alpha <= 0:
            return

        surface.set_alpha(alpha)
        rect = surface.get_rect(
            center=(int(round(center[0])), int(round(center[1])))
        )
        target.blit(surface, rect)

    def _draw_aa_circle(
        self,
        target,
        center,
        radius,
        fill_color=None,
        outline_color=None,
        outline_width=0,
        alpha=255
    ):
        surface = self._aa_circle_surface(
            radius,
            fill_color=fill_color,
            outline_color=outline_color,
            outline_width=outline_width
        )
        self._blit_centered(target, surface, center, alpha)

    def _draw_centered_text(self, target, surface, center, alpha=255):
        alpha = max(0, min(255, int(alpha)))
        if alpha <= 0:
            return

        surface.set_alpha(alpha)
        rect = surface.get_rect(
            center=(int(round(center[0])), int(round(center[1])))
        )
        target.blit(surface, rect)

    def _draw_combo_number(
        self,
        target,
        text,
        center,
        color,
        alpha=255
    ):
        outline = self.circle_number_font.render(
            text,
            True,
            (0, 0, 0)
        )
        outline.set_alpha(alpha)

        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rect = outline.get_rect(
                center=(
                    int(round(center[0] + dx)),
                    int(round(center[1] + dy))
                )
            )
            target.blit(outline, rect)

        main_text = self.circle_number_font.render(
            text,
            True,
            (255, 255, 255)
        )
        self._draw_centered_text(
            target,
            main_text,
            center,
            alpha=alpha
        )

    def _load_cursor_asset(self, filename, scale=1.0):
        path = os.path.join(
            "assets",
            "cursor",
            filename
        )

        if not os.path.exists(path):
            return None

        try:
            image = pygame.image.load(path).convert_alpha()
        except pygame.error:
            return None

        if scale != 1.0:
            width = max(1, int(image.get_width() * scale))
            height = max(1, int(image.get_height() * scale))
            image = pygame.transform.smoothscale(
                image,
                (width, height)
            )

        return image

    def _blit_asset_centered(
        self,
        target,
        image,
        center,
        alpha=255,
        scale=1.0
    ):
        if image is None:
            return

        alpha = max(0, min(255, int(alpha)))
        if alpha <= 0:
            return

        render_image = image
        if scale != 1.0:
            width = max(1, int(image.get_width() * scale))
            height = max(1, int(image.get_height() * scale))
            render_image = pygame.transform.smoothscale(
                image,
                (width, height)
            )
        else:
            render_image = image.copy()

        render_image.set_alpha(alpha)
        rect = render_image.get_rect(
            center=(
                int(round(center[0])),
                int(round(center[1]))
            )
        )
        target.blit(render_image, rect)

    def _draw_miss_pop(
        self,
        target,
        center,
        radius,
        color,
        alpha=255
    ):
        alpha = max(0, min(255, int(alpha)))
        if alpha <= 0:
            return

        radius = max(1, int(radius))
        progress = self._clamp01(1.0 - (alpha / 255.0))
        eased = progress * progress * progress * (
            progress * (progress * 6.0 - 15.0) + 10.0
        )
        collapse = 1.0 - ((1.0 - eased) ** 1.75)
        remaining = 1.0 - collapse

        fill_radius = int(radius * max(0.04, remaining ** 1.05))
        shell_radius = int(radius * max(0.07, remaining ** 0.94))
        ring_width = max(1, int(radius * (0.055 * remaining + 0.018)))
        visible_alpha = int(255 * (remaining ** 1.18))

        if fill_radius > 1:
            self._draw_aa_circle(
                target,
                center,
                fill_radius,
                fill_color=color,
                alpha=int(visible_alpha * 0.82)
            )

        self._draw_aa_circle(
            target,
            center,
            shell_radius,
            outline_color=(255, 255, 255),
            outline_width=ring_width,
            alpha=visible_alpha
        )

        if progress < 0.64:
            inner_alpha = int(visible_alpha * (1.0 - progress / 0.64) * 0.30)
            inner_radius = int(radius * max(0.03, remaining ** 1.42))
            self._draw_aa_circle(
                target,
                center,
                inner_radius,
                outline_color=(255, 255, 255),
                outline_width=max(1, int(ring_width * 0.55)),
                alpha=inner_alpha
            )

    def _draw_slider_reverse_markers(
        self,
        target,
        slider_points,
        repeat_count,
        alpha=255
    ):
        if len(slider_points) < 2 or repeat_count <= 1:
            return

        arrow_len = max(12, int(self.scaled_radius * 0.45))
        arrow_width = max(6, int(self.scaled_radius * 0.25))

        for repeat_index in range(1, repeat_count):
            if repeat_index % 2 == 1:
                pos = slider_points[-1]
                reference = slider_points[-2]
            else:
                pos = slider_points[0]
                reference = slider_points[1]

            dx = reference[0] - pos[0]
            dy = reference[1] - pos[1]
            distance = (dx * dx + dy * dy) ** 0.5
            if distance < 1e-3:
                continue

            ux = dx / distance
            uy = dy / distance
            perp_x = -uy
            perp_y = ux

            base = (
                pos[0] + ux * arrow_len,
                pos[1] + uy * arrow_len
            )
            left = (
                base[0] + perp_x * arrow_width,
                base[1] + perp_y * arrow_width
            )
            right = (
                base[0] - perp_x * arrow_width,
                base[1] - perp_y * arrow_width
            )

            pygame.draw.polygon(
                target,
                (255, 255, 255, int(alpha)),
                [pos, left, right]
            )

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

            elif event.key in (pygame.K_z, pygame.K_x):

                self._try_hit_at(
                    pygame.mouse.get_pos()
                )

        elif event.type == pygame.MOUSEBUTTONDOWN:

            if event.button in (1, 3):

                self._try_hit_at(
                    event.pos
                )

    def update(self, dt):

        if not self.music_started:

            self.start_music()

            self.music_started = True

        if self.start_time is not None:

            self.current_time = (
                pygame.time.get_ticks()
                - self.start_time
            )

        raw_cursor_pos = pygame.mouse.get_pos()
        self.cursor_pos = raw_cursor_pos
        self.cursor_trail_emit_timer += dt

        new_history = []
        for entry in self.cursor_history:
            entry["age"] += dt
            if entry["age"] <= self.cursor_tail_duration:
                new_history.append(entry)

        last_cursor_pos = getattr(
            self,
            "last_cursor_pos",
            self.cursor_pos
        )
        dx = self.cursor_pos[0] - last_cursor_pos[0]
        dy = self.cursor_pos[1] - last_cursor_pos[1]
        moved_distance = (dx * dx + dy * dy) ** 0.5

        should_add_cursor_sample = (
            self.cursor_trail_emit_timer >= self.cursor_tail_emit_interval
            and moved_distance >= self.cursor_tail_min_distance
        )

        if should_add_cursor_sample:
            new_history.append({
                "pos": self.cursor_pos,
                "age": 0.0
            })
            self.cursor_trail_emit_timer = 0.0
            self.last_cursor_pos = self.cursor_pos

        self.cursor_history = new_history[-self.cursor_tail_max_points:]

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

        for note in self.active_notes:
            if note.get("judged"):
                continue
            if note["type"] == "circle":
                if self.current_time > note["time"] + self.hit_window_50:
                    self._add_hit_result(note, 0)
            elif note["type"] == "slider":
                if self.current_time > note["time"] + self.hit_window_50:
                    self._add_hit_result(note, 0)

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
                +
                self.hit_explosion_duration
            )
        ]

    def scale_position(self, x, y):

        scaled_x = (
            self.object_offset_x
            + (x * self.object_scale)
        )

        scaled_y = (
            self.object_offset_y
            + (y * self.object_scale)
        )

        return scaled_x, scaled_y

    def _build_slider_points(self, note):

        all_points = note.get("curve_points", [])
        if not all_points:
            all_points = [
                {
                    "x": note["x"],
                    "y": note["y"]
                }
            ]

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
                        float(scaled_x),
                        float(scaled_y)
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

    def _slider_points_until_progress(self, points, progress):
        if len(points) < 2:
            return points

        progress = self._clamp01(progress)
        if progress >= 1.0:
            return points

        total_length = 0.0
        segment_lengths = []

        for i in range(len(points) - 1):
            dx = points[i + 1][0] - points[i][0]
            dy = points[i + 1][1] - points[i][1]
            length = (dx * dx + dy * dy) ** 0.5
            segment_lengths.append(length)
            total_length += length

        if total_length <= 0:
            return points[:1]

        target_length = total_length * progress
        visible_points = [points[0]]
        walked = 0.0

        for i, segment_length in enumerate(segment_lengths):
            next_walked = walked + segment_length

            if next_walked < target_length:
                visible_points.append(points[i + 1])
                walked = next_walked
                continue

            if segment_length > 0:
                t = self._clamp01((target_length - walked) / segment_length)
                x = points[i][0] + (points[i + 1][0] - points[i][0]) * t
                y = points[i][1] + (points[i + 1][1] - points[i][1]) * t
                visible_points.append((x, y))

            break

        return visible_points

    def _point_line_distance(self, point, start, end):
        dx = end[0] - start[0]
        dy = end[1] - start[1]

        if dx == 0 and dy == 0:
            px = point[0] - start[0]
            py = point[1] - start[1]
            return (px * px + py * py) ** 0.5

        return abs(
            dy * point[0]
            - dx * point[1]
            + end[0] * start[1]
            - end[1] * start[0]
        ) / ((dx * dx + dy * dy) ** 0.5)

    def _simplify_slider_points(self, points, tolerance=0.35):
        if len(points) <= 2:
            return points

        keep = {0, len(points) - 1}
        stack = [(0, len(points) - 1)]

        while stack:
            start_idx, end_idx = stack.pop()
            max_distance = 0.0
            max_idx = None

            for idx in range(start_idx + 1, end_idx):
                distance = self._point_line_distance(
                    points[idx],
                    points[start_idx],
                    points[end_idx]
                )

                if distance > max_distance:
                    max_distance = distance
                    max_idx = idx

            if max_idx is not None and max_distance > tolerance:
                keep.add(max_idx)
                stack.append((start_idx, max_idx))
                stack.append((max_idx, end_idx))

        return [points[idx] for idx in sorted(keep)]

    def _render_slider_track_surface_supersampled(
        self,
        size,
        points,
        outline_radius,
        body_radius
    ):
        width, height = size
        surface = pygame.Surface(size, pygame.SRCALPHA)

        if len(points) < 2 or width <= 0 or height <= 0:
            return surface

        aa_scale = 3
        high_surface = pygame.Surface(
            (width * aa_scale, height * aa_scale),
            pygame.SRCALPHA
        )

        high_points = [
            (
                int(round(point[0] * aa_scale)),
                int(round(point[1] * aa_scale))
            )
            for point in points
        ]

        tracks = (
            (outline_radius, (30, 30, 30, 220)),
            (body_radius, (255, 105, 180, 255))
        )

        for radius, color in tracks:
            high_radius = max(1, int(round(radius * aa_scale)))
            high_width = max(1, high_radius * 2)

            for i in range(len(high_points) - 1):
                pygame.draw.line(
                    high_surface,
                    color,
                    high_points[i],
                    high_points[i + 1],
                    high_width
                )

            for point in high_points:
                pygame.draw.circle(
                    high_surface,
                    color,
                    point,
                    high_radius
                )

        return pygame.transform.smoothscale(
            high_surface,
            size
        )

    def _slider_distance_field(
        self,
        width,
        height,
        points,
        max_distance
    ):
        if len(points) < 2:
            return None

        max_distance = float(max_distance)
        distances = np.full(
            (height, width),
            max_distance + 2.0,
            dtype=np.float32
        )

        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            dx = float(x2 - x1)
            dy = float(y2 - y1)
            length_sq = (dx * dx) + (dy * dy)

            if length_sq <= 1e-6:
                continue

            min_x = max(0, int(np.floor(min(x1, x2) - max_distance - 2)))
            max_x = min(width - 1, int(np.ceil(max(x1, x2) + max_distance + 2)))
            min_y = max(0, int(np.floor(min(y1, y2) - max_distance - 2)))
            max_y = min(height - 1, int(np.ceil(max(y1, y2) + max_distance + 2)))

            if min_x > max_x or min_y > max_y:
                continue

            ys, xs = np.mgrid[min_y:max_y + 1, min_x:max_x + 1]
            sample_x = xs.astype(np.float32) + 0.5
            sample_y = ys.astype(np.float32) + 0.5
            px = sample_x - float(x1)
            py = sample_y - float(y1)
            t = np.clip(
                ((px * dx) + (py * dy)) / length_sq,
                0.0,
                1.0
            )
            nearest_x = float(x1) + (t * dx)
            nearest_y = float(y1) + (t * dy)
            segment_distance = np.sqrt(
                ((sample_x - nearest_x) ** 2)
                + ((sample_y - nearest_y) ** 2)
            )

            current = distances[min_y:max_y + 1, min_x:max_x + 1]
            np.minimum(
                current,
                segment_distance,
                out=current
            )

        return distances

    def _slider_alpha_from_distance(self, distances, radius, alpha):
        coverage = np.clip(
            float(radius) + 0.5 - distances,
            0.0,
            1.0
        )

        return (coverage * float(alpha)).astype(np.uint8)

    def _render_slider_track_surface(
        self,
        size,
        points,
        outline_radius,
        body_radius
    ):
        width, height = size
        surface = pygame.Surface(size, pygame.SRCALPHA)

        if len(points) < 2 or width <= 0 or height <= 0:
            return surface

        if np is None:
            return self._render_slider_track_surface_supersampled(
                size,
                points,
                outline_radius,
                body_radius
            )

        distances = self._slider_distance_field(
            width,
            height,
            points,
            outline_radius + 2
        )

        if distances is None:
            return surface

        rgb = pygame.surfarray.pixels3d(surface)
        alpha = pygame.surfarray.pixels_alpha(surface)

        outline_alpha = self._slider_alpha_from_distance(
            distances,
            outline_radius,
            220
        )
        body_alpha = self._slider_alpha_from_distance(
            distances,
            body_radius,
            255
        )
        body_mask = body_alpha > 0

        rgb[:, :, :] = (30, 30, 30)
        alpha[:, :] = np.where(
            body_mask.T,
            body_alpha.T,
            outline_alpha.T
        )

        rgb[body_mask.T] = (80, 80, 80)

        del rgb
        del alpha

        return surface

    def _slider_surface_geometry(self, slider_points):
        if len(slider_points) < 2:
            return None

        min_x = int(np.floor(min(p[0] for p in slider_points))) if np is not None else int(min(p[0] for p in slider_points))
        max_x = int(np.ceil(max(p[0] for p in slider_points))) if np is not None else int(max(p[0] for p in slider_points))

        min_y = int(np.floor(min(p[1] for p in slider_points))) if np is not None else int(min(p[1] for p in slider_points))
        max_y = int(np.ceil(max(p[1] for p in slider_points))) if np is not None else int(max(p[1] for p in slider_points))

        padding = int(
            self.slider_path_radius * 2
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
            return None

        width = min(
            width,
            self.MAX_SLIDER_SURFACE_SIZE
        )

        height = min(
            height,
            self.MAX_SLIDER_SURFACE_SIZE
        )

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
                    (
                        point[0] - min_x + padding,
                        point[1] - min_y + padding
                    )
                )

        if np is None:
            local_points = self._simplify_slider_points(local_points)

        if len(local_points) < 2:
            return None

        return (
            (width, height),
            local_points,
            (
                min_x - padding,
                min_y - padding
            )
        )

    def _cache_full_slider_surface(self, note, slider_points=None):
        cache_key = note.get("render_index")
        if cache_key is None:
            return

        if cache_key in self.slider_surface_cache:
            return

        if slider_points is None:
            slider_points = note.get("scaled_slider_points")

        if slider_points is None:
            slider_points = self._build_slider_points(note)
            note["scaled_slider_points"] = slider_points

        geometry = self._slider_surface_geometry(slider_points)
        if geometry is None:
            return

        size, local_points, surface_pos = geometry

        outline_radius = self.slider_path_radius

        body_radius = int(
            self.slider_path_radius * 0.76
        )

        slider_surface = self._render_slider_track_surface(
            size,
            local_points,
            outline_radius,
            body_radius,
        )

        self.slider_surface_cache[cache_key] = (
            slider_surface,
            surface_pos
        )

    def _precache_slider_surfaces(self):
        for note in self.notes:
            if note["type"] != "slider":
                continue

            self._cache_full_slider_surface(note)

    def _draw_slider(
        self,
        screen,
        slider_points,
        alpha=255,
        draw_head_marker=True,
        draw_tail_marker=False,
        cache_key=None,
        reveal_progress=1.0,
        repeat_count=1,
        draw_reverse_markers=False
    ):

        if len(slider_points) < 2:
            return

        if alpha <= 0:
            return

        a = max(0, min(255, int(alpha)))
        reveal_progress = self._clamp01(reveal_progress)

        if cache_key is not None and reveal_progress >= 0.995:
            cached = self.slider_surface_cache.get(cache_key)
            if cached is not None:
                slider_surface, surface_pos = cached
                slider_surface.set_alpha(a)
                screen.blit(slider_surface, surface_pos)

                if draw_head_marker:
                    self._draw_aa_circle(
                        screen,
                        slider_points[0],
                        self.slider_head_radius,
                        fill_color=(0, 150, 255),
                        outline_color=(255, 255, 255),
                        outline_width=3,
                        alpha=a
                    )

                if draw_tail_marker:
                    self._draw_aa_circle(
                        screen,
                        slider_points[-1],
                        self.scaled_radius,
                        fill_color=(0, 150, 255),
                        outline_color=(255, 255, 255),
                        outline_width=3,
                        alpha=a
                    )

                if draw_reverse_markers and repeat_count > 1:
                    self._draw_slider_reverse_markers(
                        screen,
                        slider_points,
                        repeat_count,
                        alpha=a
                    )

                return

        render_points = slider_points
        if reveal_progress < 0.995:
            render_points = self._slider_points_until_progress(
                slider_points,
                reveal_progress
            )

        if len(render_points) < 2:
            if draw_head_marker:
                self._draw_aa_circle(
                    screen,
                    slider_points[0],
                    self.slider_head_radius,
                    fill_color=(0, 150, 255),
                    outline_color=(255, 255, 255),
                    outline_width=3,
                    alpha=a
                )
            return

        geometry = self._slider_surface_geometry(render_points)
        if geometry is None:
            return

        size, local_points, surface_pos = geometry

        outline_radius = self.slider_path_radius
        body_radius = int(
            self.slider_path_radius * 0.76
        )

        slider_surface = self._render_slider_track_surface(
            size,
            local_points,
            outline_radius,
            body_radius,
        )

        if cache_key is not None and reveal_progress >= 0.995:
            self.slider_surface_cache[cache_key] = (
                slider_surface,
                surface_pos
            )

        slider_surface.set_alpha(a)
        screen.blit(
            slider_surface,
            surface_pos
        )

        if draw_head_marker or draw_tail_marker:
            head_pos = slider_points[0]
            tail_pos = slider_points[-1]

            if draw_head_marker:
                self._draw_aa_circle(
                    screen,
                    head_pos,
                    self.slider_head_radius,
                    fill_color=(0, 150, 255),
                    outline_color=(255, 255, 255),
                    outline_width=3,
                    alpha=a
                )

            if draw_tail_marker:
                self._draw_aa_circle(
                    screen,
                    tail_pos,
                    self.scaled_radius,
                    fill_color=(0, 150, 255),
                    outline_color=(255, 255, 255),
                    outline_width=3,
                    alpha=a
                )

            if draw_reverse_markers and repeat_count > 1:
                self._draw_slider_reverse_markers(
                    screen,
                    slider_points,
                    repeat_count,
                    alpha=a
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

        score_text = self.font.render(
            f"{self.score:08d}",
            True,
            (255, 255, 255)
        )
        accuracy_text = self.font.render(
            f"{self._accuracy():05.2f}%",
            True,
            (255, 255, 255)
        )
        combo_text = self.font.render(
            f"{self.combo}x",
            True,
            (255, 255, 255)
        )

        screen.blit(
            score_text,
            (
                self.game.WIDTH - score_text.get_width() - 20,
                20
            )
        )
        screen.blit(
            accuracy_text,
            (
                self.game.WIDTH - accuracy_text.get_width() - 20,
                60
            )
        )
        screen.blit(
            combo_text,
            (
                20,
                self.game.HEIGHT - combo_text.get_height() - 20
            )
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
            slider_ball_alpha = 0
            if note["type"] == "slider":
                slider_ball_alpha = self._slider_ball_alpha(note)

            miss_pop_alpha = 0
            if note.get("hit_result") == 0:
                miss_pop_alpha = self._miss_pop_alpha(note)

            if (
                alpha <= 0
                and slider_ball_alpha <= 0
                and miss_pop_alpha <= 0
            ):
                continue

            scaled_hit_radius = self.scaled_radius

            approach_radius = int(
                self.scaled_radius
                + (
                    progress
                    * self.scaled_radius
                    * 2.5
                )
            )

            if alpha > 0:
                approach_alpha = int(
                    alpha * (0.42 + (0.58 * self._clamp01(progress)))
                )
                self._draw_aa_circle(
                    overlay,
                    (scaled_x, scaled_y),
                    approach_radius,
                    outline_color=(255, 255, 255),
                    outline_width=5,
                    alpha=approach_alpha
                )

            if note["type"] == "circle":
                circle_color = note.get(
                    "combo_color",
                    (0, 150, 255)
                )

                hit_result = note.get("hit_result")
                if hit_result == 0:
                    pop_alpha = self._miss_pop_alpha(note)
                    self._draw_miss_pop(
                        overlay,
                        (scaled_x, scaled_y),
                        scaled_hit_radius,
                        circle_color,
                        alpha=pop_alpha
                    )
                elif hit_result is not None and hit_result > 0:
                    hit_time = note.get("hit_time", self.current_time)
                    explosion_elapsed = self.current_time - hit_time
                    explosion_progress = min(
                        1.0,
                        explosion_elapsed / self.hit_explosion_duration
                    )
                    expansion_factor = 1.0 + (explosion_progress * 0.4)
                    explosion_radius = int(
                        scaled_hit_radius * expansion_factor
                    )
                    explosion_alpha = int(
                        alpha * (1.0 - explosion_progress)
                    )
                    self._draw_aa_circle(
                        overlay,
                        (scaled_x, scaled_y),
                        explosion_radius,
                        fill_color=circle_color,
                        outline_color=(255, 255, 255),
                        outline_width=max(1, int(3 * (1.0 - explosion_progress))),
                        alpha=explosion_alpha
                    )
                else:
                    self._draw_aa_circle(
                        overlay,
                        (scaled_x, scaled_y),
                        scaled_hit_radius,
                        fill_color=circle_color,
                        outline_color=(255, 255, 255),
                        outline_width=3,
                        alpha=alpha
                    )

                number_base_alpha = 255 if hit_result == 0 else alpha
                number_alpha = self._combo_number_alpha(
                    note,
                    number_base_alpha
                )
                if number_alpha > 0:
                    self._draw_combo_number(
                        overlay,
                        str(note["combo_index"]),
                        (scaled_x, scaled_y),
                        circle_color,
                        alpha=number_alpha
                    )

            elif note["type"] == "slider":

                slider_points = note.get("scaled_slider_points")
                if slider_points is None:
                    slider_points = self._build_slider_points(note)
                    note["scaled_slider_points"] = slider_points

                reveal_progress = self._slider_reveal_progress(note)

                self._draw_slider(
                    overlay,
                    slider_points,
                    alpha=alpha,
                    draw_head_marker=not note.get("judged", False),
                    draw_tail_marker=False,
                    cache_key=note.get("render_index"),
                    reveal_progress=reveal_progress,
                    repeat_count=note.get("repeat_count", 1),
                    draw_reverse_markers=True
                )

                head_result = note.get("head_hit_result")
                if head_result == 0:
                    pop_alpha = self._miss_pop_alpha(note)
                    self._draw_miss_pop(
                        overlay,
                        slider_points[0],
                        self.slider_head_radius,
                        note.get("combo_color", (0, 150, 255)),
                        alpha=pop_alpha
                    )

                number_base_alpha = 255 if head_result == 0 else alpha
                number_alpha = self._combo_number_alpha(
                    note,
                    number_base_alpha
                )
                if number_alpha > 0:
                    self._draw_combo_number(
                        overlay,
                        str(note["combo_index"]),
                        slider_points[0],
                        note.get("combo_color", (255, 255, 255)),
                        alpha=number_alpha
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

                    self._draw_aa_circle(
                        overlay,
                        ball_pos,
                        scaled_hit_radius,
                        fill_color=(0, 150, 255),
                        outline_color=(255, 255, 255),
                        outline_width=3,
                        alpha=slider_ball_alpha
                    )

        self.miss_indicators = [
            indicator
            for indicator in self.miss_indicators
            if self.current_time < indicator["show_time"] + self.miss_indicator_duration
        ]

        for indicator in self.miss_indicators:
            if self.current_time < indicator["show_time"]:
                continue

            elapsed = self.current_time - indicator["show_time"]
            progress = self._clamp01(
                elapsed / self.miss_indicator_duration
            )
            eased = 1.0 - (progress ** 0.7)
            alpha = int(255 * eased)
            size = int(self.scaled_radius * 0.30)
            half = max(1, size // 2)
            x, y = indicator["pos"]
            y += int(elapsed * 0.03)
            width = max(2, int(2 * eased))

            pygame.draw.line(
                overlay,
                (255, 255, 255, alpha),
                (x - half, y - half),
                (x + half, y + half),
                width
            )
            pygame.draw.line(
                overlay,
                (255, 255, 255, alpha),
                (x - half, y + half),
                (x + half, y - half),
                width
            )

        screen.blit(overlay, (0, 0))

        self._draw_custom_cursor(screen)

    def _draw_custom_cursor(self, screen):
        cursor_pos = getattr(
            self,
            "cursor_pos",
            pygame.mouse.get_pos()
        )

        trail_surface = pygame.Surface(
            screen.get_size(),
            pygame.SRCALPHA
        )

        points = [
            entry for entry in self.cursor_history
            if entry["age"] <= self.cursor_tail_duration
        ]

        for entry in points:
            progress = self._clamp01(
                entry["age"] / self.cursor_tail_duration
            )
            fade_in = self._clamp01(entry["age"] / 0.018)
            fade_out = 1.0 - progress
            alpha = int(
                220
                * self._ease_out_cubic(fade_in)
                * (fade_out ** 1.8)
            )
            scale = 0.86 + (0.14 * self._ease_out_cubic(fade_in))
            self._blit_asset_centered(
                trail_surface,
                self.cursor_trail_image,
                entry["pos"],
                alpha=alpha,
                scale=scale
            )

        screen.blit(trail_surface, (0, 0))

        self._blit_asset_centered(
            screen,
            self.cursor_image,
            cursor_pos,
            alpha=250
        )

    def destroy(self):

        pygame.mixer.music.stop()

        pygame.mouse.set_visible(True)
