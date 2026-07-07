import os
import time
from collections import defaultdict, deque

import pygame

from core.fonts import rounded_font


class FrameProfiler:
    REPORT_SECTIONS = (
        "frame",
        "events",
        "update",
        "ui_update",
        "scene_manager_update",
        "scene_update",
        "surface_warm",
        "followpoint_warm",
        "slider_geometry_warm",
        "slider_reveal_warm",
        "slider_warm",
        "slider_collect",
        "background_warm",
        "spinner_warm",
        "hitobjects",
        "input_judgement_latency",
        "audio",
        "render",
        "scene_render",
        "background_render",
        "hud_render",
        "spinner_render",
        "followpoints_render",
        "overlay_composite",
        "visualizer",
        "sliders",
        "slider_render_missing_geometry",
        "slider_surface_fallback",
        "hitobjects_render",
        "ui_draw",
        "backend_present",
        "debug_render",
        "cursor_update",
        "cursor_draw",
        "flip",
        "pacer"
    )

    def __init__(self, enabled=False, sample_limit=360):
        self.enabled = enabled or os.environ.get("PYOSU_PROFILE", "0") == "1"
        self.sample_limit = sample_limit
        self.samples = defaultdict(lambda: deque(maxlen=sample_limit))
        self.starts = {}
        self.frame_start = 0.0
        self.last_report = time.perf_counter()
        self.report_interval = 2.5
        self.font = None
        self.small_font = None
        self.scene_name = None
        self.metrics = {}
        self.overlay_update_interval = max(
            0.05,
            float(os.environ.get("PYOSU_PROFILER_OVERLAY_INTERVAL", "0.25"))
        )
        self.overlay_max_rows = max(
            8,
            int(os.environ.get("PYOSU_PROFILER_OVERLAY_ROWS", "22"))
        )
        self._overlay_surface = None
        self._overlay_size = None
        self._overlay_last_update = 0.0

    def _reset_scene_samples(self, scene_name):
        if self.scene_name == scene_name:
            return
        self.scene_name = scene_name
        self.samples.clear()
        self.starts.clear()
        self.metrics.clear()
        self.last_report = time.perf_counter()
        self._overlay_surface = None
        self._overlay_size = None
        self._overlay_last_update = 0.0

    def toggle(self):
        self.enabled = not self.enabled
        state = "ON" if self.enabled else "OFF"
        print(f"[profiler] {state}")

    def begin_frame(self):
        if not self.enabled:
            return
        self.frame_start = time.perf_counter()

    def start(self, name):
        if not self.enabled:
            return
        self.starts[name] = time.perf_counter()

    def end(self, name):
        if not self.enabled:
            return
        start = self.starts.pop(name, None)
        if start is None:
            return
        self.samples[name].append((time.perf_counter() - start) * 1000.0)

    def add(self, name, milliseconds):
        if not self.enabled:
            return
        self.samples[name].append(float(milliseconds))

    def set_metric(self, name, value):
        if not self.enabled:
            return
        self.metrics[name] = value

    def end_frame(self, scene_name, fps):
        if not self.enabled:
            return
        self._reset_scene_samples(scene_name)
        if self.frame_start:
            self.samples["frame"].append((time.perf_counter() - self.frame_start) * 1000.0)

        now = time.perf_counter()
        if now - self.last_report < self.report_interval:
            return

        self.last_report = now
        parts = [f"[profiler] {scene_name} fps={fps:.1f}"]
        for name in self.REPORT_SECTIONS:
            stats = self.stats(name)
            if stats is None:
                continue
            parts.append(
                f"{name}:avg={stats['avg']:.2f} p50={stats['p50']:.2f} p95={stats['p95']:.2f} p99={stats['p99']:.2f} max={stats['max']:.2f}ms"
            )
        if self.metrics:
            metric_text = " ".join(
                f"{key}={value}" for key, value in sorted(self.metrics.items())
            )
            parts.append(f"metrics:{metric_text}")
        print(" | ".join(parts))

    def stats(self, name):
        values = list(self.samples.get(name, ()))
        if not values:
            return None
        ordered = sorted(values)
        p50_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.50)))
        p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95)))
        p99_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.99)))
        return {
            "avg": sum(values) / len(values),
            "p50": ordered[p50_index],
            "p95": ordered[p95_index],
            "p99": ordered[p99_index],
            "max": max(values),
            "last": values[-1]
        }

    def _fit_overlay_line(self, font, line, max_width):
        if font.size(line)[0] <= max_width:
            return line
        ellipsis = "..."
        while len(line) > 4 and font.size(line + ellipsis)[0] > max_width:
            line = line[:-1]
        return line + ellipsis

    def _metric_lines(self, font, max_width):
        if not self.metrics:
            return []
        lines = []
        current = "metrics"
        for key, value in sorted(self.metrics.items()):
            part = f"  {key}: {value}"
            candidate = current + part
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            lines.append(current)
            current = "metrics" + part
        lines.append(current)
        return lines

    def draw_overlay(self, screen, scene_name, fps):
        if not self.enabled:
            return
        self._reset_scene_samples(scene_name)
        if self.font is None:
            self.font = rounded_font(15)
            self.small_font = rounded_font(13)

        now = time.perf_counter()
        screen_size = screen.get_size()
        if (
            self._overlay_surface is not None
            and self._overlay_size == screen_size
            and now - self._overlay_last_update < self.overlay_update_interval
        ):
            screen.blit(self._overlay_surface, (12, 12))
            return

        lines = [f"F3 profiler | {scene_name} | FPS {fps:5.1f}"]
        for name in self.REPORT_SECTIONS:
            stats = self.stats(name)
            if stats is None:
                continue
            lines.append(
                f"{name:<12} avg {stats['avg']:5.2f}  p95 {stats['p95']:5.2f}  p99 {stats['p99']:5.2f}  max {stats['max']:5.2f} ms"
            )
        line_height = 16
        width = min(430, max(390, screen.get_width() - 24))
        text_max_width = width - 20
        lines.extend(self._metric_lines(self.small_font, text_max_width))

        max_lines = min(
            self.overlay_max_rows,
            max(5, (screen.get_height() - 24) // line_height)
        )
        if len(lines) > max_lines:
            hidden = len(lines) - max_lines + 1
            lines = lines[:max_lines - 1] + [f"... {hidden} more profiler rows"]

        height = 12 + (len(lines) * line_height)
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 170))
        pygame.draw.rect(panel, (90, 170, 255, 180), panel.get_rect(), 1, border_radius=4)

        for index, line in enumerate(lines):
            font = self.font if index == 0 else self.small_font
            color = (230, 246, 255) if index == 0 else (215, 225, 235)
            fitted = self._fit_overlay_line(font, line, width - 20)
            text = font.render(fitted, True, color)
            panel.blit(text, (10, 8 + index * line_height))

        self._overlay_surface = panel
        self._overlay_size = screen_size
        self._overlay_last_update = now
        screen.blit(panel, (12, 12))
