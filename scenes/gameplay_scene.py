import os
import math
import time
from concurrent.futures import ThreadPoolExecutor
from bisect import bisect_left, bisect_right

import pygame

from scenes.base_scene import BaseScene
from core.audio import (
    adjust_playback_clock_for_pause,
    find_audio_file,
    get_last_start_offset_ms,
    preload_music,
    start_music,
    get_playback_time_ms
)
from core.assets import asset_path, load_image
from core.fonts import rounded_font
from core.utils import is_object_visible
from core.gameplay import hit_result_for_delta
from core.health import apply_health_drain, apply_health_result
from core.hit_detection import find_best_hit_object
from core.gameplay_input import GameplayInputController
from core.gameplay_notes import (
    clone_notes_with_combo_data,
    prepare_note_lifecycle
)
from core.performance import (
    AUDIO_OFFSET_MS,
    HIT_ERROR_DISPLAY_OFFSET_MS
)
from core.scoring import ScoreLedger
from core.beatmap_timing import (
    effective_beat_length_at,
    slider_velocity_multiplier_at
)
from core.gameplay_state import (
    activate_due_notes,
    judge_missed_notes,
    prune_inactive_notes
)
from core.spinner import SpinnerManager
from rendering.effects import GameplayEffectsRenderer
from rendering.hud import GameplayHUDRenderer
from rendering.primitives import (
    aa_circle_surface,
    blit_centered,
    draw_aa_circle,
    draw_centered_text
)
from rendering.render_backend import PygameRenderBackend
from rendering.sliders import (
    SliderRenderer,
    can_render_track_pixels,
    render_track_surface_pixels,
    surface_from_track_pixels
)
from rendering.spinner import SpinnerRenderer


class GameplayScene(BaseScene):
    draws_own_cursor = False
    prefer_low_latency_pacing = True
    uses_ui = False
    _sound_cache = {}

    GAMEPLAY_OBJECT_SCALE = 0.97335
    GAMEPLAY_OBJECT_ALPHA_SCALE = 0.86
    HITOBJECT_VISUAL_ALPHA_SCALE = 0.82
    HITCIRCLE_ALPHA_BOOST = 1.23
    FOLLOWPOINT_THICKNESS_SCALE = 0.85
    HITOBJECT_FADE_IN_DURATION_SCALE = 0.42
    FIRST_OBJECT_FADE_IN_MIN_MS = 260
    FIRST_OBJECT_FADE_IN_MAX_MS = 420
    APPROACH_SUPERSAMPLE_SIZE = 768
    APPROACH_RADIUS_EXTRA_SCALE = 3.35
    SLIDERBALL_ALPHA_THRESHOLD = 96
    SLIDERBALL_VISIBLE_SCALE = 0.98
    STACK_DISTANCE_OSU = 3.0

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

        self.font = rounded_font(32, bold=False)

        self.music_started = False
        self.music_path = None

        self.start_time = None
        self.current_time = 0
        self.music_playback_offset_ms = 0.0
        self.music_sync_correction_ms = 0.0
        self.music_sync_target_correction_ms = 0.0
        self.music_sync_last_drift_ms = 0.0
        self.music_sync_last_update_tick_ms = 0.0
        self.music_sync_slew_rate = 0.18
        self.music_sync_snap_threshold_ms = 240.0
        self.audio_offset_ms = float(AUDIO_OFFSET_MS)
        self.hit_error_display_offset_ms = float(HIT_ERROR_DISPLAY_OFFSET_MS)
        self.ready_start_time = pygame.time.get_ticks()
        self.pre_music_lead_in_ms = 0
        self.pre_music_started_at = None
        self.pre_start_delay_ms = 1500
        self.post_ready_delay_ms = 650

        combo_colors = self.DEFAULT_COMBO_COLORS
        self.game.beatmap_loader.ensure_notes_loaded(beatmap)
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
        self.slider_reveal_cache_keys = set()
        self.image_surface_cache = {}
        self.tinted_surface_cache = {}
        self.overlay_surface = None
        self.overlay_surface_size = None
        self.approach_overlay_surface = None
        self.approach_overlay_surface_size = None
        self.overlay_full_clear_frames = 4
        self.background_path = None
        self.background_load_attempted = False
        self.background_source = None
        self.background_surface = None
        self.background_surface_size = None
        self.background_surface_cache = {}
        self.render_backend = getattr(game, "render_backend", PygameRenderBackend())
        self.slider_surface_fallbacks_frame = 0
        self.slider_reveal_fallbacks_frame = 0
        self.slider_base_fallbacks_frame = 0
        self.background_dim_alpha = int(
            255
            * max(
                0,
                min(100, getattr(self.game, "gameplay_dim", 94))
            )
            / 100
        )

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
        self.object_alpha_scale = self.GAMEPLAY_OBJECT_ALPHA_SCALE
        self.slider_multiplier = (
            self.beatmap["difficulty"].get(
                "SliderMultiplier",
                1.4
            )
        )
        self.timing_points = (
            self.beatmap.get("timing_points", [])
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
        ) / 2

        self.slider_base_radius = int(
            round(self.circle_radius * self.scale)
        )

        if self.slider_base_radius < 8:
            self.slider_base_radius = 8

        self.slider_path_radius = int(self.slider_base_radius)
        if self.slider_path_radius < 10:
            self.slider_path_radius = 10

        self.scaled_radius = int(self.slider_path_radius)
        self.note_visual_radius = self.scaled_radius * 0.90

        self.followpoint_visual_radius = self.scaled_radius * 0.82

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

        # Precompute values that only change on resize
        self.approach_contact_padding = max(3.0, self.scaled_radius * 0.055)
        self.approach_contact_radius = (self.note_visual_radius * 1.12) + self.approach_contact_padding

        # Aproximação do comportamento do osu! para visibilidade:
        # fade-in durante o approach e fade-out logo após o hit.
        self.hit_fade_out_time = 380  # ms
        self.miss_fade_out_time = 150  # ms
        self.miss_pop_duration = 112  # ms
        self.hit_number_fade_out_time = 84  # ms
        self.hit_explosion_duration = 217  # ms
        self.slider_follow_return_grace_ms = 350  # ms
        self.slider_follow_button_grace_ms = 90  # ms
        self.slider_follow_tail_leniency_ms = 520  # ms
        self.slider_follow_visual_fade_ms = 900  # ms

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

        self.music_path = find_audio_file(
            self.beatmap["path"],
            self.beatmap.get("audio_filename")
        )
        self.music_preloaded = False
        self.audio_lead_in = int(self.beatmap.get("audio_lead_in", 0) or 0)
        self._load_background_surface()

        self.hit_window_300 = max(0.0, 79.5 - (6.0 * self.od))
        self.hit_window_100 = max(0.0, 139.5 - (8.0 * self.od))
        self.hit_window_50 = max(0.0, 199.5 - (10.0 * self.od))

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
        self.score_ledger = ScoreLedger(self.hit_counts)
        self.judged_objects = 0
        self.judgable_objects = len(self.notes)
        self.last_music_sync_check_ms = 0

        # Pré-computa o intervalo de visibilidade de cada objeto.
        # Isso permite desenhar com alpha/escala sem depender de "sumir instantâneo".
        prepare_note_lifecycle(
            self.notes,
            self.approach_time,
            self.hit_fade_out_time,
            self.timing_points,
            self.slider_multiplier
        )
        self._apply_intro_lead_in()
        self._precompute_note_positions()
        self._apply_stack_offsets()
        self._precompute_stream_readability()
        self.first_object_visual_time = min(
            (
                note.get("start_time", note["time"] - self.approach_time)
                for note in self.notes
            ),
            default=0
        )
        self.first_object_time = min(
            (
                note["time"]
                for note in self.notes
            ),
            default=0
        )
        self.first_object_cache_window_ms = max(
            5600,
            int(self.approach_time + 4200)
        )
        self.first_object_cache_horizon_ms = int(
            self.first_object_time + self.first_object_cache_window_ms
        )
        self.first_object_fade_in_ms = max(
            self.FIRST_OBJECT_FADE_IN_MIN_MS,
            min(
                self.FIRST_OBJECT_FADE_IN_MAX_MS,
                int(self.approach_time * 0.30)
            )
        )

        self.slider_renderer = SliderRenderer(self)
        self.slider_cache_notes = [
            note
            for note in self.notes
            if note["type"] == "slider"
        ]
        self.next_slider_cache_index = 0
        self.slider_cache_cooldown_until = 0
        self.slider_precache_complete = not self.slider_cache_notes
        self.slider_cache_executor = (
            ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="pyosu-slider-cache"
            )
            if can_render_track_pixels()
            else None
        )
        self.slider_cache_futures = {}
        self.slider_cache_failed = set()
        self.slider_geometry_notes = self.slider_cache_notes
        self.next_slider_geometry_index = 0
        self.slider_geometry_complete = not self.slider_geometry_notes
        self.slider_reveal_prewarm_cursor = 0
        self.initial_slider_cache_horizon_ms = max(
            9000,
            self.first_object_cache_horizon_ms,
            int(self.approach_time + 9000)
        )
        self.startup_critical_notes = [
            note
            for note in self.notes
            if note["time"] <= self.first_object_cache_horizon_ms
        ]
        self.startup_critical_slider_notes = [
            note
            for note in self.startup_critical_notes
            if note["type"] == "slider"
        ]
        self.circle_number_font = rounded_font(32, bold=True)

        self.circle_number_font = rounded_font(28, bold=True)
        self.effects_renderer = GameplayEffectsRenderer(self)
        self.hud_renderer = GameplayHUDRenderer(self.font)
        self.hud_start_time = None
        self.hud_fade_in_duration = 90
        self.skin_images = self._load_skin_images()
        self.button_image = self._load_image("button.png")
        self.button_surface_cache = {}
        self.followpoint_segment_surface = (
            self._build_followpoint_segment_surface()
        )
        self._reset_followpoint_connections()
        self.hit_sound = self._load_hit_sound()
        self.fail_sound = self._load_fail_sound()
        self.sliderball_diameter = self._calculate_sliderball_diameter()
        self.sliderball_visible_diameter = getattr(
            self,
            "sliderball_visible_diameter",
            self.sliderball_diameter
        )
        self.skin_cache_warm_jobs = self._build_skin_cache_warm_jobs()
        self.skin_cache_warm_index = 0
        self.skin_cache_warm_complete = not self.skin_cache_warm_jobs
        self.surface_precache_jobs = self._build_gameplay_surface_precache_jobs()
        self.surface_precache_index = 0
        self.surface_precache_complete = not self.surface_precache_jobs

        self.miss_indicators = []
        self.hit_result_indicators = []
        self.hit_error_markers = []
        self._indicator_pool = []
        self._marker_pool = []
        self._approach_draws = []
        self.hit_error_marker_duration = 3000
        self.hit_keys_held = set()
        self.hit_mouse_buttons_held = set()
        self.input_controller = GameplayInputController(self)
        self.miss_indicator_delay = 25  # ms before the X appears
        self.miss_indicator_duration = 450  # ms X/50/100 stays visible
        self.paused = False
        self.failed = False
        self.completed = False
        self.fail_time = None
        self.fail_visual_time = None
        self.pause_visual_time = None
        self.fail_fall_duration_ms = 3600
        self.lose_overlay_delay_ms = 720
        self.pause_started_at = None
        self.intro_skip_ms = self._calculate_intro_skip_ms()
        self.intro_skip_used = False
        self.skip_button_rect = None
        self.skip_button_surface = None
        self.skip_button_surface_size = None
        self.skip_button_text_surface = None
        self.spinner_bonus_text_surface = None
        self.spinner_pass_text_surface = None
        self.center_overlay_cache = {}
        self.text_surface_cache = {}
        self.center_overlay_shade = None
        self.center_overlay_shade_size = None
        self.center_overlay_buttons = []
        self.center_overlay_button_hover = {}
        self.title_overlay_font = rounded_font(54, bold=True)
        self.medium_overlay_font = rounded_font(28, bold=True)
        self.small_overlay_font = rounded_font(18, bold=False)
        self.spinner_manager = SpinnerManager(self)
        self.spinner_renderer = SpinnerRenderer(self)
        self.spinner_renderer.reset_prewarm_jobs(self.notes)
        self.startup_cache_warm_budget_ms = 9000

    def _tinted_button_image(self, tint_color, size, hover=0.0):
        image = self.button_image
        if image is None:
            return None

        size = (
            max(1, int(round(size[0]))),
            max(1, int(round(size[1])))
        )
        hover_bucket = int(round(max(0.0, min(1.0, hover)) * 8))
        tint_key = None if tint_color is None else tuple(tint_color[:3])
        key = ("overlay_button", id(image), tint_key, size, hover_bucket)
        cached = self.button_surface_cache.get(key)
        if cached is not None:
            return cached

        source = pygame.transform.smoothscale(image, size).convert_alpha()
        if tint_color is None:
            surface = source
        else:
            surface = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
            hover_amount = hover_bucket / 8.0
            color = tuple(
                int(channel + (255 - channel) * 0.13 * hover_amount)
                for channel in tint_color[:3]
            )
            for y in range(size[1]):
                for x in range(size[0]):
                    alpha = source.get_at((x, y)).a
                    if alpha:
                        surface.set_at((x, y), (*color, alpha))
        self.button_surface_cache[key] = surface
        return surface

    def _boost_hitcircle_alpha(self, alpha):
        return max(0, min(255, int(alpha * self.HITCIRCLE_ALPHA_BOOST)))

    def _cached_text_surface(self, font, text, color):
        key = (font, text, tuple(color))
        cached = self.text_surface_cache.get(key)
        if cached is not None:
            return cached

        surface = font.render(text, True, color)
        if surface is not None:
            surface = surface.convert_alpha()
        self.text_surface_cache[key] = surface
        return surface

    def _accuracy(self):
        return self.score_ledger.accuracy()

    def _rank_grade(self):
        return self.score_ledger.rank()

    def _sync_score_fields(self):
        self.score = self.score_ledger.score
        self.combo = self.score_ledger.combo
        self.max_combo = self.score_ledger.max_combo

    def _register_judgement(
        self,
        result,
        *,
        visible=True,
        max_result=300,
        statistic=None
    ):
        self.score_ledger.add_judgement(
            result,
            visible=visible,
            max_result=max_result,
            statistic=statistic
        )

    def _break_combo(self):
        self.score_ledger.break_combo()
        self._sync_score_fields()

    def _add_combo_score(self, base_score, *, combo_weight=25, combo_bonus=True):
        self.score_ledger.add_combo_score(
            base_score,
            combo_weight=combo_weight,
            combo_bonus=combo_bonus
        )
        self._sync_score_fields()

    def _add_raw_score(self, amount):
        self.score_ledger.add_raw_score(amount)
        self._sync_score_fields()

    def _result_payload(self):
        return {
            "score": int(self.score),
            "accuracy": float(round(self._accuracy(), 2)),
            "combo": int(self.max_combo),
            "rank": self._rank_grade(),
            "hit_300": int(self.hit_counts.get(300, 0)),
            "hit_100": int(self.hit_counts.get(100, 0)),
            "hit_50": int(self.hit_counts.get(50, 0)),
            "misses": int(self.hit_counts.get(0, 0)),
            "accuracy_events": int(self.score_ledger.judgement_events),
            "accuracy_misses": int(self.score_ledger.miss_events),
            "slider_ticks_hit": int(
                self.score_ledger.statistics.get("slider_tick_hit", 0)
            ),
            "slider_ticks_missed": int(
                self.score_ledger.statistics.get("slider_tick_miss", 0)
            ),
            "slider_checkpoints": int(
                self.score_ledger.statistics.get("slider_checkpoint_hit", 0)
            ),
            "spinner_bonuses": int(
                self.score_ledger.statistics.get("spinner_bonus", 0)
            )
        }

    def _refresh_playfield_layout(self):
        self.scale = min(
            self.game.WIDTH / self.osu_base_width,
            self.game.HEIGHT / self.osu_base_height
        )
        self.offset_x = (
            self.game.WIDTH
            - (self.playfield_width * self.scale)
        ) / 2
        self.offset_y = (
            self.game.HEIGHT
            - (self.playfield_height * self.scale)
        ) / 2

        self.slider_base_radius = int(
            round(self.circle_radius * self.scale)
        )
        if self.slider_base_radius < 8:
            self.slider_base_radius = 8

        self.slider_path_radius = int(self.slider_base_radius)
        if self.slider_path_radius < 10:
            self.slider_path_radius = 10

        self.scaled_radius = int(self.slider_path_radius)
        self.note_visual_radius = self.scaled_radius * 0.90
        self.followpoint_visual_radius = self.scaled_radius * 0.82
        self.slider_head_radius = int(self.scaled_radius)
        self.slider_follow_radius = self.scaled_radius * 1.89
        self.safe_margin = (
            max(
                self.slider_head_radius,
                self.slider_path_radius
            ) + 16
        )
        self.usable_width = self.playfield_width * self.scale
        self.usable_height = self.playfield_height * self.scale
        self.object_scale = self.scale
        self.object_offset_x = self.offset_x

        # Precompute values that only change on resize
        self.approach_contact_padding = max(3.0, self.scaled_radius * 0.055)
        self.approach_contact_radius = (self.note_visual_radius * 1.12) + self.approach_contact_padding
        self.object_offset_y = self.offset_y
        self.playfield_rect = (
            self.offset_x,
            self.offset_y,
            self.playfield_width * self.scale,
            self.playfield_height * self.scale
        )
        self.overlay_dirty_rect = self._build_overlay_dirty_rect()

    def on_resize(self):
        self._refresh_playfield_layout()
        if hasattr(self.game, "enable_raw_mouse"):
            self.game.enable_raw_mouse(self.game.mouse_pos)

        for cache in (
            self.circle_surface_cache,
            self.slider_surface_cache,
            self.image_surface_cache,
            self.tinted_surface_cache
        ):
            cache.clear()

        for payload in list(self.slider_cache_futures.values()):
            future = payload[0]
            try:
                future.cancel()
            except Exception:
                pass
        self.slider_cache_futures.clear()
        self.slider_cache_failed.clear()
        self.slider_reveal_cache_keys.clear()
        self.next_slider_cache_index = 0
        self.slider_precache_complete = not self.slider_cache_notes
        self.slider_cache_cooldown_until = 0
        self.next_slider_geometry_index = 0
        self.slider_geometry_complete = not self.slider_geometry_notes
        self.slider_reveal_prewarm_cursor = 0

        geometry_keys = (
            "scaled_pos",
            "scaled_slider_points",
            "scaled_slider_cumulative",
            "scaled_slider_length",
            "slider_reveal_cache_keys",
            "slider_reveal_cache_cleared",
            "slider_reveal_prewarm_bucket",
            "slider_scorepoint_geometry_key",
            "followpoint_connection",
            "followpoint_state"
        )
        for note in self.notes:
            for key in geometry_keys:
                note.pop(key, None)

        self._precompute_note_positions()
        self._apply_stack_offsets()
        self._precompute_stream_readability()
        self.followpoint_segment_surface = (
            self._build_followpoint_segment_surface()
        )
        self._reset_followpoint_connections()
        self._warm_followpoint_connections(max_ms=1, max_items=32)
        self.sliderball_diameter = self._calculate_sliderball_diameter()
        self.sliderball_visible_diameter = getattr(
            self,
            "sliderball_visible_diameter",
            self.sliderball_diameter
        )
        self.skin_cache_warm_jobs = self._build_skin_cache_warm_jobs()
        self.skin_cache_warm_index = 0
        self.skin_cache_warm_complete = not self.skin_cache_warm_jobs
        self.surface_precache_jobs = self._build_gameplay_surface_precache_jobs()
        self.surface_precache_index = 0
        self.surface_precache_complete = not self.surface_precache_jobs

        self.overlay_surface = None
        self.overlay_surface_size = None
        self.approach_overlay_surface = None
        self.approach_overlay_surface_size = None
        self.background_surface = None
        self.background_surface_size = None
        self.center_overlay_shade = None
        self.center_overlay_shade_size = None
        self.center_overlay_cache.clear()
        self.skip_button_surface = None
        self.skip_button_surface_size = None
        self.button_surface_cache.clear()
        if hasattr(self.slider_renderer, "reverse_arrow_cache"):
            self.slider_renderer.reverse_arrow_cache.clear()
        if hasattr(self.spinner_renderer, "cache"):
            self.spinner_renderer.cache.clear()
            self.spinner_renderer.reset_prewarm_jobs(self.notes)

    def _apply_intro_lead_in(self):
        self.pre_music_lead_in_ms = 0
        if not self.notes:
            return

        first_note = self.notes[0]
        first_note_time = float(first_note["time"])
        first_visual_time = float(
            first_note.get(
                "start_time",
                first_note_time - self.approach_time
            )
        )
        minimum_lead_in = max(
            850,
            int(self.approach_time * 0.78)
        )
        visual_lead_in = max(
            0,
            int(-first_visual_time)
        )
        hit_lead_in = max(
            0,
            int(minimum_lead_in - first_note_time)
        )

        self.pre_music_lead_in_ms = max(visual_lead_in, hit_lead_in)

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
        post_skip_visual_lead = max(
            780,
            min(1350, int(self.approach_time * 0.62))
        )
        skip_to = max(0, int(first_visible_time - post_skip_visual_lead))
        if skip_to < 1200:
            return 0
        return skip_to

    def _add_hit_result(self, note, result):
        note["judged"] = True
        note["active"] = True
        note["hit_result"] = result
        note["hit_time"] = self.current_time
        self.judged_objects += 1
        self._register_judgement(
            result,
            visible=True,
            statistic=(
                "slider_head"
                if note["type"] == "slider"
                else "hitcircle"
            )
        )
        self._update_health_target(result)
        if result > 0:
            self._play_hit_sound()
            self._add_hit_error_marker(note, result)
        if result in (50, 100):
            self._add_hit_result_indicator(note, result)

        if note["type"] == "slider":
            note["head_hit"] = result > 0
            note["head_hit_result"] = result
            note["head_hit_time"] = self.current_time
            if result > 0:
                note["slider_follow_engaged"] = True
                note["slider_follow_outside_since"] = None
                note["slider_follow_outside_reason"] = None
                note["slider_hit_sound_index"] = 1

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
            self._break_combo()
            return

        if note["type"] == "circle":
            note["fade_out_start"] = self.current_time
            note["fade_out_duration"] = self.hit_explosion_duration
            note["end_time"] = self.current_time + self.hit_explosion_duration

        self._advance_combo()

        self._add_combo_score(result, combo_weight=25)

    def _advance_combo(self):
        self.score_ledger.advance_combo()
        self._sync_score_fields()

    def _borrow_indicator_payload(self):
        if self._indicator_pool:
            payload = self._indicator_pool.pop()
            payload.clear()
            return payload
        return {}

    def _add_hit_result_indicator(self, note, result):
        payload = self._borrow_indicator_payload()
        payload.update({
            "result": result,
            "pos": self._note_screen_pos(note),
            "show_time": self.current_time,
            "start_time": self.current_time
        })
        self.hit_result_indicators.append(payload)

    def _add_hit_error_marker(self, note, result):
        if note["type"] not in ("circle", "slider"):
            return

        if self._marker_pool:
            payload = self._marker_pool.pop()
            payload.update({
                "delta": (
                    self.current_time
                    - note["time"]
                    + self.hit_error_display_offset_ms
                ),
                "result": result,
                "time": self.current_time,
                "duration": self.hit_error_marker_duration
            })
            self.hit_error_markers.append(payload)
            return

        self.hit_error_markers.append({
            "delta": (
                self.current_time
                - note["time"]
                + self.hit_error_display_offset_ms
            ),
            "result": result,
            "time": self.current_time,
            "duration": self.hit_error_marker_duration
        })

    def _prune_hit_error_markers(self):
        markers = self.hit_error_markers
        write_index = 0
        cutoff_time = self.current_time
        for marker in markers:
            if cutoff_time < marker["time"] + marker["duration"]:
                markers[write_index] = marker
                write_index += 1
        del markers[write_index:]

    def _load_hit_sound(self):
        candidates = (
            asset_path("normal-hitnormal.wav", "spinner"),
            asset_path("normal-hitclap.wav", "spinner"),
            asset_path("normal-hitfinish.wav", "spinner")
        )
        for path in candidates:
            if not path.exists():
                continue
            cache_key = str(path)
            cached = self._sound_cache.get(cache_key)
            if cached is not None:
                cached.set_volume(0.145)
                return cached
            try:
                sound = pygame.mixer.Sound(str(path))
                sound.set_volume(0.145)
                self._sound_cache[cache_key] = sound
                return sound
            except pygame.error:
                continue
        return None

    def _play_hit_sound(self):
        if self.hit_sound is None:
            return
        try:
            self.hit_sound.play()
        except pygame.error:
            pass

    def _load_fail_sound(self):
        path = asset_path("failsound.wav", "failsound")
        if not path.exists():
            return None
        cache_key = str(path)
        cached = self._sound_cache.get(cache_key)
        if cached is not None:
            cached.set_volume(0.72)
            return cached
        try:
            sound = pygame.mixer.Sound(str(path))
            sound.set_volume(0.72)
            self._sound_cache[cache_key] = sound
            return sound
        except pygame.error:
            return None

    def _play_fail_sound(self):
        if self.fail_sound is None:
            return
        try:
            self.fail_sound.play()
        except pygame.error:
            pass

    def _add_spinner_bonus_indicator(self, bonus_count, pos):
        payload = self._borrow_indicator_payload()
        payload.update({
            "result": "spinner_bonus",
            "bonus_count": bonus_count,
            "pos": pos,
            "show_time": self.current_time,
            "start_time": self.current_time
        })
        self.hit_result_indicators.append(payload)

    def _update_health_target(self, result):
        self.target_health = apply_health_result(
            self.target_health,
            result,
            self.hp
        )
        if self.target_health <= 0.001:
            self.health = 0.0
            self._fail()

    def _add_health_target(self, amount):
        if amount <= 0:
            return
        self.target_health = min(
            1.0,
            max(0.0, self.target_health + float(amount))
        )

    def _finish_spinner(self, note, result):
        if note.get("judged"):
            return

        note["judged"] = True
        note["hit_result"] = result
        note["hit_time"] = self.current_time
        note["fade_out_start"] = self.current_time
        note["fade_out_duration"] = 260
        note["end_time"] = self.current_time + note["fade_out_duration"]
        self.judged_objects += 1
        self._register_judgement(
            result,
            visible=True,
            statistic="spinner"
        )
        self._update_health_target(result)

        if result == 0:
            self._break_combo()
            self._add_miss_indicator(
                (
                    self.game.WIDTH // 2,
                    self.game.HEIGHT // 2
                ),
                show_time=self.current_time + self.miss_indicator_delay
            )
            return

        self._advance_combo()
        self._add_combo_score(result, combo_weight=25)
        self._play_hit_sound()

    def _add_spinner_bonus_score(self, bonus_count):
        self._add_raw_score(1000)
        self._advance_combo()
        self.score_ledger.statistics["spinner_bonus"] = (
            self.score_ledger.statistics.get("spinner_bonus", 0) + 1
        )

    def _hit_result_for_delta(self, delta):
        return hit_result_for_delta(
            delta,
            self.hit_window_300,
            self.hit_window_100,
            self.hit_window_50
        )

    def _early_hit_limit_ms(self):
        return self.hit_window_50

    def _note_can_receive_early_hit(self, note):
        return self.current_time >= note["time"] - self._early_hit_limit_ms()

    def event_tick(self, event):
        now = pygame.time.get_ticks()
        event_tick = getattr(event, "timestamp", None)
        if (
            event_tick is None
            or event_tick <= 0
            or abs(float(event_tick) - now) > 60000
        ):
            return now
        return float(event_tick)

    def event_music_time(self, event):
        return self.music_time_from_tick(self.event_tick(event))

    def music_time_from_tick(self, tick_ms):
        if self.start_time is None or not self.music_started:
            return self.current_time
        return max(
            -float(self.pre_music_lead_in_ms),
            self._clock_music_time_from_tick(tick_ms)
        )

    def _clock_music_time_from_tick(self, tick_ms):
        return (
            float(tick_ms)
            - float(self.start_time)
            + self.music_sync_correction_ms
            + self.audio_offset_ms
        )

    def _mixer_music_time(self):
        if not self.music_started:
            return None

        # Prefer playback clock from core.audio if available (higher-resolution)
        try:
            mixer_pos = get_playback_time_ms()
        except Exception:
            mixer_pos = None

        if mixer_pos is None:
            # fallback to pygame mixer position if available
            mixer_pos = pygame.mixer.music.get_pos()

        if mixer_pos is None or mixer_pos < 0:
            return None

        return (
            self.music_playback_offset_ms
            + float(mixer_pos)
            + self.audio_offset_ms
        )

    def _reset_music_sync_state(self):
        self.music_sync_correction_ms = 0.0
        self.music_sync_target_correction_ms = 0.0
        self.music_sync_last_drift_ms = 0.0
        self.music_sync_last_update_tick_ms = 0.0
        self.last_music_sync_check_ms = 0

    def _slew_music_sync_correction(self, tick_ms):
        target = float(self.music_sync_target_correction_ms)
        current = float(self.music_sync_correction_ms)
        delta = target - current
        if abs(delta) <= 0.001:
            self.music_sync_correction_ms = target
            self.music_sync_last_update_tick_ms = float(tick_ms)
            return

        previous_tick = float(self.music_sync_last_update_tick_ms or tick_ms)
        elapsed = max(0.0, float(tick_ms) - previous_tick)
        self.music_sync_last_update_tick_ms = float(tick_ms)

        max_step = max(0.20, elapsed * self.music_sync_slew_rate)
        if abs(delta) <= max_step:
            self.music_sync_correction_ms = target
            return

        self.music_sync_correction_ms = current + (
            max_step if delta > 0 else -max_step
        )

    def _update_music_sync(self, tick_ms=None):
        if self.start_time is None or not self.music_started:
            return self.current_time

        if tick_ms is None:
            tick_ms = pygame.time.get_ticks()

        clock_time = self._clock_music_time_from_tick(tick_ms)
        mixer_time = self._mixer_music_time()
        should_check_mixer = (
            mixer_time is not None
            and pygame.mixer.music.get_busy()
            and (
                self.last_music_sync_check_ms <= 0
                or tick_ms - self.last_music_sync_check_ms >= 72
            )
        )
        if should_check_mixer:
            self.last_music_sync_check_ms = tick_ms
            drift = mixer_time - clock_time
            self.music_sync_last_drift_ms = drift
            abs_drift = abs(drift)
            target = self.music_sync_correction_ms + drift
            if (
                abs_drift >= self.music_sync_snap_threshold_ms
                and not self.active_notes
            ):
                self.music_sync_correction_ms = target
                self.music_sync_target_correction_ms = target
            elif abs_drift >= 2.5:
                self.music_sync_target_correction_ms = target

        self._slew_music_sync_correction(tick_ms)
        clock_time = self._clock_music_time_from_tick(tick_ms)

        next_time = max(
            -float(self.pre_music_lead_in_ms),
            clock_time
        )
        if self.music_started and next_time < self.current_time:
            next_time = self.current_time
        self.current_time = next_time
        profiler = getattr(getattr(self, "game", None), "profiler", None)
        if profiler is not None and getattr(profiler, "enabled", False):
            profiler.set_metric(
                "music_sync_drift",
                round(float(self.music_sync_last_drift_ms), 2)
            )
            profiler.set_metric(
                "music_sync_correction",
                round(float(self.music_sync_correction_ms), 2)
            )
        return self.current_time

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
                self.current_time <= self._slider_end_time(note)
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
            if distance > self.note_visual_radius:
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

    def _activate_notes_until(self, time_ms):
        self.next_note_index = activate_due_notes(
            self.notes,
            self.active_notes,
            self.next_note_index,
            time_ms,
            self.approach_time
        )

    def _try_hit_at(self, pos, input_time=None, input_tick_ms=None):
        if input_time is not None:
            profiler = getattr(self.game, "profiler", None)
            if (
                input_tick_ms is not None
                and profiler is not None
                and getattr(profiler, "enabled", False)
            ):
                profiler.add(
                    "input_judgement_latency",
                    max(0.0, pygame.time.get_ticks() - float(input_tick_ms))
                )
            previous_time = self.current_time
            self.current_time = float(input_time)
            try:
                return self._try_hit_at(pos)
            finally:
                self.current_time = previous_time

        self._activate_notes_until(self.current_time)
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
            self.note_visual_radius,
            self.scale_position,
            self._hit_result_for_delta,
            can_attempt_hit
        )

        if best_note is None:
            if self._try_reengage_slider_follow_at(pos):
                return True
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

    def _smoothstep(self, v):
        v = self._clamp01(v)
        return v * v * (3.0 - (2.0 * v))

    def _smootherstep(self, v):
        v = self._clamp01(v)
        return v * v * v * (v * (v * 6.0 - 15.0) + 10.0)

    def _object_alpha(self, alpha):
        return max(
            0,
            min(255, int(alpha * self.object_alpha_scale))
        )

    def _future_readability_multiplier(self, note):
        if note.get("hit_result") is not None:
            return 1.0

        time_until = note["time"] - self.current_time
        if time_until <= 0:
            return 1.0

        stream_depth = float(note.get("stream_readability_depth", 0.0))
        if stream_depth <= 0:
            return 1.0

        # The AR-aware fade-in owns object visibility. This multiplier is only
        # a subtle stream/burst readability bias, so future notes do not become
        # a dark mass or stay half-transparent after their own fade has ended.
        approach_len = max(1.0, float(self.approach_time))
        approach_progress = 1.0 - self._clamp01(time_until / approach_len)
        future_weight = 1.0 - self._smoothstep(approach_progress)
        overlap_dim = min(0.14, stream_depth * 0.032) * future_weight

        return max(0.84, min(1.0, 1.0 - overlap_dim))

    def _fade_in_progress(self, note):
        start = note.get("start_time", note["time"] - self.approach_time)
        hit_time = note["time"]
        approach_len = max(1, hit_time - start)
        fade_fraction = 0.50 + (self._clamp01(self.ar / 10.0) * 0.30)
        fade_in_len = max(
            120.0,
            min(
                approach_len,
                approach_len
                * fade_fraction
                * self.HITOBJECT_FADE_IN_DURATION_SCALE
            )
        )

        progress = (self.current_time - start) / fade_in_len
        if progress <= 0:
            return 0.0

        fade = min(
            1.0,
            0.20 + (0.80 * self._smootherstep(progress))
        )
        if (
            note.get("hit_index") == 1
            and self.current_time < start + self.first_object_fade_in_ms
        ):
            intro_progress = (
                (self.current_time - start)
                / max(1.0, self.first_object_fade_in_ms)
            )
            fade *= self._smootherstep(intro_progress)

        return fade

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

        a = (
            alpha_in
            * self._clamp01(alpha_out)
            * self._future_readability_multiplier(note)
        )
        return int(255 * a)

    def _approach_visible_for_note(self, note):
        note_type = note.get("type")
        if note_type == "circle":
            return note.get("hit_result") is None
        if note_type == "slider":
            return note.get("head_hit_result") is None
        return False

    def _approach_visual_state(self, note, scaled_hit_radius, fail_alpha_factor):
        if not self._approach_visible_for_note(note):
            return None

        hit_time = float(note.get("time", self.current_time))
        start_time = float(note.get("start_time", hit_time - self.approach_time))
        preempt = max(1.0, hit_time - start_time)
        elapsed = self.current_time - start_time
        if elapsed < 0:
            return None

        progress = self._clamp01(elapsed / preempt)
        radius = (
            self._approach_contact_radius()
            + (
                (1.0 - progress)
                * scaled_hit_radius
                * self.APPROACH_RADIUS_EXTRA_SCALE
            )
        )

        fade_fraction = 0.50 + (self._clamp01(self.ar / 10.0) * 0.30)
        object_fade_duration = (
            preempt
            * fade_fraction
            * self.HITOBJECT_FADE_IN_DURATION_SCALE
        )
        fade_in_duration = min(
            preempt,
            max(
                100.0,
                object_fade_duration * 2.0
            )
        )
        alpha = self._smootherstep(elapsed / fade_in_duration) * 0.86

        if self.current_time >= hit_time:
            fade_out = self._smootherstep((self.current_time - hit_time) / 50.0)
            alpha *= 1.0 - fade_out

        alpha = int(255 * alpha * fail_alpha_factor)
        if alpha <= 2:
            return None

        return radius, alpha

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

        return int(
            255
            * alpha_in
            * self._clamp01(alpha_out)
            * self._future_readability_multiplier(note)
        )

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
            else self.hit_explosion_duration
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

    def _register_sprite_atlas(self, surface, key):
        backend = getattr(self, "render_backend", None)
        if backend is None or surface is None:
            return
        try:
            backend.register_sprite_surface(surface, key=key)
        except Exception:
            pass

    def _register_slider_surface_atlas(self, cache_key, surface):
        if cache_key is None or surface is None:
            return
        width, height = surface.get_size()
        self._register_sprite_atlas(
            surface,
            ("slider", "path", cache_key, width, height)
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
        if not parts:
            return None
        return load_image(parts[-1], *parts[:-1])

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
            ),
            "sliderscorepoint": self._load_image("sliderscorepoint.png")
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
        key = (id(image), size, "v3_fast_smoothscale")
        cached = self.image_surface_cache.get(key)
        if cached is not None:
            return cached

        try:
            scaled = pygame.transform.smoothscale(image, size).convert_alpha()
        except pygame.error:
            scaled = pygame.transform.scale(image, size).convert_alpha()
        self.image_surface_cache[key] = scaled
        return scaled

    def _quantized_diameter(self, diameter, quantum=2):
        diameter = max(1, int(round(diameter)))
        if diameter < 48:
            return diameter
        quantum = max(1, int(quantum))
        return max(1, int(round(diameter / quantum)) * quantum)

    def _scaled_square_image(self, image, diameter):
        diameter = self._quantized_diameter(diameter, quantum=2)
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
        ).convert_alpha()
        self.image_surface_cache[key] = rotated
        return rotated

    def _alpha_bounds(self, image, threshold=16):
        if image is None:
            return pygame.Rect(0, 0, 0, 0)

        threshold = max(1, min(255, int(threshold)))
        key = ("alpha_bounds", id(image), threshold)
        cached = self.image_surface_cache.get(key)
        if cached is not None:
            return cached

        min_x = image.get_width()
        min_y = image.get_height()
        max_x = -1
        max_y = -1
        width, height = image.get_size()
        for y in range(height):
            for x in range(width):
                if image.get_at((x, y)).a >= threshold:
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)

        if max_x < min_x or max_y < min_y:
            rect = pygame.Rect(0, 0, width, height)
        else:
            rect = pygame.Rect(
                min_x,
                min_y,
                max_x - min_x + 1,
                max_y - min_y + 1
            )
        self.image_surface_cache[key] = rect
        return rect

    def _skin_surface_diameter_for_visible_diameter(
        self,
        image,
        visible_diameter,
        threshold=16
    ):
        visible_diameter = max(1.0, float(visible_diameter))
        if image is None:
            return max(1, int(round(visible_diameter)))

        bounds = self._alpha_bounds(image, threshold=threshold)
        visible_source = max(1.0, float(max(bounds.width, bounds.height)))
        source_extent = max(1.0, float(max(image.get_width(), image.get_height())))
        diameter = visible_diameter * (source_extent / visible_source)
        return max(1, int(round(diameter)))

    def _alpha_width(self, image, threshold=96):
        if image is None:
            return 0

        key = ("alpha_width", id(image), int(threshold))
        cached = self.image_surface_cache.get(key)
        if cached is not None:
            return cached

        width = self._alpha_bounds(image, threshold=threshold).width
        self.image_surface_cache[key] = width
        return width

    def _calculate_sliderball_diameter(self):
        body_radius = max(
            1.0,
            self.slider_path_radius - max(3.0, self.slider_path_radius * 0.11)
        )
        sliderball_visible_diameter = max(
            1.0,
            body_radius * 2.0 * self.SLIDERBALL_VISIBLE_SCALE
        )
        self.sliderball_visible_diameter = sliderball_visible_diameter
        sliderball_image = self.skin_images.get("sliderball")
        if sliderball_image is None:
            return sliderball_visible_diameter

        return self._skin_surface_diameter_for_visible_diameter(
            sliderball_image,
            sliderball_visible_diameter,
            threshold=self.SLIDERBALL_ALPHA_THRESHOLD
        )

    def _slider_scorepoint_diameter(self):
        return max(6, int(round(self.slider_path_radius * 0.45)))

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

        cropped = image.subsurface(rect).copy().convert_alpha()
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
        tinted = tinted.convert_alpha()
        self.tinted_surface_cache[key] = tinted
        return tinted

    def _clean_approach_image(self, image, color):
        if image is None:
            return None

        rgb = tuple(int(c) for c in color[:3])
        key = ("approach_clean", id(image), rgb)
        cached = self.tinted_surface_cache.get(key)
        if cached is not None:
            return cached

        try:
            import numpy as np

            source_rgb = pygame.surfarray.array3d(image)
            source_alpha = pygame.surfarray.array_alpha(image).astype(np.float32)
            brightness = source_rgb.max(axis=2).astype(np.float32)
            strength = np.clip((brightness - 72.0) / 150.0, 0.0, 1.0)
            strength = strength * strength * (3.0 - (2.0 * strength))
            final_alpha = (source_alpha * strength).clip(0, 255).astype(np.uint8)

            cleaned = pygame.Surface(image.get_size(), pygame.SRCALPHA).convert_alpha()
            rgb_pixels = pygame.surfarray.pixels3d(cleaned)
            alpha_pixels = pygame.surfarray.pixels_alpha(cleaned)
            rgb_pixels[:, :, 0] = rgb[0]
            rgb_pixels[:, :, 1] = rgb[1]
            rgb_pixels[:, :, 2] = rgb[2]
            alpha_pixels[:, :] = final_alpha
            del rgb_pixels
            del alpha_pixels

            self.tinted_surface_cache[key] = cleaned
            return cleaned
        except Exception:
            pass

        cleaned = pygame.Surface(image.get_size(), pygame.SRCALPHA).convert_alpha()
        width, height = image.get_size()
        image.lock()
        cleaned.lock()
        try:
            for y in range(height):
                for x in range(width):
                    pixel = image.get_at((x, y))
                    alpha = pixel.a
                    if alpha <= 0:
                        continue

                    # The skin approach sprite has dark shadow pixels around the
                    # white ring. Use the sprite brightness as a mask so those
                    # pixels do not become colored shadows after combo tinting.
                    brightness = max(pixel.r, pixel.g, pixel.b)
                    if brightness <= 72:
                        continue

                    strength = self._smoothstep(
                        min(1.0, max(0.0, (brightness - 72) / 150.0))
                    )
                    final_alpha = int(alpha * strength)
                    if final_alpha > 0:
                        cleaned.set_at((x, y), (*rgb, final_alpha))
        finally:
            cleaned.unlock()
            image.unlock()

        self.tinted_surface_cache[key] = cleaned
        return cleaned

    def _approach_render_source(self, image, color):
        image = self._clean_approach_image(
            image,
            color if color is not None else (255, 255, 255)
        )
        if image is None:
            return None

        base_w, base_h = image.get_size()
        target_size = max(
            base_w,
            base_h,
            self.APPROACH_SUPERSAMPLE_SIZE
        )
        if max(base_w, base_h) >= target_size:
            return image

        key = ("approach_supersource", id(image), target_size)
        cached = self.image_surface_cache.get(key)
        if cached is not None:
            return cached

        scaled = None
        for size in (target_size, 640, 512):
            size = max(base_w, base_h, int(size))
            try:
                scaled = pygame.transform.smoothscale(
                    image,
                    (size, size)
                ).convert_alpha()
                target_size = size
                break
            except pygame.error:
                continue
        if scaled is None:
            return image
        self.image_surface_cache[key] = scaled
        return scaled

    def _scaled_approach_image(self, image, diameter):
        diameter = max(1, int(round(diameter / 2.0)) * 2)
        key = (id(image), diameter, "v7_fast_supersampled_approach")
        cached = self.image_surface_cache.get(key)
        if cached is not None:
            return cached

        try:
            scaled = pygame.transform.smoothscale(
                image,
                (diameter, diameter)
            ).convert_alpha()
        except pygame.error:
            try:
                scaled = pygame.transform.scale(
                    image,
                    (diameter, diameter)
                ).convert_alpha()
            except pygame.error:
                return image
        self.image_surface_cache[key] = scaled
        return scaled

    def _draw_image_centered(
        self,
        target,
        image,
        center,
        diameter=None,
        alpha=255,
        visible_diameter=None,
        alpha_threshold=16
    ):
        if image is None:
            return False

        surface = image
        if visible_diameter is not None:
            diameter = self._skin_surface_diameter_for_visible_diameter(
                image,
                visible_diameter,
                threshold=alpha_threshold
            )
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

    def _draw_hitcircle_skin(
        self,
        target,
        center,
        color,
        alpha=255,
        diameter_scale=1.0
    ):
        circle = self.skin_images.get("hitcircle")
        overlay = self.skin_images.get("hitcircle_overlay")
        if circle is None or overlay is None:
            return False

        visible_diameter = max(
            1,
            int(round(self.note_visual_radius * 2 * 1.12 * diameter_scale / 2.0)) * 2
        )
        body_visible_diameter = max(
            1,
            int(round((visible_diameter * 0.94) / 2.0)) * 2
        )
        tinted = self._tinted_image(
            circle,
            color
        )
        self._draw_image_centered(
            target,
            tinted,
            center,
            visible_diameter=body_visible_diameter,
            alpha=alpha,
            alpha_threshold=16
        )
        self._draw_image_centered(
            target,
            overlay,
            center,
            visible_diameter=visible_diameter,
            alpha=min(
                255,
                int(
                    round(
                        alpha / max(
                            0.01,
                            getattr(self, "object_alpha_scale", 1.0)
                        )
                    )
                )
            ),
            alpha_threshold=16
        )
        return True

    def _approach_contact_padding(self):
        return self.approach_contact_padding

    def _approach_contact_radius(self):
        return self.approach_contact_radius

    def _draw_approach_skin(self, target, center, radius, alpha=255, color=None):
        image = self.skin_images.get("approach")
        if image is None:
            return False

        image = self._approach_render_source(
            image,
            color if color is not None else (255, 255, 255)
        )
        if image is None:
            return False

        visible_diameter = max(1, int(round(radius * 2)))
        diameter = self._skin_surface_diameter_for_visible_diameter(
            image,
            visible_diameter,
            threshold=8
        )

        scaled = self._scaled_approach_image(image, diameter)

        self._blit_centered(
            target,
            scaled,
            center,
            alpha=alpha
        )
        return True

    def _add_miss_indicator(self, pos, show_time=None):
        payload = self._borrow_indicator_payload()
        payload.update({
            "pos": pos,
            "show_time": (
                self.current_time
                if show_time is None
                else show_time
            ),
            "start_time": self.current_time
        })
        self.miss_indicators.append(payload)

    def _register_slider_follow_miss(
        self,
        note,
        pos,
        early_release=False,
        register_judgement=True
    ):
        if note.get("slider_follow_missed"):
            return

        note["slider_follow_missed"] = True
        result = 100 if early_release else 0
        note["slider_break_time"] = self.current_time
        note["slider_break_result"] = result
        self._break_combo()
        if register_judgement:
            self._register_judgement(
                result,
                visible=True,
                statistic=(
                    "slider_release_break"
                    if early_release
                    else "slider_follow_break"
                )
            )
        self._update_health_target(result)
        if early_release:
            self._add_hit_result_indicator(note, 100)
        else:
            self._add_miss_indicator(pos)

    def _hit_input_held(self):
        return bool(self.hit_keys_held or self.hit_mouse_buttons_held)

    def _is_hit_held(self):
        return self._hit_input_held()

    def _slider_follow_grace_ms(self, reason):
        if reason == "release":
            return self.slider_follow_button_grace_ms
        return self.slider_follow_return_grace_ms

    def _slider_tail_leniency_ms(self, state, reason=None):
        total_duration = float(
            state.get("slider_total_duration", 0.0)
        )
        span_duration = float(
            state.get("span_duration", total_duration)
        )
        if total_duration <= 0:
            return 0.0

        if reason == "release":
            return max(
                55.0,
                min(
                    120.0,
                    total_duration * 0.14,
                    span_duration * 0.12
                )
            )

        return max(
            80.0,
            min(
                240.0,
                total_duration * 0.18,
                span_duration * 0.16
            )
        )

    def _handle_hit_input_release(self, input_time=None):
        if self.paused or self.failed:
            return

        previous_time = self.current_time
        if input_time is not None:
            self.current_time = float(input_time)

        try:
            for note in self.active_notes:
                if note["type"] == "slider":
                    self._update_slider_follow_state(
                        note,
                        force_input_released=True
                    )
        finally:
            self.current_time = previous_time

    def _poll_hit_input_state(self):
        try:
            keys = pygame.key.get_pressed()
            for key in getattr(self.game, "hit_keys", GameplayInputController.HIT_KEYS):
                if keys[key]:
                    self.hit_keys_held.add(key)
                else:
                    self.hit_keys_held.discard(key)
        except (pygame.error, IndexError):
            pass

        if getattr(self.game, "block_mouse_buttons_in_gameplay", False):
            self.hit_mouse_buttons_held.clear()
            return

        try:
            buttons = pygame.mouse.get_pressed(3)
        except TypeError:
            buttons = pygame.mouse.get_pressed()
        except pygame.error:
            buttons = ()

        button_state = {
            1: bool(len(buttons) > 0 and buttons[0]),
            3: bool(len(buttons) > 2 and buttons[2])
        }
        for button in GameplayInputController.HIT_MOUSE_BUTTONS:
            if button_state.get(button, False):
                self.hit_mouse_buttons_held.add(button)
            else:
                self.hit_mouse_buttons_held.discard(button)

    def _update_slider_checkpoint_sounds(self, note):
        if (
            note["type"] != "slider"
            or not self._slider_follow_active(note)
            or note.get("slider_follow_missed")
        ):
            return

        span_duration = float(note.get("span_duration", 0.0))
        repeat_count = int(note.get("repeat_count", 1))
        if span_duration <= 0 or repeat_count <= 0:
            return

        next_index = int(note.get("slider_hit_sound_index", 1))
        while next_index <= repeat_count:
            checkpoint_time = note["time"] + (span_duration * next_index)
            if self.current_time < checkpoint_time:
                break

            self._play_hit_sound()
            self._register_judgement(
                300,
                visible=False,
                statistic="slider_checkpoint_hit"
            )
            self._update_health_target(300)
            self._advance_combo()
            self._add_combo_score(30, combo_weight=30)
            next_index += 1

        note["slider_hit_sound_index"] = next_index

    def _slider_follow_active(self, note):
        return bool(
            note.get("head_hit")
            or note.get("slider_follow_engaged")
        )

    def _point_inside_slider_follow(self, cursor_pos, ball_pos):
        dx = float(cursor_pos[0]) - float(ball_pos[0])
        dy = float(cursor_pos[1]) - float(ball_pos[1])
        return (dx * dx + dy * dy) ** 0.5 <= self.slider_follow_radius

    def _slider_motion_state(self, note):
        if note["type"] != "slider":
            return None

        span_duration = float(note.get("span_duration", 0.0))
        repeat_count = int(note.get("repeat_count", 1))
        slider_total_duration = float(
            note.get(
                "slider_total_duration",
                span_duration * repeat_count
            )
        )
        if slider_total_duration <= 0:
            return None

        time_since_hit = self.current_time - note["time"]
        if time_since_hit < 0:
            return None

        slider_points = note.get("scaled_slider_points")
        if slider_points is None:
            slider_points = self.slider_renderer.build_points(note)
            note["scaled_slider_points"] = slider_points

        if len(slider_points) < 2:
            return None

        total_length = note.get("scaled_slider_length")
        cumulative = note.get("scaled_slider_cumulative")
        if total_length is None or cumulative is None:
            cumulative, total_length = self.slider_renderer.path_metrics(
                slider_points
            )
            note["scaled_slider_cumulative"] = cumulative
            note["scaled_slider_length"] = total_length

        within = min(slider_total_duration, time_since_hit)
        repeat_idx = 0
        t = 1.0
        forward = True
        if span_duration <= 0:
            ball_dist = total_length
        else:
            if within >= slider_total_duration:
                repeat_idx = repeat_count - 1
                t = 1.0
            else:
                repeat_idx = int(within / span_duration)
                t = (
                    within - repeat_idx * span_duration
                ) / span_duration

            forward = (repeat_idx % 2 == 0)
            ball_dist = total_length * (t if forward else (1.0 - t))

        ball_pos = self.slider_renderer.point_at_distance(
            slider_points,
            ball_dist,
            cumulative,
            total_length
        )
        return {
            "ball_pos": ball_pos,
            "span_duration": span_duration,
            "repeat_count": repeat_count,
            "slider_total_duration": slider_total_duration,
            "slider_end_time": note["time"] + slider_total_duration,
            "slider_points": slider_points,
            "cumulative": cumulative,
            "total_length": total_length,
            "span_index": repeat_idx,
            "span_progress": t,
            "forward": forward,
            "time_since_hit": time_since_hit,
            "within": within
        }

    def _slider_scorepoints(self, note):
        if note["type"] != "slider":
            return ()

        scorepoints = note.get("slider_scorepoints")
        if scorepoints is None:
            scorepoints = self._build_slider_scorepoints(note)
            note["slider_scorepoints"] = scorepoints
            note["slider_scorepoint_index"] = 0

        if not scorepoints:
            return scorepoints

        self._update_slider_scorepoint_positions(note, scorepoints)
        return scorepoints

    def _build_slider_scorepoints(self, note):
        span_duration = float(note.get("span_duration", 0.0))
        repeat_count = int(note.get("repeat_count", 1))
        pixel_length = float(note.get("slider_distance", 0.0))
        slider_multiplier = float(
            self.beatmap["difficulty"].get("SliderMultiplier", 1.4) or 1.4
        )
        tick_rate = float(
            self.beatmap["difficulty"].get("SliderTickRate", 1.0) or 1.0
        )

        if (
            span_duration <= 0
            or repeat_count <= 0
            or pixel_length <= 0
            or tick_rate <= 0
        ):
            return []

        tick_distance = max(
            1.0,
            (
                100.0
                * slider_multiplier
                * slider_velocity_multiplier_at(
                    self.timing_points,
                    note["time"]
                )
            ) / tick_rate
        )
        if tick_distance >= pixel_length - 1.0:
            return []

        endpoint_margin = max(
            6.0,
            min(
                pixel_length * 0.06,
                tick_distance * 0.125
            )
        )
        tick_end_distance = pixel_length - endpoint_margin
        if tick_distance >= tick_end_distance:
            return []

        scorepoints = []
        visual_start = note.get(
            "start_time",
            note["time"] - self.approach_time
        )
        approach_len = max(1.0, note["time"] - visual_start)
        fade_fraction = 0.50 + (self._clamp01(self.ar / 10.0) * 0.30)
        path_fade_len = max(
            120.0,
            min(
                approach_len,
                approach_len
                * fade_fraction
                * self.HITOBJECT_FADE_IN_DURATION_SCALE
            )
        )
        path_ready_time = visual_start + (path_fade_len * 0.52) + 4.0

        for span_index in range(repeat_count):
            span_start = note["time"] + (span_duration * span_index)
            distance = tick_distance
            while distance < tick_end_distance:
                span_progress = self._clamp01(distance / pixel_length)
                tick_time = span_start + (
                    span_duration
                    * (
                        span_progress
                        if span_index % 2 == 0
                        else 1.0 - span_progress
                    )
                )
                span_progress = self._clamp01(span_progress)
                path_fraction = span_progress
                span_visual_start = (
                    path_ready_time
                    if span_index == 0
                    else span_start + 6.0
                )
                scorepoints.append({
                    "time": tick_time,
                    "appear_time": span_visual_start,
                    "fade_in_duration": max(
                        8.0,
                        min(16.0, span_duration * 0.022)
                    ),
                    "fade_out_duration": 68.0,
                    "span_index": span_index,
                    "path_distance": distance,
                    "logical_length": pixel_length,
                    "path_fraction": path_fraction,
                    "processed": False,
                    "collected": False,
                    "missed": False,
                    "pos": None
                })
                distance += tick_distance

        scorepoints.sort(key=lambda item: item["time"])
        return scorepoints

    def _update_slider_scorepoint_positions(self, note, scorepoints):
        slider_points = note.get("scaled_slider_points")
        if slider_points is None:
            slider_points = self.slider_renderer.build_points(note)
            note["scaled_slider_points"] = slider_points

        if len(slider_points) < 2:
            return

        cumulative = note.get("scaled_slider_cumulative")
        total_length = note.get("scaled_slider_length")
        if cumulative is None or total_length is None:
            cumulative, total_length = self.slider_renderer.path_metrics(
                slider_points
            )
            note["scaled_slider_cumulative"] = cumulative
            note["scaled_slider_length"] = total_length

        geometry_key = (
            round(float(self.object_scale), 6),
            round(float(self.object_offset_x), 3),
            round(float(self.object_offset_y), 3),
            len(slider_points),
            round(float(total_length), 3)
        )
        if note.get("slider_scorepoint_geometry_key") == geometry_key:
            return

        for scorepoint in scorepoints:
            logical_length = max(
                1.0,
                float(
                    scorepoint.get(
                        "logical_length",
                        note.get("slider_distance", 1.0)
                    )
                )
            )
            logical_distance = float(
                scorepoint.get(
                    "path_distance",
                    logical_length * scorepoint.get("path_fraction", 0.0)
                )
            )
            fraction = self._clamp01(logical_distance / logical_length)
            distance = total_length * fraction
            scorepoint["pos"] = self.slider_renderer.point_at_distance(
                slider_points,
                distance,
                cumulative,
                total_length
            )

        note["slider_scorepoint_geometry_key"] = geometry_key

    def _slider_path_reveal_progress(self, note):
        visual_start = note.get("start_time", note["time"] - self.approach_time)
        reveal_duration = max(
            58.0,
            min(118.0, self.approach_time * 0.105)
        )
        return self._smoothstep(
            (self.current_time - visual_start) / reveal_duration
        )

    def _revealed_slider_points(
        self,
        note,
        slider_points,
        cumulative,
        total_length,
        reveal=None
    ):
        if reveal is None:
            reveal = self._slider_path_reveal_progress(note)
        if reveal >= 0.995 or total_length <= 0 or len(slider_points) < 2:
            return slider_points, 1.0

        target_distance = max(0.1, total_length * reveal)
        segment_index = max(
            0,
            min(len(slider_points) - 2, bisect_right(cumulative, target_distance) - 1)
        )
        partial = list(slider_points[:segment_index + 1])
        partial.append(
            self.slider_renderer.point_at_distance(
                slider_points,
                target_distance,
                cumulative,
                total_length
            )
        )
        if len(partial) < 2:
            partial.append(slider_points[1])
        return partial, reveal

    def _cursor_inside_slider_follow(self, pos):
        return self._point_inside_slider_follow(
            self.game.mouse_pos,
            pos
        )

    def _collect_slider_scorepoint(self, note, scorepoint):
        scorepoint["processed"] = True
        scorepoint["collected"] = True
        scorepoint["processed_time"] = self.current_time
        self._register_judgement(
            300,
            visible=False,
            statistic="slider_tick_hit"
        )
        self._update_health_target(300)
        self._advance_combo()
        self._add_combo_score(10, combo_weight=10)

    def _miss_slider_scorepoint(self, note, scorepoint, pos):
        scorepoint["processed"] = True
        scorepoint["missed"] = True
        scorepoint["processed_time"] = self.current_time
        self._register_judgement(
            0,
            visible=False,
            statistic="slider_tick_miss"
        )
        self._register_slider_follow_miss(
            note,
            pos,
            early_release=False,
            register_judgement=False
        )

    def _update_slider_scorepoints(self, note, state=None):
        if (
            note["type"] != "slider"
            or not self._slider_follow_active(note)
        ):
            return

        scorepoints = self._slider_scorepoints(note)
        if not scorepoints:
            return

        if state is None:
            state = self._slider_motion_state(note)
        if state is None:
            return

        index = int(note.get("slider_scorepoint_index", 0))
        ball_pos = state.get("ball_pos")
        while index < len(scorepoints):
            scorepoint = scorepoints[index]
            if self.current_time < scorepoint["time"]:
                break

            if not scorepoint.get("processed"):
                point_pos = scorepoint.get("pos") or ball_pos
                if self._hit_input_held() and self._cursor_inside_slider_follow(ball_pos):
                    self._collect_slider_scorepoint(note, scorepoint)
                else:
                    self._miss_slider_scorepoint(note, scorepoint, point_pos)
                    index += 1
                    break

            index += 1

        note["slider_scorepoint_index"] = index

    def _current_slider_scorepoint_span(self, note):
        span_duration = float(note.get("span_duration", 0.0))
        repeat_count = int(note.get("repeat_count", 1))
        if span_duration <= 0 or repeat_count <= 0:
            return 0

        elapsed = self.current_time - note["time"]
        if elapsed <= 0:
            return 0

        total_duration = float(
            note.get(
                "slider_total_duration",
                span_duration * repeat_count
            )
        )
        if elapsed >= total_duration:
            return max(0, repeat_count - 1)

        return max(
            0,
            min(
                repeat_count - 1,
                int(elapsed / span_duration)
            )
        )

    def _draw_slider_scorepoints(
        self,
        target,
        note,
        alpha,
        screen_offset=(0, 0)
    ):
        if alpha <= 0:
            return
        if (
            note.get("head_hit_result") == 0
            and not note.get("slider_follow_engaged")
        ):
            return

        image = self.skin_images.get("sliderscorepoint")
        if image is None:
            return
        image = self._cropped_alpha_image(image) or image

        scorepoints = self._slider_scorepoints(note)
        if not scorepoints:
            return

        diameter = self._slider_scorepoint_diameter()
        offset_x, offset_y = screen_offset
        draw_alpha = max(0, min(255, max(180, int(alpha * 1.45))))
        current_span = self._current_slider_scorepoint_span(note)

        for scorepoint in scorepoints:
            processed = bool(scorepoint.get("processed"))
            if not processed and scorepoint.get("span_index", 0) != current_span:
                continue
            appear_time = scorepoint.get("appear_time", note["time"])
            if self.current_time < appear_time:
                continue

            pos = scorepoint.get("pos")
            if pos is None:
                continue

            point_fade = self._smoothstep(
                (self.current_time - appear_time)
                / max(1.0, scorepoint.get("fade_in_duration", 64.0))
            )
            point_fade_out = 1.0
            if processed:
                processed_time = scorepoint.get("processed_time")
                if processed_time is None:
                    continue
                point_fade_out = 1.0 - self._smoothstep(
                    (self.current_time - processed_time)
                    / max(1.0, scorepoint.get("fade_out_duration", 68.0))
                )
                if point_fade_out <= 0:
                    continue

            point_alpha = int(draw_alpha * point_fade * point_fade_out)
            if point_alpha <= 0:
                continue

            self._draw_image_centered(
                target,
                image,
                (pos[0] + offset_x, pos[1] + offset_y),
                visible_diameter=diameter,
                alpha=point_alpha,
                alpha_threshold=18
            )

    def _update_slider_follow_state(
        self,
        note,
        force_input_released=False
    ):
        if (
            note["type"] != "slider"
            or not self._slider_follow_active(note)
        ):
            return

        state = self._slider_motion_state(note)
        if state is None:
            return

        slider_end_time = state["slider_end_time"]
        span_duration = state["span_duration"]
        if self.current_time > slider_end_time:
            outside_since = note.get("slider_follow_outside_since")
            if outside_since is None:
                return

            outside_duration_at_end = max(
                0.0,
                slider_end_time - outside_since
            )
            end_tolerance_ms = self._slider_tail_leniency_ms(
                state,
                note.get("slider_follow_outside_reason")
            )
            if outside_duration_at_end <= end_tolerance_ms:
                note["slider_follow_released_near_end"] = True
                note["slider_follow_outside_since"] = None
                note["slider_follow_outside_reason"] = None
                return

            # Don't block if already missed; just don't process further
            if not note.get("slider_follow_missed"):
                self._register_slider_follow_miss(
                    note,
                    state["ball_pos"],
                    early_release=(
                        note.get("slider_follow_outside_reason") == "release"
                    )
                )
            return

        mouse_x, mouse_y = self.game.mouse_pos
        ball_pos = state["ball_pos"]
        dx = mouse_x - ball_pos[0]
        dy = mouse_y - ball_pos[1]
        cursor_outside = (
            (dx * dx + dy * dy) ** 0.5 > self.slider_follow_radius
        )
        input_released = (
            force_input_released
            or not self._hit_input_held()
        )
        outside = cursor_outside or input_released
        remaining = slider_end_time - self.current_time
        current_reason = "cursor" if cursor_outside else "release"
        end_tolerance_ms = self._slider_tail_leniency_ms(
            state,
            current_reason
        )

        # If already missed but player comes back, reset to allow continuing
        if not outside and note.get("slider_follow_missed"):
            note["slider_follow_missed"] = False
            note["slider_follow_outside_since"] = None
            note["slider_follow_outside_reason"] = None

        if outside:
            if remaining <= end_tolerance_ms:
                note["slider_follow_released_near_end"] = True
                note["slider_follow_outside_since"] = None
                note["slider_follow_outside_reason"] = None
                return

            outside_since = note.get("slider_follow_outside_since")
            if outside_since is None:
                note["slider_follow_outside_since"] = self.current_time
                note["slider_follow_outside_reason"] = (
                    "cursor" if cursor_outside else "release"
                )
                return

            if cursor_outside:
                note["slider_follow_outside_reason"] = "cursor"

            outside_elapsed = self.current_time - outside_since
            reason = note.get("slider_follow_outside_reason")
            grace_ms = self._slider_follow_grace_ms(reason)
            if outside_elapsed < grace_ms:
                return

            if not note.get("slider_follow_missed"):
                self._register_slider_follow_miss(
                    note,
                    ball_pos,
                    early_release=reason == "release"
                )
            return

        note["slider_follow_outside_since"] = None
        note["slider_follow_outside_reason"] = None

    def _try_reengage_slider_follow_at(self, pos):
        if not self._hit_input_held():
            return False

        best_note = None
        best_state = None
        best_distance_sq = None
        for note in self.active_notes:
            if (
                note.get("type") != "slider"
                or note.get("head_hit")
                or note.get("slider_follow_engaged")
                or note.get("head_hit_result") != 0
            ):
                continue

            state = self._slider_motion_state(note)
            if state is None:
                continue
            if self.current_time > state["slider_end_time"]:
                continue

            ball_pos = state["ball_pos"]
            dx = float(pos[0]) - float(ball_pos[0])
            dy = float(pos[1]) - float(ball_pos[1])
            distance_sq = (dx * dx) + (dy * dy)
            if distance_sq > self.slider_follow_radius * self.slider_follow_radius:
                continue
            if best_distance_sq is None or distance_sq < best_distance_sq:
                best_note = note
                best_state = state
                best_distance_sq = distance_sq

        if best_note is None or best_state is None:
            return False

        best_note["slider_follow_engaged"] = True
        best_note["slider_follow_missed"] = False
        best_note["slider_follow_outside_since"] = None
        best_note["slider_follow_outside_reason"] = None

        span_duration = float(best_state.get("span_duration", 0.0))
        repeat_count = int(best_state.get("repeat_count", 1))
        if span_duration > 0 and repeat_count > 0:
            elapsed = max(0.0, self.current_time - best_note["time"])
            next_checkpoint = int(elapsed / span_duration) + 1
            best_note["slider_hit_sound_index"] = max(
                1,
                min(repeat_count + 1, next_checkpoint)
            )

        scorepoints = best_note.get("slider_scorepoints")
        if scorepoints:
            index = 0
            while index < len(scorepoints):
                scorepoint = scorepoints[index]
                if self.current_time < scorepoint["time"]:
                    break
                scorepoint["processed"] = True
                scorepoint["missed"] = True
                scorepoint["processed_time"] = self.current_time
                index += 1
            best_note["slider_scorepoint_index"] = max(
                int(best_note.get("slider_scorepoint_index", 0)),
                index
            )

        return True

    def _try_reengage_missed_slider_follow(self):
        return self._try_reengage_slider_follow_at(self.game.mouse_pos)

    def _note_follow_anchor(self, note):
        if note["type"] == "slider":
            points = note.get("scaled_slider_points")
            if points is None and hasattr(self, "slider_renderer"):
                points = self.slider_renderer.build_points(note)
                note["scaled_slider_points"] = points
            if points:
                # Followpoints are a visual guide. In osu! stable they leave
                # from the visible slider tail, not from the reverse-end state.
                return points[-1]
        return self._note_screen_pos(note)

    def _reset_followpoint_connections(self):
        for note in self.notes:
            note.pop("followpoint_connection", None)
            note.pop("followpoint_state", None)

        self.followpoint_prepare_index = 0
        self.followpoint_prepare_complete = len(self.notes) < 2

    def _prepare_followpoint_connections(self):
        self._reset_followpoint_connections()
        while not self.followpoint_prepare_complete:
            self._warm_followpoint_connections(max_ms=None, max_items=256)

    def _warm_followpoint_connections(self, max_ms=1, max_items=24):
        if self.followpoint_prepare_complete:
            return

        if len(self.notes) < 2:
            self.followpoint_prepare_complete = True
            return

        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        if profiler_enabled:
            profiler.start("followpoint_warm")

        start = pygame.time.get_ticks()
        count = 0
        last_index = len(self.notes) - 1
        try:
            while self.followpoint_prepare_index < last_index:
                index = self.followpoint_prepare_index
                self.followpoint_prepare_index += 1
                connection = self._build_followpoint_connection(
                    self.notes[index],
                    self.notes[index + 1],
                    index
                )
                if connection is not None:
                    self.notes[index]["followpoint_connection"] = connection
                count += 1

                if max_items is not None and count >= max_items:
                    break
                if (
                    max_ms is not None
                    and pygame.time.get_ticks() - start >= max_ms
                ):
                    break

            self.followpoint_prepare_complete = (
                self.followpoint_prepare_index >= last_index
            )
        finally:
            if profiler_enabled:
                profiler.end("followpoint_warm")

    def _build_followpoint_connection(self, note, next_note, index):
        if note["type"] == "spinner" or next_note["type"] == "spinner":
            return None

        if next_note.get("new_combo") or next_note.get("combo_index", 0) <= 1:
            return None

        is_slider_origin = note["type"] == "slider"
        origin_time = (
            self._slider_end_time(note)
            if is_slider_origin
            else note["time"]
        )
        gap = next_note["time"] - origin_time
        if gap < 65 or gap > 2600:
            return None

        start_anchor = self._note_follow_anchor(note)
        end_anchor = self._note_screen_pos(next_note)
        dx = end_anchor[0] - start_anchor[0]
        dy = end_anchor[1] - start_anchor[1]
        center_distance = (dx * dx + dy * dy) ** 0.5
        if center_distance <= 0:
            return None

        beat_length = max(
            120.0,
            float(
                effective_beat_length_at(
                    self.timing_points,
                    next_note["time"]
                )
            )
        )

        # Streams e objetos muito próximos normalmente não recebem followpoints
        # no osu! stable; eles poluem a leitura e custam draw calls extras.
        close_stream_gap = max(
            85.0,
            min(190.0, beat_length * 0.42)
        )
        close_stream_distance = self.scaled_radius * 2.35
        if gap <= close_stream_gap and center_distance < close_stream_distance:
            return None

        if center_distance < self.scaled_radius * 1.75:
            return None

        ux = dx / center_distance
        uy = dy / center_distance

        note_start = note.get(
            "start_time",
            origin_time - self.approach_time
        )
        note_approach_len = max(1.0, origin_time - note_start)
        next_start = next_note.get(
            "start_time",
            next_note["time"] - self.approach_time
        )
        next_approach_len = max(1.0, next_note["time"] - next_start)
        lead_time = min(
            gap * 0.98,
            max(
                420.0,
                min(
                    self.approach_time * 0.98,
                    beat_length * 1.58
                )
            )
        )
        both_visible_time = max(
            note_start + (note_approach_len * 0.015),
            next_start + (next_approach_len * 0.08)
        )
        earliest_pre_hit_start = origin_time - max(
            260.0,
            min(620.0, gap * 0.98, beat_length * 1.20)
        )
        latest_pre_hit_start = origin_time - max(
            105.0,
            min(270.0, gap * 0.68)
        )
        pre_hit_start = max(
            both_visible_time,
            earliest_pre_hit_start,
            note_start,
            next_note["time"] - lead_time
        )
        if pre_hit_start <= latest_pre_hit_start:
            start_time = pre_hit_start
        else:
            start_time = max(
                both_visible_time,
                note_start
            )
        if is_slider_origin:
            pre_origin_lead = min(
                420.0,
                max(120.0, gap * 0.46, beat_length * 0.32)
            )
        else:
            pre_origin_lead = min(
                920.0,
                max(340.0, gap * 0.82, beat_length * 0.76)
            )
        desired_start_time = max(
            both_visible_time,
            next_start + (next_approach_len * 0.02),
            origin_time - pre_origin_lead
        )
        start_time = min(start_time, desired_start_time)

        appear_duration = max(
            118.0,
            min(
                360.0,
                gap * 0.72,
                beat_length * 0.62,
                max(118.0, (next_note["time"] - start_time) * 0.54)
            )
        )
        fade_in_duration = max(
            38.0,
            min(110.0, appear_duration * 0.34, beat_length * 0.18)
        )
        fade_out_duration = max(
            120.0,
            min(260.0, gap * 0.26, beat_length * 0.30)
        )

        segment_surface = self.followpoint_segment_surface
        segment_width = (
            segment_surface.get_width()
            if segment_surface is not None
            else max(22, int(self.followpoint_visual_radius * 1.2))
        )
        spacing = max(10, int(segment_width * 0.58))
        visible_gap = center_distance - (self.scaled_radius * 0.82)
        if visible_gap < max(segment_width * 0.82, self.scaled_radius * 0.55):
            return None
        center_padding = min(
            self.scaled_radius * 0.16,
            max(2.0, center_distance * 0.055)
        )
        start = (
            start_anchor[0] + ux * center_padding,
            start_anchor[1] + uy * center_padding
        )
        end = (
            end_anchor[0] - ux * center_padding,
            end_anchor[1] - uy * center_padding
        )
        edge_dx = end[0] - start[0]
        edge_dy = end[1] - start[1]
        distance = (edge_dx * edge_dx + edge_dy * edge_dy) ** 0.5
        segment_count = int(distance / spacing)
        minimum_segments = 2
        if segment_count < minimum_segments:
            return None

        return {
            "target": next_note.get("render_index", index + 1),
            "start_time": start_time,
            "natural_fade_start": next_note["time"] + 145.0,
            "fade_out_duration": fade_out_duration,
            "appear_duration": appear_duration,
            "fade_in_duration": fade_in_duration,
            "sequence_smoothing": max(1.0, min(2.35, gap / 180.0)),
            "start": start,
            "dx": edge_dx,
            "dy": edge_dy,
            "distance": distance,
            "angle": -math.degrees(math.atan2(uy, ux)),
            "count": segment_count
        }

    def _note_judged_time(self, note):
        if note["type"] == "slider":
            return note.get("head_hit_time") or note.get("hit_time")
        return note.get("hit_time")

    def _build_followpoint_segment_surface(self):
        frames = self.skin_images.get("followpoints", [])
        if not frames:
            return None

        frame = self._cropped_alpha_image(frames[-1])
        if frame is None:
            return None
        surface = frame.copy().convert_alpha()
        self._register_sprite_atlas(
            surface,
            ("followpoint", "segment", surface.get_width(), surface.get_height())
        )
        return surface

    def _draw_followpoints(self, target):
        scaled = self.followpoint_segment_surface
        if scaled is None or len(self.notes) < 2:
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
            connection = note.get("followpoint_connection")
            if connection is None:
                continue

            next_note = self.notes[index + 1]
            judged_time = self._note_judged_time(next_note)
            state = note.setdefault("followpoint_state", {})
            state_index = connection["target"]
            if state.get("target") != state_index:
                state.clear()
                state["target"] = state_index

            natural_fade_start = connection["natural_fade_start"]
            requested_fade_start = (
                judged_time
                if judged_time is not None
                else natural_fade_start
            )
            fade_out_duration = connection["fade_out_duration"]
            stale_fade_end = requested_fade_start + fade_out_duration
            if self.current_time >= stale_fade_end:
                state["hidden"] = True
                continue
            if (
                self.current_time >= requested_fade_start
                and "fade_start" not in state
            ):
                state["fade_start"] = requested_fade_start

            fade_start = state.get("fade_start")
            if state.get("hidden"):
                continue

            end_time = (
                fade_start + fade_out_duration
                if fade_start is not None
                else natural_fade_start + fade_out_duration
            )
            start_time = connection["start_time"]
            if self.current_time < start_time or self.current_time > end_time:
                if self.current_time > end_time:
                    state["hidden"] = True
                continue

            elapsed = self.current_time - start_time
            appear_duration = connection["appear_duration"]
            progress = self._clamp01(elapsed / appear_duration)
            fade_in_duration = connection["fade_in_duration"]
            fade_in = self._clamp01(elapsed / fade_in_duration)
            fade_out = 1.0
            if fade_start is not None:
                fade_out_progress = self._clamp01(
                    (self.current_time - fade_start) / fade_out_duration
                )
                fade_out = self._smoothstep(1.0 - fade_out_progress)
            alpha = int(
                210
                * self._smoothstep(fade_in)
                * fade_out
            )
            if alpha <= 0:
                continue

            rotated = self._rotated_image(
                scaled,
                connection["angle"]
            )
            if rotated is None:
                continue

            start = connection["start"]
            dx = connection["dx"]
            dy = connection["dy"]
            segment_end = (start[0] + dx, start[1] + dy)
            segment_radius = max(
                self.followpoint_visual_radius,
                self.scaled_radius * 0.55
            )
            if not (
                is_object_visible(
                    start,
                    self.playfield_rect,
                    radius=segment_radius,
                    padding=12,
                )
                or is_object_visible(
                    segment_end,
                    self.playfield_rect,
                    radius=segment_radius,
                    padding=12,
                )
            ):
                continue

            count = connection["count"]
            sequence_smoothing = connection["sequence_smoothing"]
            reveal_head = progress * (count + 7)
            for point_index in range(1, count + 1):
                t = point_index / (count + 1)
                appear = self._clamp01(
                    (reveal_head - point_index + 2)
                    / sequence_smoothing
                )
                if appear <= 0.0:
                    continue
                point_fade = 0.72 + (self._smoothstep(appear) * 0.28)
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

    def _build_skin_cache_warm_jobs(self):
        jobs = []
        hitcircle = self.skin_images.get("hitcircle")
        overlay = self.skin_images.get("hitcircle_overlay")
        approach = self.skin_images.get("approach")

        normal_diameter = self._quantized_diameter(
            self.note_visual_radius * 2 * 1.12,
            quantum=2
        )
        effect_min = self._quantized_diameter(
            normal_diameter * 0.58,
            quantum=2
        )
        effect_max = self._quantized_diameter(
            normal_diameter * 1.36,
            quantum=2
        )

        if hitcircle is not None:
            for color in self.DEFAULT_COMBO_COLORS:
                jobs.append(("tint", hitcircle, color))
                for diameter in range(effect_min, effect_max + 1, 4):
                    surface_diameter = (
                        self._skin_surface_diameter_for_visible_diameter(
                            hitcircle,
                            diameter,
                            threshold=16
                        )
                    )
                    jobs.append(("scale_tinted", hitcircle, color, surface_diameter))

        if overlay is not None:
            for diameter in range(effect_min, effect_max + 1, 4):
                surface_diameter = (
                    self._skin_surface_diameter_for_visible_diameter(
                        overlay,
                        diameter,
                        threshold=16
                    )
                )
                jobs.append(("scale", overlay, surface_diameter))

        if approach is not None:
            min_radius = int(self._approach_contact_radius())
            max_radius = int(
                self._approach_contact_radius()
                + (self.note_visual_radius * self.APPROACH_RADIUS_EXTRA_SCALE)
            )
            min_diameter = self._quantized_diameter(min_radius * 2, quantum=4)
            max_diameter = self._quantized_diameter(max_radius * 2, quantum=4)
            warm_diameters = {
                min_diameter,
                max_diameter,
            }
            steps = 8
            for step_index in range(1, steps):
                t = step_index / steps
                warm_diameters.add(
                    self._quantized_diameter(
                        min_diameter + (max_diameter - min_diameter) * t,
                        quantum=8
                    )
                )
            for color in self.DEFAULT_COMBO_COLORS:
                jobs.append(("approach_source", approach, color))
                for diameter in sorted(warm_diameters):
                    source = self._approach_render_source(approach, color)
                    surface_diameter = diameter
                    if source is not None:
                        surface_diameter = (
                            self._skin_surface_diameter_for_visible_diameter(
                                source,
                                diameter,
                                threshold=8
                            )
                        )
                    jobs.append(("approach_scale", approach, color, surface_diameter))

        for key, diameter in (
            ("hit100", self.scaled_radius * 1.28),
            ("hit50", self.scaled_radius * 1.28),
            ("miss", self.scaled_radius * 1.28),
            ("sliderball", self.sliderball_diameter),
            ("sliderballfollow", self.slider_follow_radius * 2),
            ("sliderscorepoint", self._slider_scorepoint_diameter())
        ):
            image = self.skin_images.get(key)
            if image is not None:
                if key in {"sliderballfollow", "sliderscorepoint"}:
                    diameter = self._skin_surface_diameter_for_visible_diameter(
                        image,
                        diameter,
                        threshold=18
                    )
                jobs.append(("scale", image, diameter))

        digits = self.skin_images.get("combo_digits", {})
        for number in range(1, 31):
            jobs.append(("combo_number", str(number), digits))

        return jobs

    def _warm_skin_image_cache(self, max_ms=1, max_items=8):
        if self.skin_cache_warm_complete:
            return

        start = pygame.time.get_ticks()
        count = 0
        total = len(self.skin_cache_warm_jobs)
        while self.skin_cache_warm_index < total:
            job = self.skin_cache_warm_jobs[self.skin_cache_warm_index]
            self.skin_cache_warm_index += 1

            kind = job[0]
            if kind == "tint":
                _, image, color = job
                self._tinted_image(image, color)
            elif kind == "scale_tinted":
                _, image, color, diameter = job
                tinted = self._tinted_image(image, color)
                scaled = self._scaled_square_image(tinted, diameter)
                self._register_sprite_atlas(
                    scaled,
                    (
                        "skin",
                        "tinted_scale",
                        id(image),
                        tuple(color[:3]),
                        int(round(diameter))
                    )
                )
            elif kind == "scale":
                _, image, diameter = job
                scaled = self._scaled_square_image(image, diameter)
                self._register_sprite_atlas(
                    scaled,
                    ("skin", "scale", id(image), int(round(diameter)))
                )
            elif kind == "approach_source":
                _, image, color = job
                self._approach_render_source(image, color)
            elif kind == "approach_scale":
                _, image, color, diameter = job
                source = self._approach_render_source(image, color)
                if source is not None:
                    scaled = self._scaled_approach_image(source, diameter)
                    self._register_sprite_atlas(
                        scaled,
                        (
                            "skin",
                            "approach",
                            tuple(color[:3]),
                            int(round(diameter))
                        )
                    )
            elif kind == "combo_number":
                _, text, _digits = job
                self.effects_renderer.combo_number_image(text)

            count += 1
            if count >= max_items or pygame.time.get_ticks() - start >= max_ms:
                break

        self.skin_cache_warm_complete = self.skin_cache_warm_index >= total

    def _build_gameplay_surface_precache_jobs(self):
        if (
            self.skin_images.get("hitcircle") is not None
            and self.skin_images.get("hitcircle_overlay") is not None
            and self.skin_images.get("approach") is not None
        ):
            return []

        base_radius = max(1, int(self.scaled_radius))
        max_hit_radius = max(base_radius, int(base_radius * 1.42) + 1)
        jobs = []

        for color in self.DEFAULT_COMBO_COLORS:
            jobs.append((base_radius, color, (255, 255, 255), 3))
            for radius in range(base_radius, max_hit_radius + 1):
                for outline_width in (1, 2, 3):
                    jobs.append((radius, color, (255, 255, 255), outline_width))

            for radius in range(2, base_radius + 1):
                jobs.append((radius, color, None, 0))

        for radius in range(2, base_radius + 1):
            jobs.append((radius, None, (255, 255, 255), 1))
            jobs.append((radius, None, (255, 255, 255), 2))
            jobs.append((radius, None, (255, 255, 255), 3))
        return jobs

    def _precache_gameplay_surfaces(self):
        for radius, fill_color, outline_color, outline_width in (
            self._build_gameplay_surface_precache_jobs()
        ):
            self._aa_circle_surface(
                radius,
                fill_color=fill_color,
                outline_color=outline_color,
                outline_width=outline_width
            )

    def _warm_gameplay_surface_cache(self, max_ms=1, max_items=1):
        if self.surface_precache_complete:
            return

        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        if profiler_enabled:
            profiler.start("surface_warm")

        start = pygame.time.get_ticks()
        count = 0
        total_jobs = len(self.surface_precache_jobs)
        try:
            while self.surface_precache_index < total_jobs:
                radius, fill_color, outline_color, outline_width = (
                    self.surface_precache_jobs[self.surface_precache_index]
                )
                self.surface_precache_index += 1
                self._aa_circle_surface(
                    radius,
                    fill_color=fill_color,
                    outline_color=outline_color,
                    outline_width=outline_width
                )
                count += 1
                if count >= max_items or pygame.time.get_ticks() - start >= max_ms:
                    break

            self.surface_precache_complete = self.surface_precache_index >= total_jobs
        finally:
            if profiler_enabled:
                profiler.end("surface_warm")

    def _prime_initial_slider_geometry_cache(self):
        if not self.slider_geometry_notes:
            return

        horizon_time = float(self.initial_slider_cache_horizon_ms)
        index = 0
        total = len(self.slider_geometry_notes)
        while index < total:
            note = self.slider_geometry_notes[index]
            if note["time"] > horizon_time:
                break
            self._prepare_slider_geometry(note)
            index += 1

        self.next_slider_geometry_index = max(
            self.next_slider_geometry_index,
            index
        )
        self.slider_geometry_complete = self.next_slider_geometry_index >= total

    def _queue_initial_slider_surface_cache(self, horizon_ms=None, max_items=96):
        if not self.slider_cache_notes:
            return

        horizon_time = float(
            horizon_ms
            if horizon_ms is not None
            else self.initial_slider_cache_horizon_ms
        )
        queued = 0
        index = 0
        total = len(self.slider_cache_notes)
        while index < total and queued < max_items:
            note = self.slider_cache_notes[index]
            if note["time"] > horizon_time:
                break

            self._prepare_slider_geometry(note)
            cache_key = note.get("render_index")
            if cache_key in self.slider_surface_cache:
                index += 1
                continue

            if self.slider_cache_executor is not None:
                self._schedule_slider_cache_job(note)
            else:
                self.slider_renderer.cache_full_surface(note)
            queued += 1
            index += 1

        self.next_slider_cache_index = max(
            self.next_slider_cache_index,
            index
        )
        self.slider_precache_complete = (
            self.next_slider_cache_index >= total
            and not self.slider_cache_futures
        )

    def _prepare_slider_geometry(self, note, *, include_scorepoints=True):
        if note.get("type") != "slider":
            return True

        slider_points = note.get("scaled_slider_points")
        if slider_points is None:
            slider_points = self.slider_renderer.build_points(note)
            note["scaled_slider_points"] = slider_points

        if len(slider_points) < 2:
            return True

        cumulative = note.get("scaled_slider_cumulative")
        total_length = note.get("scaled_slider_length")
        if cumulative is None or total_length is None:
            cumulative, total_length = self.slider_renderer.path_metrics(
                slider_points
            )
            note["scaled_slider_cumulative"] = cumulative
            note["scaled_slider_length"] = total_length

        if include_scorepoints:
            self._slider_scorepoints(note)

        return True

    def _warm_slider_geometry_cache(
        self,
        max_ms=1.0,
        max_items=8,
        horizon_ms=None
    ):
        if self.slider_geometry_complete:
            return

        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        if profiler_enabled:
            profiler.start("slider_geometry_warm")

        start = time.perf_counter()
        count = 0
        total = len(self.slider_geometry_notes)
        if horizon_ms is None:
            horizon_time = float("inf")
        else:
            horizon_time = self.current_time + float(horizon_ms)
            if not self.music_started:
                horizon_time = max(horizon_time, float(horizon_ms))

        try:
            while self.next_slider_geometry_index < total:
                note = self.slider_geometry_notes[self.next_slider_geometry_index]
                if note["time"] > horizon_time:
                    break

                self.next_slider_geometry_index += 1
                self._prepare_slider_geometry(note)
                count += 1
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                if count >= max_items or elapsed_ms >= max_ms:
                    break

            self.slider_geometry_complete = (
                self.next_slider_geometry_index >= total
            )
        finally:
            if profiler_enabled:
                profiler.end("slider_geometry_warm")

    def _schedule_slider_surface_job(self, cache_key, slider_points):
        if self.slider_cache_executor is None:
            return False
        if cache_key is None:
            return False
        if (
            cache_key in self.slider_surface_cache
            or cache_key in self.slider_cache_futures
            or cache_key in self.slider_cache_failed
        ):
            return True

        if not slider_points:
            self.slider_cache_failed.add(cache_key)
            return True

        geometry = self.slider_renderer._surface_geometry(slider_points)
        if geometry is None:
            self.slider_cache_failed.add(cache_key)
            return True

        size, local_points, surface_pos = geometry
        outline_radius = self.slider_path_radius
        body_radius = max(
            1,
            int(outline_radius - max(3, outline_radius * 0.11))
        )
        future = self.slider_cache_executor.submit(
            render_track_surface_pixels,
            size,
            tuple(local_points),
            outline_radius,
            body_radius
        )
        self.slider_cache_futures[cache_key] = (
            future,
            size,
            surface_pos
        )
        return True

    def _schedule_slider_cache_job(self, note):
        cache_key = note.get("render_index")
        if cache_key is None:
            return False

        self._prepare_slider_geometry(note)
        slider_points = note.get("scaled_slider_points")
        return self._schedule_slider_surface_job(cache_key, slider_points)

    def _collect_slider_cache_results(self, max_ms=0.75, max_items=2):
        if not self.slider_cache_futures:
            return

        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        if profiler_enabled:
            profiler.start("slider_collect")

        start = time.perf_counter()
        installed = 0
        try:
            for cache_key, payload in list(self.slider_cache_futures.items()):
                future, size, surface_pos = payload
                if not future.done():
                    continue
                if (
                    isinstance(cache_key, tuple)
                    and cache_key[:1] == ("reveal",)
                    and cache_key not in self.slider_reveal_cache_keys
                ):
                    self.slider_cache_futures.pop(cache_key, None)
                    installed += 1
                    continue

                try:
                    pixels = future.result()
                except Exception:
                    pixels = None

                if pixels is None:
                    self.slider_cache_failed.add(cache_key)
                else:
                    slider_surface = surface_from_track_pixels(size, pixels)
                    self.slider_surface_cache[cache_key] = (
                        slider_surface,
                        surface_pos
                    )
                    self._register_slider_surface_atlas(
                        cache_key,
                        slider_surface
                    )

                self.slider_cache_futures.pop(cache_key, None)
                installed += 1
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                if installed >= max_items or elapsed_ms >= max_ms:
                    break
        finally:
            if profiler_enabled:
                profiler.end("slider_collect")

        self.slider_precache_complete = (
            self.next_slider_cache_index >= len(self.slider_cache_notes)
            and not self.slider_cache_futures
        )

    def _slider_cache_ready(self, note):
        cache_key = note.get("render_index")
        if cache_key is None:
            return True
        if cache_key in self.slider_surface_cache:
            return True

        payload = self.slider_cache_futures.get(cache_key)
        if payload is not None:
            future = payload[0]
            if future.done():
                self._collect_slider_cache_results(max_ms=1.2, max_items=4)
                return cache_key in self.slider_surface_cache
            return False

        if cache_key in self.slider_cache_failed:
            return True
        return False

    def _critical_slider_cache_ready(self, horizon_ms):
        if not self.slider_cache_notes:
            return True

        horizon_time = max(0.0, float(horizon_ms))
        for note in self.slider_cache_notes:
            if note["time"] > horizon_time:
                break
            if not self._slider_cache_ready(note):
                return False
        return True

    def _critical_slider_reveal_cache_ready(self, horizon_ms, max_bucket=9):
        if self.slider_cache_executor is None or not self.slider_cache_notes:
            return True

        horizon_time = max(0.0, float(horizon_ms))
        max_bucket = max(1, min(9, int(max_bucket)))
        for note in self.slider_cache_notes:
            if note["time"] > horizon_time:
                break
            base_cache_key = note.get("render_index")
            if base_cache_key is None:
                continue
            for bucket in range(1, max_bucket + 1):
                reveal_key = ("reveal", base_cache_key, bucket)
                if reveal_key in self.slider_surface_cache:
                    continue
                if reveal_key in self.slider_cache_failed:
                    continue
                payload = self.slider_cache_futures.get(reveal_key)
                if payload is not None and payload[0].done():
                    self._collect_slider_cache_results(max_ms=1.0, max_items=8)
                    if (
                        reveal_key in self.slider_surface_cache
                        or reveal_key in self.slider_cache_failed
                    ):
                        continue
                return False
        return True

    def _background_cache_ready(self):
        return (
            not self.background_path
            or self.background_source is not None
            or self.background_load_attempted
        )

    def _startup_cache_status(self, horizon_ms=None):
        if horizon_ms is None:
            horizon_ms = self.first_object_cache_horizon_ms

        slider_geometry_ready = True
        for note in self.startup_critical_slider_notes:
            if note["time"] > horizon_ms:
                break
            if (
                note.get("scaled_slider_points") is None
                or note.get("scaled_slider_cumulative") is None
                or note.get("scaled_slider_length") is None
            ):
                slider_geometry_ready = False
                break

        status = {
            "slider_geometry": slider_geometry_ready,
            "slider_surface": self._critical_slider_cache_ready(horizon_ms),
            "slider_reveal": self._critical_slider_reveal_cache_ready(
                horizon_ms,
                max_bucket=9
            ),
            "spinner": getattr(
                self.spinner_renderer,
                "prewarm_complete",
                True
            ),
            "skin": self.skin_cache_warm_complete,
            "surface": self.surface_precache_complete,
            "followpoints": self.followpoint_prepare_complete,
            "background": self._background_cache_ready(),
        }
        return status

    def _startup_cache_missing_mask(self, status):
        bits = {
            "slider_geometry": 1,
            "slider_surface": 2,
            "slider_reveal": 4,
            "spinner": 8,
            "skin": 16,
            "surface": 32,
            "followpoints": 64,
            "background": 128,
        }
        mask = 0
        for key, bit in bits.items():
            if not status.get(key, True):
                mask |= bit
        return mask

    def _startup_cache_ready(self, horizon_ms=None):
        return self._startup_cache_missing_mask(
            self._startup_cache_status(horizon_ms)
        ) == 0

    def _queue_slider_reveal_cache_for(self, note, max_bucket=9):
        if self.slider_cache_executor is None:
            return 0

        self._prepare_slider_geometry(note)
        slider_points = note.get("scaled_slider_points")
        cumulative = note.get("scaled_slider_cumulative")
        total_length = note.get("scaled_slider_length")
        base_cache_key = note.get("render_index")
        if (
            not slider_points
            or cumulative is None
            or total_length is None
            or base_cache_key is None
        ):
            return 0

        queued = 0
        max_bucket = max(1, min(9, int(max_bucket)))
        for bucket in range(1, max_bucket + 1):
            reveal_key = ("reveal", base_cache_key, bucket)
            if (
                reveal_key in self.slider_surface_cache
                or reveal_key in self.slider_cache_futures
                or reveal_key in self.slider_cache_failed
            ):
                continue

            revealed_points, _ = self._revealed_slider_points(
                note,
                slider_points,
                cumulative,
                total_length,
                reveal=bucket / 10.0
            )
            if not self._schedule_slider_surface_job(
                reveal_key,
                revealed_points
            ):
                continue

            note.setdefault(
                "slider_reveal_cache_keys",
                set()
            ).add(reveal_key)
            self.slider_reveal_cache_keys.add(reveal_key)
            queued += 1

        return queued

    def _warm_startup_critical_caches(self, horizon_ms, *, aggressive=False):
        item_budget = 220 if aggressive else 96
        self._warm_skin_image_cache(
            max_ms=4 if aggressive else 2,
            max_items=32 if aggressive else 18
        )
        self._warm_gameplay_surface_cache(
            max_ms=5 if aggressive else 3,
            max_items=32 if aggressive else 18
        )
        self._warm_followpoint_connections(
            max_ms=2 if aggressive else 1,
            max_items=160 if aggressive else 80
        )
        self._warm_spinner_cache(
            max_ms=3.0 if aggressive else 2.0,
            max_items=32 if aggressive else 18
        )
        self._warm_background_surface()

        self._warm_slider_geometry_cache(
            max_ms=6.0 if aggressive else 3.5,
            max_items=item_budget,
            horizon_ms=horizon_ms
        )
        self._warm_slider_cache(
            max_ms=12 if aggressive else 7,
            max_items=120 if aggressive else 48,
            horizon_ms=horizon_ms
        )

        queued_reveals = 0
        for note in self.startup_critical_slider_notes:
            if note["time"] > horizon_ms:
                break
            self._prepare_slider_geometry(note)
            if not self._slider_cache_ready(note):
                if self.slider_cache_executor is not None:
                    self._schedule_slider_cache_job(note)
                else:
                    self.slider_renderer.cache_full_surface(note)
            queued_reveals += self._queue_slider_reveal_cache_for(
                note,
                max_bucket=9
            )
            if not aggressive and queued_reveals >= 36:
                break

        self._warm_slider_reveal_cache(
            max_ms=8.0 if aggressive else 4.0,
            max_items=96 if aggressive else 42,
            horizon_ms=horizon_ms
        )
        self._collect_slider_cache_results(
            max_ms=5.0 if aggressive else 2.5,
            max_items=48 if aggressive else 18
        )

    def _clear_slider_reveal_cache_for(self, note):
        keys = note.pop("slider_reveal_cache_keys", None)
        if not keys:
            return
        for key in keys:
            self.slider_surface_cache.pop(key, None)
            self.slider_reveal_cache_keys.discard(key)
        note["slider_reveal_cache_cleared"] = True

    def _warm_slider_reveal_cache(
        self,
        max_ms=0.35,
        max_items=1,
        horizon_ms=None
    ):
        if self.slider_cache_executor is None or not self.slider_cache_notes:
            return

        self._collect_slider_cache_results(
            max_ms=min(0.16, max(0.05, max_ms * 0.35)),
            max_items=1
        )

        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        if profiler_enabled:
            profiler.start("slider_reveal_warm")

        start = time.perf_counter()
        count = 0
        total = len(self.slider_cache_notes)
        if horizon_ms is None:
            horizon_time = self.current_time + self.approach_time + 3600
        else:
            horizon_time = self.current_time + float(horizon_ms)
            if not self.music_started:
                horizon_time = max(horizon_time, float(horizon_ms))

        try:
            if self.slider_reveal_prewarm_cursor >= total:
                self.slider_reveal_prewarm_cursor = 0

            index = self.slider_reveal_prewarm_cursor
            scanned = 0
            while scanned < total and count < max_items:
                note = self.slider_cache_notes[index]
                index = (index + 1) % total
                scanned += 1

                visual_start = note.get(
                    "start_time",
                    note["time"] - self.approach_time
                )
                if visual_start > horizon_time:
                    if index == 0:
                        break
                    continue
                if self.current_time > note["time"] + 250:
                    continue

                self._prepare_slider_geometry(note)
                slider_points = note.get("scaled_slider_points")
                cumulative = note.get("scaled_slider_cumulative")
                total_length = note.get("scaled_slider_length")
                base_cache_key = note.get("render_index")
                if (
                    not slider_points
                    or cumulative is None
                    or total_length is None
                    or base_cache_key is None
                ):
                    continue

                bucket = int(note.get("slider_reveal_prewarm_bucket", 1))
                if bucket >= 10:
                    continue

                reveal_key = ("reveal", base_cache_key, bucket)
                note["slider_reveal_prewarm_bucket"] = bucket + 1
                if (
                    reveal_key in self.slider_surface_cache
                    or reveal_key in self.slider_cache_futures
                    or reveal_key in self.slider_cache_failed
                ):
                    continue

                revealed_points, _ = self._revealed_slider_points(
                    note,
                    slider_points,
                    cumulative,
                    total_length,
                    reveal=bucket / 10.0
                )
                scheduled = self._schedule_slider_surface_job(
                    reveal_key,
                    revealed_points
                )
                if not scheduled:
                    continue

                note.setdefault(
                    "slider_reveal_cache_keys",
                    set()
                ).add(reveal_key)
                self.slider_reveal_cache_keys.add(reveal_key)
                count += 1
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                if elapsed_ms >= max_ms:
                    break

            self.slider_reveal_prewarm_cursor = index
        finally:
            if profiler_enabled:
                profiler.end("slider_reveal_warm")

    def _warm_slider_cache(self, max_ms=1, max_items=1, horizon_ms=None):
        if self.slider_precache_complete:
            return

        if self.music_started:
            collect_ms = min(0.22, max(0.08, max_ms * 0.38))
            collect_items = 1
        else:
            collect_ms = min(2.4, max(0.35, max_ms * 0.68))
            collect_items = max(1, min(14, max_items // 3))
        self._collect_slider_cache_results(
            max_ms=collect_ms,
            max_items=collect_items
        )

        now = pygame.time.get_ticks()
        if now < self.slider_cache_cooldown_until:
            return

        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        if profiler_enabled:
            profiler.start("slider_warm")

        if horizon_ms is None:
            horizon_ms = self.approach_time + 2400

        try:
            horizon_time = self.current_time + horizon_ms
            if not self.music_started and self.pre_music_started_at is None:
                horizon_time = max(horizon_time, self.approach_time + 4200)

            start = now
            count = 0
            total = len(self.slider_cache_notes)
            while self.next_slider_cache_index < total:
                note = self.slider_cache_notes[self.next_slider_cache_index]
                if note["time"] > horizon_time:
                    break

                self.next_slider_cache_index += 1
                cache_key = note.get("render_index")
                if cache_key in self.slider_surface_cache:
                    continue

                if self.slider_cache_executor is not None:
                    self._schedule_slider_cache_job(note)
                    count += 1
                    if (
                        count >= max_items
                        or pygame.time.get_ticks() - start >= max_ms
                    ):
                        break
                    continue

                cache_start = pygame.time.get_ticks()
                self.slider_renderer.cache_full_surface(note)
                cache_elapsed = pygame.time.get_ticks() - cache_start
                count += 1
                if cache_elapsed > max_ms:
                    self.slider_cache_cooldown_until = (
                        pygame.time.get_ticks()
                        + min(120, max(16, int(cache_elapsed * 1.35)))
                    )
                    break
                if count >= max_items or pygame.time.get_ticks() - start >= max_ms:
                    break

            self.slider_precache_complete = (
                self.next_slider_cache_index >= total
                and not self.slider_cache_futures
            )
        finally:
            if profiler_enabled:
                profiler.end("slider_warm")

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

        self.background_path = path
        self.background_load_attempted = False


    def _warm_spinner_cache(self, max_ms=1.0, max_items=8):
        spinner_renderer = getattr(self, "spinner_renderer", None)
        if spinner_renderer is None or getattr(spinner_renderer, "prewarm_complete", True):
            return

        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        if profiler_enabled:
            profiler.start("spinner_warm")
        try:
            spinner_renderer.prewarm_step(max_ms=max_ms, max_items=max_items)
        finally:
            if profiler_enabled:
                profiler.end("spinner_warm")

    def _safe_to_warm_gameplay_caches(self, margin_ms=260):
        if self.active_notes:
            return False

        if self.next_note_index >= len(self.notes):
            return True

        next_note = self.notes[self.next_note_index]
        visual_time = next_note.get(
            "start_time",
            next_note.get("time", 0) - self.approach_time
        )
        return self.current_time < visual_time - margin_ms

    def _warm_active_slider_caches(self):
        if not self.slider_cache_notes:
            return

        self._collect_slider_cache_results(max_ms=0.14, max_items=2)
        if self.slider_cache_executor is None:
            return

        self._warm_slider_cache(
            max_ms=0.18,
            max_items=2,
            horizon_ms=self.approach_time + 14000
        )
        self._warm_slider_reveal_cache(
            max_ms=0.08,
            max_items=1,
            horizon_ms=self.approach_time + 4200
        )

    def _warm_background_surface(self):
        if (
            self.background_source is not None
            or self.background_load_attempted
            or not self.background_path
        ):
            return

        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        if profiler_enabled:
            profiler.start("background_warm")

        self.background_load_attempted = True
        try:
            self.background_source = pygame.image.load(
                self.background_path
            ).convert_alpha()
            for size in self._background_warm_sizes():
                self._scaled_background(size)
        except pygame.error:
            self.background_source = None
        finally:
            if profiler_enabled:
                profiler.end("background_warm")

    def _background_warm_sizes(self):
        sizes = []
        width = max(1, int(getattr(self.game, "WIDTH", 0)))
        height = max(1, int(getattr(self.game, "HEIGHT", 0)))
        if width <= 0 or height <= 0:
            return sizes

        sizes.append((width, height))
        return sizes

    def _scaled_background(self, screen_size):
        source = getattr(self, "background_source", None)
        if source is None:
            return None

        screen_w, screen_h = int(screen_size[0]), int(screen_size[1])
        if screen_w <= 0 or screen_h <= 0:
            return None

        cache_key = (
            screen_w,
            screen_h,
            int(self.background_dim_alpha),
            "v3_background_cache"
        )
        cached = self.background_surface_cache.get(cache_key)
        if cached is not None:
            self.background_surface = cached
            self.background_surface_size = cache_key
            return cached

        image_w, image_h = source.get_size()
        if image_w <= 0 or image_h <= 0:
            return None

        scale = max(screen_w / image_w, screen_h / image_h)
        target_size = (
            max(1, int(image_w * scale)),
            max(1, int(image_h * scale))
        )

        from core.assets import scale_image_high_quality
        # keep alpha and pixel fidelity by using convert_alpha()
        scaled = scale_image_high_quality(source, target_size).convert_alpha()
        position = (
            (screen_w - target_size[0]) // 2,
            (screen_h - target_size[1]) // 2
        )
        dim_overlay = pygame.Surface(
            target_size,
            pygame.SRCALPHA
        ).convert_alpha()
        dim_overlay.fill((0, 0, 0, self.background_dim_alpha))
        scaled.blit(dim_overlay, (0, 0))

        prepared = (scaled, position)
        self.background_surface_cache[cache_key] = prepared
        if len(self.background_surface_cache) > 6:
            self.background_surface_cache.clear()
            self.background_surface_cache[cache_key] = prepared
        self.background_surface = prepared
        self.background_surface_size = cache_key
        return prepared

    def _draw_background(self, screen, batch=None):
        background = self._scaled_background(
            screen.get_size()
        )
        if background is None:
            screen.fill((5, 5, 5))
            return

        surface, position = background
        if batch is not None:
            batch.add_surface(surface, position)
            return
        self.render_backend.blit_surface(surface, position)

    def _toggle_pause(self):
        if self.failed:
            return

        now = pygame.time.get_ticks()
        if not self.paused:
            self._sync_music_time_now()
            self.paused = True
            self.pause_visual_time = self.current_time
            self.pause_started_at = now
            if self.music_started:
                pygame.mixer.music.pause()
            return

        paused_duration = now - (self.pause_started_at or now)
        frozen_time = self.pause_visual_time
        self.paused = False
        self.pause_visual_time = None
        self.pause_started_at = None
        if self.start_time is not None:
            self.start_time += paused_duration
        if self.pre_music_started_at is not None:
            self.pre_music_started_at += paused_duration
        self.ready_start_time += paused_duration
        self.last_music_sync_check_ms = 0
        self.music_sync_last_update_tick_ms = 0.0
        if frozen_time is not None:
            self.current_time = float(frozen_time)
        if self.music_started:
            adjust_playback_clock_for_pause(paused_duration)
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
        self.music_playback_offset_ms = float(get_last_start_offset_ms())
        self._reset_music_sync_state()
        self._update_music_sync()
        self.next_note_index = 0
        self.active_notes.clear()
        self.intro_skip_used = True
        self.hud_start_time = None
        self._publish_current_track_state()

    def _fail(self):
        if self.failed:
            return
        self.failed = True
        self.paused = False
        self.fail_time = pygame.time.get_ticks()
        self.fail_visual_time = float(self.current_time)
        self.health = 0.0
        self.target_health = 0.0
        pygame.mixer.music.stop()
        self._play_fail_sound()
        pygame.mouse.set_visible(False)

    def _complete_map(self):
        if self.completed:
            return
        self.completed = True
        from scenes.result_scene import ResultScene
        payload = self._result_payload()
        self.game.scene_manager.push_scene_factory(
            lambda: ResultScene(self.game, self.beatmap, payload)
        )

    def _retry_gameplay(self):
        pygame.mixer.music.stop()
        self.music_started = False
        self.game.scene_manager.set_scene_factory(
            lambda: GameplayScene(self.game, self.beatmap)
        )

    def _quit_to_song_select(self):
        self._publish_current_track_state()
        if len(self.game.scene_manager.scene_stack) > 1:
            self.game.scene_manager.pop_scene()
            return
        from scenes.song_select_scene import SongSelectScene
        self.game.scene_manager.set_scene_factory(lambda: SongSelectScene(self.game))

    def _sync_music_time_now(self):
        if self.start_time is not None and self.music_started:
            self._update_music_sync()

    def _publish_current_track_state(self):
        self.game.current_menu_music_path = str(self.music_path) if self.music_path else None
        artist = self.beatmap.get("artist", "")
        title = self.beatmap.get("title", self.beatmap.get("name", ""))
        display_title = " - ".join(part for part in (artist, title) if part)
        self.game.current_menu_music_title = display_title or self.beatmap.get("name", "Menu music")
        self.game.current_menu_music_timing_points = self.beatmap.get("timing_points", [])
        self.game.current_menu_music_paused = False
        osu_file = self.beatmap.get("osu_file")
        if osu_file:
            self.game.current_selected_osu_file = str(osu_file)

    def handle_event(self, event):
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and (self.paused or self.failed)
        ):
            sampler = getattr(self.game, "sample_mouse_now", None)
            if sampler is not None:
                sampler()
            if self._handle_center_overlay_click(self.game.mouse_pos):
                return

        if event.type == pygame.KEYDOWN:
            if self.failed:
                if event.key == pygame.K_ESCAPE:
                    self._quit_to_song_select()
                    return
                if event.key == pygame.K_r:
                    self._retry_gameplay()
                    return

            if event.key in (pygame.K_ESCAPE, pygame.K_p):
                self._toggle_pause()
                return

            if self.paused:
                if event.key in (pygame.K_BACKSPACE, pygame.K_RETURN):
                    self._quit_to_song_select()
                    return
                if event.key == pygame.K_r:
                    self._retry_gameplay()
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

        if self.paused or self.failed:
            return

        self._sync_music_time_now()
        self.input_controller.handle_event(event)

    def update(self, dt):
        sampler = getattr(self.game, "sample_mouse_now", None)
        if sampler is not None:
            sampler()

        self._poll_hit_input_state()

        if self.failed or self.paused:
            return

        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)

        if not self.music_started:
            ready_elapsed = (
                pygame.time.get_ticks()
                - self.ready_start_time
            )
            self._warm_skin_image_cache(max_ms=3, max_items=24)
            self._warm_gameplay_surface_cache(max_ms=4, max_items=24)
            self._warm_spinner_cache(max_ms=2.0, max_items=18)
            if ready_elapsed >= 40:
                self._warm_followpoint_connections(max_ms=2, max_items=96)
                self._warm_slider_geometry_cache(
                    max_ms=3.0,
                    max_items=140,
                    horizon_ms=self.approach_time + 14000
                )
            if ready_elapsed >= 420:
                self._warm_slider_geometry_cache(
                    max_ms=3.5,
                    max_items=160,
                    horizon_ms=None
                )
                self._warm_slider_cache(
                    max_ms=6,
                    max_items=32,
                    horizon_ms=self.approach_time + 9000
                )
                self._warm_slider_reveal_cache(
                    max_ms=5.0,
                    max_items=54,
                    horizon_ms=self.approach_time + 9000
                )
            if ready_elapsed >= 650:
                self._warm_background_surface()
            if ready_elapsed >= 900:
                self._warm_music_load()
            total_intro_delay = (
                self.pre_start_delay_ms
                + self.post_ready_delay_ms
            )
            if ready_elapsed < total_intro_delay:
                return

            critical_slider_horizon = max(
                5200,
                int(self.approach_time + 7200),
                self.first_object_cache_horizon_ms
            )
            extra_slider_warm_budget = self.startup_cache_warm_budget_ms
            critical_slider_ready = self._critical_slider_cache_ready(
                critical_slider_horizon
            )
            critical_reveal_ready = self._critical_slider_reveal_cache_ready(
                critical_slider_horizon,
                max_bucket=9
            )
            critical_spinner_ready = getattr(
                self.spinner_renderer,
                "prewarm_complete",
                True
            )
            critical_assets_ready = (
                self.skin_cache_warm_complete
                and self.surface_precache_complete
            )
            critical_followpoints_ready = self.followpoint_prepare_complete
            startup_status = self._startup_cache_status(critical_slider_horizon)
            startup_missing_mask = self._startup_cache_missing_mask(
                startup_status
            )
            if (
                ready_elapsed < total_intro_delay + extra_slider_warm_budget
                and not (
                    critical_slider_ready
                    and critical_reveal_ready
                    and critical_spinner_ready
                    and critical_assets_ready
                    and critical_followpoints_ready
                    and startup_missing_mask == 0
                )
            ):
                self._warm_startup_critical_caches(
                    critical_slider_horizon,
                    aggressive=ready_elapsed >= total_intro_delay + 900
                )
                startup_status = self._startup_cache_status(
                    critical_slider_horizon
                )
                startup_missing_mask = self._startup_cache_missing_mask(
                    startup_status
                )
                if profiler_enabled:
                    profiler.set_metric(
                        "startup_ready",
                        int(startup_missing_mask == 0)
                    )
                    profiler.set_metric(
                        "startup_wait_mask",
                        startup_missing_mask
                    )
                return

            if profiler_enabled:
                profiler.set_metric("startup_ready", 1)
                profiler.set_metric("startup_wait_mask", 0)

            if self.pre_music_lead_in_ms > 0:
                if self.pre_music_started_at is None:
                    self.pre_music_started_at = pygame.time.get_ticks()

                lead_elapsed = (
                    pygame.time.get_ticks()
                    - self.pre_music_started_at
                )
                if lead_elapsed < self.pre_music_lead_in_ms:
                    self.current_time = lead_elapsed - self.pre_music_lead_in_ms
                    if self._safe_to_warm_gameplay_caches(margin_ms=320):
                        self._warm_gameplay_surface_cache(max_ms=4, max_items=24)
                        self._warm_skin_image_cache(max_ms=3, max_items=24)
                        self._warm_slider_geometry_cache(
                            max_ms=4,
                            max_items=180,
                            horizon_ms=None
                        )
                        self._warm_slider_cache(
                            max_ms=8,
                            max_items=48,
                            horizon_ms=self.approach_time + 11000
                        )
                        self._warm_slider_reveal_cache(
                            max_ms=6.0,
                            max_items=64,
                            horizon_ms=self.approach_time + 11000
                        )
                        self._warm_followpoint_connections(max_ms=2, max_items=96)
                        self._warm_spinner_cache(max_ms=2.0, max_items=20)
                    if profiler_enabled:
                        profiler.start("hitobjects")
                    self.next_note_index = activate_due_notes(
                        self.notes,
                        self.active_notes,
                        self.next_note_index,
                        self.current_time,
                        self.approach_time
                    )
                    if profiler_enabled:
                        profiler.end("hitobjects")
                    return

            if profiler_enabled:
                profiler.start("audio")
            self.start_time = start_music(
                self.music_path
            )
            if profiler_enabled:
                profiler.end("audio")
            if self.start_time is None:
                self.start_time = pygame.time.get_ticks()

            self.music_playback_offset_ms = float(get_last_start_offset_ms())
            self._reset_music_sync_state()
            self.music_started = True
            self._update_music_sync()
            self._publish_current_track_state()

        if self.start_time is not None:
            self._update_music_sync()

        if self._safe_to_warm_gameplay_caches(margin_ms=220):
            self._warm_slider_geometry_cache(
                max_ms=0.12,
                max_items=4,
                horizon_ms=self.approach_time + 10000
            )
            self._warm_slider_cache(
                max_ms=0.42,
                max_items=2,
                horizon_ms=self.approach_time + 6400
            )
            self._warm_slider_reveal_cache(
                max_ms=0.18,
                max_items=1,
                horizon_ms=self.approach_time + 3200
            )
            self._warm_skin_image_cache(max_ms=0.12, max_items=1)
            self._warm_followpoint_connections(max_ms=0.18, max_items=4)
            self._warm_spinner_cache(max_ms=0.20, max_items=1)
        else:
            self._warm_active_slider_caches()

        if self.start_time is not None:
            self._update_music_sync()

        self.target_health = apply_health_drain(
            self.target_health,
            dt,
            self.hp
        )
        health_speed = min(1.0, dt * 7.0)
        self.health += (
            self.target_health - self.health
        ) * health_speed

        if self.target_health <= 0.001:
            self.health = 0.0
            self._fail()
            return

        if profiler_enabled:
            profiler.start("hitobjects")
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

        if self._hit_input_held():
            self._try_reengage_missed_slider_follow()

        for note in self.active_notes:
            if note["type"] == "spinner":
                self.spinner_manager.update(
                    note,
                    self.current_time,
                    dt,
                    self.game.mouse_pos
                )
            elif note["type"] == "slider":
                self._update_slider_follow_state(note)
                self._update_slider_scorepoints(note)
                self._update_slider_checkpoint_sounds(note)

        self.active_notes = prune_inactive_notes(
            self.active_notes,
            self.current_time,
            self.hit_fade_out_time,
            self.hit_explosion_duration
        )
        if profiler_enabled:
            profiler.end("hitobjects")

        if (
            not self.completed
            and not self.failed
            and self.music_started
            and self.next_note_index >= len(self.notes)
            and not self.active_notes
            and self.judged_objects >= self.judgable_objects
        ):
            self._complete_map()

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

    def _stackable_note(self, note):
        return note.get("type") in {"circle", "slider"}

    def _note_osu_pos(self, note):
        return float(note.get("x", 0.0)), float(note.get("y", 0.0))

    def _slider_end_osu_pos(self, note):
        points = note.get("curve_points") or ()
        if points:
            point = points[-1]
            return float(point.get("x", note["x"])), float(point.get("y", note["y"]))
        return self._note_osu_pos(note)

    def _note_end_time_for_stack(self, note):
        if note.get("type") == "slider":
            return float(
                note.get(
                    "time",
                    0.0
                )
                + note.get("slider_total_duration", 0.0)
            )
        return float(note.get("end_time", note.get("time", 0.0)))

    def _osu_distance_sq(self, a, b):
        dx = float(a[0]) - float(b[0])
        dy = float(a[1]) - float(b[1])
        return (dx * dx) + (dy * dy)

    def _reset_stack_offsets(self):
        for note in self.notes:
            note["stack_count"] = 0
            note["stack_height"] = 0
            note["stack_offset"] = (0.0, 0.0)
            note["scaled_pos"] = (
                self.object_offset_x + (note["x"] * self.object_scale),
                self.object_offset_y + (note["y"] * self.object_scale)
            )

    def _apply_stack_offsets(self):
        self._reset_stack_offsets()

        format_version = int(self.beatmap.get("format_version", 14) or 14)
        if format_version < 6:
            self._apply_legacy_stack_heights()
        else:
            self._apply_lazer_stack_heights()

        circle_radius_osu = 54.4 - (4.48 * self.cs)
        offset_step = (circle_radius_osu / 10.0) * self.scale
        for note in self.notes:
            if not self._stackable_note(note):
                continue

            stack_height = int(note.get("stack_height", note.get("stack_count", 0)))
            note["stack_count"] = stack_height
            if stack_height == 0:
                continue

            shift = offset_step * stack_height
            note["stack_offset"] = (-shift, -shift)
            base_x = self.object_offset_x + (note["x"] * self.object_scale)
            base_y = self.object_offset_y + (note["y"] * self.object_scale)
            note["scaled_pos"] = (
                base_x - shift,
                base_y - shift
            )

    def _apply_lazer_stack_heights(self):
        stack_leniency = self.beatmap["difficulty"].get("StackLeniency", 0.7)
        time_limit = float(self.approach_time) * float(stack_leniency)
        distance_limit_sq = self.STACK_DISTANCE_OSU * self.STACK_DISTANCE_OSU

        for i in range(len(self.notes) - 1, -1, -1):
            object_i = self.notes[i]
            if (
                not self._stackable_note(object_i)
                or object_i.get("stack_height", 0) != 0
            ):
                continue

            n = i
            j = i - 1
            while j >= 0:
                object_j = self.notes[j]
                if object_i["time"] - self._note_end_time_for_stack(object_j) > time_limit:
                    break

                if not self._stackable_note(object_j):
                    j -= 1
                    continue

                object_i_pos = self._note_osu_pos(object_i)
                object_j_pos = self._note_osu_pos(object_j)

                if (
                    object_j.get("type") == "slider"
                    and self._osu_distance_sq(
                        self._slider_end_osu_pos(object_j),
                        object_i_pos
                    ) < distance_limit_sq
                ):
                    offset = (
                        int(object_i.get("stack_height", 0))
                        - int(object_j.get("stack_height", 0))
                        + 1
                    )
                    slider_end = self._slider_end_osu_pos(object_j)
                    for k in range(j + 1, n + 1):
                        object_k = self.notes[k]
                        if (
                            self._stackable_note(object_k)
                            and self._osu_distance_sq(
                                slider_end,
                                self._note_osu_pos(object_k)
                            ) < distance_limit_sq
                        ):
                            object_k["stack_height"] = (
                                int(object_k.get("stack_height", 0)) - offset
                            )
                    n = j
                    object_i = object_j
                    j -= 1
                    continue

                if self._osu_distance_sq(object_j_pos, object_i_pos) < distance_limit_sq:
                    object_j["stack_height"] = int(object_i.get("stack_height", 0)) + 1
                    object_i = object_j

                j -= 1

    def _apply_legacy_stack_heights(self):
        stack_leniency = self.beatmap["difficulty"].get("StackLeniency", 0.7)
        time_limit = float(self.approach_time) * float(stack_leniency)
        distance_limit_sq = self.STACK_DISTANCE_OSU * self.STACK_DISTANCE_OSU

        for i, object_i in enumerate(self.notes):
            if (
                not self._stackable_note(object_i)
                or object_i.get("stack_height", 0) != 0
            ):
                continue

            for j in range(i + 1, len(self.notes)):
                object_j = self.notes[j]
                if object_j["time"] - self._note_end_time_for_stack(object_i) > time_limit:
                    break
                if not self._stackable_note(object_j):
                    continue

                if (
                    self._osu_distance_sq(
                        self._note_osu_pos(object_i),
                        self._note_osu_pos(object_j)
                    ) < distance_limit_sq
                ):
                    object_j["stack_height"] = int(object_i.get("stack_height", 0)) + 1
                    object_i = object_j

    def _precompute_stream_readability(self):
        stackable = {"circle", "slider"}
        distance_limit = max(1.0, self.scaled_radius * 3.25)
        time_limit = 420.0

        for index, note in enumerate(self.notes):
            note["stream_readability_depth"] = 0.0
            if note["type"] not in stackable:
                continue

            x, y = self._note_screen_pos(note)
            depth = 0.0
            lookback = index - 1
            while lookback >= 0:
                previous = self.notes[lookback]
                dt = note["time"] - previous["time"]
                if dt > time_limit:
                    break

                if previous["type"] in stackable:
                    px, py = self._note_screen_pos(previous)
                    distance = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
                    if distance <= distance_limit:
                        spatial_weight = 1.0 - (distance / distance_limit)
                        temporal_weight = 1.0 - (dt / time_limit)
                        depth += 0.42 + (
                            spatial_weight * 0.72
                            + temporal_weight * 0.46
                        )

                lookback -= 1

            note["stream_readability_depth"] = min(4.0, depth)

    def _build_overlay_dirty_rect(self):
        approach_extent = (
            self._approach_contact_radius()
            + (self.note_visual_radius * self.APPROACH_RADIUS_EXTRA_SCALE)
        )
        margin = int(
            max(
                approach_extent + 8.0,
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

    def _prepare_render_frame_state(self, screen):
        screen_size = screen.get_size()
        if self.overlay_surface is None or self.overlay_surface_size != screen_size:
            self.overlay_surface = pygame.Surface(
                screen_size,
                pygame.SRCALPHA
            ).convert_alpha()
            self.overlay_surface_size = screen_size

        if (
            self.approach_overlay_surface is None
            or self.approach_overlay_surface_size != screen_size
        ):
            self.approach_overlay_surface = pygame.Surface(
                screen_size,
                pygame.SRCALPHA
            ).convert_alpha()
            self.approach_overlay_surface_size = screen_size

        overlay = self.overlay_surface
        approach_overlay = self.approach_overlay_surface
        if self.overlay_full_clear_frames > 0:
            overlay.fill((0, 0, 0, 0))
            approach_overlay.fill((0, 0, 0, 0))
            self.overlay_full_clear_frames -= 1
        else:
            overlay.fill((0, 0, 0, 0), self.overlay_dirty_rect)
            approach_overlay.fill((0, 0, 0, 0))
        fail_offset_y, fail_alpha_factor = self._fail_object_motion()
        return {
            "overlay": overlay,
            "approach_overlay": approach_overlay,
            "fail_offset_y": fail_offset_y,
            "fail_alpha_factor": fail_alpha_factor,
        }

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

    def record_slider_surface_fallback(self, cache_key):
        self.slider_surface_fallbacks_frame += 1
        if isinstance(cache_key, tuple) and cache_key[:1] == ("reveal",):
            self.slider_reveal_fallbacks_frame += 1
        else:
            self.slider_base_fallbacks_frame += 1

    def render(self, screen):
        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        self.slider_surface_fallbacks_frame = 0
        self.slider_reveal_fallbacks_frame = 0
        self.slider_base_fallbacks_frame = 0

        if self.music_started and not self.paused and not self.failed:
            self._sync_music_time_now()

        batch = self.render_backend.create_batch()
        if profiler_enabled:
            profiler.start("background_render")
        self._draw_background(screen, batch=batch)
        if profiler_enabled:
            profiler.end("background_render")

        if not self.music_started and self.pre_music_started_at is None:
            if batch is not None:
                self.render_backend.flush_batch(batch)
            self._render_ready(screen)
            if self.paused:
                self._draw_pause_overlay(screen)
            return

        if self._hud_should_draw():
            self._prune_hit_error_markers()
            if self.hud_start_time is None:
                self.hud_start_time = self.current_time
            hud_alpha = int(
                255
                * self._ease_out_cubic(
                    (self.current_time - self.hud_start_time)
                    / max(1, self.hud_fade_in_duration)
                )
            )
            if self.current_time >= self.first_object_visual_time - 160:
                hud_alpha = 255
            if profiler_enabled:
                profiler.start("hud_render")
            self.hud_renderer.draw(
                screen,
                self.beatmap,
                self.current_time,
                self.score,
                self._accuracy(),
                self.combo,
                self.health,
                self.hit_error_markers,
                self.hit_window_300,
                self.hit_window_100,
                self.hit_window_50,
                alpha=hud_alpha,
                batch=batch,
            )
            if profiler_enabled:
                profiler.end("hud_render")

        if batch is not None:
            self.render_backend.flush_batch(batch)

        # Camada transparente para permitir alpha real (fade in/out suave).
        render_state = self._prepare_render_frame_state(screen)
        overlay = render_state["overlay"]
        approach_overlay = render_state["approach_overlay"]
        fail_offset_y = render_state["fail_offset_y"]
        fail_alpha_factor = render_state["fail_alpha_factor"]

        slider_render_elapsed = 0.0
        if profiler_enabled:
            profiler.start("hitobjects_render")

        approach_draws = self._approach_draws
        approach_draws.clear()
        restore_current_time = None
        if self.failed and self.fail_visual_time is not None:
            restore_current_time = self.current_time
            self.current_time = self.fail_visual_time

        for note in reversed(self.active_notes):

            if note["type"] == "spinner":
                if profiler_enabled:
                    spinner_start = time.perf_counter()
                self.spinner_renderer.draw(overlay, note)
                if profiler_enabled:
                    profiler.add(
                        "spinner_render",
                        (time.perf_counter() - spinner_start) * 1000.0
                    )
                continue

            scaled_x, scaled_y = self._note_screen_pos(note)
            shake_x, shake_y = self._notelock_shake_offset(note)
            scaled_x += shake_x
            scaled_y += shake_y
            scaled_y += fail_offset_y

            if not is_object_visible(
                (scaled_x, scaled_y),
                self.playfield_rect,
                radius=self.note_visual_radius * 1.12,
                padding=24,
            ):
                continue

            alpha = self._object_alpha(self._note_alpha(note))
            alpha = int(alpha * fail_alpha_factor)
            alpha = int(alpha * self.HITOBJECT_VISUAL_ALPHA_SCALE)
            slider_ball_alpha = 0
            slider_track_alpha = alpha
            slider_scorepoint_alpha = alpha
            if note["type"] == "slider":
                slider_ball_alpha = self._slider_ball_alpha(note)
                slider_track_base_alpha = self._object_alpha(
                    self._slider_track_alpha(note)
                )
                slider_ball_alpha = int(slider_ball_alpha * fail_alpha_factor)
                slider_track_base_alpha = int(
                    slider_track_base_alpha * fail_alpha_factor
                )
                slider_scorepoint_alpha = slider_track_base_alpha
                slider_track_alpha = int(
                    slider_track_base_alpha
                    * self.HITOBJECT_VISUAL_ALPHA_SCALE
                )

            miss_pop_alpha = 0
            if note.get("hit_result") == 0:
                miss_pop_alpha = self._object_alpha(
                    self._miss_pop_alpha(note)
                )
                miss_pop_alpha = int(miss_pop_alpha * fail_alpha_factor)

            scaled_hit_radius = self.note_visual_radius
            approach_visual = self._approach_visual_state(
                note,
                scaled_hit_radius,
                fail_alpha_factor
            )

            if (
                alpha <= 0
                and slider_ball_alpha <= 0
                and miss_pop_alpha <= 0
                and approach_visual is None
            ):
                continue

            if approach_visual is not None:
                approach_radius, approach_alpha = approach_visual
                approach_draws.append((
                    (scaled_x, scaled_y),
                    approach_radius,
                    approach_alpha,
                    note.get("combo_color", (255, 255, 255))
                ))

            if note["type"] == "circle":
                circle_alpha = self._boost_hitcircle_alpha(alpha)
                circle_color = note.get(
                    "combo_color",
                    (0, 150, 255)
                )

                hit_result = None if self.failed else note.get("hit_result")
                if hit_result == 0:
                    pop_alpha = self._object_alpha(self._miss_pop_alpha(note))
                    pop_alpha = int(pop_alpha * fail_alpha_factor)
                    self.effects_renderer.draw_miss_pop(
                        overlay,
                        (scaled_x, scaled_y),
                        scaled_hit_radius,
                        circle_color,
                        alpha=pop_alpha
                    )
                elif hit_result in (50, 100, 300):
                    hit_time = note.get("hit_time", self.current_time)
                    self.effects_renderer.draw_hit_explosion(
                        overlay,
                        (scaled_x, scaled_y),
                        scaled_hit_radius,
                        circle_color,
                        hit_time,
                        alpha=circle_alpha
                    )
                else:
                    if not self._draw_hitcircle_skin(
                        overlay,
                        (scaled_x, scaled_y),
                        circle_color,
                        alpha=circle_alpha
                    ):
                        self._draw_aa_circle(
                            overlay,
                            (scaled_x, scaled_y),
                            scaled_hit_radius,
                            fill_color=circle_color,
                            outline_color=(255, 255, 255),
                            outline_width=3,
                            alpha=circle_alpha
                        )

                number_alpha = 0
                if hit_result not in (50, 100):
                    number_base_alpha = (
                        self._object_alpha(255)
                        if hit_result == 0
                        else circle_alpha
                    )
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
                    if profiler_enabled:
                        profiler.start("slider_render_missing_geometry")
                    self._prepare_slider_geometry(note)
                    if profiler_enabled:
                        profiler.end("slider_render_missing_geometry")
                    slider_points = note.get("scaled_slider_points")
                    if slider_points is None:
                        continue

                render_slider_points = slider_points
                slider_cache_key = note.get("render_index")
                slider_draw_points = render_slider_points
                reveal_progress = 1.0
                slider_screen_offset = (
                    int(round(shake_x)),
                    int(round(shake_y + fail_offset_y))
                )

                cumulative = note.get("scaled_slider_cumulative")
                total_length = note.get("scaled_slider_length")
                if cumulative is None or total_length is None:
                    cumulative, total_length = self.slider_renderer.path_metrics(
                        slider_points
                    )
                    note["scaled_slider_cumulative"] = cumulative
                    note["scaled_slider_length"] = total_length

                raw_reveal_progress = self._slider_path_reveal_progress(note)
                if raw_reveal_progress < 0.995:
                    reveal_bucket_count = 10
                    reveal_bucket = max(
                        1,
                        min(
                            reveal_bucket_count - 1,
                            int(math.ceil(raw_reveal_progress * reveal_bucket_count))
                        )
                    )
                    bucketed_reveal = reveal_bucket / reveal_bucket_count
                    revealed_points, reveal_progress = self._revealed_slider_points(
                        note,
                        render_slider_points,
                        cumulative,
                        total_length,
                        reveal=bucketed_reveal
                    )
                    slider_draw_points = revealed_points
                    base_cache_key = note.get("render_index")
                    if base_cache_key is not None:
                        slider_cache_key = (
                            "reveal",
                            base_cache_key,
                            reveal_bucket
                        )
                        note.setdefault(
                            "slider_reveal_cache_keys",
                            set()
                        ).add(slider_cache_key)
                        self.slider_reveal_cache_keys.add(slider_cache_key)
                    else:
                        slider_cache_key = None
                elif not note.get("slider_reveal_cache_cleared"):
                    self._clear_slider_reveal_cache_for(note)

                if (
                    slider_cache_key is not None
                    and slider_cache_key not in self.slider_surface_cache
                ):
                    if (
                        isinstance(slider_cache_key, tuple)
                        and slider_cache_key[:1] == ("reveal",)
                    ):
                        base_cache_key = note.get("render_index")
                        if base_cache_key in self.slider_surface_cache:
                            slider_cache_key = base_cache_key
                            slider_draw_points = render_slider_points
                            reveal_progress = 1.0
                        else:
                            reveal_cache_key = slider_cache_key
                            if reveal_cache_key not in self.slider_cache_failed:
                                self._schedule_slider_cache_job(note)
                                self._queue_slider_reveal_cache_for(note, max_bucket=9)
                            slider_cache_key = base_cache_key
                            slider_draw_points = render_slider_points
                            reveal_progress = 1.0
                    else:
                        if slider_cache_key not in self.slider_cache_failed:
                            self._schedule_slider_cache_job(note)

                if profiler_enabled:
                    slider_start = time.perf_counter()
                self.slider_renderer.draw(
                    overlay,
                    slider_draw_points,
                    alpha=slider_track_alpha,
                    object_color=note.get("combo_color", (0, 150, 255)),
                    draw_head_marker=False,
                    draw_tail_marker=False,
                    cache_key=slider_cache_key,
                    repeat_count=note.get("repeat_count", 1),
                    draw_reverse_markers=reveal_progress >= 0.985,
                    slider_start_time=note["time"],
                    span_duration=note.get("span_duration", 0.0),
                    screen_offset=slider_screen_offset
                )
                if profiler_enabled:
                    slider_render_elapsed += (
                        time.perf_counter() - slider_start
                    ) * 1000.0

                scorepoint_offset = (
                    slider_screen_offset[0]
                    + render_slider_points[0][0]
                    - slider_points[0][0],
                    slider_screen_offset[1]
                    + render_slider_points[0][1]
                    - slider_points[0][1]
                )
                self._draw_slider_scorepoints(
                    overlay,
                    note,
                    slider_scorepoint_alpha,
                    screen_offset=scorepoint_offset
                )

                head_result = None if self.failed else note.get("head_hit_result")
                head_alpha = self._slider_head_alpha(
                    note,
                    self._boost_hitcircle_alpha(alpha)
                )
                slider_head_pos = (
                    render_slider_points[0][0] + slider_screen_offset[0],
                    render_slider_points[0][1] + slider_screen_offset[1]
                )

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
                    pop_alpha = self._object_alpha(self._miss_pop_alpha(note))
                    pop_alpha = int(pop_alpha * fail_alpha_factor)
                    self.effects_renderer.draw_miss_pop(
                        overlay,
                        slider_head_pos,
                        self.slider_head_radius,
                        note.get("combo_color", (0, 150, 255)),
                        alpha=pop_alpha
                    )
                elif head_result in (50, 100, 300) and head_alpha > 0:
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

                if (
                    time_since_hit >= 0
                    and slider_total_duration > 0
                ):
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

                    ball_path_pos = self.slider_renderer.point_at_distance(
                        render_slider_points,
                        ball_dist,
                        cumulative,
                        total_length
                    )
                    ball_pos = (
                        ball_path_pos[0] + slider_screen_offset[0],
                        ball_path_pos[1] + slider_screen_offset[1]
                    )

                    follow_radius = self.slider_follow_radius
                    slider_end_time = note["time"] + slider_total_duration
                    follow_break_time = note.get("slider_break_time")
                    follow_break_elapsed = (
                        self.current_time - follow_break_time
                        if follow_break_time is not None
                        else None
                    )
                    recent_follow_break = (
                        note.get("slider_follow_missed")
                        and follow_break_elapsed is not None
                        and follow_break_elapsed <= self.slider_follow_visual_fade_ms
                    )
                    show_slider_follow = (
                        self._slider_follow_active(note)
                        and self.current_time <= slider_end_time
                        and (
                            not note.get("slider_follow_missed")
                            or recent_follow_break
                        )
                    )

                    outside_since = note.get("slider_follow_outside_since")
                    follow_alpha = slider_ball_alpha * 0.82
                    if recent_follow_break:
                        break_progress = self._clamp01(
                            follow_break_elapsed
                            / max(1.0, self.slider_follow_visual_fade_ms)
                        )
                        follow_alpha *= 1.0 - self._smoothstep(break_progress)
                    if outside_since is not None:
                        outside_elapsed = self.current_time - outside_since
                        follow_grace = self._slider_follow_grace_ms(
                            note.get("slider_follow_outside_reason")
                        )
                        fade_window = max(
                            1.0,
                            follow_grace,
                            self.slider_follow_visual_fade_ms
                        )
                        follow_progress = self._clamp01(
                            outside_elapsed / fade_window
                        )
                        follow_alpha *= 1.0 - self._smoothstep(follow_progress)

                    if show_slider_follow and follow_alpha > 1:
                        self._draw_image_centered(
                            overlay,
                            self.skin_images.get("sliderballfollow"),
                            ball_pos,
                            visible_diameter=follow_radius * 2,
                            alpha=int(follow_alpha),
                            alpha_threshold=18
                        )

                    sliderball_image = self.skin_images.get("sliderball")

                    if not self._draw_image_centered(
                        overlay,
                        sliderball_image,
                        ball_pos,
                        visible_diameter=getattr(
                            self,
                            "sliderball_visible_diameter",
                            self.sliderball_diameter
                        ),
                        alpha=slider_ball_alpha,
                        alpha_threshold=self.SLIDERBALL_ALPHA_THRESHOLD
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

        for center, approach_radius, approach_alpha, approach_color in approach_draws:
            if not self._draw_approach_skin(
                approach_overlay,
                center,
                approach_radius,
                alpha=approach_alpha,
                color=approach_color
            ):
                self._draw_aa_circle(
                    approach_overlay,
                    center,
                    approach_radius,
                    outline_color=approach_color,
                    outline_width=5,
                    alpha=approach_alpha
                )

        if restore_current_time is not None:
            self.current_time = restore_current_time

        if not self.failed:
            if profiler_enabled:
                profiler.start("followpoints_render")
            self._draw_followpoints(overlay)
            if profiler_enabled:
                profiler.end("followpoints_render")

            active_miss = []
            for indicator in self.miss_indicators:
                if self.current_time < indicator["show_time"] + self.miss_indicator_duration:
                    active_miss.append(indicator)
                else:
                    self._indicator_pool.append(indicator)
            self.miss_indicators = active_miss

            active_results = []
            for indicator in self.hit_result_indicators:
                if self.current_time < indicator["show_time"] + self.miss_indicator_duration:
                    active_results.append(indicator)
                else:
                    self._indicator_pool.append(indicator)
            self.hit_result_indicators = active_results

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
                    if result == "spinner_bonus":
                        if self.spinner_bonus_text_surface is None:
                            self.spinner_bonus_text_surface = self.medium_overlay_font.render(
                                "+1000",
                                True,
                                (255, 232, 92)
                            )
                        text = self.spinner_bonus_text_surface
                        text.set_alpha(alpha)
                        bonus_y = y - int(elapsed * 0.08)
                        overlay.blit(
                            text,
                            text.get_rect(center=(int(x), int(bonus_y)))
                        )
                        continue

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

        if profiler_enabled:
            profiler.end("hitobjects_render")
            if slider_render_elapsed > 0.0:
                profiler.add("sliders", slider_render_elapsed)
            profiler.set_metric(
                "slider_fallbacks",
                self.slider_surface_fallbacks_frame
            )
            profiler.set_metric(
                "slider_reveal_fallbacks",
                self.slider_reveal_fallbacks_frame
            )
            profiler.set_metric(
                "slider_base_fallbacks",
                self.slider_base_fallbacks_frame
            )
            profiler.set_metric(
                "slider_cache",
                len(self.slider_surface_cache)
            )
            profiler.set_metric(
                "slider_cache_pending",
                len(self.slider_cache_futures)
            )

        if profiler_enabled:
            profiler.start("overlay_composite")
        screen.blit(
            approach_overlay,
            self.overlay_dirty_rect,
            self.overlay_dirty_rect
        )
        screen.blit(
            overlay,
            self.overlay_dirty_rect,
            self.overlay_dirty_rect
        )
        if profiler_enabled:
            profiler.end("overlay_composite")

        self._draw_skip_button(screen)
        if self.paused:
            self._draw_pause_overlay(screen)
        elif self.failed:
            if self.fail_time is None:
                self._draw_lose_overlay(screen)
            elif (
                pygame.time.get_ticks() - self.fail_time
                >= self.lose_overlay_delay_ms
            ):
                self._draw_lose_overlay(screen)
        sampler = getattr(self.game, "sample_mouse_now", None)
        if sampler is not None:
            sampler()

    def _fail_object_motion(self):
        if not self.failed or self.fail_time is None:
            return 0, 1.0

        elapsed = pygame.time.get_ticks() - self.fail_time
        progress = self._clamp01(elapsed / self.fail_fall_duration_ms)
        eased = progress ** 2.15
        fall = int((self.game.HEIGHT * 0.28) * eased)
        alpha = 1.0 - ((progress ** 1.4) * 0.72)
        return fall, max(0.20, alpha)

    def _skip_button_visible_now(self):
        return not (
            self.intro_skip_used
            or self.intro_skip_ms <= 0
            or not self.music_started
            or self.current_time >= self.intro_skip_ms
            or self.paused
            or self.failed
        )

    def _hud_should_draw(self):
        gameplay_clock_active = (
            self.music_started
            or self.pre_music_started_at is not None
        )
        return gameplay_clock_active and not self._skip_button_visible_now()

    def _draw_skip_button(self, screen):
        self.skip_button_rect = None
        if not self._skip_button_visible_now():
            return

        if self.skip_button_text_surface is None:
            self.skip_button_text_surface = self.small_overlay_font.render(
                "skip intro",
                True,
                (245, 248, 255)
            )
        text = self.skip_button_text_surface
        pad_x = 14
        pad_y = 8
        rect = pygame.Rect(
            0,
            0,
            text.get_width() + pad_x * 2,
            text.get_height() + pad_y * 2
        )
        rect.center = (
            self.game.WIDTH // 2,
            self.game.HEIGHT // 2
        )
        self.skip_button_rect = rect
        if self.skip_button_surface is None or self.skip_button_surface_size != rect.size:
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
            self.skip_button_surface = surface
            self.skip_button_surface_size = rect.size

        screen.blit(self.skip_button_surface, rect)

    def _warm_music_load(self):
        if self.music_preloaded or not self.music_path:
            return
        self.music_preloaded = preload_music(self.music_path)

    def _handle_center_overlay_click(self, pos):
        if self.paused:
            buttons = (("resume", "Resume"), ("retry", "Retry"), ("quit", "Quit"))
        elif self.failed:
            buttons = (("retry", "Retry"), ("quit", "Quit"))
        else:
            buttons = ()

        hitboxes = (
            self.center_overlay_buttons
            if self.center_overlay_buttons
            else self._center_overlay_button_rects(buttons)
        )
        for action, rect in hitboxes:
            if rect.inflate(18, 12).collidepoint(pos):
                if action == "resume":
                    self._toggle_pause()
                elif action == "retry":
                    self._retry_gameplay()
                elif action == "quit":
                    self._quit_to_song_select()
                return True
        return False

    def _center_overlay_button_rects(self, buttons):
        center_x = self.game.WIDTH // 2
        center_y = self.game.HEIGHT // 2
        button_h = int(max(48, min(66, self.game.HEIGHT * 0.072)))
        if self.button_image is not None:
            aspect = self.button_image.get_width() / max(1, self.button_image.get_height())
            button_w = int(round(button_h * aspect))
        else:
            button_w = int(max(250, min(self.game.WIDTH * 0.24, 360)))
        gap = int(max(14, button_h * 0.34))
        x = center_x - button_w // 2
        y = center_y - 12
        rects = []
        for index, (action, _label) in enumerate(buttons):
            rects.append((
                action,
                pygame.Rect(x, y + index * (button_h + gap), button_w, button_h)
            ))
        return rects

    def _draw_center_overlay(self, screen, title, subtitle, accent, buttons):
        size = screen.get_size()
        if self.center_overlay_shade is None or self.center_overlay_shade_size != size:
            self.center_overlay_shade = pygame.Surface(size, pygame.SRCALPHA)
            self.center_overlay_shade_size = size

        shade = self.center_overlay_shade
        alpha = 178
        overlay_factor = 1.0
        if self.failed and self.fail_time is not None:
            elapsed = max(
                0,
                pygame.time.get_ticks()
                - self.fail_time
                - self.lose_overlay_delay_ms
            )
            overlay_factor = self._clamp01(
                elapsed / 520.0
            )
            alpha = int(178 * overlay_factor)
        shade.fill((0, 0, 0, alpha))
        screen.blit(shade, (0, 0))

        center_x = screen.get_width() // 2
        center_y = screen.get_height() // 2
        title_surface = self._cached_text_surface(
            self.title_overlay_font,
            title,
            (255, 255, 255)
        )
        subtitle_surface = self._cached_text_surface(
            self.small_overlay_font,
            subtitle,
            (230, 235, 250)
        )
        if overlay_factor < 1.0:
            title_surface.set_alpha(int(255 * overlay_factor))
            subtitle_surface.set_alpha(int(230 * overlay_factor))
        screen.blit(
            title_surface,
            title_surface.get_rect(center=(center_x, center_y - 112))
        )
        screen.blit(
            subtitle_surface,
            subtitle_surface.get_rect(center=(center_x, center_y - 64))
        )

        self.center_overlay_buttons = []
        mouse_pos = self.game.mouse_pos
        layout = self._center_overlay_button_rects(buttons)
        button_colors = {
            "resume": (255, 112, 34),
            "retry": (222, 112, 34),
            "quit": (218, 58, 66)
        }
        for action, rect in layout:
            label = dict(buttons).get(action, action.title())
            hover_target = 1.0 if rect.collidepoint(mouse_pos) else 0.0
            current_hover = self.center_overlay_button_hover.get(action, 0.0)
            hover = current_hover + (hover_target - current_hover) * 0.34
            self.center_overlay_button_hover[action] = hover
            if self.button_image is not None:
                hover_h = rect.height + int(2 * hover)
                aspect = self.button_image.get_width() / max(1, self.button_image.get_height())
                draw_rect = pygame.Rect(0, 0, int(round(hover_h * aspect)), hover_h)
                draw_rect.center = rect.center
            else:
                draw_rect = rect.inflate(int(22 * hover), int(6 * hover))
            self.center_overlay_buttons.append((action, draw_rect))
            button_surface = self._tinted_button_image(
                button_colors.get(action, accent),
                draw_rect.size,
                hover
            )
            if button_surface is not None:
                screen.blit(button_surface, draw_rect)
            else:
                pygame.draw.rect(
                    screen,
                    button_colors.get(action, accent),
                    draw_rect,
                    border_radius=draw_rect.height // 2
                )
            label_surface = self._cached_text_surface(
                self.medium_overlay_font,
                label,
                (255, 255, 255)
            )
            screen.blit(label_surface, label_surface.get_rect(center=draw_rect.center))

    def _draw_pause_overlay(self, screen):
        self._draw_center_overlay(
            screen,
            "PAUSE",
            "Take a breath",
            (120, 170, 255),
            (("resume", "Resume"), ("retry", "Retry"), ("quit", "Quit"))
        )

    def _draw_lose_overlay(self, screen):
        self._draw_center_overlay(
            screen,
            "FAILED",
            "You saw the pattern. Now go take it back.",
            (255, 92, 116),
            (("retry", "Retry"), ("quit", "Quit"))
        )

    def _render_ready(self, screen):
        remaining = max(
            0,
            self.pre_start_delay_ms
            - (pygame.time.get_ticks() - self.ready_start_time)
        )
        if remaining <= 0:
            return

        dots = "." * (1 + int((self.pre_start_delay_ms - remaining) / 400) % 3)
        text = self._cached_text_surface(
            self.font,
            f"Ready{dots}",
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

        if self.slider_cache_executor is not None:
            self.slider_cache_executor.shutdown(
                wait=False,
                cancel_futures=True
            )
            self.slider_cache_executor = None
            self.slider_cache_futures.clear()

        if self.completed:
            self._publish_current_track_state()
        elif self.music_started and not self.failed:
            if self.paused:
                now = pygame.time.get_ticks()
                paused_duration = now - (self.pause_started_at or now)
                adjust_playback_clock_for_pause(paused_duration)
                pygame.mixer.music.unpause()
                self.paused = False
            self._publish_current_track_state()
        else:
            pygame.mixer.music.stop()

        if hasattr(self.game, "sync_input_mode"):
            self.game.sync_input_mode(self.game.mouse_pos)

        pygame.mouse.set_visible(False)
