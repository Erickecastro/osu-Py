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
        "scene_manager_update",
        "scene_update",
        "surface_warm",
        "followpoint_warm",
        "slider_warm",
        "slider_collect",
        "background_warm",
        "hitobjects",
        "audio",
        "render",
        "scene_render",
        "visualizer",
        "sliders",
        "hitobjects_render",
        "ui_draw",
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

    def _reset_scene_samples(self, scene_name):
        if self.scene_name == scene_name:
            return
        self.scene_name = scene_name
        self.samples.clear()
        self.starts.clear()
        self.last_report = time.perf_counter()

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
                f"{name}:avg={stats['avg']:.2f} p95={stats['p95']:.2f} max={stats['max']:.2f}ms"
            )
        print(" | ".join(parts))

    def stats(self, name):
        values = list(self.samples.get(name, ()))
        if not values:
            return None
        ordered = sorted(values)
        p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95)))
        return {
            "avg": sum(values) / len(values),
            "p95": ordered[p95_index],
            "max": max(values),
            "last": values[-1]
        }

    def draw_overlay(self, screen, scene_name, fps):
        if not self.enabled:
            return
        self._reset_scene_samples(scene_name)
        if self.font is None:
            self.font = rounded_font(15)
            self.small_font = rounded_font(13)

        lines = [f"F3 profiler | {scene_name} | FPS {fps:5.1f}"]
        for name in self.REPORT_SECTIONS:
            stats = self.stats(name)
            if stats is None:
                continue
            lines.append(
                f"{name:<12} avg {stats['avg']:5.2f}  p95 {stats['p95']:5.2f}  max {stats['max']:5.2f} ms"
            )

        line_height = 18
        width = 390
        height = 12 + (len(lines) * line_height)
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 170))
        pygame.draw.rect(panel, (90, 170, 255, 180), panel.get_rect(), 1, border_radius=4)

        for index, line in enumerate(lines):
            font = self.font if index == 0 else self.small_font
            color = (230, 246, 255) if index == 0 else (215, 225, 235)
            text = font.render(line, True, color)
            panel.blit(text, (10, 8 + index * line_height))

        screen.blit(panel, (12, 12))
