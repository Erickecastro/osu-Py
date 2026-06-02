import math
from pathlib import Path

import pygame

from core.audio import find_audio_file
from core.assets import asset_path
from core.beatmap_info import BeatmapParser, LocalScoreManager
from scenes.base_scene import BaseScene
from scenes.gameplay_scene import GameplayScene


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def lerp(current, target, amount):
    return current + ((target - current) * clamp(amount, 0.0, 1.0))


def ease_out(value):
    value = clamp(value, 0.0, 1.0)
    return 1.0 - pow(1.0 - value, 3)


class SongCard:
    def __init__(self, info):
        self.info = info
        self.x = 0.0
        self.y = 0.0
        self.scale = 0.85
        self.alpha = 0.0
        self.hover = 0.0
        self.initialized = False

    def place_at_target(self, target):
        tx, ty, scale, _alpha, _rect = target
        self.x = tx
        self.y = ty
        self.scale = scale
        self.alpha = 0.0
        self.hover = 0.0
        self.initialized = True

    def update(self, dt, target, mouse_pos):
        if not self.initialized:
            self.place_at_target(target)

        tx, ty, scale, alpha, rect = target
        speed = 1.0 - math.exp(-dt * 14.0)
        self.x = lerp(self.x, tx, speed)
        self.y = lerp(self.y, ty, speed)
        self.scale = lerp(self.scale, scale, speed)
        self.alpha = lerp(self.alpha, alpha, speed)
        self.hover = lerp(
            self.hover,
            1.0 if rect.collidepoint(mouse_pos) and alpha > 0.45 else 0.0,
            1.0 - math.exp(-dt * 18.0)
        )

    def draw(self, screen, scene, selected=False, meta=None):
        if self.alpha <= 0.02:
            return

        is_difficulty = meta and meta.get("type") == "difficulty"
        is_group = meta and meta.get("type") == "group"
        width_factor = 0.88 if is_difficulty else 1.0
        width = int(scene.card_width * self.scale * width_factor)
        height = int(scene.card_height * self.scale)
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (int(self.x), int(self.y))

        selected_group = scene.selected_group_key()
        same_group = meta and meta.get("group") == selected_group
        is_selected_difficulty = selected and is_difficulty
        card_alpha = 82
        tint = None
        if same_group:
            card_alpha = 255 if is_group else 248
            if is_difficulty:
                tint = (255, 235, 66, 255)
            if is_selected_difficulty:
                tint = (255, 250, 118, 255)
        if selected:
            card_alpha = 255

        layer = scene.card_layer_surface(
            (width, height),
            self.info,
            meta,
            same_group,
            selected,
            is_difficulty,
            is_selected_difficulty,
            card_alpha,
            tint
        )
        layer.set_alpha(int(self.alpha * 255))
        screen.blit(layer, rect)

    def _legacy_draw_unused(self):
        pass


class SongCarousel:
    def __init__(self):
        self.cards = {}

    def card_for(self, key, info, initial_target=None):
        if key not in self.cards:
            card = SongCard(info)
            if initial_target is not None:
                card.place_at_target(initial_target)
            self.cards[key] = card
        else:
            self.cards[key].info = info
        return self.cards[key]

    def trim(self, visible_infos):
        visible = {key for key, _, _ in visible_infos}
        for key in list(self.cards):
            if key not in visible:
                del self.cards[key]


class SongSelectScene(BaseScene):
    uses_ui = False

    SORT_MODES = ("Title", "Artist", "BPM", "Stars", "Date", "Difficulty")

    def card_layer_surface(
        self,
        size,
        info,
        meta,
        same_group,
        selected,
        is_difficulty,
        is_selected_difficulty,
        card_alpha,
        tint
    ):
        key = (
            tuple(size),
            str(info.osu_file),
            meta.get("type") if meta else None,
            meta.get("count") if meta else None,
            meta.get("group") in self.expanded_groups if meta else False,
            bool(same_group),
            bool(selected),
            bool(is_difficulty),
            bool(is_selected_difficulty),
            int(card_alpha),
            tuple(tint) if tint else None
        )
        cached = self.card_layer_cache.get(key)
        if cached is not None:
            return cached

        if len(self.card_layer_cache) > 256:
            self.card_layer_cache.clear()

        width, height = size
        body = pygame.Rect(0, 0, width, height)
        layer = pygame.Surface((width, height), pygame.SRCALPHA)

        base_image = self.card_background_surface(body.size)
        if base_image is None:
            base_image = pygame.Surface(body.size, pygame.SRCALPHA)
            base_image.fill((72, 92, 160, 255))
        if tint is not None:
            base_image.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
        if not same_group:
            base_image.fill((66, 66, 78, 255), special_flags=pygame.BLEND_RGBA_MULT)
        if selected and not is_difficulty:
            base_image.fill((150, 170, 255, 255), special_flags=pygame.BLEND_RGBA_ADD)
        if is_selected_difficulty:
            base_image.fill((70, 58, 0, 255), special_flags=pygame.BLEND_RGBA_ADD)
        base_image.set_alpha(card_alpha)
        layer.blit(base_image, body.topleft)

        title = self.card_title_font.render(info.title, True, (255, 255, 255))
        artist = self.card_small_font.render(info.artist, True, (230, 230, 240))
        if meta and meta.get("type") == "group" and meta.get("count", 1) > 1:
            marker = "EXPANDED" if meta.get("group") in self.expanded_groups else "CLICK TO EXPAND"
            version_text = f"BEATMAP GROUP  |  {meta['count']} DIFFICULTIES  |  {marker}"
        else:
            prefix = "   DIFFICULTY  |  " if is_difficulty else ""
            version_text = f"{prefix}{info.version}  {info.stars:.2f}*"
        version_color = (255, 250, 145) if same_group else (215, 205, 170)
        if is_selected_difficulty:
            version_color = (255, 255, 210)
        version = self.card_small_font.render(version_text, True, version_color)
        stats = self.card_tiny_font.render(f"BPM {info.bpm_text}  {info.length_text}", True, (220, 220, 230))
        for surf, alpha in (
            (title, 255),
            (artist, 220),
            (version, 230),
            (stats, 180)
        ):
            surf.set_alpha(alpha)

        text_x = body.left + int(width * (0.10 if is_difficulty else 0.07))
        layer.blit(title, (text_x, body.top + int(height * 0.16)))
        layer.blit(artist, (text_x, body.top + int(height * 0.46)))
        layer.blit(version, (text_x, body.top + int(height * 0.66)))
        layer.blit(stats, (text_x, body.top + int(height * 0.82)))

        self.card_layer_cache[key] = layer
        return layer

    def __init__(self, game, initial_music_path=None):
        super().__init__(game)
        self.initial_music_path = str(initial_music_path) if initial_music_path else None
        self.infos = BeatmapParser.from_loaded_beatmaps(self.game.beatmaps)
        self.filtered = list(self.infos)
        self.items = []
        self.expanded_groups = set()
        self.score_manager = LocalScoreManager()
        self.carousel = SongCarousel()
        self.selected_index = 0
        self.browse_index = 0
        self.search_text = ""
        self.search_active = False
        self.sort_mode_index = 0
        self.background_cache = {}
        self.current_background_key = None
        self.current_background = None
        self.previous_background = None
        self.background_overlay = None
        self.background_overlay_size = None
        self.background_t = 1.0
        self.time = 0.0
        self.preview_volume = 0.48
        self.pending_play_info = None
        self.pending_play_elapsed = 0.0
        self.pending_play_duration = 0.22
        self.current_preview_path = None
        self.card_base_image = self._load_card_base_image()
        self.card_image_cache = {}
        self.card_layer_cache = {}
        self.text_cache = {}
        self._layout()
        self._apply_filter()
        initial_index = self._index_for_music_path(self.initial_music_path)
        if not self.initial_music_path:
            initial_index = self._first_playable_index(initial_index)
        self._confirm_selection(initial_index, play_preview=self.initial_music_path is None)
        pygame.mouse.set_visible(False)
        if hasattr(self.game, "disable_raw_mouse"):
            self.game.disable_raw_mouse()

    def _layout(self):
        w, h = self.game.WIDTH, self.game.HEIGHT
        self.card_width = int(clamp(w * 0.42, 460, 720))
        self.card_height = int(clamp(h * 0.115, 82, 116))
        self.card_center_x = int(w - (self.card_width * 0.43))
        self.card_center_y = int(h * 0.52)
        self.card_spacing = int(self.card_height * 0.86)
        self.margin = int(max(18, w * 0.018))

        self.title_font = pygame.font.SysFont("arial", max(30, h // 24), bold=True)
        self.medium_font = pygame.font.SysFont("arial", max(20, h // 38), bold=True)
        self.small_font = pygame.font.SysFont("arial", max(15, h // 55))
        self.tiny_font = pygame.font.SysFont("arial", max(13, h // 70))
        self.card_title_font = pygame.font.SysFont("arial", max(18, h // 43), bold=True)
        self.card_small_font = pygame.font.SysFont("arial", max(14, h // 58))
        self.card_tiny_font = pygame.font.SysFont("arial", max(12, h // 72))

    def _load_card_base_image(self):
        path = asset_path("menu-button-background.png", "songselect_cards")
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            return None

    def card_background_surface(self, size):
        if self.card_base_image is None:
            return None
        key = tuple(size)
        cached = self.card_image_cache.get(key)
        if cached is None:
            cached = pygame.transform.smoothscale(
                self.card_base_image,
                key
            ).convert_alpha()
            self.card_image_cache[key] = cached
        return cached.copy()

    def selected_group_key(self):
        if not self.items:
            return None
        return self.items[self.selected_index].get("group")

    def create_ui(self):
        self._layout()

    def on_resize(self):
        self._layout()
        self.background_cache.clear()
        self.current_background = None
        self.previous_background = None
        self.current_background_key = None
        self.card_image_cache.clear()
        self.card_layer_cache.clear()
        self.text_cache.clear()

    def handle_event(self, event):
        if self.pending_play_info is not None:
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.search_active and self.search_text:
                    self.search_text = ""
                    self._apply_filter()
                    return
                self.game.scene_manager.pop_scene()
                return
            if event.key in (pygame.K_DOWN, pygame.K_s):
                self._move_browse(1)
                return
            if event.key in (pygame.K_UP, pygame.K_w):
                self._move_browse(-1)
                return
            if event.key == pygame.K_RETURN:
                self._play_selected()
                return
            if event.key == pygame.K_f and pygame.key.get_mods() & pygame.KMOD_CTRL:
                self.search_active = True
                return
            if event.key == pygame.K_BACKSPACE and self.search_active:
                self.search_text = self.search_text[:-1]
                self._apply_filter()
                return
            if event.key == pygame.K_TAB:
                self._cycle_sort()
                return
            if event.unicode and (self.search_active or event.unicode.strip()):
                if event.unicode.isprintable() and event.unicode not in "\r\n\t":
                    self.search_active = True
                    self.search_text += event.unicode
                    self._apply_filter()
                return

        if event.type == pygame.MOUSEWHEEL:
            self._move_browse(-event.y)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._handle_search_click(event.pos):
                return
            clicked = self._card_index_at(event.pos)
            if clicked is not None:
                item = self.items[clicked]
                if item["type"] == "group" and item["count"] > 1:
                    self._confirm_selection(clicked, play_preview=False)
                elif clicked == self.selected_index:
                    self._play_selected()
                else:
                    self._confirm_selection(clicked, play_preview=True)

    def update(self, dt):
        self.time += min(dt, 1.0 / 20.0)
        if self.pending_play_info is not None:
            self.pending_play_elapsed += dt
            progress = clamp(
                self.pending_play_elapsed / self.pending_play_duration,
                0.0,
                1.0
            )
            pygame.mixer.music.set_volume(self.preview_volume * (1.0 - progress) ** 2)
            if progress >= 1.0:
                info = self.pending_play_info
                self.pending_play_info = None
                pygame.mixer.music.stop()
                pygame.mixer.music.set_volume(self.preview_volume)
                self.game.scene_manager.push_scene(
                    GameplayScene(self.game, info.difficulty_data)
                )
                return

        if not self.items:
            return

        self.selected_index = max(0, min(self.selected_index, len(self.items) - 1))
        self.browse_index = max(0, min(self.browse_index, len(self.items) - 1))
        selected = self.items[self.selected_index]["info"]
        self._ensure_background(selected)
        self.background_t = min(1.0, self.background_t + dt * 3.0)

        visible = self._visible_infos()
        self.carousel.trim(visible)
        mouse_pos = self.game.mouse_pos
        for key, index, info in visible:
            target = self._target_for_index(index)
            card = self.carousel.card_for(key, info, target)
            card.update(dt, target, mouse_pos)

    def render(self, screen):
        self._draw_background(screen)
        self._draw_search_bar(screen)
        self._draw_info_panel(screen)
        self._draw_rank_panel(screen)
        self._draw_cards(screen)
        self._draw_bottom_bar(screen)

    def destroy(self):
        pass

    def _move_browse(self, amount):
        if not self.items:
            return
        self.browse_index = int(clamp(self.browse_index + amount, 0, len(self.items) - 1))

    def _confirm_selection(self, index, play_preview=False):
        if not self.items:
            return
        index = int(clamp(index, 0, len(self.items) - 1))
        item = self.items[index]

        if item["type"] == "group" and item["count"] > 1:
            group = item["group"]
            if group in self.expanded_groups:
                self.expanded_groups.remove(group)
            else:
                self.expanded_groups.add(group)
            self._rebuild_items()
            self.selected_index = min(index, len(self.items) - 1)
            self.browse_index = self.selected_index
            self._ensure_background(self.items[self.selected_index]["info"])
            self._start_preview_music(self.items[self.selected_index]["info"])
            return

        self.selected_index = index
        self.browse_index = self.selected_index
        self._ensure_background(self.items[self.selected_index]["info"])
        if play_preview:
            self._start_preview_music(self.items[self.selected_index]["info"])

    def _start_preview_music(self, info):
        music_path = find_audio_file(
            info.folder_path,
            info.difficulty_data.get("audio_filename")
        )
        if not music_path:
            return
        if self.initial_music_path and Path(music_path) == Path(self.initial_music_path):
            self.current_preview_path = str(Path(music_path))
            self.initial_music_path = None
            return
        normalized = str(Path(music_path))
        if self.current_preview_path == normalized and pygame.mixer.music.get_busy():
            return
        try:
            pygame.mixer.music.load(music_path)
            pygame.mixer.music.set_volume(self.preview_volume)
            pygame.mixer.music.play()
            self.current_preview_path = normalized
        except pygame.error:
            pass

    def _index_for_music_path(self, music_path):
        if not music_path or not self.items:
            return 0
        target = Path(music_path)
        for index, item in enumerate(self.items):
            info = item["info"]
            candidate = find_audio_file(
                info.folder_path,
                info.difficulty_data.get("audio_filename")
            )
            if candidate and Path(candidate) == target:
                if item["type"] == "group" and item["count"] > 1:
                    self.expanded_groups.add(item["group"])
                    self._rebuild_items()
                    return min(index + 1, len(self.items) - 1)
                return index
        return 0

    def _first_playable_index(self, index):
        if not self.items:
            return 0
        index = int(clamp(index, 0, len(self.items) - 1))
        item = self.items[index]
        if item["type"] == "group" and item["count"] > 1:
            self.expanded_groups.add(item["group"])
            self._rebuild_items()
            return min(index + 1, len(self.items) - 1)
        return index

    def _play_selected(self):
        if not self.items:
            return
        item = self.items[self.selected_index]
        if item["type"] == "group" and item["count"] > 1:
            return
        self.pending_play_info = item["info"]
        self.pending_play_elapsed = 0.0

    def _cycle_sort(self):
        self.sort_mode_index = (self.sort_mode_index + 1) % len(self.SORT_MODES)
        self._apply_filter()

    def _handle_search_click(self, pos):
        rect = self._search_rect()
        if rect.collidepoint(pos):
            self.search_active = True
            return True
        return False

    def _card_index_at(self, pos):
        for index, _item in enumerate(self.items):
            target = self._target_for_index(index)
            if target[4].collidepoint(pos) and target[3] > 0.35:
                return index
        return None

    def _apply_filter(self):
        query = self.search_text.strip().lower()
        if query:
            self.filtered = [info for info in self.infos if query in info.search_text]
        else:
            self.filtered = list(self.infos)

        sort_mode = self.SORT_MODES[self.sort_mode_index]
        key_funcs = {
            "Title": lambda info: (info.title.lower(), info.artist.lower(), info.version.lower()),
            "Artist": lambda info: (info.artist.lower(), info.title.lower(), info.version.lower()),
            "BPM": lambda info: (info.bpm_max, info.title.lower()),
            "Stars": lambda info: (info.stars, info.title.lower()),
            "Date": lambda info: (info.added_time, info.title.lower()),
            "Difficulty": lambda info: (info.version.lower(), info.title.lower())
        }
        reverse = sort_mode in ("BPM", "Stars", "Date")
        self.filtered.sort(key=key_funcs[sort_mode], reverse=reverse)
        self._rebuild_items()
        self.selected_index = int(clamp(self.selected_index, 0, max(0, len(self.items) - 1)))
        self.browse_index = int(clamp(self.browse_index, 0, max(0, len(self.items) - 1)))

    def _rebuild_items(self):
        groups = {}
        order = []
        for info in self.filtered:
            if info.folder_path not in groups:
                groups[info.folder_path] = []
                order.append(info.folder_path)
            groups[info.folder_path].append(info)

        items = []
        for group in order:
            difficulties = sorted(groups[group], key=lambda info: info.stars)
            representative = difficulties[-1]
            items.append({
                "type": "group",
                "group": group,
                "info": representative,
                "count": len(difficulties)
            })
            if group in self.expanded_groups and len(difficulties) > 1:
                for difficulty in difficulties:
                    items.append({
                        "type": "difficulty",
                        "group": group,
                        "info": difficulty,
                        "count": 1
                    })
        self.items = items

    def _visible_infos(self):
        if not self.items:
            return []
        start = max(0, self.browse_index - 6)
        end = min(len(self.items), self.browse_index + 7)
        return [
            (self._item_key(index), index, self.items[index]["info"])
            for index in range(start, end)
        ]

    def _item_key(self, index):
        item = self.items[index]
        if item["type"] == "group":
            return f"group:{item['group']}"
        return f"difficulty:{item['info'].osu_file}"

    def _target_for_index(self, index):
        offset = index - self.browse_index
        distance = abs(offset)
        selected = offset == 0
        scale = 1.08 if selected else max(0.72, 0.92 - distance * 0.045)
        alpha = 1.0 if selected else max(0.18, 0.72 - distance * 0.08)
        x_shift = int((distance ** 1.15) * 24)
        x = self.card_center_x + x_shift
        y = self.card_center_y + offset * self.card_spacing
        rect = pygame.Rect(0, 0, int(self.card_width * scale), int(self.card_height * scale))
        rect.center = (int(x), int(y))
        return x, y, scale, alpha, rect

    def _draw_background(self, screen):
        if self.current_background is None:
            self._draw_fallback_background(screen)
        else:
            if self.previous_background and self.background_t < 1.0:
                screen.blit(self.previous_background, (0, 0))
                previous_alpha = self.current_background.get_alpha()
                self.current_background.set_alpha(
                    int(ease_out(self.background_t) * 255)
                )
                screen.blit(self.current_background, (0, 0))
                self.current_background.set_alpha(previous_alpha)
            else:
                screen.blit(self.current_background, (0, 0))

        size = screen.get_size()
        if self.background_overlay is None or self.background_overlay_size != size:
            self.background_overlay = pygame.Surface(size, pygame.SRCALPHA)
            self.background_overlay.fill((0, 0, 0, 178))
            self.background_overlay_size = size
        screen.blit(self.background_overlay, (0, 0))

    def _draw_fallback_background(self, screen):
        w, h = screen.get_size()
        screen.fill((18, 18, 34))
        for i in range(10):
            angle = self.time * 0.08 + i * 0.8
            center = (
                int(w * 0.5 + math.cos(angle) * w * 0.35),
                int(h * 0.5 + math.sin(angle) * h * 0.28)
            )
            pygame.draw.circle(screen, (60, 55, 105), center, int(min(w, h) * (0.12 + i * 0.012)), 2)

    def _ensure_background(self, info):
        key = info.background_path
        if key == self.current_background_key:
            return

        self.previous_background = self.current_background
        self.current_background_key = key
        self.current_background = self._load_background_surface(key)
        self.background_t = 0.0

    def _load_background_surface(self, path):
        if not path:
            return None
        if path in self.background_cache:
            return self.background_cache[path]
        try:
            image = pygame.image.load(path).convert()
        except pygame.error:
            return None
        surface = self._cover_scale(image, self.game.screen.get_size())
        self.background_cache[path] = surface
        return surface

    def thumbnail_for(self, info, size):
        path = info.background_path
        if not path:
            return None
        key = (path, size)
        if key in self.thumbnail_cache:
            return self.thumbnail_cache[key]
        try:
            image = pygame.image.load(path).convert()
        except pygame.error:
            return None
        thumb = self._cover_scale(image, size)
        self.thumbnail_cache[key] = thumb
        return thumb

    def _cover_scale(self, image, target_size):
        target_w, target_h = target_size
        source_w, source_h = image.get_size()
        scale = max(target_w / source_w, target_h / source_h)
        scaled_size = (max(1, int(source_w * scale)), max(1, int(source_h * scale)))
        scaled = pygame.transform.smoothscale(image, scaled_size)
        result = pygame.Surface(target_size).convert()
        result.blit(scaled, ((target_w - scaled_size[0]) // 2, (target_h - scaled_size[1]) // 2))
        return result

    def _draw_search_bar(self, screen):
        rect = self._search_rect()
        pygame.draw.rect(screen, (13, 14, 26, 220), rect, border_radius=7)
        pygame.draw.rect(screen, (92, 135, 255, 145), rect, 2, border_radius=7)
        text = self._text_surface(
            self.small_font,
            f"Search: {self.search_text or 'Type to search!'}",
            (235, 238, 255)
        )
        screen.blit(text, (rect.x + 16, rect.y + rect.height // 2 - text.get_height() // 2))

    def _search_rect(self):
        width = int(clamp(self.game.WIDTH * 0.34, 360, 560))
        return pygame.Rect(
            self.game.WIDTH - width - 18,
            22,
            width,
            42
        )

    def _draw_info_panel(self, screen):
        if not self.items:
            self._draw_empty(screen)
            return
        info = self.items[self.selected_index]["info"]
        x = self.margin
        y = 18
        width = int(self.game.WIDTH * 0.51)
        height = int(clamp(self.game.HEIGHT * 0.18, 118, 150))
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(screen, (0, 0, 0, 185), rect, border_radius=8)
        pygame.draw.rect(screen, (78, 130, 255, 185), rect, 2, border_radius=8)

        title_text = f"{info.artist} - {info.title} [{info.version}]"
        title = self._text_surface(self.medium_font, title_text, (255, 255, 255))
        mapper = self._text_surface(self.small_font, f"Mapped by {info.creator}", (230, 235, 245))
        stats1 = self._text_surface(
            self.small_font,
            f"Length: {info.length_text}  BPM: {info.bpm_text}  Objects: {info.object_count}",
            (238, 238, 245)
        )
        stats2 = self._text_surface(
            self.small_font,
            f"Circles: {info.circle_count}  Sliders: {info.slider_count}  Spinners: {info.spinner_count}",
            (238, 238, 245)
        )
        stats3 = self._text_surface(
            self.tiny_font,
            f"CS:{info.cs:g} AR:{info.ar:g} OD:{info.od:g} HP:{info.hp:g}  Star Rating: {info.stars:.2f}",
            (225, 230, 245)
        )
        for surf, yy in (
            (title, y + 10),
            (mapper, y + 40),
            (stats1, y + 67),
            (stats2, y + 91),
            (stats3, y + 116)
        ):
            screen.blit(surf, (x + 14, yy))

    def _draw_rank_panel(self, screen):
        x = self.margin
        y = int(self.game.HEIGHT * 0.205)
        w = int(self.game.WIDTH * 0.42)
        h = int(self.game.HEIGHT * 0.095)
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(screen, (15, 15, 26, 145), rect, border_radius=8)
        pygame.draw.rect(screen, (78, 130, 255, 155), rect, 2, border_radius=8)
        title = self._text_surface(self.small_font, "Local Ranking", (255, 255, 255))
        screen.blit(title, (x + 14, y + 9))

        records = []
        if self.items:
            records = self.score_manager.records_for(self.items[self.selected_index]["info"].osu_file)
        if not records:
            text = self._text_surface(self.tiny_font, "No records set!", (210, 210, 225))
            screen.blit(text, (x + 14, y + 38))

    def _draw_cards(self, screen):
        if not self.items:
            return
        visible = self._visible_infos()
        visible.sort(key=lambda item: abs(item[1] - self.browse_index), reverse=True)
        for key, index, info in visible:
            self.carousel.card_for(key, info).draw(
                screen,
                self,
                selected=index == self.browse_index,
                meta=self.items[index]
            )

    def _draw_bottom_bar(self, screen):
        h = 58
        y = self.game.HEIGHT - h
        pygame.draw.rect(screen, (10, 10, 18, 205), (0, y, self.game.WIDTH, h))
        back = pygame.Rect(18, y + 10, 118, 38)
        pygame.draw.rect(screen, (130, 70, 120, 220), back, border_radius=6)
        pygame.draw.rect(screen, (255, 255, 255, 80), back, 1, border_radius=6)
        screen.blit(self._text_surface(self.medium_font, "Back", (255, 255, 255)), (back.x + 33, back.y + 7))
        guest = self._text_surface(self.small_font, "Guest", (230, 230, 240))
        screen.blit(guest, (self.game.WIDTH - guest.get_width() - 22, y + 20))
        action = self._text_surface(self.small_font, "Enter: play   Up/Down or wheel: navigate   Ctrl+F: search   Tab: sort", (200, 200, 215))
        screen.blit(action, (160, y + 20))

    def _draw_empty(self, screen):
        text = self._text_surface(self.title_font, "No beatmaps found", (255, 255, 255))
        screen.blit(text, text.get_rect(center=(self.game.WIDTH // 2, self.game.HEIGHT // 2)))

    def _text_surface(self, font, text, color):
        key = (id(font), str(text), tuple(color))
        cached = self.text_cache.get(key)
        if cached is not None:
            return cached

        if len(self.text_cache) > 192:
            self.text_cache.clear()

        surface = font.render(str(text), True, color)
        self.text_cache[key] = surface
        return surface
