import math

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
        self.band_targets = [0.0] * bar_count
        self.band_alpha = [0.0] * bar_count
        self.angles = [(index / bar_count) * math.tau for index in range(bar_count)]
        self.units = [(math.cos(angle), math.sin(angle)) for angle in self.angles]
        self.variation = [
            0.54 + ((((index * 37) % 100) / 100.0) * 0.84)
            for index in range(bar_count)
        ]
        self.alpha_variation = [
            0.68 + ((((index * 53) % 100) / 100.0) * 0.42)
            for index in range(bar_count)
        ]
        self.max_length_scale = 0.503
        self.bar_width_min = 2
        self.bar_width_max = 3
        self.minimum_level_base = 0.15
        self.minimum_alpha = 34
        self.attack_amount = 0.85
        self.release_amount = 0.12
        self.sweep_position = 0.0

        self.center = (0, 0)
        self.radius = 160.0
        self.energy = 0.12
        self.beat_level = 0.0
        self.beat_phase = 0.0
        self.kiai_level = 0.0
        self.analysis_step_ms = 36
        self.analysis = []
        self.rms_envelope = []
        self.timing_points = []
        self._layer = None
        self._layer_size = None

    def load_audio_analysis(self, audio_path, timing_points=None):
        self.timing_points = self.parse_timing_points(timing_points or [])
        self.analysis = []
        self.rms_envelope = []
        self.energy = 0.12
        self.beat_level = 0.0
        self.beat_phase = 0.0
        self.kiai_level = 0.0
        self.levels = [0.0] * self.bar_count

        if not audio_path:
            return

        cache_key = (str(audio_path), self.bar_count, self.analysis_step_ms)
        cached = self._analysis_cache.get(cache_key)
        if cached is not None:
            self.analysis, self.rms_envelope = cached
            return

        try:
            import numpy as np
        except ImportError:
            return

        try:
            sound = pygame.mixer.Sound(str(audio_path))
            samples = pygame.sndarray.array(sound)
        except (pygame.error, ValueError, TypeError):
            return

        if samples.size == 0:
            return

        samples = samples.astype("float32")
        if samples.ndim > 1:
            samples = samples.mean(axis=1)

        peak = float(np.max(np.abs(samples))) if samples.size else 0.0
        if peak <= 0.0:
            return
        samples = samples / peak

        mixer_init = pygame.mixer.get_init()
        sample_rate = mixer_init[0] if mixer_init else 44100
        fft_size = 2048
        hop = max(1, int(sample_rate * self.analysis_step_ms / 1000))
        if len(samples) < fft_size:
            return

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
            return

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

        self.analysis = matrix.astype("float32")
        self.rms_envelope = [float(value) for value in rms]
        if len(self._analysis_cache) > 8:
            self._analysis_cache.clear()
        self._analysis_cache[cache_key] = (self.analysis, self.rms_envelope)

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

    def update(self, dt, current_time_ms):
        current_time_ms = max(0.0, float(current_time_ms or 0.0))
        timing = self._timing_at(current_time_ms)
        if timing:
            ms_per_beat = max(1.0, timing["ms_per_beat"])
            self.beat_phase = ((current_time_ms - timing["time"]) / ms_per_beat) % 1.0
            self.sweep_position = ((current_time_ms - timing["time"]) / (ms_per_beat * 4.0)) % 1.0
            self.kiai_level = _lerp(
                self.kiai_level,
                1.0 if timing.get("kiai") else 0.0,
                1.0 - math.exp(-dt * 3.0)
            )
        else:
            self.beat_phase = (self.beat_phase + (dt * 118.0 / 60.0)) % 1.0
            self.sweep_position = (self.sweep_position + (dt * 118.0 / 240.0)) % 1.0
            self.kiai_level = _lerp(self.kiai_level, 0.0, 1.0 - math.exp(-dt * 3.0))

        bands, rms = self._analysis_at(current_time_ms)
        beat_distance = min(self.beat_phase, 1.0 - self.beat_phase)
        timing_beat = _clamp(1.0 - (beat_distance / 0.125), 0.0, 1.0) ** 2.15

        if bands is None:
            rms = max(0.04, timing_beat * 0.32)
            bands = [
                max(0.0, math.sin((index / self.bar_count) * math.tau * 3.0 + self.beat_phase * math.tau))
                * rms
                for index in range(self.bar_count)
            ]

        low = sum(bands[:max(1, self.bar_count // 5)]) / max(1, self.bar_count // 5)
        mid_start = self.bar_count // 5
        mid_end = self.bar_count * 3 // 5
        mid = sum(bands[mid_start:mid_end]) / max(1, mid_end - mid_start)
        high = sum(bands[mid_end:]) / max(1, self.bar_count - mid_end)

        beat_audio = _clamp((low * 0.72) + (rms * 0.42), 0.0, 1.0)
        beat_pulse = _clamp(timing_beat * 0.72, 0.0, 1.0)
        fft_pulse = _clamp(beat_audio * 0.58, 0.0, 1.0)
        self.beat_level = _lerp(
            self.beat_level,
            max(beat_pulse, fft_pulse),
            1.0 - math.exp(-dt * 15.0)
        )
        self.energy = _lerp(
            self.energy,
            _clamp((low * 0.32) + (mid * 0.30) + (high * 0.14) + (rms * 0.42), 0.15, 1.0),
            1.0 - math.exp(-dt * (7.5 if rms > self.energy else 3.2))
        )

        wave_offset = self.beat_phase
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
                + (sweep * (0.018 + beat_pulse * 0.060 + rms * 0.026)),
                0.0,
                1.0
            )
            minimum = self.minimum_level_base + (rms * 0.026) + (self.kiai_level * 0.014)
            target = max(minimum * self.variation[index], band)
            target *= 0.82 + (beat_pulse * 0.20) + (fft_pulse * 0.12) + (self.kiai_level * 0.14)
            target *= 0.78 + ((self.variation[index] - 0.54) * 0.24)
            target = _clamp(target, 0.0, 1.0)

            amount = self.attack_amount if target > self.levels[index] else self.release_amount
            amount = 1.0 - ((1.0 - amount) ** max(0.0, dt * 60.0))
            self.levels[index] = _lerp(
                self.levels[index],
                target,
                amount
            )

    def draw(self, surface, center, radius, beat_level=None, music_energy=None, color=(255, 255, 255)):
        self.center = center
        self.radius = float(radius)
        energy = self.energy if music_energy is None else max(self.energy, float(music_energy) * 0.75)
        beat = self.beat_level if beat_level is None else max(self.beat_level, float(beat_level) * 0.75)

        logo_radius = self.radius * 1.06
        inner_radius = logo_radius - max(6.0, self.radius * 0.052)
        max_length = (
            self.radius
            * (0.28 + energy * 1.28 + beat * 0.70 + self.kiai_level * 0.28)
            * self.max_length_scale
        )
        layer_radius = int(logo_radius + max_length + self.bar_width_max + 6)
        output_size = (layer_radius * 2, layer_radius * 2)
        if self._layer is None or self._layer_size != output_size:
            self._layer = pygame.Surface(output_size, pygame.SRCALPHA).convert_alpha()
            self._layer_size = output_size
        layer = self._layer
        layer.fill((0, 0, 0, 0))
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
        if level <= 0.001:
            return

        ux, uy = self.units[index]
        position = index / self.bar_count
        sweep_distance = abs(((position - self.sweep_position + 0.5) % 1.0) - 0.5) * 2.0
        sweep = max(0.0, 1.0 - (sweep_distance / 0.30)) ** 2.2
        length = max(3.0, max_length * (level ** 1.08) * self.variation[index])
        length *= 1.0 + (sweep * (0.08 + beat * 0.07))
        start_radius = inner_radius
        end_radius = logo_radius + max(5.0, length)
        width = self.bar_width_min if level < 0.56 else self.bar_width_max
        arc_spacing = (math.tau * logo_radius) / max(1, self.bar_count)
        width = int(_clamp(width, 2, max(2, min(self.bar_width_max, int(arc_spacing * 0.58)))))
        brightness = _clamp(0.34 + level * 0.56 + sweep * (0.12 + beat * 0.08), 0.34, 1.0)
        alpha = int(_clamp(
            (38 + level * 190 + sweep * (28 + beat * 38)) * self.alpha_variation[index],
            self.minimum_alpha,
            232
        ))
        line_color = (
            int(_clamp(255 * brightness, 0, 255)),
            int(_clamp(255 * brightness, 0, 255)),
            int(_clamp(255 * brightness, 0, 255)),
            alpha
        )
        start = (
            int(local_center[0] + ux * start_radius),
            int(local_center[1] + uy * start_radius)
        )
        end = (
            int(local_center[0] + ux * end_radius),
            int(local_center[1] + uy * end_radius)
        )
        pygame.draw.line(layer, line_color, start, end, width)

    def _analysis_at(self, current_time_ms):
        if self.analysis is None or len(self.analysis) == 0:
            return None, 0.0
        index = int(current_time_ms / self.analysis_step_ms)
        if index >= len(self.analysis):
            index %= len(self.analysis)
        bands = self.analysis[index]
        rms = self.rms_envelope[index] if index < len(self.rms_envelope) else 0.0
        return bands, rms

    def _timing_at(self, current_time_ms):
        active = None
        for point in self.timing_points:
            if point["time"] <= current_time_ms:
                active = point
            else:
                break
        return active
