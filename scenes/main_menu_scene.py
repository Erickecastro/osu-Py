import math
import random
from pathlib import Path

import pygame

from core.audio import is_sound_effect_file, mark_music_loaded
from core.assets import ACTIVE_SKIN_DIR, ASSETS_ROOT, asset_path, load_image
from core.fonts import rounded_font
from rendering.menu_visualizer import CircularMenuVisualizer
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


def lerp_color(start, end, amount):
    amount = clamp(amount, 0.0, 1.0)
    return (
        int(lerp(start[0], end[0], amount)),
        int(lerp(start[1], end[1], amount)),
        int(lerp(start[2], end[2], amount)),
    )


_tint_surface_cache = {}

def tint_surface_from_alpha(source, size, color, alpha=255):
    width, height = max(1, int(size[0])), max(1, int(size[1]))
    key = (id(source), (width, height), color, alpha, "v2_high_quality")
    cached = _tint_surface_cache.get(key)
    if cached is not None:
        return cached
    from core.assets import scale_image_high_quality
    scaled = scale_image_high_quality(source, (width, height)).convert_alpha()
    tinted = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
    tinted.fill((color[0], color[1], color[2], max(0, min(255, int(alpha)))))
    try:
        source_alpha = pygame.surfarray.array_alpha(scaled)
        target_alpha = pygame.surfarray.pixels_alpha(tinted)
        if alpha < 255:
            source_alpha = (source_alpha * (alpha / 255.0)).astype(source_alpha.dtype)
        target_alpha[:, :] = source_alpha
        del target_alpha
    except (ImportError, pygame.error, ValueError, TypeError, AttributeError):
        tinted.blit(scaled, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    _tint_surface_cache[key] = tinted
    return tinted


class MenuOption:
    NORMAL_COLOR = (95, 70, 220)
    HOVER_COLOR = (235, 105, 170)

    def __init__(self, label, action):
        self.label = label
        self.action = action
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.width_factor = 1.0
        self.hover = 0.0
        self.visible = 0.0
        self.delay = 0.0
        self._surface_cache = {}
        self._text_cache = {}
        self._pattern_cache = {}
        self._button_source = None

    def set_layout(self, left_x, y, width, height, delay, width_factor=1.0):
        self.width_factor = width_factor
        width = int(width * width_factor)
        self.rect = pygame.Rect(0, 0, int(width), int(height))
        self.rect.left = int(left_x)
        self.rect.centery = int(y)
        self.delay = delay

    def update(self, dt, mouse_pos, menu_open):
        if not menu_open and self.visible <= 0.001 and self.hover <= 0.001:
            return

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
        hover_style = round(hover * 24.0) / 24.0
        slide = int((1.0 - visible) * -self.rect.width * 0.54)
        expand_width = int(self.rect.width * (0.055 * hover_style))
        expand_height = int(self.rect.height * (0.035 * hover_style))
        rect = pygame.Rect(
            self.rect.left + slide,
            self.rect.top - (expand_height // 2),
            self.rect.width + expand_width,
            self.rect.height + expand_height
        )
        text_alpha = 255
        cache_key = (
            "asset-v1",
            rect.width,
            rect.height,
            self.label,
            font.get_height(),
            int(hover_style * 24)
        )
        cached = self._surface_cache.get(cache_key)
        if cached is not None:
            render_alpha = int(255 * visible)
            if cached["surface"].get_alpha() != render_alpha:
                cached["surface"].set_alpha(render_alpha)
            surface.blit(
                cached["surface"],
                (rect.x - cached["pad_x"], rect.y - cached["pad_y"])
            )
            return

        pad_x = max(4, int(rect.height * 0.08))
        pad_y = max(3, int(rect.height * 0.08))
        layer_size = (rect.width + (pad_x * 2), rect.height + (pad_y * 2))
        layer = pygame.Surface(layer_size, pygame.SRCALPHA).convert_alpha()
        layer.fill((0, 0, 0, 0))
        body = pygame.Rect(pad_x, pad_y, rect.width, rect.height)

        source = self._main_button_source()
        if source is not None:
            button = self._menu_button_surface(source, body.size, hover_style)
            layer.blit(button, body)
        else:
            pygame.draw.rect(
                layer,
                (*lerp_color(self.NORMAL_COLOR, self.HOVER_COLOR, hover_style), 255),
                body,
                border_radius=body.height // 2
            )

        available_width = max(24, body.width - int(body.height * 1.28))
        text = self._text_surface(font, available_width)
        if text.get_alpha() != text_alpha:
            text.set_alpha(text_alpha)
        text_center_x = min(
            body.right - (text.get_width() // 2) - int(body.height * 0.22),
            body.centerx + int(body.height * 0.43)
        )
        text_rect = text.get_rect(center=(text_center_x, body.centery))
        layer.blit(text, text_rect)

        if len(self._surface_cache) > 56:
            self._surface_cache.clear()
        self._surface_cache[cache_key] = {
            "surface": layer,
            "pad_x": pad_x,
            "pad_y": pad_y
        }

        render_alpha = int(255 * visible)
        if layer.get_alpha() != render_alpha:
            layer.set_alpha(render_alpha)
        surface.blit(layer, (rect.x - pad_x, rect.y - pad_y))

    def _main_button_source(self):
        if self._button_source is None:
            self._button_source = load_image("main-menu-buttons.png")
        return self._button_source

    def _menu_button_surface(self, source, size, hover_style):
        key = (
            "menu_button",
            int(size[0]),
            int(size[1]),
            int(round(hover_style * 24))
        )
        cached = self._surface_cache.get(key)
        if cached is not None:
            return cached

        button = self._nine_slice_button(source, size)
        if hover_style > 0.001:
            purple = tint_surface_from_alpha(
                button,
                button.get_size(),
                (126, 88, 238),
                int(145 * hover_style)
            )
            button.blit(purple, (0, 0))

            shine = pygame.Surface(button.get_size(), pygame.SRCALPHA).convert_alpha()
            shine.fill((190, 166, 255, int(10 * hover_style)))
            button.blit(shine, (0, 0))

        if len(self._surface_cache) > 72:
            self._surface_cache.clear()
        self._surface_cache[key] = button
        return button

    def _nine_slice_button(self, source, size):
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        src_w, src_h = source.get_size()
        if src_w <= 2 or src_h <= 2:
            return pygame.transform.smoothscale(source, (width, height)).convert_alpha()

        cap_src = min(src_w // 2, max(1, src_h // 2))
        cap_dst = min(width // 2, max(1, int(height * cap_src / src_h)))
        center_dst_w = max(0, width - (cap_dst * 2))

        left_src = pygame.Rect(0, 0, cap_src, src_h)
        right_src = pygame.Rect(src_w - cap_src, 0, cap_src, src_h)
        center_src = pygame.Rect(cap_src, 0, max(1, src_w - cap_src * 2), src_h)

        output = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
        output.blit(
            pygame.transform.smoothscale(source.subsurface(left_src), (cap_dst, height)),
            (0, 0)
        )
        if center_dst_w > 0:
            output.blit(
                pygame.transform.smoothscale(source.subsurface(center_src), (center_dst_w, height)),
                (cap_dst, 0)
            )
        output.blit(
            pygame.transform.smoothscale(source.subsurface(right_src), (cap_dst, height)),
            (width - cap_dst, 0)
        )
        return output

    def _text_surface(self, font, available_width):
        key = (self.label, id(font), font.get_height(), int(available_width))
        cached = self._text_cache.get(key)
        if cached is not None:
            return cached

        text = font.render(self.label, True, (255, 255, 255))
        if text.get_width() > available_width:
            target_height = max(12, int(font.get_height() * (available_width / text.get_width())))
            render_font = rounded_font(target_height, bold=True)
            text = render_font.render(self.label, True, (255, 255, 255))
            while text.get_width() > available_width and target_height > 12:
                target_height -= 1
                render_font = rounded_font(target_height, bold=True)
                text = render_font.render(self.label, True, (255, 255, 255))

        if len(self._text_cache) > 24:
            self._text_cache.clear()
        self._text_cache[key] = text
        return text

    def _pattern_surface(self, size, scale):
        key = (int(size[0]), int(size[1]), int(scale))
        cached = self._pattern_cache.get(key)
        if cached is not None:
            return cached

        width, height = max(1, int(size[0]) * scale), max(1, int(size[1]) * scale)
        pattern = pygame.Surface((width, height), pygame.SRCALPHA)
        rng = random.Random((width * 73856093) ^ (height * 19349663))
        count = max(5, int(width / max(26, height * 0.58)))
        for _ in range(count):
            size_px = rng.randint(max(7, height // 5), max(12, height // 2))
            x = rng.randint(-size_px, width)
            y = rng.randint(-size_px // 2, height)
            shade = rng.choice((255, 230, 200, 170))
            alpha = rng.randint(13, 27)
            points = (
                (x, y - size_px // 2),
                (x + size_px // 2, y + size_px // 2),
                (x - size_px // 2, y + size_px // 2)
            )
            pygame.draw.polygon(pattern, (shade, shade, shade, alpha), points)

        mask = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(
            mask,
            (255, 255, 255, 255),
            mask.get_rect(),
            border_radius=height // 2
        )
        pattern.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        if len(self._pattern_cache) > 16:
            self._pattern_cache.clear()
        self._pattern_cache[key] = pattern
        return pattern


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
        self.max_particles = 27

    def load(self):
        self.image = self._load_image()

    def update(self, dt, width, height):
        if not self.image:
            return

        self.spawn_timer -= dt
        if self.spawn_timer <= 0.0 and len(self.particles) < self.max_particles:
            self.spawn_timer = self.random.uniform(0.24, 0.63)
            self.particles.append(self._new_particle(width, height))

        next_particles = []
        for particle in self.particles:
            particle["age"] += dt

            if not particle["settled"]:
                particle["x"] += math.sin(
                    particle["age"] * particle["drift_speed"]
                    + particle["phase"]
                ) * particle["drift"] * dt
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
            alpha = int(255 * clamp(particle["fade"], 0.0, 1.0))
            if alpha <= 2:
                continue

            image = particle["image"]
            if particle.get("last_alpha") != alpha:
                image.set_alpha(alpha)
                particle["last_alpha"] = alpha
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
        ).convert_alpha()
        rotation = self.random.uniform(0.0, 360.0)
        if abs(rotation) > 0.5:
            image = pygame.transform.rotozoom(image, rotation, 1.0).convert_alpha()

        return {
            "x": self.random.uniform(-20, width + 20),
            "y": -size,
            "speed": self.random.uniform(height * 0.035, height * 0.072),
            "drift": self.random.uniform(12, 42),
            "drift_speed": self.random.uniform(0.42, 0.95),
            "phase": self.random.uniform(0.0, math.tau),
            "size": size,
            "rotation": rotation,
            "spin": 0.0,
            "image": image,
            "last_alpha": None,
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
            image = load_image(name, "menu")
            if image is not None:
                return image

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
        self.target_pulse_scale = 1.0
        self.last_beat_phase = 0.0
        self.ghost_scale = 1.0
        self.ghost_alpha = 0.0
        self.idle_pulse_phase = 0.0
        self.beat_waves = []
        self.font = None
        self._base_font = None
        self.small_font = None
        self._font_radius = 0
        self._scratch_surfaces = {}
        self._logo_surface = None
        self._logo_cache = {}
        self._caption_cache = {}
        self._logo_source_size = None

    def layout(self, width, height):
        self.center = (width // 2, height // 2)
        self.base_radius = int(clamp(min(width, height) * 0.309, 184, 380))

        if self._font_radius != self.base_radius:
            self._font_radius = self.base_radius
            self._logo_cache.clear()
            self.small_font = rounded_font(max(12, int(self.base_radius * 0.105)), bold=True)
            self._caption_cache.clear()
            if self._logo_surface is None:
                self._logo_surface = self._load_logo_surface()

    def _rounded_font(self, size):
        return rounded_font(size, bold=True)

    def contains(self, pos):
        dx = pos[0] - self.center[0]
        dy = pos[1] - self.center[1]
        return (dx * dx) + (dy * dy) <= (self.radius * self.radius)

    def update(self, dt, mouse_pos, time_seconds, beat_level, beat_phase, music_energy, music_active, menu_open):
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
        self.ghost_alpha = max(0.0, self.ghost_alpha - (dt * 4.0))
        next_waves = []
        for wave in self.beat_waves:
            wave["age"] += dt
            if wave["age"] < wave["duration"]:
                next_waves.append(wave)
        self.beat_waves = next_waves

        music_active = bool(music_active)
        beat_phase = clamp(beat_phase, 0.0, 1.0)
        music_energy = clamp(music_energy, 0.0, 1.0) if music_active else 0.02
        crossed_beat = self.last_beat_phase > 0.78 and beat_phase < 0.22
        if music_active and crossed_beat:
            self.ghost_scale = max(
                self.pulse_scale,
                1.055 + (music_energy * 0.055)
            )
            self.ghost_alpha = clamp(0.78 + (music_energy * 0.28), 0.0, 0.98)
            self.beat_waves.append({
                "age": 0.0,
                "duration": 0.33,
                "energy": music_energy
            })

        if music_active:
            expand_start = 0.06
            return_start = 0.80
            if beat_phase < expand_start:
                prebeat = 0.0
            elif beat_phase < return_start:
                prebeat = ease_in_out(
                    (beat_phase - expand_start)
                    / (return_start - expand_start)
                )
            else:
                prebeat = 1.0 - ease_out_cubic(
                    (beat_phase - return_start)
                    / (1.0 - return_start)
                )
        else:
            previous_idle_phase = self.idle_pulse_phase
            self.idle_pulse_phase = (self.idle_pulse_phase + max(0.0, dt)) % 1.0
            if self.idle_pulse_phase < previous_idle_phase:
                self.ghost_scale = 1.018
                self.ghost_alpha = max(self.ghost_alpha, 0.42)

            expand_end = 0.66
            if self.idle_pulse_phase < expand_end:
                progress = self.idle_pulse_phase / expand_end
                prebeat = ease_in_out(progress)
            else:
                return_phase = (self.idle_pulse_phase - expand_end) / (1.0 - expand_end)
                prebeat = 1.0 - ease_out_cubic(return_phase)
            self.last_beat_phase = 0.0

        if music_active:
            beat_push = prebeat * (0.09 + music_energy * 0.03)
        else:
            beat_push = max(0.0, prebeat * 0.014)
        hover_push = self.hover * 0.075
        flash_push = ease_out_cubic(self.click_flash) * 0.14
        menu_push = 0.025 if menu_open else 0.0
        self.target_pulse_scale = 1.0 + beat_push + hover_push + flash_push + menu_push
        expand_speed = 8.2 + music_energy * 4.4
        if not music_active:
            expand_speed = 4.8
        scale_speed = expand_speed
        if self.target_pulse_scale < self.pulse_scale:
            scale_speed = expand_speed * (1.65 if music_active else 1.42)
        self.pulse_scale = lerp(
            self.pulse_scale,
            self.target_pulse_scale,
            1.0 - math.exp(-dt * scale_speed)
        )
        self.radius = self.base_radius * self.pulse_scale
        if music_active:
            self.last_beat_phase = beat_phase

    def trigger_click(self):
        self.click_flash = 1.0

    def draw(self, surface, time_seconds, beat_level, menu_open):
        radius = int(self.radius)
        center_x, center_y = self.center
        self._draw_beat_waves(surface, center_x, center_y)

        if self.ghost_alpha > 0.01:
            ghost_radius = int(self.base_radius * self.ghost_scale)
            ghost = self._scaled_logo(ghost_radius)
            previous_alpha = ghost.get_alpha()
            ghost.set_alpha(int(205 * self.ghost_alpha))
            ghost_rect = ghost.get_rect(center=(center_x, center_y))
            surface.blit(ghost, ghost_rect)
            ghost.set_alpha(previous_alpha)

        body = self._scaled_logo(radius)
        body_rect = body.get_rect(center=(center_x, center_y))
        surface.blit(body, body_rect)

    def _draw_beat_waves(self, surface, center_x, center_y):
        if not self.beat_waves:
            return

        logo_radius = self.radius * 1.06
        max_width = max(2, int(self.base_radius * 0.035))
        layer_radius = int(logo_radius * 1.23 + max_width + 4)
        layer_size = layer_radius * 2
        cache_key = ("beat_wave", layer_size)
        layer = self._scratch_surfaces.get(cache_key)
        if layer is None:
            layer = pygame.Surface((layer_size, layer_size), pygame.SRCALPHA)
            self._scratch_surfaces[cache_key] = layer
        layer.fill((0, 0, 0, 0))
        local_center = (layer_radius, layer_radius)

        for wave in self.beat_waves:
            progress = clamp(wave["age"] / wave["duration"], 0.0, 1.0)
            eased = ease_out_cubic(progress)
            radius = int(logo_radius * (1.0 + (0.16 * eased)))
            alpha = int((145 + wave["energy"] * 52) * ((1.0 - progress) ** 1.45))
            if alpha <= 2:
                continue
            width = max(1, int(max_width * (1.0 - progress * 0.42)))
            pygame.draw.circle(
                layer,
                (255, 255, 255, alpha),
                local_center,
                radius,
                width
            )

        surface.blit(layer, (center_x - layer_radius, center_y - layer_radius))

    def _draw_caption(self, surface, caption, radius, alpha):
        center_x, center_y = self.center
        caption_key = (caption, self.small_font.get_height())
        caption_surface = self._caption_cache.get(caption_key)
        if caption_surface is None:
            caption_surface = self.small_font.render(caption.upper(), True, (255, 255, 255))
            if len(self._caption_cache) > 8:
                self._caption_cache.clear()
            self._caption_cache[caption_key] = caption_surface
        caption_surface.set_alpha(int(clamp(alpha, 0, 255)))
        caption_rect = caption_surface.get_rect(
            center=(center_x, center_y + int(radius * 0.44))
        )
        surface.blit(caption_surface, caption_rect)

    def _scaled_logo(self, radius):
        radius_key = max(1, int(round(radius / 2.0) * 2))
        key = radius_key
        cached = self._logo_cache.get(key)
        if cached is not None:
            return cached

        source = self._logo_surface or self._load_logo_surface()
        self._logo_surface = source
        diameter = max(1, int(radius_key * 2.12))
        scaled = pygame.transform.smoothscale(source, (diameter, diameter)).convert_alpha()

        if len(self._logo_cache) > 96:
            self._logo_cache.clear()
        self._logo_cache[key] = scaled
        return scaled

    def _load_logo_surface(self):
        for logo_name in ("Osu!_Logo_2016.svg", "Osu!_Logo_2016.svg.png"):
            logo_path = asset_path(logo_name)
            if logo_path.exists():
                try:
                    return self._normalise_logo_source(
                        pygame.image.load(str(logo_path)).convert_alpha()
                    )
                except pygame.error:
                    pass

        size = 768
        fallback = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        pygame.draw.circle(fallback, (226, 92, 168, 255), center, size // 2 - 12)
        pygame.draw.circle(fallback, (255, 255, 255, 255), center, size // 2 - 12, 42)
        return fallback

    def _normalise_logo_source(self, surface):
        max_size = 1152
        width, height = surface.get_size()
        largest = max(width, height)
        if largest <= max_size:
            return surface

        scale = max_size / largest
        return pygame.transform.smoothscale(
            surface,
            (max(1, int(width * scale)), max(1, int(height * scale)))
        )

    def _scratch_surface(self, key, size):
        surface = self._scratch_surfaces.get(key)
        if surface is None or surface.get_size() != size:
            surface = pygame.Surface(size, pygame.SRCALPHA)
            self._scratch_surfaces[key] = surface
        surface.fill((0, 0, 0, 0))
        return surface

class MainMenuScene(BaseScene):
    uses_ui = False

    IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
    AUDIO_EXTENSIONS = (".ogg", ".mp3", ".wav")
    MENU_MUSIC_EXTENSIONS = (".ogg", ".mp3")
    BACKGROUND_NAMES = (
        "background",
        "menu_background",
        "main_menu_background"
    )

    def __init__(self, game):
        super().__init__(game)

        self.assets_dir = ACTIVE_SKIN_DIR
        self.menu_music_dir = ASSETS_ROOT / "menu"
        self.title = "OSU!"
        self.time_seconds = 0.0
        self.beat_phase = 0.0
        self.beat_level = 0.0
        self.menu_open = False
        self.settings_open = False
        self.settings_slider_rect = pygame.Rect(0, 0, 0, 0)
        self.settings_dragging = None
        self.settings_panel_t = 0.0
        self.settings_scroll = 0.0
        self.settings_scroll_target = 0.0
        self.settings_content_height = 0.0
        self.settings_scroll_overshoot = 90.0
        self.settings_controls = {}
        self.settings_rebind_slot = None
        self.menu_t = 0.0
        self.light_overlay = False
        self.music_started = False
        self.music_paused = False
        self.music_paused_at_ms = 0
        self.keep_music_on_destroy = False
        self.music_path = None
        self.music_title = "simulated pulse"
        self.music_bpm = 118.0
        self.music_energy = 0.45
        self.current_timing_points = []
        self.music_started_ticks = 0
        self.analyzed_music_path = None
        self.visualizer_analysis_delay = 0.0
        self.last_shared_music_path = None
        self.music_tracks = self._build_music_playlist()
        self.current_track_index = self._initial_track_index()
        self.option_font = None
        self.footer_font = None
        self.layout_size = None
        self.footer_cache = {}
        self.settings_panel_cache = {}
        self.settings_key_button_cache = {}
        self.intro_elapsed = 0.0
        self.intro_duration = 0.82
        self.intro_overlay = None
        self.intro_overlay_size = None
        self.menu_music_target_volume = 0.42
        self.exit_requested = False
        self.exit_elapsed = 0.0
        self.exit_duration = 1.15
        self.exit_music_volume = 1.0
        self.exit_overlay = None
        self.exit_overlay_size = None
        self.exit_snapshot = None
        self.exit_snapshot_size = None

        self.circle = PulseCircle(self.title)
        self.visualizer = CircularMenuVisualizer(bar_count=96)
        self.snow = MenuSnow(self.assets_dir)
        self.snow.load()
        self.options = [
            MenuOption("Play", self._open_song_select),
            MenuOption("Settings", self._open_settings),
            MenuOption("Previous Track", self._previous_menu_track),
            MenuOption("Next Track", self._next_menu_track),
            MenuOption("Exit", self._exit_game)
        ]

        self.background = None
        self.background_load_attempted = False
        self.scaled_background = None
        self.dimmed_background = None
        self.background_size = None
        self.dimmed_background_key = None
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
        if hasattr(self.game, "sync_input_mode"):
            self.game.sync_input_mode(self.game.mouse_pos)
        pygame.mouse.set_visible(False)

    def _layout(self):
        width = self.game.WIDTH
        height = self.game.HEIGHT
        size = (width, height)
        if self.layout_size != size:
            self._clear_size_dependent_caches()
            self.layout_size = size

        self.circle.layout(width, height)
        self.option_font = rounded_font(
            max(28, int(self.circle.base_radius * 0.164)),
            bold=True
        )
        self.footer_font = rounded_font(max(14, height // 64), bold=False)
        self.footer_cache.clear()

        option_width = int(clamp(width * 0.318, 330, 566))
        option_height = int(clamp(height * 0.075, 56, 79))
        spacing = int(option_height * 1.24)
        open_circle_x = self.circle.center[0] - int(self.circle.base_radius * 0.48)
        open_circle_right = open_circle_x + int(self.circle.base_radius * 1.06)
        logo_overlap = int(max(
            int(option_height * 1.08),
            int(self.circle.base_radius * 0.18)
        ) * 1.55)
        left_x = open_circle_right - logo_overlap
        left_x = min(left_x, width - option_width - 24)
        start_y = self.circle.center[1] - int(spacing * (len(self.options) - 1) * 0.5)

        if start_y < 58:
            start_y = 58
        if start_y + (spacing * (len(self.options) - 1)) > height - 70:
            start_y = height - 70 - (spacing * (len(self.options) - 1))

        width_factors = [0.72, 0.84, 1.02, 0.88, 0.64]
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
        self._sync_from_shared_music(defer_analysis=False)
        self._start_menu_music()

    def on_resume(self):
        self._prepare_mouse()
        self._layout()
        self._sync_from_shared_music(defer_analysis=False)

    def on_resize(self):
        self._layout()
        self._clear_size_dependent_caches()

    def _clear_size_dependent_caches(self):
        self.scaled_background = None
        self.dimmed_background = None
        self.background_size = None
        self.dimmed_background_key = None
        self.fallback_background = None
        self.fallback_background_size = None
        self.fallback_orbit = None
        self.fallback_orbit_size = None
        self.overlay_cache.clear()
        self.settings_panel_cache.clear()
        self.settings_key_button_cache.clear()
        for option in self.options:
            option._surface_cache.clear()
            option._text_cache.clear()

    def handle_event(self, event):
        if self.exit_requested:
            return

        if event.type == pygame.KEYDOWN:
            if self.settings_rebind_slot is not None:
                if event.key == pygame.K_ESCAPE:
                    self.settings_rebind_slot = None
                else:
                    self.game.set_hit_key(self.settings_rebind_slot, event.key)
                    self.settings_rebind_slot = None
                    self.settings_panel_cache.clear()
                return
            if event.key == pygame.K_ESCAPE and self.settings_open:
                self.settings_open = False
                self.settings_dragging = None
                self.settings_rebind_slot = None
                return
            if event.key == pygame.K_ESCAPE and self.menu_open:
                self.menu_open = False
                return
            if event.key == pygame.K_SPACE:
                self._toggle_menu_music_pause()
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
                if self.settings_controls.get("mouse_sensitivity", pygame.Rect(0, 0, 0, 0)).collidepoint(self.game.mouse_pos):
                    self._adjust_mouse_sensitivity(event.y * 0.05)
                elif self.settings_controls.get("cursor_scale", pygame.Rect(0, 0, 0, 0)).collidepoint(self.game.mouse_pos):
                    self._adjust_cursor_scale(event.y * 0.05)
                elif self.settings_controls.get("gameplay_dim", pygame.Rect(0, 0, 0, 0)).collidepoint(self.game.mouse_pos):
                    self._adjust_gameplay_dim(event.y * 3)
                else:
                    self._scroll_settings(-event.y * 58)
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.settings_controls.get("mouse_sensitivity", pygame.Rect(0, 0, 0, 0)).collidepoint(event.pos):
                    self.settings_dragging = "mouse_sensitivity"
                    self._set_mouse_sensitivity_from_pos(event.pos[0])
                    return
                if self.settings_controls.get("cursor_scale", pygame.Rect(0, 0, 0, 0)).collidepoint(event.pos):
                    self.settings_dragging = "cursor_scale"
                    self._set_cursor_scale_from_pos(event.pos[0])
                    return
                if self.settings_controls.get("gameplay_dim", pygame.Rect(0, 0, 0, 0)).collidepoint(event.pos):
                    self.settings_dragging = "gameplay_dim"
                    self._set_gameplay_dim_from_pos(event.pos[0])
                    return
                if self.settings_controls.get("hit_key_1", pygame.Rect(0, 0, 0, 0)).collidepoint(event.pos):
                    self.settings_rebind_slot = 1
                    self.settings_panel_cache.clear()
                    return
                if self.settings_controls.get("hit_key_2", pygame.Rect(0, 0, 0, 0)).collidepoint(event.pos):
                    self.settings_rebind_slot = 2
                    self.settings_panel_cache.clear()
                    return
                if self.settings_controls.get("raw_mouse", pygame.Rect(0, 0, 0, 0)).collidepoint(event.pos):
                    self.game.set_raw_mouse_enabled(not self.game.raw_mouse_preferred)
                    self.settings_panel_cache.clear()
                    return
                if self.settings_controls.get("tablet_input", pygame.Rect(0, 0, 0, 0)).collidepoint(event.pos):
                    self.game.set_tablet_input_enabled(not self.game.tablet_input_enabled)
                    self.settings_panel_cache.clear()
                    return
                if self.settings_controls.get("block_mouse_buttons", pygame.Rect(0, 0, 0, 0)).collidepoint(event.pos):
                    self.game.set_block_mouse_buttons_in_gameplay(
                        not self.game.block_mouse_buttons_in_gameplay
                    )
                    self.settings_panel_cache.clear()
                    return
                return
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.settings_dragging = None
                return
            if event.type == pygame.MOUSEMOTION and self.settings_dragging:
                if self.settings_dragging == "mouse_sensitivity":
                    self._set_mouse_sensitivity_from_pos(event.pos[0])
                elif self.settings_dragging == "cursor_scale":
                    self._set_cursor_scale_from_pos(event.pos[0])
                elif self.settings_dragging == "gameplay_dim":
                    self._set_gameplay_dim_from_pos(event.pos[0])
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.menu_open:
                for option in self.options:
                    if option.handle_event(event):
                        return

            if self.circle.contains(event.pos):
                if self.menu_open and self.menu_t > 0.72:
                    self._open_song_select()
                    return
                self.menu_open = True
                self.circle.trigger_click()
                for index, option in enumerate(self.options):
                    option.delay = index * 0.055

    def update(self, dt):
        dt = min(dt, 1.0 / 20.0)
        self.time_seconds += dt
        if self.exit_requested:
            self.exit_elapsed = min(
                self.exit_duration,
                self.exit_elapsed + dt
            )
            progress = clamp(self.exit_elapsed / max(0.01, self.exit_duration), 0.0, 1.0)
            eased = progress * progress * (3.0 - (2.0 * progress))
            try:
                pygame.mixer.music.set_volume(self.exit_music_volume * (1.0 - eased))
            except pygame.error:
                pass
            if progress >= 1.0:
                try:
                    pygame.mixer.music.stop()
                except pygame.error:
                    pass
                self.game.running = False
        elif self.intro_elapsed < self.intro_duration:
            self.intro_elapsed = min(
                self.intro_duration,
                self.intro_elapsed + dt
            )
            progress = clamp(self.intro_elapsed / max(0.01, self.intro_duration), 0.0, 1.0)
            eased = progress * progress * (3.0 - (2.0 * progress))
            if self.music_started and not self.music_paused:
                try:
                    pygame.mixer.music.set_volume(self.menu_music_target_volume * eased)
                except pygame.error:
                    pass

        mouse_pos = self.game.mouse_pos
        if self.time_seconds >= 0.08:
            self._warm_background()

        self._sync_from_shared_music()
        if self.visualizer_analysis_delay > 0.0:
            self.visualizer_analysis_delay = max(0.0, self.visualizer_analysis_delay - dt)
        if self.visualizer_analysis_delay <= 0.0:
            self._ensure_visualizer_analysis()
        current_time_ms = self._current_music_position_ms()
        music_active = (
            self.music_started
            and not self.music_paused
            and pygame.mixer.music.get_busy()
        )
        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        if profiler_enabled:
            profiler.start("visualizer")
        self.visualizer.update(dt, current_time_ms, music_active)
        if profiler_enabled:
            profiler.end("visualizer")
        self.beat_level = self.visualizer.beat_level
        self.beat_phase = self.visualizer.beat_phase
        self.music_energy = self.visualizer.energy
        self.menu_t = lerp(
            self.menu_t,
            1.0 if self.menu_open else 0.0,
            1.0 - math.exp(-dt * 10.0)
        )
        if self.settings_dragging == "mouse_sensitivity":
            self._set_mouse_sensitivity_from_pos(mouse_pos[0])
        elif self.settings_dragging == "cursor_scale":
            self._set_cursor_scale_from_pos(mouse_pos[0])
        elif self.settings_dragging == "gameplay_dim":
            self._set_gameplay_dim_from_pos(mouse_pos[0])

        self.settings_panel_t = lerp(
            self.settings_panel_t,
            1.0 if self.settings_open else 0.0,
            1.0 - math.exp(-dt * 12.0)
        )
        self._update_settings_scroll(dt)

        self.circle.update(
            dt,
            mouse_pos,
            self.time_seconds,
            self.beat_level,
            self.beat_phase,
            self.music_energy,
            music_active,
            self.menu_open
        )
        for option in self.options:
            option.update(dt, mouse_pos, self.menu_open)

        self.snow.update(dt, self.game.WIDTH, self.game.HEIGHT)
        if profiler_enabled:
            profiler.start("audio")
        if not self.exit_requested:
            self._advance_finished_menu_track()
        if profiler_enabled:
            profiler.end("audio")

    def render(self, screen):
        if screen.get_size() != (self.game.WIDTH, self.game.HEIGHT):
            self._layout()

        self._draw_background(screen)
        if not self.background:
            self._draw_overlay(screen)
        self.snow.draw(screen)

        menu_t = ease_in_out(self.menu_t)
        menu_shift_x = int(menu_t * -self.circle.base_radius * 0.48)
        original_center = self.circle.center
        self.circle.center = (original_center[0] + menu_shift_x, original_center[1])
        profiler = getattr(self.game, "profiler", None)
        profiler_enabled = bool(profiler and profiler.enabled)
        if profiler_enabled:
            profiler.start("visualizer")
        self.visualizer.draw(
            screen,
            self.circle.center,
            self.circle.radius,
            self.beat_level,
            self.music_energy,
            (255, 240, 252)
        )
        if profiler_enabled:
            profiler.end("visualizer")

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
        if self.settings_open or self.settings_panel_t > 0.01:
            self._draw_settings_panel(screen)
        if self.intro_elapsed < self.intro_duration:
            self._draw_intro_fade(screen)
        if self.exit_requested:
            self._draw_exit_fade(screen)

    def destroy(self):
        if self.music_started and not self.keep_music_on_destroy:
            pygame.mixer.music.stop()
            self.music_started = False
            self.music_paused = False
        self.keep_music_on_destroy = False

    def _current_music_position_ms(self):
        if self.music_paused:
            return self.music_paused_at_ms

        try:
            from core.audio import get_playback_time_ms
            music_pos = get_playback_time_ms()
        except Exception:
            music_pos = pygame.mixer.music.get_pos()

        if music_pos is None or music_pos < 0:
            return pygame.time.get_ticks() - self.music_started_ticks
        return music_pos

    def _open_song_select(self):
        self.keep_music_on_destroy = True
        self._publish_current_music_state()
        self.game.scene_manager.push_scene_factory(
            lambda: SongSelectScene(
                self.game,
                initial_music_path=str(self.music_path) if self.music_path else None
            )
        )

    def _open_settings(self):
        if not self.settings_open:
            self.settings_scroll = 0.0
            self.settings_scroll_target = 0.0
        self.settings_open = True
        self.menu_open = True
        self.circle.trigger_click()

    def _settings_max_scroll(self):
        visible_height = max(1.0, float(self.game.HEIGHT))
        return max(0.0, float(self.settings_content_height) - visible_height)

    def _scroll_settings(self, amount):
        max_scroll = self._settings_max_scroll()
        overshoot = self.settings_scroll_overshoot
        self.settings_scroll_target = clamp(
            self.settings_scroll_target + amount,
            -overshoot,
            max_scroll + overshoot
        )

    def _update_settings_scroll(self, dt):
        if self.settings_panel_t <= 0.01 and not self.settings_open:
            self.settings_scroll = 0.0
            self.settings_scroll_target = 0.0
            return

        max_scroll = self._settings_max_scroll()
        clamped_target = clamp(self.settings_scroll_target, 0.0, max_scroll)
        if abs(self.settings_scroll_target - clamped_target) > 0.01:
            self.settings_scroll_target = lerp(
                self.settings_scroll_target,
                clamped_target,
                1.0 - math.exp(-dt * 8.5)
            )
            if abs(self.settings_scroll_target - clamped_target) < 0.25:
                self.settings_scroll_target = clamped_target

        self.settings_scroll = lerp(
            self.settings_scroll,
            self.settings_scroll_target,
            1.0 - math.exp(-dt * 11.0)
        )
        if abs(self.settings_scroll - self.settings_scroll_target) < 0.18:
            self.settings_scroll = self.settings_scroll_target

    def _adjust_mouse_sensitivity(self, amount):
        self.game.set_mouse_sensitivity(
            self.game.raw_mouse_sensitivity + amount
        )
        self.settings_panel_cache.clear()

    def _set_mouse_sensitivity_from_pos(self, x):
        rect = self.settings_controls.get("mouse_sensitivity", self.settings_slider_rect)
        if rect.width <= 0:
            return
        t = clamp((x - rect.left) / rect.width, 0.0, 1.0)
        value = 0.40 + (t * (2.00 - 0.40))
        self.game.set_mouse_sensitivity(round(value, 2))
        self.settings_panel_cache.clear()

    def _adjust_cursor_scale(self, amount):
        self.game.set_cursor_scale(self.game.cursor_scale + amount)
        self.settings_panel_cache.clear()

    def _set_cursor_scale_from_pos(self, x):
        rect = self.settings_controls.get("cursor_scale", pygame.Rect(0, 0, 0, 0))
        if rect.width <= 0:
            return
        t = clamp((x - rect.left) / rect.width, 0.0, 1.0)
        value = 0.50 + (t * (2.00 - 0.50))
        self.game.set_cursor_scale(round(value, 2))
        self.settings_panel_cache.clear()

    def _adjust_gameplay_dim(self, amount):
        self.game.set_gameplay_dim(self.game.gameplay_dim + amount)
        self.settings_panel_cache.clear()

    def _set_gameplay_dim_from_pos(self, x):
        rect = self.settings_controls.get("gameplay_dim", pygame.Rect(0, 0, 0, 0))
        if rect.width <= 0:
            return
        t = clamp((x - rect.left) / rect.width, 0.0, 1.0)
        self.game.set_gameplay_dim(round(t * 100))
        self.settings_panel_cache.clear()

    def _exit_game(self):
        if self.exit_requested:
            return
        self.exit_requested = True
        self.exit_elapsed = 0.0
        self.exit_music_volume = 1.0
        display = pygame.display.get_surface()
        if display is not None:
            try:
                self.exit_snapshot = display.copy().convert()
                self.exit_snapshot_size = display.get_size()
            except pygame.error:
                self.exit_snapshot = None
                self.exit_snapshot_size = None
        try:
            self.exit_music_volume = pygame.mixer.music.get_volume()
        except pygame.error:
            pass

    def _draw_exit_fade(self, screen):
        size = screen.get_size()
        if self.exit_overlay is None or self.exit_overlay_size != size:
            self.exit_overlay = pygame.Surface(size).convert()
            self.exit_overlay.fill((0, 0, 0))
            self.exit_overlay_size = size

        progress = clamp(self.exit_elapsed / max(0.01, self.exit_duration), 0.0, 1.0)
        eased = progress * progress * (3.0 - (2.0 * progress))
        alpha = int(255 * eased)
        if self.exit_overlay.get_alpha() != alpha:
            self.exit_overlay.set_alpha(alpha)
        screen.blit(self.exit_overlay, (0, 0))

    def _toggle_menu_music_pause(self):
        if not self.music_tracks:
            return

        if self.music_paused:
            pygame.mixer.music.unpause()
            self.music_paused = False
            self.music_started = True
        else:
            if not self.music_started:
                self._start_menu_music()
            self.music_paused_at_ms = max(0, self._current_music_position_ms())
            pygame.mixer.music.pause()
            self.music_paused = True

        self._publish_current_music_state()

    def _initial_track_index(self):
        shared_index = self._track_index_for_path(
            getattr(self.game, "current_menu_music_path", None)
        )
        if shared_index is not None:
            return shared_index
        if self.music_tracks:
            return random.randrange(len(self.music_tracks))
        return 0

    def _track_index_for_path(self, path):
        if not path:
            return None
        try:
            target = Path(path).resolve()
        except (OSError, RuntimeError):
            target = Path(path)

        for index, track in enumerate(self.music_tracks):
            try:
                candidate = Path(track["path"]).resolve()
            except (OSError, RuntimeError):
                candidate = Path(track["path"])
            if candidate == target:
                return index
        return None

    def _publish_current_music_state(self):
        self.game.current_menu_music_path = str(self.music_path) if self.music_path else None
        self.game.current_menu_music_title = self.music_title
        self.game.current_menu_music_timing_points = self.current_timing_points
        self.game.current_menu_music_paused = self.music_paused
        self.last_shared_music_path = self.game.current_menu_music_path

    def _sync_from_shared_music(self, defer_analysis=False):
        shared_path = getattr(self.game, "current_menu_music_path", None)
        if not shared_path:
            return False

        if self.last_shared_music_path == shared_path and self.music_path:
            self.music_paused = bool(getattr(self.game, "current_menu_music_paused", False))
            self.music_started = pygame.mixer.music.get_busy() or self.music_paused
            return True

        track_index = self._track_index_for_path(shared_path)
        if track_index is None:
            self.music_path = Path(shared_path)
            self.music_title = getattr(
                self.game,
                "current_menu_music_title",
                self.music_path.stem
            )
            self.current_timing_points = getattr(
                self.game,
                "current_menu_music_timing_points",
                []
            )
            self.footer_cache.clear()
            self.analyzed_music_path = str(self.music_path)
            self.visualizer_analysis_delay = 0.0
            self.visualizer.request_audio_analysis(
                self.music_path,
                self.current_timing_points
            )
        else:
            self._set_track_metadata(track_index)

        self.music_paused = bool(getattr(self.game, "current_menu_music_paused", False))
        self.music_started = pygame.mixer.music.get_busy() or self.music_paused
        if not self.music_paused:
            self.music_paused_at_ms = 0
        self.last_shared_music_path = shared_path
        if defer_analysis:
            self.visualizer_analysis_delay = max(self.visualizer_analysis_delay, 0.85)
        else:
            self._ensure_visualizer_analysis()
        return True

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

    def _warm_background(self):
        if self.background is not None or self.background_load_attempted:
            return

        self.background_load_attempted = True
        self.background = self._load_background()
        self.scaled_background = None
        self.dimmed_background = None
        self.background_size = None
        self.dimmed_background_key = None

    def _start_menu_music(self):
        self._sync_from_shared_music(defer_analysis=False)
        if self.music_started and (pygame.mixer.music.get_busy() or self.music_paused):
            return

        if not self.music_tracks:
            return

        self._play_track(self.current_track_index)

    def _play_track(self, index):
        if not self.music_tracks:
            return

        self._set_track_metadata(index)

        try:
            pygame.mixer.music.load(str(self.music_path))
            mark_music_loaded(self.music_path)
            start_volume = (
                0.0
                if self.intro_elapsed < self.intro_duration
                else self.menu_music_target_volume
            )
            pygame.mixer.music.set_volume(start_volume)
            pygame.mixer.music.play()
            self.music_started = True
            self.music_paused = False
            self.music_paused_at_ms = 0
            self.music_started_ticks = pygame.time.get_ticks()
            self._publish_current_music_state()
        except pygame.error:
            self.music_started = False
            self.music_paused = False

    def _draw_intro_fade(self, screen):
        size = screen.get_size()
        if self.intro_overlay is None or self.intro_overlay_size != size:
            self.intro_overlay = pygame.Surface(size).convert()
            self.intro_overlay.fill((0, 0, 0))
            self.intro_overlay_size = size

        progress = clamp(self.intro_elapsed / max(0.01, self.intro_duration), 0.0, 1.0)
        eased = progress * progress * (3.0 - (2.0 * progress))
        alpha = int(255 * (1.0 - eased))
        if self.intro_overlay.get_alpha() != alpha:
            self.intro_overlay.set_alpha(alpha)
        screen.blit(self.intro_overlay, (0, 0))

    def _ensure_visualizer_analysis(self, force=False):
        if not self.music_path:
            return

        music_path = str(self.music_path)
        if not force and self.analyzed_music_path == music_path:
            return
        if not force and self.visualizer_analysis_delay > 0.0:
            return

        self.visualizer.request_audio_analysis(
            self.music_path,
            self.current_timing_points
        )
        self.analyzed_music_path = music_path

    def _set_track_metadata(self, index):
        self.current_track_index = index % len(self.music_tracks)
        track = self.music_tracks[self.current_track_index]
        self.music_path = track["path"]
        self.music_title = track["title"]
        self.footer_cache.clear()
        self.music_bpm = track["bpm"]
        self.music_energy = track["energy"]
        self.current_timing_points = track.get("timing_points", [])
        self.beat_phase = 0.0
        self.analyzed_music_path = str(self.music_path)
        self.visualizer_analysis_delay = 0.0
        self.visualizer.request_audio_analysis(
            self.music_path,
            self.current_timing_points
        )

    def _advance_finished_menu_track(self):
        if (
            not self.music_tracks
            or self.music_paused
            or not self.music_started
            or pygame.mixer.music.get_busy()
        ):
            return

        if len(self.music_tracks) == 1:
            self._play_track(0)
            return

        offset = random.randrange(1, len(self.music_tracks))
        self._play_track(self.current_track_index + offset)

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

        for path in self._iter_asset_files(self.menu_music_dir, self.MENU_MUSIC_EXTENSIONS):
            if not self._is_menu_music_file(path):
                continue
            title = self._clean_display_text(
                path.stem.replace("_", " ").replace("-", " ").strip()
            )
            tracks.append({
                "path": path,
                "title": title or "Menu music",
                "bpm": 118.0,
                "energy": 0.48,
                "timing_points": []
            })

        for beatmap in getattr(self.game, "beatmaps", []):
            difficulty = beatmap["difficulties"][0]
            audio_path = self._first_audio_in_folder(
                Path(beatmap["path"]),
                difficulty.get("audio_filename")
            )
            if not audio_path:
                continue

            bpm = self._bpm_from_timing_points(difficulty.get("timing_points", []))
            tracks.append({
                "path": audio_path,
                "title": self._clean_display_text(
                    beatmap.get("display_name", beatmap["name"])
                ),
                "bpm": bpm,
                "energy": self._energy_from_bpm(bpm),
                "timing_points": difficulty.get("timing_points", [])
            })

        return tracks

    def _first_audio_in_folder(self, folder, preferred_filename=None):
        if preferred_filename:
            preferred = folder / preferred_filename
            if preferred.exists() and not is_sound_effect_file(preferred):
                return preferred

        for extensions in ((".mp3", ".ogg"), (".wav",)):
            for path in self._iter_asset_files(folder, extensions):
                if not is_sound_effect_file(path):
                    return path

        return None

    def _is_menu_music_file(self, path):
        return not is_sound_effect_file(path)

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
            if ch.isprintable() and ch not in "\ufffdâ–¡â– "
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
            dim_key = (size, self.light_overlay)
            if self.dimmed_background is None or self.dimmed_background_key != dim_key:
                self.scaled_background = self._cover_scale(self.background, size)
                self.background_size = size
                self.dimmed_background = self.scaled_background.copy()
                if self.light_overlay:
                    self.dimmed_background.fill((245, 235, 250), special_flags=pygame.BLEND_RGB_ADD)
                    self.dimmed_background.fill((188, 188, 188), special_flags=pygame.BLEND_RGB_MULT)
                else:
                    self.dimmed_background.fill((130, 130, 130), special_flags=pygame.BLEND_RGB_MULT)
                self.dimmed_background_key = dim_key
            screen.blit(self.dimmed_background, (0, 0))
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
        scaled = pygame.transform.scale(image, scaled_size)
        result = pygame.Surface(target_size)
        result.blit(
            scaled,
            (
                (target_w - scaled_size[0]) // 2,
                (target_h - scaled_size[1]) // 2
            )
        )
        return result.convert()

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
        hint = "Left/Right change music  |  Space pause  |  F11 fullscreen"
        if self.music_paused:
            hint = "Music paused  |  Space resume  |  F11 fullscreen"
        if self.menu_open:
            hint += "  |  ESC back"

        text = self._footer_surface(music_text, 110)
        hint_surface = self._footer_surface(hint, 100)
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
        progress = ease_out_cubic(self.settings_panel_t)
        if progress <= 0.01:
            self.settings_controls.clear()
            return

        screen_w, screen_h = screen.get_size()
        width = int(clamp(screen_w * 0.36, 390, 560))
        visible_width = max(1, int(width * progress))
        panel = pygame.Rect(0, 0, visible_width, screen_h)
        self.settings_controls.clear()

        surface = pygame.Surface(panel.size, pygame.SRCALPHA).convert_alpha()
        surface.fill((3, 3, 8, 240))
        pygame.draw.rect(
            surface,
            (10, 9, 18, 234),
            surface.get_rect().inflate(-2, -2),
            border_radius=0
        )
        pygame.draw.line(
            surface,
            (235, 105, 170, 222),
            (visible_width - 1, 0),
            (visible_width - 1, screen_h),
            2
        )

        content_alpha = int(255 * clamp((progress - 0.25) / 0.75, 0.0, 1.0))
        if content_alpha > 0:
            x = 28
            scroll_y = int(round(self.settings_scroll))
            y = 34 - scroll_y
            title = self.option_font.render("Settings", True, (255, 255, 255))
            title.set_alpha(content_alpha)
            surface.blit(title, (x, y))
            y += max(48, title.get_height() + 22)

            y = self._draw_settings_section(surface, "Input", x, y, content_alpha)
            y = self._draw_settings_slider(
                surface,
                "mouse_sensitivity",
                "Mouse sensitivity",
                f"{self.game.raw_mouse_sensitivity:.2f}x",
                clamp((self.game.raw_mouse_sensitivity - 0.40) / 1.60, 0.0, 1.0),
                x,
                y,
                visible_width,
                content_alpha
            )
            y = self._draw_settings_slider(
                surface,
                "cursor_scale",
                "Cursor size",
                f"{self.game.cursor_scale:.2f}x",
                clamp((self.game.cursor_scale - 0.50) / 1.50, 0.0, 1.0),
                x,
                y,
                visible_width,
                content_alpha
            )
            y = self._draw_settings_keys(surface, x, y, visible_width, content_alpha)
            y = self._draw_settings_toggle(
                surface,
                "raw_mouse",
                "Raw mouse input",
                self.game.raw_mouse_preferred,
                x,
                y,
                visible_width,
                content_alpha
            )
            y = self._draw_settings_toggle(
                surface,
                "tablet_input",
                "Tablet absolute input",
                self.game.tablet_input_enabled,
                x,
                y,
                visible_width,
                content_alpha
            )

            y += 8
            y = self._draw_settings_section(surface, "Gameplay", x, y, content_alpha)
            y = self._draw_settings_slider(
                surface,
                "gameplay_dim",
                "Background dim",
                f"{self.game.gameplay_dim:d}%",
                clamp(self.game.gameplay_dim / 100.0, 0.0, 1.0),
                x,
                y,
                visible_width,
                content_alpha
            )
            y = self._draw_settings_toggle(
                surface,
                "block_mouse_buttons",
                "Block mouse hit buttons",
                self.game.block_mouse_buttons_in_gameplay,
                x,
                y,
                visible_width,
                content_alpha
            )
            hint_lines = (
                "Tablet mode uses absolute cursor position.",
                "Mouse sensitivity affects raw mouse input only.",
                "Raw off uses the operating system pointer speed.",
                "Tablet input disables raw mouse input.",
                "Cursor size affects cursor and trail together.",
                "Click a key button, then press the new hit key."
            )
            for line in hint_lines:
                hint = self.footer_font.render(line, True, (186, 188, 210))
                hint.set_alpha(int(content_alpha * 0.78))
                surface.blit(hint, (x, y + 8))
                y += hint.get_height() + 7

            self.settings_content_height = max(
                0.0,
                float(y + scroll_y + 36)
            )

        screen.blit(surface, panel)

    def _draw_settings_section(self, surface, label, x, y, alpha):
        text = self.footer_font.render(label.upper(), True, (255, 215, 238))
        text.set_alpha(alpha)
        surface.blit(text, (x, y))
        pygame.draw.line(
            surface,
            (255, 105, 170, int(alpha * 0.46)),
            (x, y + text.get_height() + 5),
            (surface.get_width() - 28, y + text.get_height() + 5),
            1
        )
        return y + text.get_height() + 22

    def _draw_settings_pill(self, surface, rect, color):
        rect = pygame.Rect(rect)
        if rect.width <= 0 or rect.height <= 0:
            return
        radius = rect.height // 2
        pill = self._settings_rounded_surface(rect.size, color, radius)
        surface.blit(pill, rect)

    def _settings_rounded_surface(self, size, color, radius=None):
        width = max(1, int(size[0]))
        height = max(1, int(size[1]))
        if len(color) >= 4:
            alpha = max(0, min(255, int(round(color[3] / 8.0) * 8)))
            rgb = tuple(int(c) for c in color[:3])
        else:
            alpha = 255
            rgb = tuple(int(c) for c in color[:3])
        radius = height // 2 if radius is None else max(0, int(radius))
        key = ("rounded", width, height, radius, rgb, alpha)
        cached = self.settings_panel_cache.get(key)
        if cached is not None:
            return cached

        scale = 5
        high_size = (width * scale, height * scale)
        high = pygame.Surface(high_size, pygame.SRCALPHA).convert_alpha()
        pygame.draw.rect(
            high,
            (*rgb, alpha),
            high.get_rect(),
            border_radius=radius * scale
        )
        surface = pygame.transform.smoothscale(high, (width, height)).convert_alpha()
        if len(self.settings_panel_cache) > 192:
            self.settings_panel_cache.clear()
        self.settings_panel_cache[key] = surface
        return surface

    def _settings_circle_surface(self, radius, color):
        radius = max(1, int(radius))
        if len(color) >= 4:
            alpha = max(0, min(255, int(round(color[3] / 8.0) * 8)))
            rgb = tuple(int(c) for c in color[:3])
        else:
            alpha = 255
            rgb = tuple(int(c) for c in color[:3])
        key = ("circle", radius, rgb, alpha)
        cached = self.settings_panel_cache.get(key)
        if cached is not None:
            return cached

        diameter = radius * 2
        scale = 5
        high = pygame.Surface(
            (diameter * scale, diameter * scale),
            pygame.SRCALPHA
        ).convert_alpha()
        pygame.draw.circle(
            high,
            (*rgb, alpha),
            (radius * scale, radius * scale),
            radius * scale
        )
        surface = pygame.transform.smoothscale(
            high,
            (diameter, diameter)
        ).convert_alpha()
        if len(self.settings_panel_cache) > 192:
            self.settings_panel_cache.clear()
        self.settings_panel_cache[key] = surface
        return surface

    def _draw_settings_circle(self, surface, center, radius, color):
        circle = self._settings_circle_surface(radius, color)
        rect = circle.get_rect(
            center=(int(round(center[0])), int(round(center[1])))
        )
        surface.blit(circle, rect)

    def _draw_settings_slider(self, surface, key, label, value_text, t, x, y, panel_width, alpha):
        label_surface = self.footer_font.render(label, True, (238, 240, 255))
        label_surface.set_alpha(alpha)
        value_surface = self.footer_font.render(value_text, True, (255, 232, 145))
        value_surface.set_alpha(alpha)
        surface.blit(label_surface, (x, y))
        surface.blit(value_surface, (panel_width - value_surface.get_width() - 28, y))

        slider = pygame.Rect(x, y + label_surface.get_height() + 13, panel_width - x - 32, 12)
        self._draw_settings_pill(surface, slider, (54, 50, 77, int(alpha * 0.95)))
        fill = slider.copy()
        fill.width = max(slider.height, int(slider.width * t))
        self._draw_settings_pill(surface, fill, (226, 94, 166, alpha))
        knob_x = slider.left + int(slider.width * t)
        self._draw_settings_circle(
            surface,
            (knob_x, slider.centery),
            9,
            (255, 255, 255, alpha)
        )
        self._draw_settings_circle(
            surface,
            (knob_x, slider.centery),
            4,
            (122, 92, 238, alpha)
        )
        self.settings_controls[key] = slider
        if key == "mouse_sensitivity":
            self.settings_slider_rect = slider
        return slider.bottom + 24

    def _draw_settings_keys(self, surface, x, y, panel_width, alpha):
        label = self.footer_font.render("Hit keys", True, (238, 240, 255))
        label.set_alpha(alpha)
        surface.blit(label, (x, y))

        button_w = int(clamp((panel_width - x - 58) * 0.36, 96, 132))
        button_h = int(clamp(button_w * 0.35, 28, 34))
        gap = 14
        top = y + label.get_height() + 10
        keys = (
            ("hit_key_1", 1, self.game.hit_keys[0]),
            ("hit_key_2", 2, self.game.hit_keys[1])
        )
        for index, (control, slot, key_value) in enumerate(keys):
            rect = pygame.Rect(x + index * (button_w + gap), top, button_w, button_h)
            active = self.settings_rebind_slot == slot
            color = (224, 88, 166) if active else (62, 83, 210)
            button = self._settings_key_button_surface(rect.size, color, alpha)
            surface.blit(button, rect)
            name = "press..." if active else pygame.key.name(key_value).upper()
            text = self.footer_font.render(name, True, (255, 255, 255))
            text.set_alpha(alpha)
            surface.blit(text, text.get_rect(center=rect.center))
            self.settings_controls[control] = rect
        return top + button_h + 24

    def _settings_key_button_surface(self, size, color, alpha):
        key = ("key_button", int(size[0]), int(size[1]), tuple(color), int(alpha))
        cached = self.settings_key_button_cache.get(key)
        if cached is not None:
            return cached

        surface = self._settings_rounded_surface(
            size,
            (*color, int(alpha)),
            max(1, int(size[1]) // 2)
        )
        if len(self.settings_key_button_cache) > 24:
            self.settings_key_button_cache.clear()
        self.settings_key_button_cache[key] = surface
        return surface

    def _draw_settings_toggle(self, surface, key, label, enabled, x, y, panel_width, alpha):
        rect = pygame.Rect(x, y, panel_width - x - 32, 38)
        self._draw_settings_pill(surface, rect, (30, 28, 48, int(alpha * 0.88)))
        knob_area = pygame.Rect(rect.right - 72, rect.y + 7, 54, 24)
        fill = (230, 102, 170) if enabled else (74, 72, 94)
        self._draw_settings_pill(surface, knob_area, (*fill, alpha))
        knob_x = knob_area.right - 12 if enabled else knob_area.left + 12
        self._draw_settings_circle(
            surface,
            (knob_x, knob_area.centery),
            9,
            (255, 255, 255, alpha)
        )
        text = self.footer_font.render(label, True, (238, 240, 255))
        text.set_alpha(alpha)
        surface.blit(text, (rect.x + 16, rect.centery - text.get_height() // 2))
        self.settings_controls[key] = rect
        return rect.bottom + 14

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
