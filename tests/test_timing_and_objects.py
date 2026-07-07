import unittest
from unittest import mock

from core.beatmap_timing import (
    effective_beat_length_at,
    slider_span_duration,
    slider_velocity_multiplier_at,
)
from core.spinner import SpinnerScoring
import scenes.gameplay_scene as gameplay_scene
from scenes.gameplay_scene import GameplayScene


class TimingAndObjectTests(unittest.TestCase):
    def _stack_scene(self, notes, format_version=14):
        scene = object.__new__(GameplayScene)
        scene.notes = notes
        scene.beatmap = {
            "format_version": format_version,
            "difficulty": {
                "StackLeniency": 0.7,
            }
        }
        scene.approach_time = 600.0
        scene.cs = 4.0
        scene.scale = 1.0
        scene.object_scale = 1.0
        scene.object_offset_x = 0.0
        scene.object_offset_y = 0.0
        scene._precompute_note_positions()
        scene._apply_stack_offsets()
        return scene

    def test_lazer_stack_offsets_same_position_notes(self):
        notes = [
            {"type": "circle", "x": 256, "y": 192, "time": 1000, "end_time": 1000},
            {"type": "circle", "x": 256, "y": 192, "time": 1100, "end_time": 1100},
            {"type": "circle", "x": 256, "y": 192, "time": 1200, "end_time": 1200},
        ]

        self._stack_scene(notes)

        self.assertEqual([note["stack_height"] for note in notes], [2, 1, 0])
        self.assertLess(notes[0]["scaled_pos"][0], notes[1]["scaled_pos"][0])
        self.assertLess(notes[1]["scaled_pos"][0], notes[2]["scaled_pos"][0])

    def test_lazer_stack_offsets_slider_end_negative_stack(self):
        notes = [
            {
                "type": "slider",
                "x": 100,
                "y": 100,
                "time": 1000,
                "end_time": 2000,
                "slider_total_duration": 1000,
                "curve_points": [{"x": 100, "y": 100}, {"x": 200, "y": 100}],
            },
            {"type": "circle", "x": 200, "y": 100, "time": 1500, "end_time": 1500},
        ]

        self._stack_scene(notes)

        self.assertEqual(notes[0]["stack_height"], 0)
        self.assertEqual(notes[1]["stack_height"], -1)
        self.assertGreater(notes[1]["scaled_pos"][0], notes[1]["x"])

    def test_inherited_timing_controls_slider_velocity(self):
        timing_points = [
            {"time": 0.0, "ms_per_beat": 500.0, "uninherited": 1, "effects": 0},
            {"time": 1000.0, "ms_per_beat": -50.0, "uninherited": 0, "effects": 0},
        ]

        self.assertEqual(effective_beat_length_at(timing_points, 500), 500.0)
        self.assertEqual(slider_velocity_multiplier_at(timing_points, 1500), 2.0)
        self.assertEqual(effective_beat_length_at(timing_points, 1500), 250.0)
        self.assertAlmostEqual(
            slider_span_duration(timing_points, 1.4, 1500, 280.0),
            500.0,
        )

    def test_slider_scorepoints_follow_tick_rate_and_repeats(self):
        scene = object.__new__(GameplayScene)
        scene.beatmap = {
            "difficulty": {
                "SliderMultiplier": 1.4,
                "SliderTickRate": 1.0,
            }
        }
        scene.timing_points = [
            {"time": 0.0, "ms_per_beat": 500.0, "uninherited": 1, "effects": 0}
        ]
        scene.approach_time = 600.0
        scene.ar = 9.0
        scene.HITOBJECT_FADE_IN_DURATION_SCALE = GameplayScene.HITOBJECT_FADE_IN_DURATION_SCALE
        scene._clamp01 = GameplayScene._clamp01.__get__(scene, GameplayScene)

        note = {
            "type": "slider",
            "time": 1000.0,
            "start_time": 400.0,
            "span_duration": 1000.0,
            "repeat_count": 2,
            "slider_distance": 420.0,
        }
        scorepoints = scene._build_slider_scorepoints(note)

        self.assertEqual(len(scorepoints), 4)
        self.assertEqual([point["span_index"] for point in scorepoints], [0, 0, 1, 1])
        self.assertTrue(all(0.0 < point["path_fraction"] < 1.0 for point in scorepoints))
        self.assertEqual(scorepoints, sorted(scorepoints, key=lambda item: item["time"]))

    def test_slider_follow_can_reengage_after_head_miss(self):
        class FakeSliderRenderer:
            def point_at_distance(self, points, distance, cumulative, total_length):
                return (float(distance), 0.0)

        scene = object.__new__(GameplayScene)
        scene.current_time = 1250.0
        scene.slider_follow_radius = 32.0
        scene.hit_keys_held = {1}
        scene.hit_mouse_buttons_held = set()
        scene.slider_renderer = FakeSliderRenderer()
        note = {
            "type": "slider",
            "time": 1000.0,
            "head_hit": False,
            "head_hit_result": 0,
            "judged": True,
            "span_duration": 1000.0,
            "repeat_count": 1,
            "slider_total_duration": 1000.0,
            "scaled_slider_points": [(0.0, 0.0), (100.0, 0.0)],
            "scaled_slider_cumulative": [0.0, 100.0],
            "scaled_slider_length": 100.0,
        }
        scene.active_notes = [note]

        self.assertTrue(scene._try_reengage_slider_follow_at((25.0, 0.0)))
        self.assertTrue(note["slider_follow_engaged"])
        self.assertFalse(note["slider_follow_missed"])

    def test_slider_follow_reengages_while_hit_is_already_held(self):
        class FakeSliderRenderer:
            def point_at_distance(self, points, distance, cumulative, total_length):
                return (float(distance), 0.0)

        class FakeGame:
            mouse_pos = (25.0, 0.0)

        scene = object.__new__(GameplayScene)
        scene.game = FakeGame()
        scene.current_time = 1250.0
        scene.slider_follow_radius = 32.0
        scene.hit_keys_held = {1}
        scene.hit_mouse_buttons_held = set()
        scene.slider_renderer = FakeSliderRenderer()
        note = {
            "type": "slider",
            "time": 1000.0,
            "head_hit": False,
            "head_hit_result": 0,
            "judged": True,
            "span_duration": 1000.0,
            "repeat_count": 1,
            "slider_total_duration": 1000.0,
            "scaled_slider_points": [(0.0, 0.0), (100.0, 0.0)],
            "scaled_slider_cumulative": [0.0, 100.0],
            "scaled_slider_length": 100.0,
        }
        scene.active_notes = [note]

        self.assertTrue(scene._try_reengage_missed_slider_follow())
        self.assertTrue(note["slider_follow_engaged"])

    def test_slider_follow_does_not_reengage_without_hit_input(self):
        scene = object.__new__(GameplayScene)
        scene.hit_keys_held = set()
        scene.hit_mouse_buttons_held = set()
        scene.active_notes = []

        self.assertFalse(scene._try_reengage_slider_follow_at((0.0, 0.0)))

    def test_intro_skip_keeps_visible_lead_before_first_object(self):
        scene = object.__new__(GameplayScene)
        scene.approach_time = 1000.0
        scene.notes = [{
            "type": "circle",
            "time": 10000,
            "start_time": 9000,
        }]

        skip_to = scene._calculate_intro_skip_ms()

        self.assertLessEqual(skip_to, 9000 - 780)
        self.assertGreater(skip_to, 0)

    def test_first_object_fade_does_not_pop_at_visual_start(self):
        scene = object.__new__(GameplayScene)
        scene.current_time = 0.0
        scene.ar = 9.0
        scene.approach_time = 1000.0
        scene.HITOBJECT_FADE_IN_DURATION_SCALE = GameplayScene.HITOBJECT_FADE_IN_DURATION_SCALE
        scene.first_object_fade_in_ms = 300.0
        scene._clamp01 = GameplayScene._clamp01.__get__(scene, GameplayScene)
        scene._smootherstep = GameplayScene._smootherstep.__get__(scene, GameplayScene)

        note = {
            "type": "circle",
            "time": 1000.0,
            "start_time": 0.0,
            "hit_index": 1,
        }

        self.assertEqual(scene._fade_in_progress(note), 0.0)

        scene.current_time = 300.0

        self.assertGreater(scene._fade_in_progress(note), 0.50)

    def test_music_sync_uses_audio_clock_as_authoritative_time(self):
        scene = object.__new__(GameplayScene)
        scene.start_time = 0.0
        scene.current_time = 1000.0
        scene.music_started = True
        scene.pre_music_lead_in_ms = 0.0
        scene.music_sync_correction_ms = 0.0
        scene.music_sync_target_correction_ms = 0.0
        scene.music_sync_last_drift_ms = 0.0
        scene.music_sync_last_update_tick_ms = 1000.0
        scene.music_sync_slew_rate = 0.18
        scene.music_sync_snap_threshold_ms = 240.0
        scene.audio_offset_ms = 0.0
        scene.music_playback_offset_ms = 0.0
        scene.last_music_sync_check_ms = 0
        scene.active_notes = [{"type": "circle"}]
        scene.game = type("Game", (), {"profiler": None})()
        scene._mixer_music_time = lambda: 1060.0

        with mock.patch.object(
            gameplay_scene.pygame.mixer.music,
            "get_busy",
            return_value=True
        ):
            scene._update_music_sync(tick_ms=1000.0)
            self.assertEqual(scene.music_sync_correction_ms, 60.0)
            self.assertEqual(scene.music_sync_target_correction_ms, 60.0)
            self.assertEqual(scene.current_time, 1060.0)

            scene._mixer_music_time = lambda: 1076.0
            scene._update_music_sync(tick_ms=1016.0)
            self.assertEqual(scene.music_sync_correction_ms, 60.0)
            self.assertEqual(scene.current_time, 1076.0)

    def test_startup_cache_mask_blocks_until_critical_assets_are_ready(self):
        scene = object.__new__(GameplayScene)
        scene.first_object_cache_horizon_ms = 2000
        scene.startup_critical_slider_notes = [{
            "time": 1000,
            "scaled_slider_points": None,
            "scaled_slider_cumulative": None,
            "scaled_slider_length": None,
        }]
        scene.spinner_renderer = type(
            "Spinner",
            (),
            {"prewarm_complete": False}
        )()
        scene.skin_cache_warm_complete = False
        scene.surface_precache_complete = True
        scene.followpoint_prepare_complete = True
        scene.background_path = "bg.jpg"
        scene.background_source = None
        scene.background_load_attempted = False
        scene._critical_slider_cache_ready = lambda _horizon: False
        scene._critical_slider_reveal_cache_ready = lambda _horizon, max_bucket=9: True

        status = scene._startup_cache_status()
        mask = scene._startup_cache_missing_mask(status)

        self.assertFalse(scene._startup_cache_ready())
        self.assertTrue(mask & 1)    # slider geometry
        self.assertTrue(mask & 2)    # slider surface
        self.assertTrue(mask & 8)    # spinner
        self.assertTrue(mask & 16)   # skin
        self.assertTrue(mask & 128)  # background

        scene.startup_critical_slider_notes[0].update({
            "scaled_slider_points": [(0, 0), (10, 0)],
            "scaled_slider_cumulative": [0, 10],
            "scaled_slider_length": 10,
        })
        scene.spinner_renderer.prewarm_complete = True
        scene.skin_cache_warm_complete = True
        scene.background_load_attempted = True
        scene._critical_slider_cache_ready = lambda _horizon: True

        self.assertTrue(scene._startup_cache_ready())

    def test_pause_resume_keeps_gameplay_clock_frozen(self):
        scene = object.__new__(GameplayScene)
        scene.failed = False
        scene.paused = True
        scene.music_started = True
        scene.pause_visual_time = 1234.0
        scene.pause_started_at = 1000
        scene.start_time = 700
        scene.pre_music_started_at = 800
        scene.ready_start_time = 900
        scene.current_time = 9999.0
        scene.last_music_sync_check_ms = 42

        with mock.patch.object(
            gameplay_scene.pygame.time,
            "get_ticks",
            return_value=4600
        ), mock.patch.object(
            gameplay_scene.pygame.mixer.music,
            "unpause"
        ) as unpause, mock.patch.object(
            gameplay_scene,
            "adjust_playback_clock_for_pause"
        ) as adjust_clock:
            scene._toggle_pause()

        self.assertFalse(scene.paused)
        self.assertIsNone(scene.pause_visual_time)
        self.assertIsNone(scene.pause_started_at)
        self.assertEqual(scene.start_time, 4300)
        self.assertEqual(scene.pre_music_started_at, 4400)
        self.assertEqual(scene.ready_start_time, 4500)
        self.assertEqual(scene.current_time, 1234.0)
        self.assertEqual(scene.last_music_sync_check_ms, 0)
        adjust_clock.assert_called_once_with(3600)
        unpause.assert_called_once()

    def test_spinner_pass_tolerance_distinguishes_near_pass_and_miss(self):
        scoring = SpinnerScoring()
        note = {
            "spinner_start_time": 0,
            "spinner_end_time": 3000,
            "od": 5.0,
        }
        required = scoring.required_rotations(note)
        tolerance = scoring.pass_tolerance_rotations(note)

        self.assertGreater(required, 1.5)
        self.assertGreater(tolerance, 0.0)
        self.assertEqual(scoring.result_for_progress(1.0), 300)
        self.assertEqual(scoring.result_for_progress(0.79), 100)
        self.assertEqual(scoring.result_for_progress(0.49), 50)
        self.assertEqual(scoring.result_for_progress(0.30), 0)

        near_pass_progress = (required - (tolerance * 0.5)) / required
        clear_miss_progress = (required - (tolerance * 1.5)) / required
        self.assertGreater(near_pass_progress, clear_miss_progress)
        self.assertLess(near_pass_progress, 1.0)


if __name__ == "__main__":
    unittest.main()
