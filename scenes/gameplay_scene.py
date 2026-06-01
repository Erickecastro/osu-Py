import os
import math
from bisect import bisect_left, bisect_right

import pygame

from scenes.base_scene import BaseScene
from core.audio import find_audio_file, start_music
from core.gameplay import calculate_accuracy, hit_result_for_delta
from core.health import apply_health_drain, apply_health_result
from core.hit_detection import find_best_hit_object
from core.gameplay_input import GameplayInputController
from core.gameplay_notes import (
    clone_notes_with_combo_data,
    prepare_note_lifecycle
)
from core.beatmap_timing import effective_beat_length_at
from core.gameplay_state import (
    activate_due_notes,
    judge_missed_notes,
    prune_inactive_notes
)
from core.spinner import SpinnerManager
from rendering.cursor import CursorRenderer
from rendering.effects import GameplayEffectsRenderer
from rendering.hud import GameplayHUDRenderer
from rendering.primitives import (
    aa_circle_surface,
    blit_centered,
    draw_aa_circle,
    draw_centered_text
)
from rendering.sliders import SliderRenderer
from rendering.spinner import SpinnerRenderer


class GameplayScene(BaseScene):
    uses_ui = False

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
        self.game.enable_raw_mouse()

        self.font = pygame.font.SysFont(
            "arial",
            32
        )

        self.music_started = False
        self.music_path = None

        self.start_time = None
        self.current_time = 0
        self.ready_start_time = pygame.time.get_ticks()
        self.pre_music_lead_in_ms = 0
        self.pre_music_started_at = None
        self.pre_start_delay_ms = 1500
        self.post_ready_delay_ms = 650

        combo_colors = self.DEFAULT_COMBO_COLORS
        self.notes = clone_notes_with_combo_data(
            beatmap["notes"],
            combo_colors
        )
        self.note_times = [
            note["time"]
            for note in self.notes
        ]
        self.active_notes = []
        self.next_note_index = 0
        self.circle_surface_cache = {}
        self.slider_surface_cache = {}
        self.image_surface_cache = {}
        self.tinted_surface_cache = {}
        self.overlay_surface = None
        self.overlay_surface_size = None
        self.background_source = None
        self.background_surface = None
        self.background_surface_size = None
        self.background_dim_alpha = 240

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
        self.hp = self.beatmap[
            "difficulty"
        ].get(
            "HP",
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
        self.osu_base_width = 640
        self.osu_base_height = 480
        self.object_size_multiplier = 1.1433

        self.scale = min(
            self.game.WIDTH / self.osu_base_width,
            self.game.HEIGHT / self.osu_base_height
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
        ) / 2 + (8 * self.scale)

        self.slider_base_radius = int(
            self.circle_radius
            * self.scale
            * 0.675143859456
            * self.object_size_multiplier
        )

        if self.slider_base_radius < 40:
            self.slider_base_radius = 40

        self.slider_path_radius = int(
            self.slider_base_radius * 1.22
        )
        if self.slider_path_radius < 40:
            self.slider_path_radius = 40

        self.scaled_radius = int(self.slider_path_radius)

        self.followpoint_visual_radius = self.scaled_radius / 1.03

        self.slider_head_radius = int(
            self.scaled_radius
        )

        self.slider_follow_radius = self.scaled_radius * 1.89

        self.safe_margin = (
            max(
                self.slider_head_radius,
                self.slider_path_radius
            ) + 16
        )

        # Aproximação do comportamento do osu! para visibilidade:
        # fade-in durante o approach e fade-out logo após o hit.
        self.hit_fade_out_time = 460  # ms
        self.miss_fade_out_time = 180  # ms
        self.miss_pop_duration = 112  # ms
        self.hit_number_fade_out_time = 220  # ms
        self.hit_explosion_duration = 380  # ms

        self.usable_width = (
            self.playfield_width * self.scale
        )

        self.usable_height = (
            self.playfield_height * self.scale
        )

        self.object_scale = self.scale
        self.object_offset_x = self.offset_x
        self.object_offset_y = self.offset_y
        self.playfield_rect = (
            self.offset_x,
            self.offset_y,
            self.playfield_width * self.scale,
            self.playfield_height * self.scale
        )
        self.overlay_dirty_rect = self._build_overlay_dirty_rect()
        self._precompute_note_positions()

        self.music_path = find_audio_file(
            self.beatmap["path"],
            self.beatmap.get("audio_filename")
        )
        self.audio_lead_in = int(self.beatmap.get("audio_lead_in", 0) or 0)
        self._load_background_surface()
        self._scaled_background(
            (self.game.WIDTH, self.game.HEIGHT)
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
        self.hit_window_300 = min(
            self.hit_window_300 * 1.18,
            self.hit_window_100 - 1
        )
        self.hit_window_100 = min(
            self.hit_window_100 * 1.12,
            self.hit_window_50 - 1
        )
        self.hit_window_50 *= 1.08

        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.health = 1.0
        self.target_health = 1.0
        self.hit_counts = {
            300: 0,
            100: 0,
            50: 0,
            0: 0
        }
        self.judged_objects = 0
        self.judgable_objects = len(self.notes)
        self._apply_intro_lead_in()

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
        self.effects_renderer = GameplayEffectsRenderer(self)
        self.hud_renderer = GameplayHUDRenderer(self.font)
        self.skin_images = self._load_skin_images()
        self.sliderball_diameter = self._calculate_sliderball_diameter()
        self._precache_gameplay_surfaces()
        
        self.miss_indicators = []
        self.hit_result_indicators = []
        self.hit_keys_held = set()
        self.hit_mouse_buttons_held = set()
        self.input_controller = GameplayInputController(self)
        self.miss_indicator_delay = 25  # ms before the X appears
        self.miss_indicator_duration = 520  # ms X stays visible
        self.paused = False
        self.failed = False
        self.fail_time = None
        self.pause_started_at = None
        self.intro_skip_ms = self._calculate_intro_skip_ms()
        self.intro_skip_used = False
        self.skip_button_rect = None
        self.title_overlay_font = pygame.font.SysFont("arial", 54, bold=True)
        self.medium_overlay_font = pygame.font.SysFont("arial", 28, bold=True)
        self.small_overlay_font = pygame.font.SysFont("arial", 18)
        self.spinner_manager = SpinnerManager(self)
        self.spinner_renderer = SpinnerRenderer(self)

    def _accuracy(self):
        return calculate_accuracy(
            self.hit_counts
        )

    def _apply_intro_lead_in(self):
        self.pre_music_lead_in_ms = 0
        if not self.notes:
            return

        first_note_time = self.notes[0]["time"]
        minimum_lead_in = max(
            850,
            int(self.approach_time * 0.78)
        )
        if first_note_time >= minimum_lead_in:
            return

        self.pre_music_lead_in_ms = minimum_lead_in - first_note_time

    def _calculate_intro_skip_ms(self):
        if not self.notes:
            return 0

        first_note = self.notes[0]
        first_time = first_note["time"]
        if first_time < 5000:
            return 0

        first_visible_time = first_note.get(
            "start_time",
            first_time - self.approach_time
        )
        skip_to = max(0, int(first_visible_time - 350))
        if skip_to < 1200:
            return 0
        return skip_to

    def _add_hit_result(self, note, result):
        note["judged"] = True
        note["active"] = True
        note["hit_result"] = result
        note["hit_time"] = self.current_time
        self.judged_objects += 1
        self.hit_counts[result] += 1
        self._update_health_target(result)
        if result in (50, 100):
            self._add_hit_result_indicator(note, result)

        if note["type"] == "slider":
            note["head_hit"] = result > 0
            note["head_hit_result"] = result
            note["head_hit_time"] = self.current_time

        if result == 0:
            miss_fade_end = self.current_time + self.miss_fade_out_time
            miss_pop_end = self.current_time + self.miss_pop_duration
            self._add_miss_indicator(
                self._note_screen_pos(note),
                show_time=miss_fade_end + self.miss_indicator_delay
            )
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
            if result in (50, 100):
                note["fade_out_duration"] = 1
                note["end_time"] = self.current_time + 1
            else:
                note["fade_out_duration"] = self.hit_number_fade_out_time
                note["end_time"] = self.current_time + self.hit_number_fade_out_time

        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)

        combo_bonus = max(0, self.combo - 1) * result // 25
        self.score += result + combo_bonus

    def _add_hit_result_indicator(self, note, result):
        self.hit_result_indicators.append({
            "result": result,
            "pos": self._note_screen_pos(note),
            "show_time": self.current_time,
            "start_time": self.current_time
        })

    def _update_health_target(self, result):
        self.target_health = apply_health_result(
            self.target_health,
            result,
            self.hp
        )

    def _finish_spinner(self, note, result):
        if note.get("judged"):
            return

        note["judged"] = True
        note["hit_result"] = result
        note["hit_time"] = self.current_time
        note["fade_out_start"] = self.current_time
        note["fade_out_duration"] = 1
        note["end_time"] = self.current_time
        self.judged_objects += 1
        self.hit_counts[result] += 1
        self._update_health_target(result)

        if result == 0:
            self.combo = 0
            self._add_miss_indicator(
                (
                    self.game.WIDTH // 2,
                    self.game.HEIGHT // 2
                ),
                show_time=self.current_time + self.miss_indicator_delay
            )
            return

        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)
        bonus = note.get("spinner_bonus_count", 0) * 1000
        self.score += result + bonus

    def _hit_result_for_delta(self, delta):
        if delta < -self.hit_window_50:
            early_delta = abs(delta)
            if early_delta <= self._early_hit_limit_ms():
                return 50

        return hit_result_for_delta(
            delta,
            self.hit_window_300,
            self.hit_window_100,
            self.hit_window_50
        )

    def _early_hit_limit_ms(self):
        return max(
            self.hit_window_50 * 1.15,
            min(
                self.approach_time * 0.30,
                self.hit_window_50 * 1.55
            )
        )

    def _note_can_receive_early_hit(self, note):
        return self.current_time >= note["time"] - self._early_hit_limit_ms()

    def _slider_end_time(self, note):
        span_duration = float(note.get("span_duration", 0.0))
        repeat_count = int(note.get("repeat_count", 1))
        slider_total_duration = float(
            note.get(
                "slider_total_duration",
                span_duration * repeat_count
            )
        )
        return note["time"] + slider_total_duration

    def _note_blocks_notelock(self, note):
        if note["type"] == "circle":
            return not note.get("judged")

        if note["type"] != "slider":
            if note["type"] == "spinner":
                return not note.get("judged")
            return False

        if note.get("head_hit"):
            return (
                not note.get("slider_follow_missed")
                and self.current_time <= self._slider_end_time(note)
            )

        return note.get("head_hit_result") is None

    def _notelock_target(self):
        candidates = [
            note
            for note in self.active_notes
            if self._note_blocks_notelock(note)
        ]
        if not candidates:
            return None

        return min(
            candidates,
            key=lambda note: (
                note["time"],
                note.get("render_index", 0)
            )
        )

    def _note_is_clickable_target(self, note):
        return not (
            note["type"] == "slider"
            and note.get("head_hit")
        )

    def _note_at_pos(self, pos):
        best_note = None
        best_distance = None

        for note in self.active_notes:
            if note["type"] not in ("circle", "slider"):
                continue
            if not self._note_blocks_notelock(note):
                continue
            if not self._note_is_clickable_target(note):
                continue

            scaled_x, scaled_y = self._note_screen_pos(note)
            dx = pos[0] - scaled_x
            dy = pos[1] - scaled_y
            distance = (dx * dx + dy * dy) ** 0.5
            if distance > self.scaled_radius:
                continue
            if best_distance is None or distance < best_distance:
                best_note = note
                best_distance = distance

        return best_note

    def _trigger_notelock_shake(self, note):
        note["notelock_shake_start"] = self.current_time
        note["notelock_shake_until"] = self.current_time + 220

    def _notelock_shake_offset(self, note):
        start = note.get("notelock_shake_start")
        until = note.get("notelock_shake_until")
        if start is None or until is None:
            return (0.0, 0.0)
        if self.current_time >= until:
            return (0.0, 0.0)

        duration = max(1, until - start)
        progress = self._clamp01((self.current_time - start) / duration)
        amplitude = self.scaled_radius * 0.14 * (1.0 - progress)
        wobble = math.sin(progress * math.tau * 4.0)
        return (amplitude * wobble, 0.0)

    def _try_hit_at(self, pos):
        locked_note = self._notelock_target()

        def can_attempt_hit(note):
            return (
                note is locked_note
                and self._note_is_clickable_target(note)
                and self._note_can_receive_early_hit(note)
            )

        best_note, best_result = find_best_hit_object(
            self.active_notes,
            self.current_time,
            pos,
            self.scaled_radius,
            self.scale_position,
            self._hit_result_for_delta,
            can_attempt_hit
        )

        if best_note is None:
            clicked_note = self._note_at_pos(pos)
            if (
                clicked_note is not None
                and locked_note is not None
                and clicked_note is not locked_note
            ):
                self._trigger_notelock_shake(clicked_note)
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
        fade_in_len = max(180, min(420, approach_len * 0.42))

        return self._ease_out_cubic(
            (self.current_time - start) / fade_in_len
        )

    def _note_alpha(self, note):
        """Alpha suave: fade-in no approach e fade-out no fim do objeto."""
        hit_time = note["time"]

        # Fade-in até o hit.
        alpha_in = self._fade_in_progress(note)

        if note["type"] == "slider":
            if note.get("head_hit_result") == 0:
                fade_out_start = note.get(
                    "fade_out_start",
                    self.current_time
                )
                fade_out_duration = note.get(
                    "fade_out_duration",
                    self.miss_fade_out_time
                )
            else:
                fade_out_start = (
                    hit_time + note.get("slider_total_duration", 0.0)
                )
                fade_out_duration = self.hit_fade_out_time
        elif note["type"] == "spinner":
            hit_time = note.get("spinner_start_time", note["time"])
            alpha_in = self._ease_out_cubic(
                (self.current_time - hit_time) / 240.0
            )
            fade_out_start = note.get(
                "fade_out_start",
                note.get("spinner_end_time", hit_time)
            )
            fade_out_duration = note.get(
                "fade_out_duration",
                self.hit_fade_out_time
            )
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

    def _slider_track_alpha(self, note):
        hit_time = note["time"]
        alpha_in = self._fade_in_progress(note)
        fade_out_start = (
            hit_time + note.get("slider_total_duration", 0.0)
        )
        fade_out_duration = max(1, self.hit_fade_out_time)
        fade_out_end = fade_out_start + fade_out_duration

        if self.current_time <= fade_out_start:
            alpha_out = 1.0
        elif self.current_time >= fade_out_end:
            alpha_out = 0.0
        else:
            alpha_out = (fade_out_end - self.current_time) / fade_out_duration

        return int(255 * alpha_in * self._clamp01(alpha_out))

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

    def _slider_head_alpha(self, note, base_alpha):
        result = note.get("head_hit_result")
        hit_time = note.get("head_hit_time")
        if result is None or hit_time is None:
            return base_alpha

        elapsed = self.current_time - hit_time
        duration = (
            self.miss_pop_duration
            if result == 0
            else self.hit_number_fade_out_time
        )
        progress = self._clamp01(
            elapsed / max(1, duration)
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

    def _load_image(self, *parts):
        path = os.path.join("assets", *parts)
        if not os.path.exists(path):
            return None

        try:
            return pygame.image.load(path).convert_alpha()
        except pygame.error:
            return None

    def _load_skin_images(self):
        images = {
            "hitcircle": self._load_image("hitcircle", "hitcircle.png"),
            "hitcircle_overlay": self._load_image(
                "hitcircle",
                "hitcircleoverlay.png"
            ),
            "approach": self._load_image(
                "novo_approach_circle",
                "approachcircle.png"
            ),
            "hit100": self._load_image("novo_hits", "hit100.png"),
            "hit50": self._load_image("novo_hits", "hit50.png"),
            "miss": self._load_image("novo_miss", "miss.png"),
            "sliderball": self._load_image(
                "novo_sliderball",
                "sliderball.png"
            ),
            "sliderballfollow": self._load_image(
                "novo_sliderballfollow",
                "sliderballfollow.png"
            )
        }

        images["combo_digits"] = {
            str(number): self._load_image(
                "numeros_combo",
                f"default-{number}.png"
            )
            for number in range(10)
        }
        images["followpoints"] = [
            image
            for image in (
                self._load_image(
                    "novo_followpoint",
                    f"followpoint-{index}.png"
                )
                for index in range(8)
            )
            if image is not None and image.get_width() > 1
        ]
        return images

    def _scaled_image(self, image, size):
        if image is None:
            return None

        size = (
            max(1, int(round(size[0]))),
            max(1, int(round(size[1])))
        )
        key = (id(image), size)
        cached = self.image_surface_cache.get(key)
        if cached is not None:
            return cached

        scaled = pygame.transform.smoothscale(image, size)
        self.image_surface_cache[key] = scaled
        return scaled

    def _scaled_square_image(self, image, diameter):
        diameter = max(1, int(round(diameter)))
        return self._scaled_image(
            image,
            (diameter, diameter)
        )

    def _rotated_image(self, image, angle):
        if image is None:
            return None

        key = ("rotated", id(image), round(float(angle), 1))
        cached = self.image_surface_cache.get(key)
        if cached is not None:
            return cached

        rotated = pygame.transform.rotozoom(
            image,
            angle,
            1.0
        )
        self.image_surface_cache[key] = rotated
        return rotated

    def _alpha_width(self, image, threshold=96):
        if image is None:
            return 0

        key = ("alpha_width", id(image), int(threshold))
        cached = self.image_surface_cache.get(key)
        if cached is not None:
            return cached

        min_x = image.get_width()
        max_x = -1
        for y in range(image.get_height()):
            for x in range(image.get_width()):
                if image.get_at((x, y)).a >= threshold:
                    min_x = min(min_x, x)
                    max_x = max(max_x, x)

        width = 0 if max_x < min_x else max_x - min_x + 1
        self.image_surface_cache[key] = width
        return width

    def _calculate_sliderball_diameter(self):
        sliderball_visible_diameter = max(
            1,
            (
                self.slider_path_radius
                - max(2, self.slider_path_radius * 0.07)
            )
            * 2
            * 0.98
        )
        sliderball_image = self.skin_images.get("sliderball")
        if sliderball_image is None:
            return sliderball_visible_diameter

        opaque_width = self._alpha_width(
            sliderball_image,
            threshold=16
        )
        if opaque_width <= 0:
            return sliderball_visible_diameter

        return sliderball_visible_diameter * (
            sliderball_image.get_width()
            / opaque_width
        )

    def _cropped_alpha_image(self, image):
        if image is None:
            return None

        key = ("alpha_crop", id(image))
        cached = self.image_surface_cache.get(key)
        if cached is not None:
            return cached

        rect = image.get_bounding_rect()
        if rect.width <= 0 or rect.height <= 0:
            self.image_surface_cache[key] = image
            return image

        cropped = image.subsurface(rect).copy()
        self.image_surface_cache[key] = cropped
        return cropped

    def _tinted_image(self, image, color):
        if image is None:
            return None

        key = (id(image), tuple(color[:3]))
        cached = self.tinted_surface_cache.get(key)
        if cached is not None:
            return cached

        tinted = image.copy()
        tint = pygame.Surface(
            tinted.get_size(),
            pygame.SRCALPHA
        )
        tint.fill((*color[:3], 255))
        tinted.blit(
            tint,
            (0, 0),
            special_flags=pygame.BLEND_RGBA_MULT
        )
        self.tinted_surface_cache[key] = tinted
        return tinted

    def _draw_image_centered(
        self,
        target,
        image,
        center,
        diameter=None,
        alpha=255
    ):
        if image is None:
            return False

        surface = image
        if diameter is not None:
            surface = self._scaled_square_image(
                image,
                diameter
            )

        self._blit_centered(
            target,
            surface,
            center,
            alpha=alpha
        )
        return True

    def _draw_hitcircle_skin(self, target, center, color, alpha=255):
        circle = self.skin_images.get("hitcircle")
        overlay = self.skin_images.get("hitcircle_overlay")
        if circle is None or overlay is None:
            return False

        diameter = self.scaled_radius * 2 * 1.12
        tinted = self._tinted_image(
            circle,
            color
        )
        self._draw_image_centered(
            target,
            tinted,
            center,
            diameter=diameter,
            alpha=alpha
        )
        self._draw_image_centered(
            target,
            overlay,
            center,
            diameter=diameter,
            alpha=alpha
        )
        return True

    def _draw_approach_skin(self, target, center, radius, alpha=255):
        image = self.skin_images.get("approach")
        if image is None:
            return False

        return self._draw_image_centered(
            target,
            image,
            center,
            diameter=radius * 2,
            alpha=alpha
        )

    def _add_miss_indicator(self, pos, show_time=None):
        self.miss_indicators.append({
            "pos": pos,
            "show_time": (
                self.current_time
                if show_time is None
                else show_time
            ),
            "start_time": self.current_time
        })

    def _register_slider_follow_miss(self, note, pos, early_release=False):
        if note.get("slider_follow_missed"):
            return

        note["slider_follow_missed"] = True
        result = 100 if early_release else 0
        if not early_release:
            self.combo = 0
        self.hit_counts[result] += 1
        self.judged_objects += 1
        self._update_health_target(result)
        if early_release:
            self._add_hit_result_indicator(note, 100)
        else:
            self._add_miss_indicator(pos)

    def _hit_input_held(self):
        return bool(self.hit_keys_held or self.hit_mouse_buttons_held)

    def _note_follow_anchor(self, note):
        if note["type"] == "slider":
            points = note.get("scaled_slider_points")
            if points:
                return points[-1]
        return self._note_screen_pos(note)

    def _note_judged_time(self, note):
        if note["type"] == "slider":
            return note.get("head_hit_time") or note.get("hit_time")
        return note.get("hit_time")

    def _draw_followpoints(self, target):
        frames = self.skin_images.get("followpoints", [])
        if not frames or len(self.notes) < 2:
            return

        start_index = max(
            0,
            bisect_left(
                self.note_times,
                self.current_time - 2200
            ) - 1
        )
        end_index = min(
            len(self.notes) - 1,
            bisect_right(
                self.note_times,
                self.current_time + self.approach_time + 250
            ) + 1
        )

        for index in range(start_index, end_index):
            note = self.notes[index]
            next_note = self.notes[index + 1]
            if note["type"] == "spinner" or next_note["type"] == "spinner":
                continue
            if next_note.get("new_combo"):
                continue

            gap = next_note["time"] - note["time"]
            if gap < 80 or gap > 1800:
                continue

            note_start = note.get(
                "start_time",
                note["time"] - self.approach_time
            )
            note_approach_len = max(1.0, note["time"] - note_start)
            next_start = next_note.get(
                "start_time",
                next_note["time"] - self.approach_time
            )
            next_approach_len = max(1.0, next_note["time"] - next_start)
            beat_length = max(
                120.0,
                float(
                    effective_beat_length_at(
                        self.timing_points,
                        next_note["time"]
                    )
                )
            )
            lead_time = min(
                gap * 0.98,
                max(
                    240.0,
                    min(
                        self.approach_time * 0.68,
                        beat_length * 1.05
                    )
                )
            )
            both_visible_time = max(
                note_start + (note_approach_len * 0.10),
                next_start + (next_approach_len * 0.015)
            )
            earliest_pre_hit_start = note["time"] - max(
                210.0,
                min(430.0, gap * 0.92, beat_length * 0.95)
            )
            latest_pre_hit_start = note["time"] - max(
                90.0,
                min(230.0, gap * 0.58)
            )
            pre_hit_start = max(
                both_visible_time,
                earliest_pre_hit_start,
                note_start
            )
            if pre_hit_start <= latest_pre_hit_start:
                start_time = pre_hit_start
            else:
                start_time = max(
                    both_visible_time,
                    note_start
                )
            judged_time = self._note_judged_time(next_note)
            fade_out_duration = max(
                38.0,
                min(92.0, gap * 0.12, beat_length * 0.12)
            )
            state = note.setdefault("followpoint_state", {})
            state_index = next_note.get("render_index", index + 1)
            if state.get("target") != state_index:
                state.clear()
                state["target"] = state_index

            natural_fade_start = next_note["time"] + 18.0
            requested_fade_start = (
                judged_time
                if judged_time is not None
                else natural_fade_start
            )
            if (
                self.current_time >= requested_fade_start
                and "fade_start" not in state
            ):
                state["fade_start"] = self.current_time

            fade_start = state.get("fade_start")
            if state.get("hidden"):
                continue

            end_time = (
                fade_start + fade_out_duration
                if fade_start is not None
                else natural_fade_start + fade_out_duration
            )
            if self.current_time < start_time or self.current_time > end_time:
                if self.current_time > end_time:
                    state["hidden"] = True
                continue

            start = self._note_follow_anchor(note)
            end = self._note_screen_pos(next_note)
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            distance = (dx * dx + dy * dy) ** 0.5
            if distance < self.scaled_radius * 1.15:
                continue

            ux = dx / distance
            uy = dy / distance
            start = (
                start[0] + ux * self.scaled_radius * 0.92,
                start[1] + uy * self.scaled_radius * 0.92
            )
            end = (
                end[0] - ux * self.scaled_radius * 0.92,
                end[1] - uy * self.scaled_radius * 0.92
            )
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            distance = (dx * dx + dy * dy) ** 0.5
            if distance <= 0:
                continue

            angle = -math.degrees(
                math.atan2(uy, ux)
            )
            elapsed = self.current_time - start_time
            appear_duration = max(
                82.0,
                min(
                    280.0,
                    gap * 0.50,
                    beat_length * 0.48,
                    max(82.0, (next_note["time"] - start_time) * 0.36)
                )
            )
            progress = self._clamp01(elapsed / appear_duration)
            fade_in_duration = max(
                35.0,
                min(95.0, appear_duration * 0.34, beat_length * 0.16)
            )
            fade_in = self._clamp01(elapsed / fade_in_duration)
            fade_out = 1.0
            if fade_start is not None:
                fade_out_progress = self._clamp01(
                    (self.current_time - fade_start) / fade_out_duration
                )
                fade_out = (1.0 - fade_out_progress) ** 1.65
            alpha = int(
                255
                * fade_in
                * fade_out
            )
            if alpha <= 0:
                continue

            followpoint_radius = self.followpoint_visual_radius
            segment_width = max(22, int(followpoint_radius * 0.86))
            spacing = max(10, int(segment_width * 0.48))
            count = max(1, int(distance / spacing))
            frame = self._cropped_alpha_image(frames[-1])
            size = (
                int(segment_width * 1.42),
                max(9, int(followpoint_radius * 0.22))
            )
            scaled = self._scaled_image(frame, size)
            if scaled is None:
                continue
            rotated = self._rotated_image(
                scaled,
                angle
            )
            if rotated is None:
                continue

            for point_index in range(1, count + 1):
                t = point_index / (count + 1)
                sequence_smoothing = max(
                    1.0,
                    min(2.35, gap / 180.0)
                )
                appear = self._clamp01(
                    (progress * (count + 7) - point_index + 2)
                    / sequence_smoothing
                )
                point_fade = appear
                point_alpha = int(alpha * point_fade)
                if point_alpha <= 0:
                    continue

                center = (
                    start[0] + dx * t,
                    start[1] + dy * t
                )
                self._blit_centered(
                    target,
                    rotated,
                    center,
                    alpha=point_alpha
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

    def _load_background_surface(self):
        background = self.beatmap.get("background")
        if not background:
            return

        path = os.path.join(
            self.beatmap["path"],
            background.replace("\\", os.sep)
        )
        if not os.path.exists(path):
            return

        try:
            self.background_source = pygame.image.load(path).convert()
        except pygame.error:
            self.background_source = None

    def _scaled_background(self, screen_size):
        source = getattr(self, "background_source", None)
        if source is None:
            return None

        if (
            self.background_surface is not None
            and self.background_surface_size == screen_size
        ):
            return self.background_surface

        screen_w, screen_h = screen_size
        image_w, image_h = source.get_size()
        if image_w <= 0 or image_h <= 0:
            return None

        scale = max(screen_w / image_w, screen_h / image_h)
        target_size = (
            max(1, int(image_w * scale)),
            max(1, int(image_h * scale))
        )
        scaled = pygame.transform.smoothscale(
            source,
            target_size
        ).convert()
        position = (
            (screen_w - target_size[0]) // 2,
            (screen_h - target_size[1]) // 2
        )
        dim_overlay = pygame.Surface(
            target_size,
            pygame.SRCALPHA
        )
        dim_overlay.fill((0, 0, 0, self.background_dim_alpha))
        scaled.blit(dim_overlay, (0, 0))

        self.background_surface = (scaled, position)
        self.background_surface_size = screen_size
        return self.background_surface

    def _draw_background(self, screen):
        background = self._scaled_background(
            screen.get_size()
        )
        if background is None:
            screen.fill((5, 5, 5))
            return

        surface, position = background
        screen.blit(surface, position)

    def _toggle_pause(self):
        if self.failed:
            return

        now = pygame.time.get_ticks()
        if not self.paused:
            self.paused = True
            self.pause_started_at = now
            if self.music_started:
                pygame.mixer.music.pause()
            return

        paused_duration = now - (self.pause_started_at or now)
        self.paused = False
        self.pause_started_at = None
        if self.start_time is not None:
            self.start_time += paused_duration
        if self.pre_music_started_at is not None:
            self.pre_music_started_at += paused_duration
        self.ready_start_time += paused_duration
        if self.music_started:
            pygame.mixer.music.unpause()

    def _skip_intro(self):
        if (
            self.intro_skip_used
            or self.intro_skip_ms <= 0
            or not self.music_started
            or self.current_time >= self.intro_skip_ms
        ):
            return

        new_start = start_music(
            self.music_path,
            self.intro_skip_ms
        )
        if new_start is None:
            return

        self.start_time = new_start
        self.current_time = pygame.time.get_ticks() - self.start_time
        self.next_note_index = 0
        self.active_notes.clear()
        self.intro_skip_used = True

    def _fail(self):
        if self.failed:
            return
        self.failed = True
        self.paused = False
        self.fail_time = pygame.time.get_ticks()
        pygame.mixer.music.stop()
        pygame.mouse.set_visible(True)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if self.failed:
                if event.key == pygame.K_ESCAPE:
                    self.game.scene_manager.pop_scene()
                    return
                if event.key == pygame.K_r:
                    self.game.scene_manager.set_scene(
                        GameplayScene(self.game, self.beatmap)
                    )
                    return

            if event.key in (pygame.K_ESCAPE, pygame.K_p):
                self._toggle_pause()
                return

            if self.paused:
                if event.key in (pygame.K_BACKSPACE, pygame.K_RETURN):
                    self.game.scene_manager.pop_scene()
                    return
                return

            if event.key == pygame.K_SPACE:
                self._skip_intro()
                return

        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.skip_button_rect is not None
            and self.skip_button_rect.collidepoint(event.pos)
        ):
            self._skip_intro()
            return

        self.input_controller.handle_event(event)

    def update(self, dt):
        self.cursor_renderer.update(
            dt,
            self.game.mouse_pos
        )

        if self.failed or self.paused:
            return

        if not self.music_started:
            ready_elapsed = (
                pygame.time.get_ticks()
                - self.ready_start_time
            )
            total_intro_delay = (
                self.pre_start_delay_ms
                + self.post_ready_delay_ms
            )
            if ready_elapsed < total_intro_delay:
                return

            if self.pre_music_lead_in_ms > 0:
                if self.pre_music_started_at is None:
                    self.pre_music_started_at = pygame.time.get_ticks()

                lead_elapsed = (
                    pygame.time.get_ticks()
                    - self.pre_music_started_at
                )
                if lead_elapsed < self.pre_music_lead_in_ms:
                    self.current_time = lead_elapsed - self.pre_music_lead_in_ms
                    self.next_note_index = activate_due_notes(
                        self.notes,
                        self.active_notes,
                        self.next_note_index,
                        self.current_time,
                        self.approach_time
                    )
                    return

            self.start_time = start_music(
                self.music_path
            )
            if self.start_time is None:
                self.start_time = pygame.time.get_ticks()

            self.music_started = True

        if self.start_time is not None:

            self.current_time = (
                pygame.time.get_ticks()
                - self.start_time
            )

        self.target_health = apply_health_drain(
            self.target_health,
            dt,
            self.hp
        )
        health_speed = min(1.0, dt * 7.0)
        self.health += (
            self.target_health - self.health
        ) * health_speed

        if self.health <= 0.001:
            self._fail()
            return

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

        for note in self.active_notes:
            if note["type"] == "spinner":
                self.spinner_manager.update(
                    note,
                    self.current_time,
                    dt,
                    self.game.mouse_pos
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

    def _precompute_note_positions(self):
        for note in self.notes:
            note["scaled_pos"] = (
                self.object_offset_x + (note["x"] * self.object_scale),
                self.object_offset_y + (note["y"] * self.object_scale)
            )

    def _build_overlay_dirty_rect(self):
        margin = int(
            max(
                self.scaled_radius * 4.4,
                self.slider_follow_radius,
                self.slider_path_radius * 2.0
            )
        )
        screen_rect = pygame.Rect(
            0,
            0,
            self.game.WIDTH,
            self.game.HEIGHT
        )
        return pygame.Rect(self.playfield_rect).inflate(
            margin * 2,
            margin * 2
        ).clip(screen_rect)

    def _note_screen_pos(self, note):
        pos = note.get("scaled_pos")
        if pos is not None:
            return pos

        pos = self.scale_position(
            note["x"],
            note["y"]
        )
        note["scaled_pos"] = pos
        return pos

    def render(self, screen):

        self._draw_background(screen)

        if not self.music_started and self.pre_music_started_at is None:
            self._render_ready(screen)
            self.cursor_renderer.draw(screen, self.game.mouse_pos)
            if self.paused:
                self._draw_pause_overlay(screen)
            return

        if self.music_started:
            self.hud_renderer.draw(
                screen,
                self.beatmap,
                self.current_time,
                self.score,
                self._accuracy(),
                self.combo,
                self.health
            )

        pygame.draw.rect(

            screen,

            (40, 40, 40),

            self.playfield_rect,

            3
        )

        # Camada transparente para permitir alpha real (fade in/out suave).
        screen_size = screen.get_size()
        if self.overlay_surface is None or self.overlay_surface_size != screen_size:
            self.overlay_surface = pygame.Surface(
                screen_size,
                pygame.SRCALPHA
            ).convert_alpha()
            self.overlay_surface_size = screen_size

        overlay = self.overlay_surface
        overlay.fill((0, 0, 0, 0), self.overlay_dirty_rect)

        self._draw_followpoints(overlay)

        for note in self.active_notes:

            if note["type"] == "spinner":
                self.spinner_renderer.draw(overlay, note)
                continue

            scaled_x, scaled_y = self._note_screen_pos(note)
            shake_x, shake_y = self._notelock_shake_offset(note)
            scaled_x += shake_x
            scaled_y += shake_y
            fail_offset_y, fail_alpha_factor = self._fail_object_motion()
            scaled_y += fail_offset_y

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
            alpha = int(alpha * fail_alpha_factor)
            slider_ball_alpha = 0
            slider_track_alpha = alpha
            if note["type"] == "slider":
                slider_ball_alpha = self._slider_ball_alpha(note)
                slider_track_alpha = self._slider_track_alpha(note)

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
                self.scaled_radius * 1.12
                + (
                    progress
                    * self.scaled_radius
                    * 2.82
                )
            )

            draw_note_approach = not (
                note["type"] == "slider"
                and note.get("head_hit_result") is not None
            )

            if alpha > 0 and draw_note_approach:
                approach_alpha = int(
                    alpha * (0.42 + (0.58 * self._clamp01(progress)))
                )
                if not self._draw_approach_skin(
                    overlay,
                    (scaled_x, scaled_y),
                    approach_radius,
                    alpha=approach_alpha
                ):
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
                    self.effects_renderer.draw_miss_pop(
                        overlay,
                        (scaled_x, scaled_y),
                        scaled_hit_radius,
                        circle_color,
                        alpha=pop_alpha
                    )
                elif hit_result == 300:
                    hit_time = note.get("hit_time", self.current_time)
                    self.effects_renderer.draw_hit_explosion(
                        overlay,
                        (scaled_x, scaled_y),
                        scaled_hit_radius,
                        circle_color,
                        hit_time,
                        alpha=alpha
                    )
                else:
                    if not self._draw_hitcircle_skin(
                        overlay,
                        (scaled_x, scaled_y),
                        circle_color,
                        alpha=alpha
                    ):
                        self._draw_aa_circle(
                            overlay,
                            (scaled_x, scaled_y),
                            scaled_hit_radius,
                            fill_color=circle_color,
                            outline_color=(255, 255, 255),
                            outline_width=3,
                            alpha=alpha
                        )

                number_alpha = 0
                if hit_result not in (50, 100):
                    number_base_alpha = 255 if hit_result == 0 else alpha
                    number_alpha = self._combo_number_alpha(
                        note,
                        number_base_alpha
                    )
                if number_alpha > 0:
                    self.effects_renderer.draw_combo_number(
                        overlay,
                        str(note["combo_index"]),
                        (scaled_x, scaled_y),
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

                if shake_x or shake_y:
                    render_slider_points = [
                        (x + shake_x, y + shake_y)
                        for x, y in slider_points
                    ]
                    slider_cache_key = None
                else:
                    render_slider_points = slider_points
                    slider_cache_key = note.get("render_index")

                if fail_offset_y:
                    render_slider_points = [
                        (x, y + fail_offset_y)
                        for x, y in render_slider_points
                    ]
                    slider_cache_key = None

                self.slider_renderer.draw(
                    overlay,
                    render_slider_points,
                    alpha=slider_track_alpha,
                    object_color=note.get("combo_color", (0, 150, 255)),
                    draw_head_marker=(
                        note.get("head_hit_result") is None
                        and self.current_time < note["time"]
                    ),
                    draw_tail_marker=False,
                    cache_key=slider_cache_key,
                    repeat_count=note.get("repeat_count", 1),
                    draw_reverse_markers=True,
                    slider_start_time=note["time"],
                    span_duration=note.get("span_duration", 0.0)
                )

                head_result = note.get("head_hit_result")
                head_alpha = self._slider_head_alpha(note, alpha)
                slider_head_pos = render_slider_points[0]

                if head_result is None and head_alpha > 0:
                    if not self._draw_hitcircle_skin(
                        overlay,
                        slider_head_pos,
                        note.get("combo_color", (0, 150, 255)),
                        alpha=head_alpha
                    ):
                        self._draw_aa_circle(
                            overlay,
                            slider_head_pos,
                            self.slider_head_radius,
                            fill_color=note.get("combo_color", (0, 150, 255)),
                            outline_color=(255, 255, 255),
                            outline_width=3,
                            alpha=head_alpha
                        )
                    self.effects_renderer.draw_combo_number(
                        overlay,
                        str(note["combo_index"]),
                        slider_head_pos,
                        alpha=head_alpha
                    )
                elif head_result == 0 and head_alpha > 0:
                    pop_alpha = self._miss_pop_alpha(note)
                    self.effects_renderer.draw_miss_pop(
                        overlay,
                        slider_head_pos,
                        self.slider_head_radius,
                        note.get("combo_color", (0, 150, 255)),
                        alpha=pop_alpha
                    )
                elif head_result == 300 and head_alpha > 0:
                    self.effects_renderer.draw_hit_explosion(
                        overlay,
                        slider_head_pos,
                        self.slider_head_radius,
                        note.get("combo_color", (0, 150, 255)),
                        note.get("head_hit_time", self.current_time),
                        alpha=head_alpha
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
                        render_slider_points,
                        ball_dist,
                        cumulative,
                        total_length
                    )

                    follow_radius = self.slider_follow_radius
                    show_slider_follow = (
                        note.get("head_hit")
                        and self.current_time <= note["time"] + slider_total_duration
                    )
                    if (
                        show_slider_follow
                        and not note.get("slider_follow_missed")
                    ):
                        mouse_x, mouse_y = self.game.mouse_pos
                        dx = mouse_x - ball_pos[0]
                        dy = mouse_y - ball_pos[1]
                        cursor_outside = (
                            (dx * dx + dy * dy) ** 0.5 > follow_radius
                        )
                        input_released = not self._hit_input_held()
                        outside = cursor_outside or input_released
                        remaining = (
                            note["time"]
                            + slider_total_duration
                            - self.current_time
                        )
                        tolerance_ms = max(
                            120,
                            min(240, span_duration * 0.12)
                        )
                        if outside:
                            if remaining <= tolerance_ms:
                                note["slider_follow_released_near_end"] = True
                            else:
                                outside_since = note.get(
                                    "slider_follow_outside_since"
                                )
                                if outside_since is None:
                                    note["slider_follow_outside_since"] = (
                                        self.current_time
                                    )
                                    note["slider_follow_outside_reason"] = (
                                        "cursor"
                                        if cursor_outside
                                        else "release"
                                    )
                                elif self.current_time - outside_since > 250:
                                    if cursor_outside:
                                        note[
                                            "slider_follow_outside_reason"
                                        ] = "cursor"
                                    early_release = (
                                        note.get(
                                            "slider_follow_outside_reason"
                                        )
                                        == "release"
                                    )
                                    self._register_slider_follow_miss(
                                        note,
                                        ball_pos,
                                        early_release=early_release
                                    )
                        else:
                            note["slider_follow_outside_since"] = None
                            note["slider_follow_outside_reason"] = None

                    outside_since = note.get("slider_follow_outside_since")
                    follow_alpha = slider_ball_alpha * 0.82
                    if outside_since is not None:
                        outside_elapsed = self.current_time - outside_since
                        follow_alpha *= 1.0 - self._clamp01(
                            outside_elapsed / 250
                        )

                    if show_slider_follow:
                        self._draw_image_centered(
                            overlay,
                            self.skin_images.get("sliderballfollow"),
                            ball_pos,
                            diameter=follow_radius * 2,
                            alpha=int(follow_alpha)
                        )

                    sliderball_image = self.skin_images.get("sliderball")

                    if not self._draw_image_centered(
                        overlay,
                        sliderball_image,
                        ball_pos,
                        diameter=self.sliderball_diameter,
                        alpha=slider_ball_alpha
                    ):
                        self._draw_aa_circle(
                            overlay,
                            ball_pos,
                            int(self.slider_path_radius * 0.68),
                            fill_color=(255, 255, 255),
                            outline_color=(255, 255, 255),
                            outline_width=2,
                            alpha=slider_ball_alpha
                        )

        self.miss_indicators = [
            indicator
            for indicator in self.miss_indicators
            if self.current_time < indicator["show_time"] + self.miss_indicator_duration
        ]
        self.hit_result_indicators = [
            indicator
            for indicator in self.hit_result_indicators
            if self.current_time < indicator["show_time"] + self.miss_indicator_duration
        ]

        for indicators in (
            self.miss_indicators,
            self.hit_result_indicators
        ):
            for indicator in indicators:
                if self.current_time < indicator["show_time"]:
                    continue

                elapsed = self.current_time - indicator["show_time"]
                progress = self._clamp01(
                    elapsed / self.miss_indicator_duration
                )
                eased = 1.0 - (progress ** 0.7)
                alpha = int(255 * eased)
                x, y = indicator["pos"]
                y += int(elapsed * 0.03)

                result = indicator.get("result", 0)
                image = self.skin_images.get(
                    "hit100" if result == 100
                    else "hit50" if result == 50
                    else "miss"
                )
                if image is not None:
                    self._draw_image_centered(
                        overlay,
                        image,
                        (x, y),
                        diameter=self.scaled_radius * 1.28,
                        alpha=alpha
                    )
                    continue

                size = int(self.scaled_radius * 0.30)
                half = max(1, size // 2)
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

        screen.blit(
            overlay,
            self.overlay_dirty_rect,
            self.overlay_dirty_rect
        )

        self.cursor_renderer.draw(screen, self.game.mouse_pos)
        self._draw_skip_button(screen)
        if self.paused:
            self._draw_pause_overlay(screen)
        elif self.failed:
            self._draw_lose_overlay(screen)

    def _fail_object_motion(self):
        if not self.failed or self.fail_time is None:
            return 0, 1.0

        elapsed = pygame.time.get_ticks() - self.fail_time
        progress = self._clamp01(elapsed / 1650.0)
        eased = progress * progress * (3.0 - 2.0 * progress)
        fall = int((self.game.HEIGHT * 0.28) * eased)
        alpha = 1.0 - (progress * 0.72)
        return fall, max(0.20, alpha)

    def _draw_skip_button(self, screen):
        self.skip_button_rect = None
        if (
            self.intro_skip_used
            or self.intro_skip_ms <= 0
            or not self.music_started
            or self.current_time >= self.intro_skip_ms
            or self.paused
            or self.failed
        ):
            return

        text = self.small_overlay_font.render("skip intro", True, (245, 248, 255))
        pad_x = 14
        pad_y = 8
        rect = pygame.Rect(
            0,
            0,
            text.get_width() + pad_x * 2,
            text.get_height() + pad_y * 2
        )
        rect.midbottom = (
            self.game.WIDTH // 2,
            self.game.HEIGHT - 28
        )
        self.skip_button_rect = rect
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            surface,
            (18, 18, 28, 130),
            surface.get_rect(),
            border_radius=rect.height // 2
        )
        pygame.draw.rect(
            surface,
            (255, 255, 255, 92),
            surface.get_rect(),
            1,
            border_radius=rect.height // 2
        )
        surface.blit(text, (pad_x, pad_y))
        screen.blit(surface, rect)

    def _draw_center_overlay(self, screen, title, subtitle, accent):
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        alpha = 178
        overlay_factor = 1.0
        if self.failed and self.fail_time is not None:
            overlay_factor = self._clamp01(
                (pygame.time.get_ticks() - self.fail_time) / 520.0
            )
            alpha = int(178 * overlay_factor)
        shade.fill((0, 0, 0, alpha))
        screen.blit(shade, (0, 0))

        panel_w = int(min(screen.get_width() * 0.52, 640))
        panel_h = int(min(screen.get_height() * 0.30, 230))
        panel = pygame.Rect(0, 0, panel_w, panel_h)
        panel.center = (screen.get_width() // 2, screen.get_height() // 2)
        panel_surface = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(
            panel_surface,
            (16, 15, 30, int(232 * overlay_factor)),
            panel_surface.get_rect(),
            border_radius=14
        )
        pygame.draw.rect(
            panel_surface,
            (*accent[:3], int(255 * overlay_factor)),
            panel_surface.get_rect(),
            3,
            border_radius=14
        )

        title_surface = self.title_overlay_font.render(title, True, (255, 255, 255))
        subtitle_surface = self.small_overlay_font.render(subtitle, True, (230, 235, 250))
        title_surface.set_alpha(int(255 * overlay_factor))
        subtitle_surface.set_alpha(int(255 * overlay_factor))
        panel_surface.blit(
            title_surface,
            title_surface.get_rect(center=(panel_w // 2, int(panel_h * 0.38)))
        )
        panel_surface.blit(
            subtitle_surface,
            subtitle_surface.get_rect(center=(panel_w // 2, int(panel_h * 0.66)))
        )
        screen.blit(panel_surface, panel)

    def _draw_pause_overlay(self, screen):
        self._draw_center_overlay(
            screen,
            "PAUSE",
            "ESC/P: resume   Enter/Backspace: song select",
            (120, 170, 255)
        )

    def _draw_lose_overlay(self, screen):
        self._draw_center_overlay(
            screen,
            "FAILED",
            "R: retry   ESC: back to song select",
            (255, 92, 116)
        )

    def _render_ready(self, screen):
        pygame.draw.rect(
            screen,
            (40, 40, 40),
            (
                self.playfield_rect
            ),
            3
        )

        remaining = max(
            0,
            self.pre_start_delay_ms
            - (pygame.time.get_ticks() - self.ready_start_time)
        )
        if remaining <= 0:
            return

        dots = "." * (1 + int((self.pre_start_delay_ms - remaining) / 400) % 3)
        text = self.font.render(
            f"Ready{dots}",
            True,
            (255, 255, 255)
        )
        rect = text.get_rect(
            center=(
                self.game.WIDTH // 2,
                self.game.HEIGHT // 2
            )
        )
        screen.blit(text, rect)

    def destroy(self):

        pygame.mixer.music.stop()

        self.game.disable_raw_mouse()

        pygame.mouse.set_visible(True)
