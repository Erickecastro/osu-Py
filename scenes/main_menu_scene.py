import math
import random
from pathlib import Path

import pygame
import pygame.sndarray

from core.assets import ACTIVE_SKIN_DIR, asset_path
from scenes.base_scene import BaseScene
from scenes.song_select_scene import SongSelectScene


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def ease_out_cubic(value):
    value = clamp(value, 0.0, 1.0)
    return 1.0 - pow(1.0 - value, 3)


def ease_in_out(value):
    value = clamp(value, 0.0, 1.0)
    return value * value * (3.0 - (2.0 * value))


def lerp(current, target, amount):
    return current + ((target - current) * clamp(amount, 0.0, 1.0))


class MenuOption:
    def __init__(self, label, action):
        self.label = label
        self.action = action
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.width_factor = 1.0
        self.hover = 0.0
        self.visible = 0.0
        self.delay = 0.0
        self._surface_cache = {}

    def set_layout(self, left_x, y, width, height, delay, width_factor=1.0):
        self.width_factor = width_factor
        width = int(width * width_factor)
        self.rect = pygame.Rect(0, 0, int(width), int(height))
        self.rect.left = int(left_x)
        self.rect.centery = int(y)
        self.delay = delay

    def update(self, dt, mouse_pos, menu_open):
        target_visible = 1.0 if menu_open else 0.0
        if menu_open and self.delay > 0:
            self.delay = max(0.0, self.delay - dt)
            target_visible = 0.0

        speed = 8.0 if target_visible > self.visible else 10.0
        self.visible = lerp(
            self.visible,
            target_visible,
            1.0 - math.exp(-dt * speed)
        )
        self.hover = lerp(
            self.hover,
            1.0 if self.rect.collidepoint(mouse_pos) and self.visible > 0.5 else 0.0,
            1.0 - math.exp(-dt * 18.0)
        )

    def handle_event(self, event):
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.visible > 0.65
            and self.rect.collidepoint(event.pos)
        ):
            self.action()
            return True

        return False

    def draw(self, surface, font):
        if self.visible <= 0.01:
            return

        visible = ease_out_cubic(self.visible)
        hover = ease_out_cubic(self.hover)
        slide = int((1.0 - visible) * -self.rect.width * 0.78)
        rect = self.rect.move(slide, 0)
        alpha = int(220 * visible)
        cache_key = (
            rect.width,
            rect.height,
            self.label,
            font.get_height(),
            int(visible * 40),
            int(hover * 24)
        )
        cached = self._surface_cache.get(cache_key)
        if cached is not None:
            surface.blit(cached, (rect.x - 20, rect.y - 11))
            return

        scale = 2
        layer_size = (rect.width + 64, rect.height + 30)
        shape_layer = pygame.Surface(
            (layer_size[0] * scale, layer_size[1] * scale),
            pygame.SRCALPHA
        )
        body = pygame.Rect(20, 11, rect.width, rect.height)
        skew = int(body.height * 0.22)
        cap_radius = body.height // 2
        cap_center = (body.right - cap_radius, body.centery)
        body_points = [
            (body.left + skew, body.top),
            (cap_center[0], body.top),
            (cap_center[0], body.bottom),
            (body.left, body.bottom)
        ]
        fill_alpha = int((180 + (42 * hover)) * visible)
        edge_alpha = int((42 + (75 * hover)) * visible)

        def scaled(points):
            return [(int(x * scale), int(y * scale)) for x, y in points]

        def draw_card(target, offset, color, outline_width=0):
            ox, oy = offset
            points = [(x + ox, y + oy) for x, y in body_points]
            center = (cap_center[0] + ox, cap_center[1] + oy)
            radius = cap_radius
            if outline_width:
                outline = pygame.Surface(target.get_size(), pygame.SRCALPHA)
                fill = pygame.Surface(target.get_size(), pygame.SRCALPHA)
                pygame.draw.polygon(outline, color, scaled(points))
                pygame.draw.circle(
                    outline,
                    color,
                    (int(center[0] * scale), int(center[1] * scale)),
                    int(radius * scale)
                )
                inset = outline_width
                inset_points = [
                    (body.left + skew + (inset // scale), body.top + (inset // scale)),
                    (cap_center[0] - (inset // scale), body.top + (inset // scale)),
                    (cap_center[0] - (inset // scale), body.bottom - (inset // scale)),
                    (body.left + (inset // scale), body.bottom - (inset // scale))
                ]
                pygame.draw.polygon(fill, (255, 255, 255, 255), scaled(inset_points))
                pygame.draw.circle(
                    fill,
                    (255, 255, 255, 255),
                    (int((center[0] - (inset // scale)) * scale), int(center[1] * scale)),
                    max(1, int((radius - (inset // scale)) * scale))
                )
                outline.blit(fill, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
                target.blit(outline, (0, 0))
                return

            pygame.draw.polygon(target, color, scaled(points))
            pygame.draw.circle(
                target,
                color,
                (int(center[0] * scale), int(center[1] * scale)),
                int(radius * scale)
            )

        mask = pygame.Surface(shape_layer.get_size(), pygame.SRCALPHA)
        draw_card(shape_layer, (5, 6), (0, 0, 0, int(50 * visible)))
        draw_card(shape_layer, (0, 0), (74, 54, 178, fill_alpha))
        draw_card(mask, (0, 0), (255, 255, 255, 255))

        highlight = pygame.Surface(shape_layer.get_size(), pygame.SRCALPHA)
        highlight_points = [
            (body.left + skew, body.top),
            (cap_center[0] + cap_radius * 0.64, body.top),
            (cap_center[0] + cap_radius * 0.18, body.top + int(body.height * 0.42)),
            (body.left + int(skew * 0.35), body.top + int(body.height * 0.38))
        ]
        pygame.draw.polygon(
            highlight,
            (126, 98, 245, int((60 + 52 * hover) * visible)),
            scaled(highlight_points)
        )
        highlight.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        shape_layer.blit(highlight, (0, 0))

        draw_card(shape_layer, (0, 0), (255, 255, 255, edge_alpha), max(2, int(body.height * 0.055 * scale)))
        if hover > 0.01:
            draw_card(
                shape_layer,
                (int(hover * 4), 0),
                (255, 255, 255, int(30 * hover * visible)),
                max(2, int(body.height * 0.075 * scale))
            )

        layer = pygame.transform.smoothscale(shape_layer, layer_size)

        available_width = max(24, body.right - (body.left + int(body.width * 0.42)) - int(body.height * 0.22))
        render_font = font
        text = render_font.render(self.label, True, (255, 255, 255))
        if text.get_width() > available_width:
            target_height = max(12, int(font.get_height() * (available_width / text.get_width())))
            render_font = pygame.font.Font(font.get_name() if False else None, target_height)
            text = render_font.render(self.label, True, (255, 255, 255))
            while text.get_width() > available_width and target_height > 12:
                target_height -= 1
                render_font = pygame.font.Font(None, target_height)
                text = render_font.render(self.label, True, (255, 255, 255))
        text.set_alpha(alpha)
        text_rect = text.get_rect(
            midleft=(body.left + int(body.width * 0.42), body.centery)
        )
        layer.blit(text, text_rect)

        if len(self._surface_cache) > 96:
            self._surface_cache.clear()
        self._surface_cache[cache_key] = layer

        surface.blit(layer, (rect.x - 20, rect.y - 11))


class CircularVisualizer:
    def __init__(self, bar_count=108):
        self.bar_count = bar_count
        self.levels = [0.0] * bar_count
        self.phases = [
            (i * 0.61803398875) % 1.0
            for i in range(bar_count)
        ]
        self.angle_ts = [
            i / bar_count
            for i in range(bar_count)
        ]
        self.unit_vectors = [
            (
                math.cos((i / bar_count) * math.tau),
                math.sin((i / bar_count) * math.tau)
            )
            for i in range(bar_count)
        ]
        self._layer = None
        self._layer_size = None

    def update(self, dt, time_seconds, beat_level, hover, beat_phase, music_energy):
        energy = clamp(music_energy, 0.0, 1.0)
        for index in range(self.bar_count):
            phase = self.phases[index]
            angle_t = self.angle_ts[index]
            rotation = (time_seconds * (0.012 + energy * 0.026)) % 1.0
            sweep = 1.0 - abs(((angle_t - beat_phase - rotation + 0.5) % 1.0) - 0.5) * 2.0
            sweep = pow(clamp(sweep, 0.0, 1.0), 3.4)
            texture = (
                max(0.0, math.sin((time_seconds * (1.8 + energy * 3.2)) + (index * 0.31))) * 0.22
                + max(0.0, math.sin((time_seconds * (0.9 + energy * 2.4)) + (phase * math.tau))) * 0.18
            )
            threshold = 0.9 - (energy * 0.42) - (beat_level * 0.32) - (hover * 0.08)
            active = max(0.0, (sweep + texture) - threshold)
            active = pow(active, 1.35)
            family_scale = 0.34 + ((index % 5) * 0.14) + ((index % 11) * 0.014)
            beat_energy = pow(clamp(beat_level, 0.0, 1.0), 0.54)
            target = active * family_scale * (0.26 + energy * 0.88 + beat_energy * 0.72)
            target += hover * (0.025 + energy * 0.035)
            target = clamp(target, 0.0, 1.0)
            speed = 6.4 + energy * 3.4
            if target < self.levels[index]:
                speed = (0.85 + energy * 0.55) * 1.22

            self.levels[index] = lerp(
                self.levels[index],
                target,
                1.0 - math.exp(-dt * speed)
            )

    def draw(self, surface, center, radius, beat_level, music_energy, color=(255, 255, 255)):
        energy = clamp(music_energy, 0.0, 1.0)
        inner_radius = radius - max(5, radius * 0.012)
        base_length = max(20, radius * (0.068 + energy * 0.056))
        max_length = max(120, radius * (0.583 + energy * 1.064))
        layer_radius = int(inner_radius + base_length + max_length + 12)
        layer_size = layer_radius * 2
        size = (layer_size, layer_size)
        if self._layer is None or self._layer_size != size:
            self._layer = pygame.Surface(size, pygame.SRCALPHA)
            self._layer_size = size

        layer = self._layer
        layer.fill((0, 0, 0, 0))
        local_center = (layer_radius, layer_radius)

        for index, level in enumerate(self.levels):
            ux, uy = self.unit_vectors[index]
            length = base_length + (max_length * pow(level, 0.86))
            start_radius = inner_radius
            end_radius = start_radius + length

            start = (
                int(local_center[0] + (ux * start_radius)),
                int(local_center[1] + (uy * start_radius))
            )
            end = (
                int(local_center[0] + (ux * end_radius)),
                int(local_center[1] + (uy * end_radius))
            )
            alpha = int((58 + (197 * level)) * clamp(level * 2.55, 0.0, 1.0))
            width = max(5, int(radius * 0.02 + level * radius * 0.032))

            if alpha <= 4:
                continue

            pygame.draw.line(
                layer,
                (color[0], color[1], color[2], alpha),
                start,
                end,
                width
            )
            cap_radius = max(2, width // 2)
            pygame.draw.circle(layer, (color[0], color[1], color[2], alpha), start, cap_radius)
            pygame.draw.circle(layer, (color[0], color[1], color[2], alpha), end, cap_radius)

        surface.blit(layer, (center[0] - layer_radius, center[1] - layer_radius))

    def dampen(self, amount):
        amount = clamp(amount, 0.0, 1.0)
        factor = 1.0 - amount
        for index, level in enumerate(self.levels):
            self.levels[index] = level * factor


class MenuSnow:
    IMAGE_NAMES = (
        "menu-snow.png",
        "snow.png",
        "snow_note.png",
        "menu_snow.png"
    )

    def __init__(self, assets_dir):
        self.assets_dir = assets_dir
        self.random = random.Random(20260531)
        self.particles = []
        self.spawn_timer = 0.0
        self.image = None
        self.max_particles = 22

    def load(self):
        self.image = self._load_image()

    def update(self, dt, width, height):
        if not self.image:
            return

        self.spawn_timer -= dt
        if self.spawn_timer <= 0.0 and len(self.particles) < self.max_particles:
            self.spawn_timer = self.random.uniform(0.30, 0.78)
            self.particles.append(self._new_particle(width, height))

        next_particles = []
        for particle in self.particles:
            particle["age"] += dt
            particle["x"] += math.sin(particle["age"] * particle["drift_speed"] + particle["phase"]) * particle["drift"] * dt

            if not particle["settled"]:
                particle["y"] += particle["speed"] * dt
                particle["rotation"] += particle["spin"] * dt

                if particle["fade_before_ground"] and particle["y"] >= particle["fade_y"]:
                    particle["fade"] -= dt / particle["fade_time"]
                elif particle["y"] >= particle["ground_y"]:
                    particle["y"] = particle["ground_y"]
                    particle["settled"] = True
                    particle["settle_age"] = 0.0
            else:
                particle["settle_age"] += dt
                if particle["settle_age"] > particle["settle_time"]:
                    particle["fade"] -= dt / particle["fade_time"]

            if particle["fade"] > 0.0:
                next_particles.append(particle)

        self.particles = next_particles

    def draw(self, surface):
        if not self.image:
            return

        for particle in self.particles:
            alpha = int(particle["alpha"] * clamp(particle["fade"], 0.0, 1.0))
            if alpha <= 2:
                continue

            image = particle["image"]
            image.set_alpha(alpha)
            rect = image.get_rect(center=(int(particle["x"]), int(particle["y"])))
            surface.blit(image, rect)

    def _new_particle(self, width, height):
        size = self.random.uniform(
            max(9, min(width, height) * 0.012),
            max(15, min(width, height) * 0.026)
        )
        fade_before_ground = self.random.random() < 0.58
        ground_y = height - self.random.uniform(5, 22)
        image = pygame.transform.smoothscale(
            self.image,
            (max(4, int(size)), max(4, int(size)))
        )
        rotation = self.random.uniform(0.0, 360.0)
        if abs(rotation) > 0.5:
            image = pygame.transform.rotozoom(image, rotation, 1.0)

        return {
            "x": self.random.uniform(-20, width + 20),
            "y": -size,
            "speed": self.random.uniform(height * 0.035, height * 0.072),
            "drift": self.random.uniform(12, 42),
            "drift_speed": self.random.uniform(0.42, 0.95),
            "phase": self.random.uniform(0.0, math.tau),
            "size": size,
            "alpha": self.random.randint(46, 92),
            "rotation": rotation,
            "spin": 0.0,
            "image": image,
            "age": 0.0,
            "fade": 1.0,
            "fade_time": self.random.uniform(1.2, 2.4),
            "fade_before_ground": fade_before_ground,
            "fade_y": self.random.uniform(height * 0.45, height * 0.82),
            "ground_y": ground_y,
            "settled": False,
            "settle_age": 0.0,
            "settle_time": self.random.uniform(1.4, 3.6)
        }

    def _load_image(self):
        for name in self.IMAGE_NAMES:
            path = asset_path(name, "menu")
            if path.exists():
                try:
                    return pygame.image.load(str(path)).convert_alpha()
                except pygame.error:
                    continue

        return None


class PulseCircle:
    def __init__(self, title="OSU!"):
        self.title = title
        self.center = (0, 0)
        self.base_radius = 160
        self.radius = 160
        self.hover = 0.0
        self.click_flash = 0.0
        self.pulse_scale = 1.0
        self.font = None
        self._base_font = None
        self.small_font = None
        self._font_radius = 0
        self._title_surface_cache = {}
        self._scratch_surfaces = {}

    def layout(self, width, height):
        self.center = (width // 2, height // 2)
        self.base_radius = int(clamp(min(width, height) * 0.301, 180, 370))

        if self._font_radius != self.base_radius:
            self._font_radius = self.base_radius
            self._title_surface_cache.clear()
            title_size = max(54, int(self.base_radius * 0.53))
            self.font = self._rounded_font(title_size)
            self._base_font = self._rounded_font(title_size)
            self.small_font = pygame.font.SysFont(
                "arial",
                max(13, int(self.base_radius * 0.105)),
                bold=True
            )

    def _rounded_font(self, size):
        for name in (
            "arialrounded",
            "arialroundedmtbold",
            "segoeui",
            "segoeuisemibold",
            "verdana",
            "arial"
        ):
            path = pygame.font.match_font(name, bold=True)
            if path:
                return pygame.font.Font(path, size)

        return pygame.font.Font(None, size)

    def contains(self, pos):
        dx = pos[0] - self.center[0]
        dy = pos[1] - self.center[1]
        return (dx * dx) + (dy * dy) <= (self.radius * self.radius)

    def update(self, dt, mouse_pos, time_seconds, beat_level, menu_open):
        dx = mouse_pos[0] - self.center[0]
        dy = mouse_pos[1] - self.center[1]
        hover_target = 1.0 if (dx * dx) + (dy * dy) <= (self.radius * self.radius) else 0.0
        if menu_open:
            hover_target *= 0.35

        self.hover = lerp(
            self.hover,
            hover_target,
            1.0 - math.exp(-dt * 16.0)
        )
        self.click_flash = max(0.0, self.click_flash - (dt * 3.8))

        beat_push = ease_out_cubic(beat_level) * 0.16
        hover_push = self.hover * 0.065
        flash_push = ease_out_cubic(self.click_flash) * 0.12
        menu_push = 0.025 if menu_open else 0.0
        self.pulse_scale = 1.0 + beat_push + hover_push + flash_push + menu_push
        target_radius = self.base_radius * self.pulse_scale
        self.radius = lerp(
            self.radius,
            target_radius,
            1.0 - math.exp(-dt * 18.0)
        )

    def trigger_click(self):
        self.click_flash = 1.0

    def draw(self, surface, time_seconds, beat_level, menu_open):
        radius = int(self.radius)
        center_x, center_y = self.center
        padding = int(radius * 0.42)
        size = (radius * 2) + (padding * 2)
        layer = self._scratch_surface("circle", (size, size))
        local_center = (size // 2, size // 2)

        for index in range(9, 0, -1):
            shadow_radius = radius + int(index * radius * 0.032)
            shadow_alpha = int((20 + (beat_level * 14)) * (index / 9.0))
            pygame.draw.circle(
                layer,
                (0, 0, 0, shadow_alpha),
                local_center,
                shadow_radius
            )

        hover = ease_out_cubic(self.hover)
        magenta = (
            int(222 + (25 * hover)),
            int(58 + (36 * hover)),
            int(156 + (42 * hover))
        )
        pygame.draw.circle(layer, (*magenta, 255), local_center, radius)

        effects = self._scratch_surface("effects", (size, size))
        shine_radius = int(radius * (0.82 + beat_level * 0.06))
        pygame.draw.circle(
            effects,
            (255, 255, 255, int(20 + (hover * 18))),
            (local_center[0] - int(radius * 0.22), local_center[1] - int(radius * 0.22)),
            shine_radius
        )
        circle_mask = self._scratch_surface("mask", (size, size))
        pygame.draw.circle(circle_mask, (255, 255, 255, 255), local_center, radius)
        effects.blit(circle_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        layer.blit(effects, (0, 0))

        self._draw_inner_geometry(layer, local_center, radius, time_seconds)

        border_width = max(8, int(radius * 0.075))
        pygame.draw.circle(
            layer,
            (255, 255, 255, 248),
            local_center,
            radius,
            border_width
        )
        pygame.draw.circle(
            layer,
            (255, 255, 255, int(58 + (self.click_flash * 100))),
            local_center,
            int(radius * (1.0 + self.click_flash * 0.22)),
            max(3, border_width // 3)
        )

        text_scale = 1.0 + ((self.pulse_scale - 1.0) * 0.72)
        title = self._title_surface(text_scale)
        title_rect = title.get_rect(center=(local_center[0], local_center[1] - int(radius * 0.02)))
        layer.blit(title, title_rect)

        caption = "click to start" if not menu_open else "select an option"
        caption_surface = self.small_font.render(caption.upper(), True, (255, 255, 255))
        shared_alpha = int((120 if not menu_open else 155) + ((self.pulse_scale - 1.0) * 360))
        caption_surface.set_alpha(clamp(shared_alpha, 120, 205))
        caption_rect = caption_surface.get_rect(
            center=(local_center[0], local_center[1] + int(radius * 0.42))
        )
        layer.blit(caption_surface, caption_rect)

        surface.blit(
            layer,
            (center_x - local_center[0], center_y - local_center[1])
        )

    def _draw_inner_geometry(self, layer, center, radius, time_seconds):
        geometry = self._scratch_surface("geometry", layer.get_size())
        cx, cy = center
        alpha = 34
        spin = time_seconds * 0.25

        for i in range(7):
            angle = spin + (i * math.tau / 7.0)
            start_radius = radius * (0.28 + ((i % 3) * 0.1))
            end_radius = start_radius + (radius * 0.22)
            start = (
                int(cx + math.cos(angle) * start_radius),
                int(cy + math.sin(angle) * start_radius)
            )
            end = (
                int(cx + math.cos(angle + 0.22) * end_radius),
                int(cy + math.sin(angle + 0.22) * end_radius)
            )
            pygame.draw.line(geometry, (255, 255, 255, alpha), start, end, max(2, radius // 70))

        for i in range(4):
            angle = -spin * 1.4 + (i * math.tau / 4.0)
            distance = radius * 0.56
            px = cx + math.cos(angle) * distance
            py = cy + math.sin(angle) * distance
            triangle_radius = radius * 0.045
            points = []
            for corner in range(3):
                corner_angle = angle + (corner * math.tau / 3.0)
                points.append((
                    int(px + math.cos(corner_angle) * triangle_radius),
                    int(py + math.sin(corner_angle) * triangle_radius)
                ))
            pygame.draw.polygon(geometry, (255, 255, 255, 28), points)

        layer.blit(geometry, (0, 0))

    def _scratch_surface(self, key, size):
        surface = self._scratch_surfaces.get(key)
        if surface is None or surface.get_size() != size:
            surface = pygame.Surface(size, pygame.SRCALPHA)
            self._scratch_surfaces[key] = surface
        surface.fill((0, 0, 0, 0))
        return surface

    def _title_surface(self, text_scale):
        key = int(text_scale * 100)
        cached = self._title_surface_cache.get(key)
        if cached is not None:
            return cached

        base = self._base_font.render(self.title, True, (255, 255, 255))
        scaled = pygame.transform.smoothscale(
            base,
            (
                max(1, int(base.get_width() * text_scale)),
                max(1, int(base.get_height() * text_scale))
            )
        )
        if len(self._title_surface_cache) > 48:
            self._title_surface_cache.clear()
        self._title_surface_cache[key] = scaled
        return scaled


class MainMenuScene(BaseScene):
    uses_ui = False

    IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
    AUDIO_EXTENSIONS = (".ogg", ".mp3", ".wav")
    BACKGROUND_NAMES = (
        "background",
        "menu_background",
        "main_menu_background"
    )

    def __init__(self, game):
        super().__init__(game)

        self.assets_dir = ACTIVE_SKIN_DIR
        self.menu_music_dir = Path("assets") / "menu"
        self.title = "OSU!"
        self.time_seconds = 0.0
        self.beat_phase = 0.0
        self.beat_level = 0.0
        self.menu_open = False
        self.settings_open = False
        self.settings_slider_rect = pygame.Rect(0, 0, 0, 0)
        self.settings_dragging = False
        self.menu_t = 0.0
        self.light_overlay = False
        self.music_started = False
        self.keep_music_on_destroy = False
        self.music_path = None
        self.music_title = "simulated pulse"
        self.music_bpm = 118.0
        self.music_energy = 0.45
        self.current_timing_points = []
        self.music_started_ticks = 0
        self.audio_envelope = []
        self.audio_envelope_step_ms = 120
        self.music_tracks = self._build_music_playlist()
        self.current_track_index = (
            random.randrange(len(self.music_tracks))
            if self.music_tracks
            else 0
        )
        self.option_font = None
        self.footer_font = None
        self.footer_cache = {}

        self.circle = PulseCircle(self.title)
        self.visualizer = CircularVisualizer()
        self.snow = MenuSnow(self.assets_dir)
        self.snow.load()
        self.options = [
            MenuOption("Play", self._open_song_select),
            MenuOption("Settings", self._open_settings),
            MenuOption("Previous Track", self._previous_menu_track),
            MenuOption("Next Track", self._next_menu_track),
            MenuOption("Exit", self._exit_game)
        ]

        self.background = self._load_background()
        self.scaled_background = None
        self.background_size = None
        self.fallback_background = None
        self.fallback_background_size = None
        self.fallback_orbit = None
        self.fallback_orbit_size = None
        self.overlay_cache = {}
        self.fallback_points = [
            ((i * 97) % 1000 / 1000.0, (i * 193) % 1000 / 1000.0, 0.35 + ((i % 5) * 0.12))
            for i in range(46)
        ]

        self._layout()
        self._prepare_mouse()
        self._start_menu_music()

    def _prepare_mouse(self):
        if hasattr(self.game, "disable_raw_mouse"):
            self.game.disable_raw_mouse()
        pygame.mouse.set_visible(True)

    def _layout(self):
        width = self.game.WIDTH
        height = self.game.HEIGHT
        self.circle.layout(width, height)
        self.option_font = pygame.font.SysFont(
            "arial",
            max(22, int(self.circle.base_radius * 0.13)),
            bold=True
        )
        self.footer_font = pygame.font.SysFont("arial", max(14, height // 64))
        self.footer_cache.clear()

        option_width = int(clamp(width * 0.312, 288, 496))
        option_height = int(clamp(height * 0.067, 46, 67))
        spacing = int(option_height * 1.16)
        open_circle_x = self.circle.center[0] - int(self.circle.base_radius * 0.48)
        left_x = open_circle_x + int(self.circle.base_radius * 0.6)
        left_x = min(left_x, width - option_width - 24)
        start_y = self.circle.center[1] - int(spacing * (len(self.options) - 1) * 0.5)

        if start_y < 58:
            start_y = 58
        if start_y + (spacing * (len(self.options) - 1)) > height - 70:
            start_y = height - 70 - (spacing * (len(self.options) - 1))

        width_factors = [0.54, 0.7, 0.9, 0.72, 0.5]
        for index, option in enumerate(self.options):
            option.set_layout(
                left_x,
                start_y + (index * spacing),
                option_width,
                option_height,
                index * 0.045,
                width_factors[index] if index < len(width_factors) else 0.8
            )

    def create_ui(self):
        self._prepare_mouse()
        self._layout()
        self._start_menu_music()

    def on_resize(self):
        self._layout()
        self.scaled_background = None
        self.background_size = None
        self.fallback_background = None
        self.fallback_background_size = None
        self.fallback_orbit = None
        self.fallback_orbit_size = None
        self.overlay_cache.clear()

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and self.settings_open:
                self.settings_open = False
                self.settings_dragging = False
                return
            if event.key == pygame.K_ESCAPE and self.menu_open:
                self.menu_open = False
                return
            if self.settings_open:
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    self._adjust_mouse_sensitivity(-0.05)
                    return
                if event.key in (pygame.K_RIGHT, pygame.K_d):
                    self._adjust_mouse_sensitivity(0.05)
                    return
            if event.key in (pygame.K_RIGHT, pygame.K_d):
                self._next_menu_track()
                return
            if event.key in (pygame.K_LEFT, pygame.K_a):
                self._previous_menu_track()
                return

        if self.settings_open:
            if event.type == pygame.MOUSEWHEEL:
                self._adjust_mouse_sensitivity(event.y * 0.05)
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.settings_slider_rect.collidepoint(event.pos):
                    self.settings_dragging = True
                    self._set_mouse_sensitivity_from_pos(event.pos[0])
                return
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.settings_dragging = False
                return
            if event.type == pygame.MOUSEMOTION and self.settings_dragging:
                self._set_mouse_sensitivity_from_pos(event.pos[0])
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.menu_open:
                for option in self.options:
                    if option.handle_event(event):
                        return

            if self.circle.contains(event.pos):
                self.menu_open = True
                self.circle.trigger_click()
                for index, option in enumerate(self.options):
                    option.delay = index * 0.055

    def update(self, dt):
        dt = min(dt, 1.0 / 20.0)
        self.time_seconds += dt
        mouse_pos = self.game.mouse_pos

        self.beat_level = self._update_beat(dt)
        self.menu_t = lerp(
            self.menu_t,
            1.0 if self.menu_open else 0.0,
            1.0 - math.exp(-dt * 10.0)
        )

        self.circle.update(
            dt,
            mouse_pos,
            self.time_seconds,
            self.beat_level,
            self.menu_open
        )
        self.visualizer.update(
            dt,
            self.time_seconds,
            self.beat_level,
            self.circle.hover,
            self.beat_phase,
            self.music_energy
        )

        for option in self.options:
            option.update(dt, mouse_pos, self.menu_open)

        self.snow.update(dt, self.game.WIDTH, self.game.HEIGHT)

    def render(self, screen):
        if screen.get_size() != (self.game.WIDTH, self.game.HEIGHT):
            self._layout()

        self._draw_background(screen)
        self._draw_overlay(screen)
        self.snow.draw(screen)

        menu_t = ease_in_out(self.menu_t)
        menu_shift_x = int(menu_t * -self.circle.base_radius * 0.48)
        original_center = self.circle.center
        self.circle.center = (original_center[0] + menu_shift_x, original_center[1])
        self.visualizer.draw(
            screen,
            self.circle.center,
            self.circle.radius,
            self.beat_level,
            self.music_energy,
            (255, 240, 252)
        )

        for option in self.options:
            option.draw(screen, self.option_font)

        self.circle.draw(
            screen,
            self.time_seconds,
            self.beat_level,
            self.menu_open
        )
        self.circle.center = original_center

        self._draw_footer(screen)
        if self.settings_open:
            self._draw_settings_panel(screen)

    def destroy(self):
        if self.music_started and not self.keep_music_on_destroy:
            pygame.mixer.music.stop()
            self.music_started = False
        self.keep_music_on_destroy = False

    def _open_song_select(self):
        self.keep_music_on_destroy = True
        self.game.scene_manager.push_scene(
            SongSelectScene(
                self.game,
                initial_music_path=str(self.music_path) if self.music_path else None
            )
        )

    def _open_settings(self):
        self.settings_open = True
        self.menu_open = True
        self.circle.trigger_click()

    def _adjust_mouse_sensitivity(self, amount):
        self.game.set_mouse_sensitivity(
            self.game.raw_mouse_sensitivity + amount
        )

    def _set_mouse_sensitivity_from_pos(self, x):
        rect = self.settings_slider_rect
        if rect.width <= 0:
            return
        t = clamp((x - rect.left) / rect.width, 0.0, 1.0)
        value = 0.40 + (t * (2.00 - 0.40))
        self.game.set_mouse_sensitivity(round(value, 2))

    def _exit_game(self):
        self.game.running = False

    def _update_beat(self, dt):
        bpm, phase, music_pos = self._current_music_timing(dt)
        self.music_bpm = lerp(
            self.music_bpm,
            bpm,
            1.0 - math.exp(-dt * 8.0)
        )
        target_energy = self._combined_music_energy(bpm, music_pos)
        energy_speed = 12.0 if target_energy < self.music_energy else 5.0
        self.music_energy = lerp(
            self.music_energy,
            target_energy,
            1.0 - math.exp(-dt * energy_speed)
        )
        if target_energy < self.music_energy - 0.08:
            self.visualizer.dampen(1.0 - math.exp(-dt * 6.0))
        self.beat_phase = phase
        beat_distance = min(self.beat_phase, 1.0 - self.beat_phase)
        beat = clamp(1.0 - (beat_distance / 0.18), 0.0, 1.0)
        kick = pow(beat, 2.65)
        groove = (math.sin((phase * math.tau) - 0.55) + 1.0) * 0.025
        shimmer = (math.sin(phase * math.tau * 2.0) + 1.0) * 0.018
        return clamp(kick + groove + shimmer, 0.0, 1.0)

    def _current_music_timing(self, dt):
        if not self.current_timing_points:
            bpm = self.music_bpm
            phase = (self.beat_phase + (dt * bpm / 60.0)) % 1.0
            music_pos = pygame.mixer.music.get_pos()
            if music_pos < 0:
                music_pos = pygame.time.get_ticks() - self.music_started_ticks
            return bpm, phase, music_pos

        music_pos = pygame.mixer.music.get_pos()
        if music_pos < 0:
            music_pos = pygame.time.get_ticks() - self.music_started_ticks

        active = self._active_timing_point(music_pos)
        if active is None:
            bpm = self.music_bpm
            phase = (self.beat_phase + (dt * bpm / 60.0)) % 1.0
            return bpm, phase, music_pos

        ms_per_beat = max(1.0, active["ms_per_beat"])
        bpm = clamp(60000.0 / ms_per_beat, 40.0, 360.0)
        phase = ((music_pos - active["time"]) / ms_per_beat) % 1.0
        return bpm, phase, music_pos

    def _active_timing_point(self, music_pos):
        active = None
        for timing_point in self.current_timing_points:
            if timing_point.get("uninherited", 1) != 1:
                continue
            if timing_point.get("ms_per_beat", 0) <= 0:
                continue
            if timing_point.get("time", 0) <= music_pos:
                active = timing_point
            else:
                break

        if active is None:
            for timing_point in self.current_timing_points:
                if (
                    timing_point.get("uninherited", 1) == 1
                    and timing_point.get("ms_per_beat", 0) > 0
                ):
                    return timing_point

        return active

    def _combined_music_energy(self, bpm, music_pos):
        bpm_energy = self._energy_from_bpm(bpm)
        volume_energy = self._volume_energy_at(music_pos)

        if volume_energy is None:
            beat_swell = pow(clamp(self.beat_level, 0.0, 1.0), 0.7)
            return clamp((bpm_energy * 0.65) + (beat_swell * 0.35), 0.12, 1.0)

        return clamp((bpm_energy * 0.28) + (volume_energy * 0.72), 0.04, 1.0)

    def _volume_energy_at(self, music_pos):
        if not self.audio_envelope:
            return None

        index = int(max(0, music_pos) / self.audio_envelope_step_ms)
        if index >= len(self.audio_envelope):
            return 0.0

        start = max(0, index - 1)
        end = min(len(self.audio_envelope), index + 2)
        return sum(self.audio_envelope[start:end]) / max(1, end - start)

    def _load_background(self):
        root_background = asset_path("menu-bg.jpg")
        if root_background.exists():
            try:
                return pygame.image.load(str(root_background)).convert()
            except pygame.error:
                pass

        for name in self.BACKGROUND_NAMES:
            for extension in self.IMAGE_EXTENSIONS:
                path = self.assets_dir / f"{name}{extension}"
                if not path.exists():
                    continue

                try:
                    return pygame.image.load(str(path)).convert()
                except pygame.error:
                    continue

        return None

    def _start_menu_music(self):
        if self.music_started and pygame.mixer.music.get_busy():
            return

        if not self.music_tracks:
            return

        self._play_track(self.current_track_index)

    def _play_track(self, index):
        if not self.music_tracks:
            return

        self.current_track_index = index % len(self.music_tracks)
        track = self.music_tracks[self.current_track_index]
        self.music_path = track["path"]
        self.music_title = track["title"]
        self.footer_cache.clear()
        self.music_bpm = track["bpm"]
        self.music_energy = track["energy"]
        self.current_timing_points = track.get("timing_points", [])
        if track.get("envelope") is None:
            track["envelope"] = self._build_audio_envelope(self.music_path)
        self.audio_envelope = track.get("envelope") or []
        self.beat_phase = 0.0

        try:
            pygame.mixer.music.load(str(self.music_path))
            pygame.mixer.music.set_volume(0.42)
            pygame.mixer.music.play(-1)
            self.music_started = True
            self.music_started_ticks = pygame.time.get_ticks()
        except pygame.error:
            self.music_started = False

    def _next_menu_track(self):
        if self.music_tracks:
            self._play_track(self.current_track_index + 1)
            self.circle.trigger_click()

    def _previous_menu_track(self):
        if self.music_tracks:
            self._play_track(self.current_track_index - 1)
            self.circle.trigger_click()

    def _build_music_playlist(self):
        tracks = []

        for path in self._iter_asset_files(self.menu_music_dir, self.AUDIO_EXTENSIONS):
            title = self._clean_display_text(
                path.stem.replace("_", " ").replace("-", " ").strip()
            )
            tracks.append({
                "path": path,
                "title": title or "Menu music",
                "bpm": 118.0,
                "energy": 0.48,
                "timing_points": [],
                "envelope": None
            })

        for beatmap in getattr(self.game, "beatmaps", []):
            audio_path = self._first_audio_in_folder(Path(beatmap["path"]))
            if not audio_path:
                continue

            difficulty = beatmap["difficulties"][0]
            bpm = self._bpm_from_timing_points(difficulty.get("timing_points", []))
            tracks.append({
                "path": audio_path,
                "title": self._clean_display_text(
                    beatmap.get("display_name", beatmap["name"])
                ),
                "bpm": bpm,
                "energy": self._energy_from_bpm(bpm),
                "timing_points": difficulty.get("timing_points", []),
                "envelope": None
            })

        return tracks

    def _first_audio_in_folder(self, folder):
        for path in self._iter_asset_files(folder, self.AUDIO_EXTENSIONS):
            return path

        return None

    def _build_audio_envelope(self, path):
        try:
            sound = pygame.mixer.Sound(str(path))
            samples = pygame.sndarray.array(sound)
        except (pygame.error, ValueError, TypeError):
            return []

        try:
            import numpy as np
        except ImportError:
            return []

        if samples.size == 0:
            return []

        samples = samples.astype("float32")
        if samples.ndim > 1:
            samples = samples.mean(axis=1)

        sample_rate = pygame.mixer.get_init()[0]
        window = max(256, int(sample_rate * self.audio_envelope_step_ms / 1000))
        usable = (len(samples) // window) * window
        if usable <= 0:
            return []

        samples = samples[:usable].reshape((-1, window))
        rms = np.sqrt(np.mean(samples * samples, axis=1))
        peak = float(np.percentile(rms, 95)) if len(rms) else 0.0
        if peak <= 0.0:
            return []

        envelope = np.clip(rms / peak, 0.0, 1.0)
        envelope = np.power(envelope, 0.72)
        return [float(value) for value in envelope]

    def _bpm_from_timing_points(self, timing_points):
        for timing_point in timing_points:
            ms_per_beat = timing_point.get("ms_per_beat", 0)
            if timing_point.get("uninherited", 1) == 1 and ms_per_beat > 0:
                return clamp(60000.0 / ms_per_beat, 70.0, 240.0)

        return 118.0

    def _energy_from_bpm(self, bpm):
        return clamp((bpm - 78.0) / 132.0, 0.22, 1.0)

    def _clean_display_text(self, text):
        text = "".join(
            ch
            for ch in str(text)
            if ch.isprintable() and ch not in "\ufffd□■"
        ).strip()
        return " ".join(text.split())

    def _iter_asset_files(self, directory, extensions):
        if not directory.exists():
            return []

        files = []
        for extension in extensions:
            files.extend(directory.glob(f"*{extension}"))
        return sorted(files)

    def _draw_background(self, screen):
        size = screen.get_size()
        if self.background:
            if self.scaled_background is None or self.background_size != size:
                self.scaled_background = self._cover_scale(self.background, size)
                self.background_size = size
            screen.blit(self.scaled_background, (0, 0))
            return

        self._draw_fallback_background(screen)

    def _cover_scale(self, image, target_size):
        target_w, target_h = target_size
        image_w, image_h = image.get_size()
        scale = max(target_w / image_w, target_h / image_h)
        scaled_size = (
            max(1, int(image_w * scale)),
            max(1, int(image_h * scale))
        )
        scaled = pygame.transform.smoothscale(image, scaled_size)
        result = pygame.Surface(target_size)
        result.blit(
            scaled,
            (
                (target_w - scaled_size[0]) // 2,
                (target_h - scaled_size[1]) // 2
            )
        )
        return result

    def _draw_fallback_background(self, screen):
        width, height = screen.get_size()
        size = (width, height)
        if self.fallback_background is None or self.fallback_background_size != size:
            self.fallback_background = pygame.Surface(size).convert()
            self.fallback_background_size = size
            base_top = (22, 18, 32)
            base_bottom = (58, 23, 54)

            for y in range(0, height, 4):
                t = y / max(1, height - 1)
                color = (
                    int(lerp(base_top[0], base_bottom[0], t)),
                    int(lerp(base_top[1], base_bottom[1], t)),
                    int(lerp(base_top[2], base_bottom[2], t))
                )
                pygame.draw.rect(self.fallback_background, color, (0, y, width, 4))

        screen.blit(self.fallback_background, (0, 0))

        if self.fallback_orbit is None or self.fallback_orbit_size != size:
            self.fallback_orbit = pygame.Surface(size, pygame.SRCALPHA)
            self.fallback_orbit_size = size

        orbit = self.fallback_orbit
        orbit.fill((0, 0, 0, 0))
        for x_factor, y_factor, speed in self.fallback_points:
            x = int((x_factor * width + math.sin(self.time_seconds * speed) * 28) % width)
            y = int((y_factor * height + math.cos(self.time_seconds * speed * 0.8) * 24) % height)
            pygame.draw.circle(orbit, (255, 255, 255, 18), (x, y), 2)

        for i in range(8):
            angle = self.time_seconds * 0.09 + (i * math.tau / 8.0)
            center = (
                int(width * 0.5 + math.cos(angle) * width * 0.34),
                int(height * 0.5 + math.sin(angle) * height * 0.22)
            )
            radius = int(min(width, height) * (0.22 + (i % 3) * 0.055))
            pygame.draw.circle(orbit, (255, 92, 180, 10), center, radius, 2)

        screen.blit(orbit, (0, 0))

    def _draw_overlay(self, screen):
        size = screen.get_size()
        key = (size, self.light_overlay)
        overlay = self.overlay_cache.get(key)
        if overlay is None:
            overlay = pygame.Surface(size, pygame.SRCALPHA)
            if self.light_overlay:
                overlay.fill((245, 235, 250, 58))
            else:
                overlay.fill((0, 0, 0, 126))
            self.overlay_cache[key] = overlay
        screen.blit(overlay, (0, 0))

    def _draw_footer(self, screen):
        music_text = "menu music: "
        music_text += self.music_title
        hint = "Left/Right change music  |  F11 fullscreen"
        if self.menu_open:
            hint += "  |  ESC back"

        text = self._footer_surface(music_text, 110)
        hint_surface = self._footer_surface(hint, 100)
        text.set_alpha(110)
        hint_surface.set_alpha(100)
        screen.blit(text, (18, self.game.HEIGHT - text.get_height() - 16))
        screen.blit(
            hint_surface,
            (
                self.game.WIDTH - hint_surface.get_width() - 18,
                self.game.HEIGHT - hint_surface.get_height() - 16
            )
        )
        signature = self._footer_surface("OSU! made with python by a fan", 118)
        screen.blit(signature, (18, 18))

    def _draw_settings_panel(self, screen):
        width = int(clamp(screen.get_width() * 0.34, 360, 520))
        height = int(clamp(screen.get_height() * 0.20, 150, 210))
        panel = pygame.Rect(0, 0, width, height)
        panel.center = (
            int(screen.get_width() * 0.62),
            int(screen.get_height() * 0.50)
        )

        surface = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(
            surface,
            (18, 16, 34, 224),
            surface.get_rect(),
            border_radius=14
        )
        pygame.draw.rect(
            surface,
            (142, 118, 255, 190),
            surface.get_rect(),
            2,
            border_radius=14
        )

        value = self.game.raw_mouse_sensitivity
        title = self.option_font.render("Settings", True, (255, 255, 255))
        label = self.footer_font.render("Mouse sensitivity", True, (230, 232, 250))
        value_text = self.footer_font.render(f"{value:.2f}x", True, (255, 244, 160))
        hint = self.footer_font.render("Left/Right, wheel, or drag", True, (190, 190, 210))

        surface.blit(title, (24, 18))
        surface.blit(label, (24, 62))
        surface.blit(value_text, (width - value_text.get_width() - 24, 62))

        slider = pygame.Rect(24, 102, width - 48, 12)
        pygame.draw.rect(
            surface,
            (58, 54, 82, 255),
            slider,
            border_radius=slider.height // 2
        )
        t = clamp((value - 0.40) / 1.60, 0.0, 1.0)
        fill_rect = slider.copy()
        fill_rect.width = int(slider.width * t)
        pygame.draw.rect(
            surface,
            (152, 112, 255, 255),
            fill_rect,
            border_radius=slider.height // 2
        )
        knob_x = slider.left + int(slider.width * t)
        pygame.draw.circle(
            surface,
            (255, 255, 255, 255),
            (knob_x, slider.centery),
            10
        )
        pygame.draw.circle(
            surface,
            (124, 94, 235, 255),
            (knob_x, slider.centery),
            5
        )
        surface.blit(hint, (24, height - hint.get_height() - 18))

        self.settings_slider_rect = slider.move(panel.topleft)
        screen.blit(surface, panel)

    def _footer_surface(self, text, alpha):
        key = (text, int(alpha), id(self.footer_font))
        cached = self.footer_cache.get(key)
        if cached is not None:
            return cached

        if len(self.footer_cache) > 16:
            self.footer_cache.clear()

        surface = self.footer_font.render(text, True, (255, 255, 255))
        surface.set_alpha(alpha)
        self.footer_cache[key] = surface
        return surface
