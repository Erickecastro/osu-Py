import pygame
import copy

from scenes.base_scene import BaseScene
from core.audio import find_audio_file, start_music
from core.gameplay import calculate_accuracy, hit_result_for_delta
from rendering.cursor import CursorRenderer
from rendering.primitives import (
    aa_circle_surface,
    blit_centered,
    draw_aa_circle,
    draw_centered_text
)
from rendering.sliders import SliderRenderer


class GameplayScene(BaseScene):

    MAX_SLIDER_SURFACE_SIZE = 4096
    MAX_SLIDER_POINTS = 4000
    DEFAULT_COMBO_COLORS = (
        (233, 182, 29),
        (89, 80, 203),
        (66, 198, 221),
        (224, 73, 73)
    )

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

        combo_colors = self.DEFAULT_COMBO_COLORS

        self.active_notes = []
        self.next_note_index = 0
        self.circle_surface_cache = {}
        self.slider_surface_cache = {}
        self.overlay_surface = None
        self.overlay_surface_size = None

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

        self.music_path = find_audio_file(
            self.beatmap["path"]
        )

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

        self.slider_renderer = SliderRenderer(self)
        self.slider_renderer.precache_surfaces()

        self.circle_number_font = pygame.font.SysFont(
            "arial",
            32,
            bold=True
        )

        self.cursor_renderer = CursorRenderer()
        self.circle_number_font = pygame.font.SysFont(
            "arial",
            28,
            bold=True
        )
        self.hud_text_cache = {}
        self.combo_number_surface_cache = {}
        
        self.miss_indicators = []
        self.miss_indicator_delay = 25  # ms before the X appears
        self.miss_indicator_duration = 520  # ms X stays visible

    def _accuracy(self):
        return calculate_accuracy(
            self.hit_counts
        )

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
        return hit_result_for_delta(
            delta,
            self.hit_window_300,
            self.hit_window_100,
            self.hit_window_50
        )

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
        return aa_circle_surface(
            self.circle_surface_cache,
            radius,
            fill_color=fill_color,
            outline_color=outline_color,
            outline_width=outline_width
        )

    def _blit_centered(self, target, surface, center, alpha=255):
        blit_centered(
            target,
            surface,
            center,
            alpha=alpha
        )

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
        draw_aa_circle(
            target,
            self.circle_surface_cache,
            center,
            radius,
            fill_color=fill_color,
            outline_color=outline_color,
            outline_width=outline_width,
            alpha=alpha
        )

    def _draw_centered_text(self, target, surface, center, alpha=255):
        draw_centered_text(
            target,
            surface,
            center,
            alpha=alpha
        )

    def _hud_text_surface(self, text, color=(255, 255, 255)):
        key = (text, tuple(color))
        cached = self.hud_text_cache.get(key)
        if cached is not None:
            return cached

        if len(self.hud_text_cache) > 96:
            self.hud_text_cache.clear()

        surface = self.font.render(
            text,
            True,
            color
        )
        self.hud_text_cache[key] = surface
        return surface

    def _combo_number_surfaces(self, text):
        cached = self.combo_number_surface_cache.get(text)
        if cached is not None:
            return cached

        surfaces = (
            self.circle_number_font.render(
                text,
                True,
                (0, 0, 0)
            ),
            self.circle_number_font.render(
                text,
                True,
                (255, 255, 255)
            )
        )
        self.combo_number_surface_cache[text] = surfaces
        return surfaces

    def _draw_combo_number(
        self,
        target,
        text,
        center,
        color,
        alpha=255
    ):
        outline, main_text = self._combo_number_surfaces(text)
        outline.set_alpha(alpha)

        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rect = outline.get_rect(
                center=(
                    int(round(center[0] + dx)),
                    int(round(center[1] + dy))
                )
            )
            target.blit(outline, rect)

        self._draw_centered_text(
            target,
            main_text,
            center,
            alpha=alpha
        )

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

            self.start_time = start_music(
                self.music_path
            )

            self.music_started = True

        if self.start_time is not None:

            self.current_time = (
                pygame.time.get_ticks()
                - self.start_time
            )

        self.cursor_renderer.update(
            dt,
            pygame.mouse.get_pos()
        )

        while self.next_note_index < len(self.notes):
            note = self.notes[self.next_note_index]
            start_time = note.get(
                "start_time",
                note["time"] - self.approach_time
            )
            if self.current_time < start_time:
                break

            note["active"] = True
            self.active_notes.append(note)
            self.next_note_index += 1

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

        title_text = self._hud_text_surface(
            f"{title} [{version}]",
            (255, 255, 255)
        )

        screen.blit(
            title_text,
            (20, 20)
        )

        display_time = int(self.current_time // 25) * 25
        time_text = self._hud_text_surface(
            f"{display_time} ms",
            (0, 255, 0)
        )

        screen.blit(
            time_text,
            (20, 60)
        )

        score_text = self._hud_text_surface(
            f"{self.score:08d}",
            (255, 255, 255)
        )
        accuracy_text = self._hud_text_surface(
            f"{self._accuracy():05.2f}%",
            (255, 255, 255)
        )
        combo_text = self._hud_text_surface(
            f"{self.combo}x",
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
        screen_size = screen.get_size()
        if self.overlay_surface is None or self.overlay_surface_size != screen_size:
            self.overlay_surface = pygame.Surface(
                screen_size,
                pygame.SRCALPHA
            )
            self.overlay_surface_size = screen_size

        overlay = self.overlay_surface
        overlay.fill((0, 0, 0, 0))

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
                    slider_points = self.slider_renderer.build_points(note)
                    note["scaled_slider_points"] = slider_points

                reveal_progress = self._slider_reveal_progress(note)

                self.slider_renderer.draw(
                    overlay,
                    slider_points,
                    alpha=alpha,
                    object_color=note.get("combo_color", (0, 150, 255)),
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

                    ball_pos = self.slider_renderer.point_at_distance(
                        slider_points,
                        ball_dist
                    )

                    self._draw_aa_circle(
                        overlay,
                        ball_pos,
                        scaled_hit_radius,
                        fill_color=note.get("combo_color", (0, 150, 255)),
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

        self.cursor_renderer.draw(screen)

    def destroy(self):

        pygame.mixer.music.stop()

        pygame.mouse.set_visible(True)
