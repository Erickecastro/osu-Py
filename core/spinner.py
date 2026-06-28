import math

import pygame

from core.assets import asset_path


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _angle_delta(current, previous):
    delta = current - previous
    while delta > math.pi:
        delta -= math.tau
    while delta < -math.pi:
        delta += math.tau
    return delta


class SpinnerScoring:
    def required_rotations(self, note):
        duration_seconds = max(
            0.001,
            (note["spinner_end_time"] - note["spinner_start_time"]) / 1000.0
        )
        od = float(note.get("spinner_od", note.get("od", 5.0)) or 5.0)
        difficulty_factor = 0.88 + (_clamp(od, 0.0, 10.0) * 0.024)
        return max(1.5, duration_seconds * 2.85 * difficulty_factor)

    def pass_tolerance_rotations(self, note):
        required = self.required_rotations(note)
        return max(0.18, min(0.62, required * 0.075))

    def result_for_progress(self, progress):
        if progress >= 1.0:
            return 300
        if progress >= 0.78:
            return 100
        if progress >= 0.48:
            return 50
        return 0


class SpinnerEffects:
    def __init__(self):
        self.spin_sound = self._load_sound(asset_path("spinnerspin.wav", "spinner"))
        self.bonus_sound = self._load_sound(asset_path("spinnerbonus.ogg", "spinner"))
        self.complete_sound = None

    def _load_sound(self, path):
        try:
            return pygame.mixer.Sound(str(path))
        except pygame.error:
            return None

    def update_sounds(self, note, current_time):
        rpm = note.get("spinner_rpm", 0.0)
        if rpm > 70 and current_time >= note.get("next_spin_sound_time", 0):
            if self.spin_sound is not None:
                volume = _clamp((rpm - 70.0) / 320.0, 0.08, 0.42)
                self.spin_sound.set_volume(volume)
                self.spin_sound.play()
            interval = int(_clamp(190 - rpm * 0.22, 55, 150))
            note["next_spin_sound_time"] = current_time + interval

        if note.get("spinner_goal_reached") and not note.get("spinner_goal_sound"):
            note["spinner_goal_sound"] = True
            if self.complete_sound is not None:
                self.complete_sound.set_volume(0.62)
                self.complete_sound.play()

        bonus_index = note.get("spinner_bonus_count", 0)
        played_bonus = note.get("spinner_bonus_sound_count", 0)
        if bonus_index > played_bonus:
            note["spinner_bonus_sound_count"] = bonus_index
            if self.bonus_sound is not None:
                self.bonus_sound.set_volume(0.46)
                self.bonus_sound.play()


class SpinnerManager:
    def __init__(self, scene):
        self.scene = scene
        self.scoring = SpinnerScoring()
        self.effects = SpinnerEffects()

    def update(self, note, current_time, dt, mouse_pos):
        if note.get("judged"):
            return

        start = note["spinner_start_time"]
        end = note["spinner_end_time"]
        if current_time < start:
            return

        if not note.get("spinner_initialized"):
            self._initialize(note, mouse_pos)

        center = self.center
        dx = mouse_pos[0] - center[0]
        dy = mouse_pos[1] - center[1]
        radius = math.hypot(dx, dy)
        hit_held = self.scene._is_hit_held()
        if radius >= max(24.0, self.scene.scaled_radius * 0.55):
            angle = math.atan2(dy, dx)
            previous_angle = note.get("spinner_previous_angle", angle)
            delta = _angle_delta(angle, previous_angle)
            note["spinner_previous_angle"] = angle

            noise_floor = 0.008
            if not hit_held:
                delta = 0.0

            if abs(delta) >= noise_floor:
                direction = 1 if delta > 0 else -1
                previous_direction = note.get("spinner_direction", direction)
                continuity = 1.0 if direction == previous_direction else 0.72
                accepted = abs(delta) * continuity
                accepted = min(accepted, math.radians(95))
                note["spinner_direction"] = direction
                note["spinner_rotation"] += accepted / math.tau
                note["spinner_visual_angle"] += delta

                instantaneous_rpm = (accepted / math.tau) / max(dt, 1e-4) * 60.0
                instantaneous_rpm = _clamp(instantaneous_rpm, 0.0, 520.0)
                note["spinner_rpm"] += (
                    instantaneous_rpm - note["spinner_rpm"]
                ) * _clamp(dt * 14.0, 0.0, 1.0)
            elif not hit_held:
                note["spinner_rpm"] += (
                    0.0 - note["spinner_rpm"]
                ) * _clamp(dt * 12.0, 0.0, 1.0)
        else:
            note["spinner_rpm"] += (0.0 - note["spinner_rpm"]) * _clamp(dt * 8.0, 0.0, 1.0)

        elapsed_seconds = max(0.001, (current_time - start) / 1000.0)
        note["spinner_average_rpm"] = (
            note["spinner_rotation"] / elapsed_seconds * 60.0
        )

        required = note["spinner_required_rotations"]
        pass_tolerance = note.get("spinner_pass_tolerance_rotations", 0.0)
        progress = _clamp(note["spinner_rotation"] / required, 0.0, 1.35)
        note["spinner_progress"] = progress
        note["spinner_pass_tolerance_progress"] = _clamp(
            (note["spinner_rotation"] + pass_tolerance) / required,
            0.0,
            1.0
        )
        if progress >= 1.0:
            if not note.get("spinner_goal_reached"):
                note["spinner_pass_time"] = current_time
            note["spinner_goal_reached"] = True
            over = max(0.0, note["spinner_rotation"] - required)
            bonus_count = int(over)
            if bonus_count > note.get("spinner_bonus_count", 0):
                note["spinner_bonus_count"] = bonus_count
                self.scene._add_spinner_bonus_score(bonus_count)
                self.scene._add_spinner_bonus_indicator(
                    bonus_count,
                    self.center
                )

        if current_time < end:
            score_bank = note.get("spinner_score_bank", 0.0)
            if hit_held:
                score_bank += note["spinner_rpm"] * dt * 0.42
            whole_points = int(score_bank)
            if whole_points > 0:
                self.scene._add_raw_score(whole_points)
                score_bank -= whole_points
            note["spinner_score_bank"] = score_bank
            if hit_held:
                self.effects.update_sounds(note, current_time)
            return

        result_progress = (
            1.0
            if note["spinner_rotation"] + pass_tolerance >= required
            else progress
        )
        result = self.scoring.result_for_progress(result_progress)
        self.scene._finish_spinner(note, result)

    def _initialize(self, note, mouse_pos):
        note["spinner_initialized"] = True
        note["spinner_rotation"] = 0.0
        note["spinner_rpm"] = 0.0
        note["spinner_average_rpm"] = 0.0
        note["spinner_progress"] = 0.0
        note["spinner_visual_angle"] = 0.0
        note["spinner_bonus_count"] = 0
        note["spinner_score_bank"] = 0.0
        note["spinner_od"] = getattr(self.scene, "od", 5.0)
        note["spinner_required_rotations"] = self.scoring.required_rotations(note)
        note["spinner_pass_tolerance_rotations"] = (
            self.scoring.pass_tolerance_rotations(note)
        )

        dx = mouse_pos[0] - self.center[0]
        dy = mouse_pos[1] - self.center[1]
        note["spinner_previous_angle"] = math.atan2(dy, dx)
        note["spinner_direction"] = 1

    @property
    def center(self):
        return (
            self.scene.game.WIDTH // 2,
            self.scene.game.HEIGHT // 2
        )
