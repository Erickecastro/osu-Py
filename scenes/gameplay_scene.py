import pygame

from scenes.base_scene import BaseScene
from core.audio import find_audio_file, start_music
from core.gameplay import calculate_accuracy, hit_result_for_delta
from core.hit_detection import find_best_hit_object
from core.gameplay_notes import (
    clone_notes_with_combo_data,
    prepare_note_lifecycle
)
from core.gameplay_state import (
    activate_due_notes,
    judge_missed_notes,
    prune_inactive_notes
)
from rendering.cursor import CursorRenderer
from rendering.hud import GameplayHUDRenderer
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

        combo_colors = self.DEFAULT_COMBO_COLORS
        self.notes = clone_notes_with_combo_data(
            beatmap["notes"],
            combo_colors
        )

        self.active_notes = []
        self.next_note_index = 0
        self.circle_surface_cache = {}
        self.slider_surface_cache = {}
        self.overlay_surface = None
        self.overlay_surface_size = None

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
        prepare_note_lifecycle(
            self.notes,
            self.approach_time,
            self.hit_fade_out_time,
            self.timing_points,
            self.slider_multiplier
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
        self.combo_number_surface_cache = {}
        self.hud_renderer = GameplayHUDRenderer(self.font)
        self._precache_gameplay_surfaces()
        
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
        best_note, best_result = find_best_hit_object(
            self.active_notes,
            self.current_time,
            pos,
            self.scaled_radius,
            self.scale_position,
            self._hit_result_for_delta
        )

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

    def _precache_gameplay_surfaces(self):
        base_radius = max(1, int(self.scaled_radius))
        max_hit_radius = max(base_radius, int(base_radius * 1.42) + 1)

        for color in self.DEFAULT_COMBO_COLORS:
            self._aa_circle_surface(
                base_radius,
                fill_color=color,
                outline_color=(255, 255, 255),
                outline_width=3
            )
            for radius in range(base_radius, max_hit_radius + 1):
                for outline_width in (1, 2, 3):
                    self._aa_circle_surface(
                        radius,
                        fill_color=color,
                        outline_color=(255, 255, 255),
                        outline_width=outline_width
                    )

            for radius in range(2, base_radius + 1):
                self._aa_circle_surface(
                    radius,
                    fill_color=color
                )

        for radius in range(2, base_radius + 1):
            self._aa_circle_surface(
                radius,
                outline_color=(255, 255, 255),
                outline_width=1
            )
            self._aa_circle_surface(
                radius,
                outline_color=(255, 255, 255),
                outline_width=2
            )
            self._aa_circle_surface(
                radius,
                outline_color=(255, 255, 255),
                outline_width=3
            )

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

        self.next_note_index = activate_due_notes(
            self.notes,
            self.active_notes,
            self.next_note_index,
            self.current_time,
            self.approach_time
        )

        judge_missed_notes(
            self.active_notes,
            self.current_time,
            self.hit_window_50,
            self._add_hit_result
        )

        self.active_notes = prune_inactive_notes(
            self.active_notes,
            self.current_time,
            self.hit_fade_out_time,
            self.hit_explosion_duration
        )

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

        self.hud_renderer.draw(
            screen,
            self.beatmap,
            self.current_time,
            self.score,
            self._accuracy(),
            self.combo
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
                    cumulative, total_length = self.slider_renderer.path_metrics(
                        slider_points
                    )
                    note["scaled_slider_cumulative"] = cumulative
                    note["scaled_slider_length"] = total_length

                self.slider_renderer.draw(
                    overlay,
                    slider_points,
                    alpha=alpha,
                    object_color=note.get("combo_color", (0, 150, 255)),
                    draw_head_marker=not note.get("judged", False),
                    draw_tail_marker=False,
                    cache_key=note.get("render_index"),
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
                    total_length = note.get("scaled_slider_length")
                    cumulative = note.get("scaled_slider_cumulative")
                    if total_length is None or cumulative is None:
                        cumulative, total_length = self.slider_renderer.path_metrics(
                            slider_points
                        )
                        note["scaled_slider_cumulative"] = cumulative
                        note["scaled_slider_length"] = total_length

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
                        ball_dist,
                        cumulative,
                        total_length
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
