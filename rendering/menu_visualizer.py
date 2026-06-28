import math
import threading

import pygame
import pygame.sndarray


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _lerp(current, target, amount):
    return current + ((target - current) * _clamp(amount, 0.0, 1.0))


class CircularMenuVisualizer:
    _analysis_cache = {}

    def __init__(self, bar_count=256):
        self.bar_count = bar_count
        self.levels = [0.0] * bar_count
        self.silent_bands = [0.0] * bar_count
        self.band_targets = [0.0] * bar_count
        self.band_alpha = [0.0] * bar_count
        self.level_hold = [0.0] * bar_count
        self.band_memory = [0.0] * bar_count
        self.band_transients = [0.0] * bar_count
        self.dynamic_caps = [1.0] * bar_count
        self.bar_cooldowns = [0.0] * bar_count
        self.bar_attack_windows = [0.0] * bar_count
        self.peak_cut_masks = [0.0] * bar_count
        self.peak_centers = [0.0, 0.25, 0.50, 0.75]
        self.peak_strengths = [0.0, 0.0, 0.0, 0.0]
        self._peak_bucket = None
        self.angles = [(index / bar_count) * math.tau for index in range(bar_count)]
        self.units = [(math.cos(angle), math.sin(angle)) for angle in self.angles]
        self.variation = []
        for index in range(bar_count):
            value = ((index * 37) % 100) / 100.0
            self.variation.append(0.42 + (value ** 1.28) * 1.22)
        self.length_bias = [
            0.86 + (((value - 0.42) / 1.22) * 0.28)
            for value in self.variation
        ]
        self.alpha_variation = [
            0.68 + ((((index * 53) % 100) / 100.0) * 0.42)
            for index in range(bar_count)
        ]
        self.activity_bias = []
        self.alpha_bias = []
        for index in range(bar_count):
            value = ((index * 97 + 23) % 100) / 100.0
            if value < 0.27:
                self.activity_bias.append(0.10 + value * 0.34)
                self.alpha_bias.append(0.30 + value * 0.48)
            elif value < 0.56:
                self.activity_bias.append(0.42 + (value - 0.27) * 1.08)
                self.alpha_bias.append(0.52 + (value - 0.27) * 0.76)
            elif value < 0.88:
                self.activity_bias.append(0.74 + (value - 0.56) * 0.92)
                self.alpha_bias.append(0.70 + (value - 0.56) * 0.64)
            else:
                self.activity_bias.append(1.06 + (value - 0.88) * 1.25)
                self.alpha_bias.append(0.90 + (value - 0.88) * 0.84)
        self.region_targets = [0.0] * bar_count
        self.instant_bands = [0.0] * bar_count
        self.instant_rms = 0.0
        self.max_length_scale = 0.68
        self.bar_width = 7.75
        self.minimum_level_base = 0.045
        self.minimum_alpha = 0
        self.attack_amount = 0.22
        self.release_amount = 0.105
        self.sweep_position = 0.0
        self.intense_peak_boost = 1.0

        self.center = (0, 0)
        self.radius = 160.0
        self.energy = 0.12
        self.audible_level = 0.0
        self.beat_level = 0.0
        self.beat_phase = 0.0
        self.kiai_level = 0.0
        self.analysis_step_ms = 42
        self.analysis = []
        self.rms_envelope = []
        self.timing_points = []
        self._timing_index = 0
        self._layer = None
        self._layer_size = None
        self._layer_radius = 0
        self._layer_shrink_elapsed = 0.0
        self._redraw_elapsed = 1.0
        self.render_interval = 1.0 / 180.0
        self._analysis_lock = threading.Lock()
        self._analysis_thread = None
        self._analysis_thread_key = None
        self._pending_analysis = None

    def load_audio_analysis(self, audio_path, timing_points=None):
        self._reset_analysis_state(timing_points)

        if not audio_path:
            self._analysis_thread_key = None
            self._pending_analysis = None
            return

        cache_key = (str(audio_path), self.bar_count, self.analysis_step_ms)
        self._analysis_thread_key = cache_key
        self._pending_analysis = None
        cached = self._analysis_cache.get(cache_key)
        if cached is not None:
            self.analysis, self.rms_envelope = cached
            self._prime_from_analysis()
            return

        result = self._build_audio_analysis(audio_path)
        if result is None:
            return

        self.analysis, self.rms_envelope = result
        self._store_analysis_cache(cache_key, result)
        self._prime_from_analysis()

    def request_audio_analysis(self, audio_path, timing_points=None):
        self._reset_analysis_state(timing_points)

        if not audio_path:
            self._analysis_thread_key = None
            self._pending_analysis = None
            return

        cache_key = (str(audio_path), self.bar_count, self.analysis_step_ms)
        cached = self._analysis_cache.get(cache_key)
        if cached is not None:
            self._analysis_thread_key = cache_key
            self._pending_analysis = None
            self.analysis, self.rms_envelope = cached
            self._prime_from_analysis()
            return

        if (
            self._analysis_thread is not None
            and self._analysis_thread.is_alive()
            and self._analysis_thread_key == cache_key
        ):
            return

        self._analysis_thread_key = cache_key
        self._pending_analysis = None
        thread = threading.Thread(
            target=self._analysis_worker,
            args=(cache_key, audio_path),
            daemon=True
        )
        self._analysis_thread = thread
        thread.start()

    def _reset_analysis_state(self, timing_points=None):
        self.timing_points = self.parse_timing_points(timing_points or [])
        self._timing_index = 0
        self.analysis = []
        self.rms_envelope = []
        self.energy = 0.12
        self.audible_level = 0.0
        self.beat_level = 0.0
        self.beat_phase = 0.0
        self.kiai_level = 0.0
        self.levels = [0.0] * self.bar_count
        self.band_alpha = [0.0] * self.bar_count
        self.level_hold = [0.0] * self.bar_count
        self.band_memory = [0.0] * self.bar_count
        self.band_transients = [0.0] * self.bar_count
        self.dynamic_caps = [1.0] * self.bar_count
        self.bar_cooldowns = [0.0] * self.bar_count
        self.bar_attack_windows = [0.0] * self.bar_count
        self.peak_cut_masks = [0.0] * self.bar_count
        self.region_targets = [0.0] * self.bar_count
        self.instant_bands = [0.0] * self.bar_count
        self.instant_rms = 0.0
        self.peak_strengths = [0.0] * len(self.peak_centers)
        self._peak_bucket = None

    def _analysis_worker(self, cache_key, audio_path):
        result = self._build_audio_analysis(audio_path)
        with self._analysis_lock:
            self._pending_analysis = (cache_key, result)

    def _apply_pending_analysis(self):
        with self._analysis_lock:
            pending = self._pending_analysis
            self._pending_analysis = None

        if pending is None:
            return

        cache_key, result = pending
        if cache_key != self._analysis_thread_key or result is None:
            return

        self.analysis, self.rms_envelope = result
        self._store_analysis_cache(cache_key, result)
        self._prime_from_analysis()

    def _prime_from_analysis(self):
        if self.analysis is None or len(self.analysis) == 0:
            return

        first_bands = self.analysis[0]
        first_rms = self.rms_envelope[0] if self.rms_envelope else 0.0
        self.instant_rms = float(first_rms)

        for index, value in enumerate(first_bands):
            value = float(value)
            self.instant_bands[index] = value
            seed = _clamp((value * 0.24) + (first_rms * 0.26), 0.0, 0.42)
            seeded_level = seed * (0.82 + self.activity_bias[index] * 0.18)
            self.levels[index] = max(self.levels[index], seeded_level)
            self.band_memory[index] = value
            self.region_targets[index] = max(self.region_targets[index], seeded_level)

        self.audible_level = max(self.audible_level, _clamp(first_rms * 0.95, 0.0, 0.48))
        self.energy = max(self.energy, _clamp(first_rms * 0.72, 0.0, 0.48))
        self._redraw_elapsed = self.render_interval

    def _store_analysis_cache(self, cache_key, result):
        while len(self._analysis_cache) >= 12:
            oldest_key = next(iter(self._analysis_cache))
            self._analysis_cache.pop(oldest_key, None)
        self._analysis_cache[cache_key] = result

    def _build_audio_analysis(self, audio_path):
        try:
            import numpy as np
        except ImportError:
            return None

        try:
            sound = pygame.mixer.Sound(str(audio_path))
            samples = pygame.sndarray.array(sound)
        except (pygame.error, ValueError, TypeError):
            return None

        if samples.size == 0:
            return None

        samples = samples.astype("float32")
        if samples.ndim > 1:
            samples = samples.mean(axis=1)

        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        if peak <= 0.0:
            return None
        samples = samples / peak

        mixer_init = pygame.mixer.get_init()
        sample_rate = mixer_init[0] if mixer_init else 44100
        fft_size = 2048
        hop = max(1, int(sample_rate * self.analysis_step_ms / 1000))
        if len(samples) < fft_size:
            return None

        freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
        edges = np.geomspace(38.0, min(17000.0, sample_rate * 0.48), self.bar_count + 1)
        starts = np.searchsorted(freqs, edges[:-1], side="left")
        stops = np.searchsorted(freqs, edges[1:], side="left")
        starts = np.clip(starts, 0, len(freqs) - 1)
        stops = np.clip(stops, starts + 1, len(freqs))
        widths = np.maximum(1, stops - starts).astype("float32")

        window = np.hanning(fft_size).astype("float32")
        frames = []
        rms_values = []
        for start in range(0, len(samples) - fft_size, hop):
            chunk = samples[start:start + fft_size]
            rms = float(np.sqrt(np.mean(chunk * chunk)))
            spectrum = np.abs(np.fft.rfft(chunk * window))
            cumulative = np.empty(len(spectrum) + 1, dtype="float32")
            cumulative[0] = 0.0
            np.cumsum(spectrum, out=cumulative[1:])
            bands = (cumulative[stops] - cumulative[starts]) / widths
            frames.append(bands)
            rms_values.append(rms)

        if not frames:
            return None

        matrix = np.vstack(frames)
        band_floor = np.percentile(matrix, 18, axis=0)
        band_peak = np.percentile(matrix, 98, axis=0)
        denom = np.maximum(1e-6, band_peak - band_floor)
        matrix = np.clip((matrix - band_floor) / denom, 0.0, 1.0)
        matrix = np.power(matrix, 0.72)

        rms = np.array(rms_values, dtype="float32")
        rms_floor = float(np.percentile(rms, 18))
        rms_peak = float(np.percentile(rms, 98))
        rms = np.clip((rms - rms_floor) / max(1e-6, rms_peak - rms_floor), 0.0, 1.0)
        rms = np.power(rms, 0.86)

        return matrix.astype("float32"), [float(value) for value in rms]

    def parse_timing_points(self, timing_points):
        parsed = []
        for point in timing_points or []:
            ms_per_beat = float(point.get("ms_per_beat", point.get("beat_length", 0)) or 0)
            uninherited = int(point.get("uninherited", 1))
            effects = int(point.get("effects", point.get("effect", 0)) or 0)
            if uninherited == 1 and ms_per_beat > 0:
                parsed.append({
                    "time": float(point.get("time", 0) or 0),
                    "ms_per_beat": ms_per_beat,
                    "kiai": bool(effects & 1)
                })
        parsed.sort(key=lambda item: item["time"])
        return parsed

    def update(self, dt, current_time_ms, audio_active=True):
        self._apply_pending_analysis()
        self._redraw_elapsed += dt
        self._layer_shrink_elapsed += dt
        audio_active = bool(audio_active)
        current_time_ms = max(0.0, float(current_time_ms or 0.0))
        timing = self._timing_at(current_time_ms)
        if timing:
            ms_per_beat = max(1.0, timing["ms_per_beat"])
            beat_seconds = ms_per_beat / 1000.0
            self.beat_phase = ((current_time_ms - timing["time"]) / ms_per_beat) % 1.0
            self.sweep_position = ((current_time_ms - timing["time"]) / (ms_per_beat * 13.0)) % 1.0
            self.kiai_level = _lerp(
                self.kiai_level,
                1.0 if timing.get("kiai") else 0.0,
                1.0 - math.exp(-dt * 3.0)
            )
        else:
            beat_seconds = 60.0 / 118.0
            self.beat_phase = (self.beat_phase + (dt * 118.0 / 60.0)) % 1.0
            self.sweep_position = (self.sweep_position + (dt * 118.0 / 850.0)) % 1.0
            self.kiai_level = _lerp(self.kiai_level, 0.0, 1.0 - math.exp(-dt * 3.0))

        bands, rms = self._analysis_at(current_time_ms)
        if not audio_active:
            rms = 0.0
            bands = self.silent_bands
        beat_distance = min(self.beat_phase, 1.0 - self.beat_phase)
        timing_beat = _clamp(1.0 - (beat_distance / 0.125), 0.0, 1.0) ** 2.15

        if bands is None:
            if audio_active:
                rms = max(0.115, timing_beat * 0.28, self.instant_rms * 0.72)
                bands = [
                    (
                        0.20
                        + (
                            max(
                                0.0,
                                math.sin(
                                    (index / self.bar_count) * math.tau * 3.0
                                    + self.beat_phase * math.tau
                                )
                            )
                            * 0.80
                        )
                    )
                    * rms
                    * (0.74 + self.activity_bias[index] * 0.22)
                    for index in range(self.bar_count)
                ]
                if max(self.levels) < 0.040:
                    for index, value in enumerate(bands):
                        seeded_level = _clamp(
                            (float(value) * 0.42)
                            * (0.80 + self.activity_bias[index] * 0.20),
                            0.0,
                            0.16
                        )
                        self.levels[index] = max(self.levels[index], seeded_level)
                        self.band_memory[index] = max(self.band_memory[index], float(value))
                    self.audible_level = max(self.audible_level, 0.32)
                    self.energy = max(self.energy, 0.18)
            else:
                rms = 0.0
                bands = self.silent_bands
        elif audio_active and bands is not self.silent_bands:
            self.instant_rms = _lerp(
                self.instant_rms,
                float(rms),
                1.0 - math.exp(-dt * 18.0)
            )
            for index, value in enumerate(bands):
                self.instant_bands[index] = _lerp(
                    self.instant_bands[index],
                    float(value),
                    1.0 - math.exp(-dt * 14.0)
                )

        low_end = max(1, self.bar_count // 5)
        low = self._mean_band_range(bands, 0, low_end)
        mid_start = self.bar_count // 5
        mid_end = self.bar_count * 3 // 5
        mid = self._mean_band_range(bands, mid_start, mid_end)
        high = self._mean_band_range(bands, mid_end, self.bar_count)
        band_signal = max(low, mid, high)
        audible_signal = (rms * 0.68) + (band_signal * 0.32)
        audible_target = _clamp((audible_signal - 0.010) / 0.120, 0.0, 1.0)
        if audio_active and audible_signal > 0.006:
            audible_target = max(audible_target, 0.095)
        self.audible_level = _lerp(
            self.audible_level,
            audible_target,
            1.0 - math.exp(-dt * (13.0 if audible_target > self.audible_level else 4.2))
        )

        beat_audio = _clamp((low * 0.72) + (rms * 0.42), 0.0, 1.0)
        beat_pulse = _clamp(timing_beat * 0.72 * self.audible_level, 0.0, 1.0)
        fft_pulse = _clamp(beat_audio * 0.58, 0.0, 1.0)
        self.beat_level = _lerp(
            self.beat_level,
            max(beat_pulse, fft_pulse),
            1.0 - math.exp(-dt * 15.0)
        )
        self.energy = _lerp(
            self.energy,
            _clamp(((low * 0.32) + (mid * 0.30) + (high * 0.14) + (rms * 0.42)) * self.audible_level, 0.0, 1.0),
            1.0 - math.exp(-dt * (7.5 if rms > self.energy else 3.2))
        )

        if timing:
            beat_bucket = int((current_time_ms - timing["time"]) / max(1.0, timing["ms_per_beat"]))
        else:
            beat_bucket = int(current_time_ms / 508.0)
        wave_base = (1.0 - self.sweep_position) % 1.0
        for slot in range(len(self.peak_centers)):
            self.peak_centers[slot] = (wave_base + slot * 0.25) % 1.0
        audio_intensity = _clamp((rms * 0.62) + (band_signal * 0.38), 0.0, 1.0)
        peak_drive = _clamp(max(audio_intensity, self.beat_level * 0.65), 0.0, 1.0)
        frenzy_gate = _clamp((audio_intensity - 0.28) / 0.72, 0.0, 1.0)
        vocal_instrument_push = _clamp(
            (((rms * 0.50) + (mid * 0.32) + (high * 0.24)) - 0.42) / 0.58,
            0.0,
            1.0
        )
        frenzy_gate = max(frenzy_gate, vocal_instrument_push * 0.82)
        self.intense_peak_boost = 1.0 + (vocal_instrument_push * 0.72)
        if (
            audio_active
            and beat_bucket != self._peak_bucket
            and timing_beat > 0.62
            and self.audible_level > 0.12
            and audio_intensity > 0.18
        ):
            self._peak_bucket = beat_bucket
            seed = (
                (beat_bucket * 1103515245)
                + int(current_time_ms * 13.0)
                + int(rms * 997.0)
                + int(low * 619.0)
                + int(high * 383.0)
            ) & 0xFFFFFFFF
            for slot in range(len(self.peak_centers)):
                seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
                strength = 0.52 + ((((seed >> 16) & 0xFF) / 255.0) * 0.48)
                self.peak_strengths[slot] = max(
                    self.peak_strengths[slot],
                    strength * frenzy_gate * (0.76 + peak_drive * 0.94)
                )
        release_peak = 1.0 - math.exp(-dt * 4.7)
        for slot, strength in enumerate(self.peak_strengths):
            self.peak_strengths[slot] = _lerp(strength, 0.0, release_peak)
            continuous_floor = (
                _clamp((audio_intensity - 0.16) / 0.64, 0.0, 1.0)
                * self.audible_level
                * (0.052 + self.beat_level * 0.092 + self.kiai_level * 0.034)
            )
            if continuous_floor > 0.0:
                slot_bias = 0.86 + (self.alpha_variation[(slot * self.bar_count // 4) % self.bar_count] * 0.12)
                self.peak_strengths[slot] = max(
                    self.peak_strengths[slot],
                    continuous_floor * slot_bias
                )

        wave_offset = self.beat_phase
        raw_targets = self.region_targets
        for index, value in enumerate(bands):
            position = index / self.bar_count
            left_2_value = float(bands[(index - 2) % self.bar_count])
            left_1_value = float(bands[(index - 1) % self.bar_count])
            right_1_value = float(bands[(index + 1) % self.bar_count])
            right_2_value = float(bands[(index + 2) % self.bar_count])
            local_average = (
                (float(value) * 0.36)
                + ((left_1_value + right_1_value) * 0.22)
                + ((left_2_value + right_2_value) * 0.10)
            )
            previous_band = self.band_memory[index]
            transient = max(0.0, float(value) - previous_band)
            memory_speed = 18.0 if value > previous_band else 4.8
            self.band_memory[index] = _lerp(
                previous_band,
                float(value),
                1.0 - math.exp(-dt * memory_speed)
            )
            self.band_transients[index] = _lerp(
                self.band_transients[index],
                transient,
                1.0 - math.exp(-dt * (28.0 if transient > self.band_transients[index] else 8.0))
            )
            contrast = _clamp(
                ((float(value) - local_average) * 2.35)
                + (self.band_transients[index] * 1.75),
                0.0,
                1.0
            )
            wave = (
                math.sin((position - wave_offset) * math.tau * 2.0)
                + 1.0
            ) * 0.5
            detail_wave = (
                math.sin(
                    (position * math.tau * 9.0)
                    - (self.sweep_position * math.tau * 2.6)
                )
                + 1.0
            ) * 0.5
            anti_sweep = (1.0 - self.sweep_position) % 1.0
            wave_lift = 0.0
            for wave_slot in range(4):
                wave_center = (anti_sweep + wave_slot * 0.25) % 1.0
                wave_distance = abs(((position - wave_center + 0.5) % 1.0) - 0.5) * 2.0
                wave_lift = max(
                    wave_lift,
                    max(0.0, 1.0 - (wave_distance / 0.118)) ** 2.25
                )
            sweep = wave_lift
            local_peak = 0.0
            peak_cut = 0.0
            for center, strength in zip(self.peak_centers, self.peak_strengths):
                step = ((center - position) % 1.0) * self.bar_count
                stair_peak = 0.0
                if 0.0 <= step < 4.0:
                    stair_weights = (0.40, 0.78, 1.18, 1.72)
                    stair_index = max(0, min(3, int(step + 0.0001)))
                    slot_center = stair_index + 0.5
                    slot_fill = max(0.0, 1.0 - abs(step - slot_center) / 0.72) ** 0.82
                    stair_peak = stair_weights[stair_index] * (0.86 + slot_fill * 0.14)
                elif 4.0 <= step < 5.35:
                    peak_cut = max(peak_cut, 1.0 - ((step - 4.0) / 1.35))
                local_peak = max(
                    local_peak,
                    strength * stair_peak * self.intense_peak_boost
                )
            local_peak = max(
                local_peak,
                wave_lift * self.audible_level * (0.10 + audio_intensity * 0.12)
            )
            self.peak_cut_masks[index] = peak_cut
            band = _clamp(
                (value * 0.86)
                + (mid * 0.16)
                + (high * 0.12 * self.alpha_variation[index])
                + (low * 0.14 * (wave ** 1.6))
                + (contrast * (0.24 + (rms * 0.22) + (beat_pulse * 0.10)))
                + (detail_wave * contrast * 0.08)
                + (wave_lift * (0.112 + beat_pulse * 0.155 + rms * 0.082) * self.audible_level)
                + (local_peak * 1.72),
                0.0,
                1.0
            )
            calm_visibility = (
                0.04
                + (self.activity_bias[index] * 0.12)
                + (detail_wave * 0.07)
                + (wave_lift * 0.84)
            )
            minimum = (
                self.minimum_level_base
                + (rms * 0.012)
                + (self.kiai_level * 0.008)
            ) * self.audible_level * calm_visibility
            target = max(minimum * self.length_bias[index], band)
            target *= 0.82 + (beat_pulse * 0.20) + (fft_pulse * 0.12) + (self.kiai_level * 0.14)
            target *= 1.0 + (wave_lift * (0.76 + beat_pulse * 0.24 + rms * 0.12))
            target *= 0.90 + ((self.length_bias[index] - 1.0) * 0.18)
            target *= 0.84 + (self.activity_bias[index] * 0.22)
            target *= 1.0 + (contrast * 0.42) + (self.band_transients[index] * 0.30)
            target *= 1.0 + (local_peak * (4.28 + self.alpha_variation[index] * 0.78))
            peak_drive = _clamp(max(beat_pulse, fft_pulse, rms), 0.0, 1.0)
            dynamic_rank = _clamp(
                (float(value) * 0.44)
                + (contrast * 0.42)
                + (self.band_transients[index] * 0.32)
                + (wave_lift * 0.07)
                + (wave_lift * 0.10)
                + (detail_wave * 0.05)
                + (local_peak * 0.94),
                0.0,
                1.0
            )
            diversity_gate = 0.42 + (dynamic_rank * 0.58)
            target *= 1.0 - (peak_drive * (1.0 - diversity_gate) * 0.70)
            self.dynamic_caps[index] = _clamp(
                0.15
                + (dynamic_rank * 0.30)
                + (wave_lift * 0.22)
                + (local_peak * 1.32)
                + (self.kiai_level * 0.03),
                0.14,
                1.0
            )
            target *= self.audible_level
            raw_targets[index] = _clamp(target, 0.0, 1.0)

        for index, target in enumerate(raw_targets):
            left_2 = raw_targets[(index - 2) % self.bar_count]
            left_1 = raw_targets[(index - 1) % self.bar_count]
            right_1 = raw_targets[(index + 1) % self.bar_count]
            right_2 = raw_targets[(index + 2) % self.bar_count]
            target = (target * 0.74) + ((left_1 + right_1) * 0.09) + ((left_2 + right_2) * 0.04)
            if self.peak_cut_masks[index] > 0.0:
                target = min(target, raw_targets[index])
            target = min(target, self.dynamic_caps[index])
            target = _clamp(target, 0.0, 1.0)
            self.bar_cooldowns[index] = max(0.0, self.bar_cooldowns[index] - dt)
            self.bar_attack_windows[index] = max(0.0, self.bar_attack_windows[index] - dt)
            rising = target > self.levels[index] + 0.012
            if rising and self.bar_cooldowns[index] <= 0.0:
                cooldown = _clamp(beat_seconds * 0.60, 0.175, 0.500)
                self.bar_cooldowns[index] = cooldown * (0.86 + self.alpha_variation[index] * 0.18)
                self.bar_attack_windows[index] = _clamp(cooldown * 0.34, 0.070, 0.150)
            elif rising and self.bar_attack_windows[index] <= 0.0:
                target = min(target, max(0.0, self.levels[index] * 0.58))
            if self.bar_cooldowns[index] > 0.0 and self.bar_attack_windows[index] <= 0.0:
                target = min(target, self.levels[index] * 0.74)
            instant_target = target
            peak_target = max(0.0, instant_target - self.levels[index])
            peak_target = _clamp(
                (
                    (peak_target * 4.1)
                    + (beat_pulse * 0.15 * instant_target)
                    + (fft_pulse * 0.12 * instant_target)
                    + (self.kiai_level * 0.08 * instant_target)
                )
                * self.alpha_bias[index],
                0.0,
                1.0
            )
            peak_amount = 0.70 if peak_target > self.band_alpha[index] else 0.22
            peak_amount = 1.0 - ((1.0 - peak_amount) ** max(0.0, dt * 60.0))
            self.band_alpha[index] = _lerp(self.band_alpha[index], peak_target, peak_amount)

            amount = self.attack_amount if target > self.levels[index] else self.release_amount
            amount = 1.0 - ((1.0 - amount) ** max(0.0, dt * 60.0))
            self.levels[index] = _lerp(
                self.levels[index],
                target,
                amount
            )

    def draw(self, surface, center, radius, beat_level=None, music_energy=None, color=(255, 255, 255)):
        self.center = center
        self.radius = float(max(1, int(round(float(radius) / 4.0) * 4)))
        energy = self.energy if music_energy is None else max(self.energy, float(music_energy) * 0.75)
        beat = self.beat_level if beat_level is None else max(self.beat_level, float(beat_level) * 0.75)

        logo_radius = self.radius * 1.06
        inner_radius = logo_radius - max(6.0, self.radius * 0.052)
        max_length = (
            self.radius
            * (0.36 + energy * 1.02 + beat * 0.48 + self.kiai_level * 0.16)
            * self.max_length_scale
        )
        target_layer_radius = int(math.ceil((logo_radius + max_length + self.bar_width + 6) / 32.0) * 32)
        layer_radius = target_layer_radius
        if self._layer_radius > 0:
            if target_layer_radius > self._layer_radius:
                self._layer_shrink_elapsed = 0.0
                layer_radius = int(math.ceil((target_layer_radius * 1.12) / 32.0) * 32)
            elif target_layer_radius < self._layer_radius:
                if self._layer_shrink_elapsed < 1.20:
                    layer_radius = self._layer_radius
                else:
                    layer_radius = int(math.ceil((target_layer_radius * 1.12) / 32.0) * 32)
        else:
            layer_radius = int(math.ceil((target_layer_radius * 1.12) / 32.0) * 32)
        output_size = (layer_radius * 2, layer_radius * 2)
        if (
            self._layer is not None
            and self._layer_size == output_size
            and self._redraw_elapsed < self.render_interval
        ):
            surface.blit(self._layer, (center[0] - self._layer_radius, center[1] - self._layer_radius))
            return

        if self._layer is None or self._layer_size != output_size:
            self._layer = pygame.Surface(output_size, pygame.SRCALPHA).convert_alpha()
            self._layer_size = output_size
            self._redraw_elapsed = self.render_interval
        layer = self._layer
        layer.fill((0, 0, 0, 0))
        self._layer_radius = layer_radius
        self._redraw_elapsed = 0.0
        local_center = (layer_radius, layer_radius)
        drop_glow = _clamp(
            ((energy * 0.78) + (beat * 0.52) + (self.kiai_level * 0.34) - 0.62)
            / 0.42,
            0.0,
            1.0
        )
        if drop_glow > 0.02:
            self._draw_base_glow(layer, local_center, logo_radius, drop_glow)

        for index, level in enumerate(self.levels):
            self._draw_bar(
                layer,
                local_center,
                index,
                level,
                inner_radius,
                logo_radius,
                max_length,
                beat
            )
        surface.blit(layer, (center[0] - layer_radius, center[1] - layer_radius))

    def _draw_base_glow(self, layer, local_center, logo_radius, glow):
        alpha = int(82 * _clamp(glow, 0.0, 1.0))
        if alpha <= 0:
            return
        base_radius = int(round(logo_radius))
        for offset, scale in ((0, 1.0), (4, 0.62), (9, 0.34)):
            pygame.draw.circle(
                layer,
                (255, 255, 255, int(alpha * scale)),
                local_center,
                base_radius + offset,
                max(2, int(self.radius * (0.012 + offset * 0.001)))
            )

    def _draw_bar(self, layer, local_center, index, level, inner_radius, logo_radius, max_length, beat):
        if level <= 0.020 or self.audible_level <= 0.004:
            return

        ux, uy = self.units[index]
        position = index / self.bar_count
        anti_sweep = (1.0 - self.sweep_position) % 1.0
        sweep = 0.0
        for wave_slot in range(4):
            wave_center = (anti_sweep + wave_slot * 0.25) % 1.0
            wave_distance = abs(((position - wave_center + 0.5) % 1.0) - 0.5) * 2.0
            sweep = max(sweep, max(0.0, 1.0 - (wave_distance / 0.118)) ** 2.25)
        transient = self.band_transients[index]
        length = max(10.0, max_length * (level ** 1.02) * self.length_bias[index])
        length *= 1.0 + (transient * 0.08)
        length *= 1.0 + (sweep * (0.20 + beat * 0.09))
        if level > 0.72:
            length *= 1.0 + ((level - 0.72) / 0.28) * (0.38 + beat * 0.29)
        start_radius = inner_radius
        end_radius = logo_radius + max(5.0, length)
        width = max(2, int(round(self.bar_width)))
        brightness = _clamp(
            0.42
            + (self.audible_level * 0.22)
            + (beat * 0.13)
            + (self.kiai_level * 0.10),
            0.0,
            1.0
        )
        base_gray = int(_clamp(166 + (brightness * 38), 160, 214))
        base_alpha = int(_clamp(
            37
            + (self.audible_level * 12)
            + (beat * 6)
            + (self.kiai_level * 5),
            25,
            64
        ))
        line_color = (
            base_gray,
            base_gray,
            base_gray,
            base_alpha
        )
        self._draw_radial_rect(
            layer,
            line_color,
            local_center,
            ux,
            uy,
            start_radius,
            end_radius,
            width
        )

    def _draw_radial_rect(self, layer, color, local_center, ux, uy, start_radius, end_radius, width):
        line_width = float(max(1, int(round(width))))
        half = line_width * 0.5
        px = -uy * half
        py = ux * half
        start_x = local_center[0] + ux * start_radius
        start_y = local_center[1] + uy * start_radius
        end_x = local_center[0] + ux * end_radius
        end_y = local_center[1] + uy * end_radius
        points = (
            (int(round(start_x + px)), int(round(start_y + py))),
            (int(round(end_x + px)), int(round(end_y + py))),
            (int(round(end_x - px)), int(round(end_y - py))),
            (int(round(start_x - px)), int(round(start_y - py))),
        )
        pygame.draw.polygon(layer, color, points)

    def _analysis_at(self, current_time_ms):
        if self.analysis is None or len(self.analysis) == 0:
            return None, 0.0
        index = int(current_time_ms / self.analysis_step_ms)
        if index >= len(self.analysis):
            index %= len(self.analysis)
        bands = self.analysis[index]
        rms = self.rms_envelope[index] if index < len(self.rms_envelope) else 0.0
        return bands, rms

    def _mean_band_range(self, bands, start, stop):
        count = max(1, stop - start)
        segment = bands[start:stop]
        mean = getattr(segment, "mean", None)
        if mean is not None:
            return float(mean())
        return sum(segment) / count

    def _timing_at(self, current_time_ms):
        if not self.timing_points:
            return None

        if (
            self._timing_index >= len(self.timing_points)
            or self.timing_points[self._timing_index]["time"] > current_time_ms
        ):
            self._timing_index = 0

        while (
            self._timing_index + 1 < len(self.timing_points)
            and self.timing_points[self._timing_index + 1]["time"] <= current_time_ms
        ):
            self._timing_index += 1

        point = self.timing_points[self._timing_index]
        if point["time"] > current_time_ms:
            return None
        return point
