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
        self.angles = [(index / bar_count) * math.tau for index in range(bar_count)]
        self.units = [(math.cos(angle), math.sin(angle)) for angle in self.angles]
        self.variation = []
        for index in range(bar_count):
            value = ((index * 37) % 100) / 100.0
            self.variation.append(0.42 + (value ** 1.28) * 1.22)
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
        self.max_length_scale = 0.904
        self.bar_width = 12.0
        self.minimum_level_base = 0.08
        self.minimum_alpha = 0
        self.attack_amount = 0.85
        self.release_amount = 0.075
        self.sweep_position = 0.0

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
        self.render_interval = 1.0 / 60.0
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
            return

        result = self._build_audio_analysis(audio_path)
        if result is None:
            return

        self.analysis, self.rms_envelope = result
        self._store_analysis_cache(cache_key, result)

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
        self.region_targets = [0.0] * self.bar_count

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

    def _store_analysis_cache(self, cache_key, result):
        if len(self._analysis_cache) > 8:
            self._analysis_cache.clear()
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
            self.beat_phase = ((current_time_ms - timing["time"]) / ms_per_beat) % 1.0
            self.sweep_position = ((current_time_ms - timing["time"]) / (ms_per_beat * 6.0)) % 1.0
            self.kiai_level = _lerp(
                self.kiai_level,
                1.0 if timing.get("kiai") else 0.0,
                1.0 - math.exp(-dt * 3.0)
            )
        else:
            self.beat_phase = (self.beat_phase + (dt * 118.0 / 60.0)) % 1.0
            self.sweep_position = (self.sweep_position + (dt * 118.0 / 360.0)) % 1.0
            self.kiai_level = _lerp(self.kiai_level, 0.0, 1.0 - math.exp(-dt * 3.0))

        bands, rms = self._analysis_at(current_time_ms)
        if not audio_active:
            rms = 0.0
            bands = self.silent_bands
        beat_distance = min(self.beat_phase, 1.0 - self.beat_phase)
        timing_beat = _clamp(1.0 - (beat_distance / 0.125), 0.0, 1.0) ** 2.15

        if bands is None:
            rms = max(0.0, timing_beat * 0.24)
            bands = [
                max(0.0, math.sin((index / self.bar_count) * math.tau * 3.0 + self.beat_phase * math.tau))
                * rms
                for index in range(self.bar_count)
            ]

        audible_target = _clamp((rms - 0.026) / 0.15, 0.0, 1.0)
        self.audible_level = _lerp(
            self.audible_level,
            audible_target,
            1.0 - math.exp(-dt * (12.0 if audible_target > self.audible_level else 5.0))
        )

        low_end = max(1, self.bar_count // 5)
        low = self._mean_band_range(bands, 0, low_end)
        mid_start = self.bar_count // 5
        mid_end = self.bar_count * 3 // 5
        mid = self._mean_band_range(bands, mid_start, mid_end)
        high = self._mean_band_range(bands, mid_end, self.bar_count)

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

        wave_offset = self.beat_phase
        raw_targets = self.region_targets
        for index, value in enumerate(bands):
            position = index / self.bar_count
            wave = (
                math.sin((position - wave_offset) * math.tau * 2.0)
                + 1.0
            ) * 0.5
            sweep_distance = abs(((position - self.sweep_position + 0.5) % 1.0) - 0.5) * 2.0
            sweep = max(0.0, 1.0 - (sweep_distance / 0.30)) ** 2.2
            band = _clamp(
                (value * 0.72)
                + (mid * 0.16)
                + (high * 0.08 * self.alpha_variation[index])
                + (low * 0.14 * (wave ** 1.6))
                + (sweep * (0.034 + beat_pulse * 0.082 + rms * 0.038)),
                0.0,
                1.0
            )
            minimum = (self.minimum_level_base + (rms * 0.034) + (self.kiai_level * 0.014)) * self.audible_level
            target = max(minimum * self.variation[index], band)
            target *= 0.82 + (beat_pulse * 0.20) + (fft_pulse * 0.12) + (self.kiai_level * 0.14)
            target *= 1.0 + (sweep * (0.18 + beat_pulse * 0.10))
            target *= 0.72 + ((self.variation[index] - 0.54) * 0.20)
            target *= self.activity_bias[index]
            target *= self.audible_level
            raw_targets[index] = _clamp(target, 0.0, 1.0)

        for index, target in enumerate(raw_targets):
            left_2 = raw_targets[(index - 2) % self.bar_count]
            left_1 = raw_targets[(index - 1) % self.bar_count]
            right_1 = raw_targets[(index + 1) % self.bar_count]
            right_2 = raw_targets[(index + 2) % self.bar_count]
            target = (
                (target * 0.52)
                + ((left_1 + right_1) * 0.18)
                + ((left_2 + right_2) * 0.06)
            )
            target = _clamp(target, 0.0, 1.0)
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

            if target >= self.levels[index]:
                self.level_hold[index] = 0.055
            else:
                self.level_hold[index] = max(0.0, self.level_hold[index] - dt)
                if self.level_hold[index] > 0.0:
                    target = max(target, self.levels[index] * 0.985)

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
            * (0.28 + energy * 1.28 + beat * 0.70 + self.kiai_level * 0.28)
            * self.max_length_scale
        )
        target_layer_radius = int(math.ceil((logo_radius + max_length + self.bar_width + 6) / 32.0) * 32)
        layer_radius = target_layer_radius
        if self._layer_radius > 0:
            if target_layer_radius > self._layer_radius:
                self._layer_shrink_elapsed = 0.0
            elif target_layer_radius < self._layer_radius and self._layer_shrink_elapsed < 0.45:
                layer_radius = self._layer_radius
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

    def _draw_bar(self, layer, local_center, index, level, inner_radius, logo_radius, max_length, beat):
        if level <= 0.007 or self.audible_level <= 0.012:
            return

        ux, uy = self.units[index]
        position = index / self.bar_count
        sweep_distance = abs(((position - self.sweep_position + 0.5) % 1.0) - 0.5) * 2.0
        sweep = max(0.0, 1.0 - (sweep_distance / 0.24)) ** 2.0
        length = max(4.0, max_length * (level ** 1.12) * self.variation[index])
        length *= 1.0 + (sweep * (0.14 + beat * 0.08))
        start_radius = inner_radius
        end_radius = logo_radius + max(5.0, length)
        base_arc_spacing = (math.tau * start_radius) / max(1, self.bar_count)
        base_gap = max(1.0, base_arc_spacing * 0.17)
        width = int(math.floor(_clamp(
            self.bar_width,
            2.0,
            max(2.0, base_arc_spacing - base_gap)
        )))
        bar_light = _clamp(
            0.22
            + (level * 0.26)
            + (sweep * (0.44 + beat * 0.16))
            + (self.kiai_level * 0.08),
            0.0,
            1.0
        )
        base_gray = int(_clamp(156 + (bar_light * 74), 130, 236))
        base_alpha = int(_clamp(
            (44 + (self.audible_level * 10) + (beat * 4) + (sweep * 16))
            * (0.58 + (self.alpha_bias[index] * 0.36)),
            16,
            82
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

        peak = self.band_alpha[index]
        if peak <= 0.105:
            return

        moving_slot = ((index * 47) + int(self.sweep_position * 100.0)) % 100
        highlight_chance = 15.0 + (peak * 13.0) + (beat * 4.0) + (sweep * 3.0) + (self.kiai_level * 4.0)
        if moving_slot > highlight_chance:
            return

        highlight_ratio = _clamp(0.10 + (peak * 0.075) + (beat * 0.018), 0.10, 0.20)
        highlight_length = max(3.0, length * highlight_ratio)
        highlight_start_radius = max(start_radius + 2.0, end_radius - highlight_length)
        highlight_alpha = int(_clamp(
            (peak * 166 + beat * 10 + sweep * 8) * self.alpha_variation[index],
            0,
            176
        ))
        if highlight_alpha <= 4:
            return

        highlight_width = max(1, width - 2)
        self._draw_radial_rect(
            layer,
            (255, 255, 255, highlight_alpha),
            local_center,
            ux,
            uy,
            highlight_start_radius,
            end_radius,
            highlight_width
        )

    def _draw_radial_rect(self, layer, color, local_center, ux, uy, start_radius, end_radius, width):
        half = max(0.5, width * 0.5)
        px = -uy * half
        py = ux * half
        sx = local_center[0] + ux * start_radius
        sy = local_center[1] + uy * start_radius
        ex = local_center[0] + ux * end_radius
        ey = local_center[1] + uy * end_radius
        pygame.draw.polygon(
            layer,
            color,
            (
                (int(round(sx + px)), int(round(sy + py))),
                (int(round(ex + px)), int(round(ey + py))),
                (int(round(ex - px)), int(round(ey - py))),
                (int(round(sx - px)), int(round(sy - py)))
            )
        )

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
