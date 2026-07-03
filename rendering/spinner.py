import math

import pygame

from core.assets import load_image

 
class SpinnerRenderer:
    def __init__(self, scene):
        self.scene = scene
        self.images = {
            "approach": self._load_image("spinner-approachcircle.png"),
            "circle": self._load_image("spinner-circle.png")
        }
        self.cache = {}
        self.prewarm_jobs = []
        self.prewarm_index = 0
        self.prewarm_complete = True
        # Small buckets keep the spinner approach circle visually continuous.
        # Cache pruning below prevents the old every-scale prewarm OOM.
        self.approach_quantize_step = 8
        self.cache_limit = 176
        self.scaled_cache_limit = 72
        self.rotated_cache_limit = 32
        self.rotation_angle_step = 15
        self.circle_scale = 0.686
        self.approach_start_scale = 3.68
        self.approach_end_scale = 0.16
        self.approach_curve_power = 1.12

    def _load_image(self, filename):
        img = load_image(filename, "spinner")
        if img is None:
            return None
        img = img.convert_alpha()
        if filename == "spinner-circle.png":
            return self._trim_transparent_padding(img, padding=4)
        return img

    def _trim_transparent_padding(self, image, padding=0):
        bounds = image.get_bounding_rect()
        if bounds.width <= 0 or bounds.height <= 0:
            return image
        padded = bounds.inflate(padding * 2, padding * 2)
        padded.clamp_ip(image.get_rect())
        if padded.size == image.get_size():
            return image
        trimmed = image.subsurface(padded).copy()
        try:
            return trimmed.convert_alpha()
        except pygame.error:
            return trimmed

    def reset_prewarm_jobs(self, notes):
        self.prewarm_jobs = self._build_prewarm_jobs(notes)
        self.prewarm_index = 0
        self.prewarm_complete = not self.prewarm_jobs

    def _spinner_radius(self):
        return int(min(self.scene.game.WIDTH, self.scene.game.HEIGHT) * 0.44)

    def _spinner_circle_diameter(self):
        return int(self._spinner_radius() * self.circle_scale)

    def _spinner_center(self):
        return (
            int(round(self.scene.game.WIDTH * 0.5)),
            int(round(self.scene.game.HEIGHT * 0.5))
        )

    def _build_prewarm_jobs(self, notes):
        if not any(note.get("type") == "spinner" for note in notes):
            return []

        jobs = []
        radius = self._spinner_radius()
        circle = self.images.get("circle")
        approach = self.images.get("approach")

        circle_diameter = self._spinner_circle_diameter()
        if circle is not None:
            jobs.append(("scale", circle, circle_diameter, None))
            for angle in range(0, 360, self.rotation_angle_step):
                jobs.append(("rotated", circle, circle_diameter, angle))

        if approach is not None:
            max_diameter = int(radius * self.approach_start_scale)
            min_diameter = max(1, int(radius * self.approach_end_scale))
            step = max(4, int(self.approach_quantize_step))
            warm_diameters = {max_diameter, min_diameter}
            for index in range(1, 23):
                t = index / 23.0
                diameter = max_diameter + ((min_diameter - max_diameter) * t)
                warm_diameters.add(max(1, int(round(diameter / step)) * step))
            for diameter in sorted(warm_diameters, reverse=True):
                jobs.append(("scale", approach, diameter, step))

        return jobs

    def prewarm_step(self, max_ms=1.0, max_items=8):
        if self.prewarm_complete:
            return True

        start = pygame.time.get_ticks()
        count = 0
        total = len(self.prewarm_jobs)
        while self.prewarm_index < total:
            job = self.prewarm_jobs[self.prewarm_index]
            self.prewarm_index += 1
            kind = job[0]
            if kind == "scale":
                _, image, diameter, quantize_step = job
                self._scaled(image, diameter, quantize_step=quantize_step)
            elif kind == "rotated":
                _, image, diameter, angle = job
                self._rotated(image, diameter, angle)

            count += 1
            if count >= max_items or pygame.time.get_ticks() - start >= max_ms:
                break

        self.prewarm_complete = self.prewarm_index >= total
        return self.prewarm_complete

    def draw(self, target, note):
        start = note["spinner_start_time"]
        end = note["spinner_end_time"]
        current = self.scene.current_time
        if current < start or current > note.get("end_time", end):
            return

        center = self._spinner_center()
        duration = max(1, end - start)
        radius = self._spinner_radius()
        progress = self.scene._clamp01((current - start) / duration)
        approach_progress = 1.0 - ((1.0 - progress) ** self.approach_curve_power)
        fade_in = self.scene._ease_out_cubic((current - start) / 110.0)
        fade_out = 1.0
        fade_out_start = note.get("fade_out_start")
        if fade_out_start is not None:
            fade_out_duration = max(1.0, float(note.get("fade_out_duration", 260)))
            fade_out_progress = self.scene._clamp01(
                (current - fade_out_start) / fade_out_duration
            )
            fade_out = (1.0 - fade_out_progress) ** 1.35
        object_alpha_scale = getattr(self.scene, "object_alpha_scale", 1.0)
        alpha = int(255 * fade_in * fade_out * object_alpha_scale)
        visual_angle = -math.degrees(note.get("spinner_visual_angle", 0.0))
        approach_close_fade = 1.0 - self.scene._smoothstep(
            self.scene._clamp01((progress - 0.94) / 0.06)
        )
        approach_alpha = int(
            235
            * fade_in
            * fade_out
            * object_alpha_scale
            * approach_close_fade
        )

        if approach_alpha > 0:
            self._draw_image_centered(
                target,
                self.images["approach"],
                center,
                int(
                    radius
                    * (
                        self.approach_start_scale
                        - (
                            (self.approach_start_scale - self.approach_end_scale)
                            * approach_progress
                        )
                    )
                ),
                alpha=approach_alpha,
                quantize_step=self.approach_quantize_step
            )
        if not self._draw_rotated_centered(
            target,
            self.images["circle"],
            center,
            self._spinner_circle_diameter(),
            visual_angle,
            alpha=alpha
        ):
            pygame.draw.circle(
                target,
                (235, 235, 245, int(175 * fade_in * fade_out * object_alpha_scale)),
                center,
                int(radius * 0.68),
                max(6, radius // 28)
            )

        if note.get("spinner_goal_reached"):
            text = getattr(self.scene, "spinner_pass_text_surface", None)
            if text is None:
                text = self.scene.medium_overlay_font.render(
                    "PASS",
                    True,
                    (255, 245, 150)
                )
                self.scene.spinner_pass_text_surface = text
            pass_time = note.get("spinner_pass_time", current)
            pop = self.scene._clamp01((current - pass_time) / 180.0)
            settle = self.scene._clamp01((current - pass_time) / 520.0)
            text_alpha = int(210 * fade_in * fade_out * (1.0 - settle * 0.28))
            previous_alpha = text.get_alpha()
            text.set_alpha(max(0, min(255, text_alpha)))
            text_rect = text.get_rect(
                center=(
                    center[0],
                    center[1] + int(radius * (0.42 - 0.035 * self.scene._ease_out_cubic(pop)))
                )
            )
            target.blit(text, text_rect)
            text.set_alpha(previous_alpha)

    def _draw_image_centered(
        self,
        target,
        image,
        center,
        diameter,
        alpha=255,
        quantize_step=None
    ):
        if image is None:
            return False
        scaled = self._scaled(image, diameter, quantize_step=quantize_step)
        previous_alpha = scaled.get_alpha()
        if alpha != 255:
            scaled.set_alpha(alpha)
        target.blit(scaled, scaled.get_rect(center=center))
        if alpha != 255:
            scaled.set_alpha(previous_alpha)
        return True

    def _draw_rotated_centered(self, target, image, center, diameter, angle, alpha=255):
        if image is None:
            return False
        angle_key = int(round(angle / self.rotation_angle_step) * self.rotation_angle_step) % 360
        rotated = self._rotated(image, diameter, angle_key)

        previous_alpha = rotated.get_alpha()
        if alpha != 255:
            rotated.set_alpha(alpha)
        target.blit(rotated, rotated.get_rect(center=center))
        if alpha != 255:
            rotated.set_alpha(previous_alpha)
        return True

    def _rotated(self, image, diameter, angle_key):
        key = ("rotated", id(image), max(1, int(diameter)), int(angle_key) % 360)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        scaled = self._scaled(image, diameter)
        try:
            cached = pygame.transform.rotozoom(scaled, key[3], 1.0).convert_alpha()
        except pygame.error:
            cached = scaled
        self.cache[key] = cached
        self._prune_cache(protected_key=key)
        return cached

    def _scaled(self, image, diameter, quantize_step=None):
        diameter = max(1, int(diameter))
        if quantize_step is not None:
            step = max(1, int(quantize_step))
            diameter = max(1, int(round(diameter / step)) * step)
        elif diameter >= 128:
            diameter = max(1, int(round(diameter / 8.0)) * 8)
        elif diameter >= 48:
            diameter = max(1, int(round(diameter / 4.0)) * 4)
        key = (id(image), diameter)
        cached = self.cache.get(key)
        if cached is None:
            try:
                cached = pygame.transform.smoothscale(
                    image,
                    (diameter, diameter)
                ).convert_alpha()
            except pygame.error:
                try:
                    cached = pygame.transform.scale(
                        image,
                        (diameter, diameter)
                    ).convert_alpha()
                except pygame.error:
                    return image
            self.cache[key] = cached
            self._prune_cache(protected_key=key)
        return cached

    def _prune_cache(self, protected_key=None):
        scaled_keys = []
        rotated_keys = []
        protected_is_scaled = (
            isinstance(protected_key, tuple)
            and len(protected_key) == 2
            and isinstance(protected_key[1], int)
        )
        protected_is_rotated = (
            isinstance(protected_key, tuple)
            and protected_key[:1] == ("rotated",)
        )
        for key in self.cache:
            if key == protected_key:
                continue
            if (
                isinstance(key, tuple)
                and len(key) == 2
                and isinstance(key[1], int)
            ):
                scaled_keys.append(key)
            elif isinstance(key, tuple) and key[:1] == ("rotated",):
                rotated_keys.append(key)

        scaled_limit = max(
            0,
            self.scaled_cache_limit - (1 if protected_is_scaled else 0)
        )
        rotated_limit = max(
            0,
            self.rotated_cache_limit - (1 if protected_is_rotated else 0)
        )

        while len(rotated_keys) > rotated_limit:
            self.cache.pop(rotated_keys.pop(0), None)

        while len(scaled_keys) > scaled_limit:
            self.cache.pop(scaled_keys.pop(0), None)

        for key in list(self.cache):
            if len(self.cache) <= self.cache_limit:
                break
            if key != protected_key:
                self.cache.pop(key, None)
