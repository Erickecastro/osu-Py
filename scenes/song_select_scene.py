import math
import shutil
from pathlib import Path

import pygame

from core.audio import find_audio_file, mark_music_loaded
from core.assets import load_image
from core.beatmap_info import BeatmapParser, LocalScoreManager
from core.fonts import rounded_font
from core.utils import discover_user_data_directories
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
        width = scene.quantize_card_size(scene.card_width * self.scale * width_factor, 8)
        height = scene.quantize_card_size(scene.card_height * self.scale, 4)
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (int(self.x), int(self.y))

        selected_group = scene.selected_group_key()
        same_group = meta and meta.get("group") == selected_group
        is_selected_difficulty = selected and is_difficulty
        layer = scene.card_layer_surface(
            (width, height),
            self.info,
            meta,
            same_group,
            selected,
            is_difficulty,
            is_selected_difficulty
        )
        alpha = int(self.alpha * 255)
        if layer.get_alpha() != alpha:
            layer.set_alpha(alpha)
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
        is_selected_difficulty
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
            bool(is_selected_difficulty)
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
            base_image.fill((255, 255, 255, 255))

        is_multi_group_card = (
            meta
            and meta.get("type") == "group"
            and meta.get("count", 1) > 1
        )
        if is_selected_difficulty:
            color = (255, 238, 82, 242)
            add_color = (180, 150, 34, 0)
        elif is_difficulty:
            color = (118, 74, 218, 214)
            add_color = (52, 30, 128, 0)
        elif same_group or selected:
            color = (255, 222, 72, 232)
            add_color = (165, 126, 28, 0)
        else:
            color = (42, 43, 50, 148)
            add_color = (0, 0, 0, 0)

        base_image.fill(color, special_flags=pygame.BLEND_RGBA_MULT)
        if add_color[:3] != (0, 0, 0):
            base_image.fill(add_color, special_flags=pygame.BLEND_RGB_ADD)
        base_image.set_alpha(color[3])
        layer.blit(base_image, body.topleft)

        title_text = info.version if is_difficulty else info.title
        text_x = body.left + int(width * (0.13 if is_difficulty else 0.07))
        text_w = max(60, width - text_x - int(width * 0.08))
        title = self._fit_text_surface(
            self.card_title_font,
            title_text,
            (255, 255, 255),
            text_w
        ).copy()
        artist_line = f"{info.artist} // {info.creator}"
        artist = self._fit_text_surface(
            self.card_small_font,
            artist_line,
            (232, 232, 240),
            text_w
        ).copy()
        for surf, alpha in (
            (title, 255),
            (artist, 220)
        ):
            surf.set_alpha(alpha)

        layer.blit(title, (text_x, body.top + int(height * 0.16)))
        layer.blit(artist, (text_x, body.top + int(height * 0.46)))
        show_stars = (
            (is_difficulty or selected or same_group)
            and not is_multi_group_card
        )
        if show_stars:
            self._draw_star_rating(
                layer,
                info.stars,
                text_x,
                int(height * 0.70),
                int(width * 0.25),
                230 if same_group or selected or is_selected_difficulty else 170
            )

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
        self.selected_info = None
        self.selected_osu_file = getattr(
            self.game,
            "current_selected_osu_file",
            None
        )
        self.search_text = ""
        self.search_active = False
        self.sort_mode_index = 0
        self.background_cache = {}
        self.background_load_delay = 0.12
        self.current_background_key = None
        self.current_background = None
        self.previous_background = None
        self.background_overlay = None
        self.background_overlay_size = None
        self.background_t = 1.0
        self.visible_items = []
        self.time = 0.0
        self.preview_volume = 0.48
        self.pending_play_info = None
        self.pending_play_elapsed = 0.0
        self.pending_play_duration = 0.22
        self.selection_play_armed = False
        self.selection_play_osu_file = None
        self.current_preview_path = None
        self.back_button_rect = pygame.Rect(0, 0, 0, 0)
        self.card_base_image = self._load_card_base_image()
        self.top_band_image = load_image("songselect-top-band.png")
        self.back_button_image = load_image("songselect-back-button.png")
        self.star_image = load_image("star.png")
        self.rank_images = {
            "SS": load_image("ranking-X-small.png"),
            "S": load_image("ranking-S-small.png"),
            "A": load_image("ranking-a-small.png"),
            "B": load_image("ranking-b-small.png"),
            "C": load_image("ranking-c-small.png"),
            "D": load_image("ranking-d-small.png")
        }
        self.card_image_cache = {}
        self.card_layer_cache = {}
        self.text_cache = {}
        self.panel_surface_cache = {}
        self.rank_record_rects = []
        self.pending_delete_record = None
        self.pending_delete_beatmap = None
        self.delete_prompt_rect = None
        self.drag_scroll_active = False
        self.drag_scroll_start_y = 0
        self.drag_scroll_start_index = 0
        self.last_mouse_x = None
        self._layout()
        self._apply_filter()
        initial_index = self._index_for_music_path(self.initial_music_path)
        if not self.initial_music_path:
            restored_index = self._find_index_by_osu_file(self.selected_osu_file)
            initial_index = (
                restored_index
                if restored_index is not None
                else self._first_playable_index(initial_index)
            )
        self._confirm_selection(initial_index, play_preview=self.initial_music_path is None)
        if self.initial_music_path and self.items:
            info = self.items[self.selected_index]["info"]
            music_path = find_audio_file(
                info.folder_path,
                info.difficulty_data.get("audio_filename")
            )
            if music_path:
                self.current_preview_path = str(Path(music_path))
                self._publish_preview_music(info, self.current_preview_path)
            self.initial_music_path = None
        pygame.mouse.set_visible(False)
        if hasattr(self.game, "sync_input_mode"):
            self.game.sync_input_mode(self.game.mouse_pos)

    def _layout(self):
        w, h = self.game.WIDTH, self.game.HEIGHT
        self.card_width = int(clamp(w * 0.53, 584, 914))
        self.card_height = int(clamp(h * 0.146, 104, 148))
        self.card_center_x = int(w - (self.card_width * 0.39))
        self.card_center_y = int(h * 0.52)
        self.card_spacing = int(self.card_height * 0.7935)
        self.margin = int(max(18, w * 0.018))
        fallback_button_h = int(clamp(h * 0.064, 50, 64))
        if self.back_button_image is not None:
            back_w, button_h = self.back_button_image.get_size()
        else:
            button_h = fallback_button_h
            back_w = int(clamp(button_h * 3.64, 180, 236))
        bottom_h = max(fallback_button_h * 2, button_h + fallback_button_h)
        self.bottom_bar_height = bottom_h
        self.back_button_rect = pygame.Rect(
            0,
            h - bottom_h + ((bottom_h - button_h) // 2),
            back_w,
            button_h
        )

        self.title_font = rounded_font(max(30, h // 24), bold=True)
        self.medium_font = rounded_font(max(20, h // 38), bold=True)
        self.small_font = rounded_font(max(15, h // 55), bold=False)
        self.tiny_font = rounded_font(max(13, h // 70), bold=False)
        self.card_title_font = rounded_font(max(18, h // 43), bold=True)
        self.card_small_font = rounded_font(max(14, h // 58), bold=False)
        self.card_tiny_font = rounded_font(max(12, h // 72), bold=False)
        self.back_hover_t = getattr(self, "back_hover_t", 0.0)

    def _load_card_base_image(self):
        return load_image("menu-button-background.png", "songselect_cards")

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

    def _draw_star_rating(self, target, stars, x, y, max_width, alpha=210):
        if self.star_image is None:
            text = self.card_tiny_font.render(f"{stars:.2f}*", True, (255, 238, 100))
            target.blit(text, (x, y))
            return

        stars = max(0.0, float(stars or 0.0))
        full_count = min(10, int(stars))
        has_half = stars - int(stars) > 0.05 and full_count < 10
        draw_count = full_count + (1 if has_half else 0)
        if draw_count <= 0:
            draw_count = 1
        base_size = max_width / max(1, min(10, draw_count))
        size = int(clamp(base_size * 1.10, 9, 17))
        gap = max(2, int(size * 0.18))
        scaled = self.card_image_cache.get(("star", size))
        if scaled is None:
            scaled = pygame.transform.smoothscale(
                self.star_image,
                (size, size)
            ).convert_alpha()
            self.card_image_cache[("star", size)] = scaled

        cx = int(x)
        previous_alpha = scaled.get_alpha()
        scaled.set_alpha(max(0, min(255, int(alpha))))
        for _ in range(full_count):
            target.blit(scaled, (cx, int(y)))
            cx += size + gap
        if has_half:
            clip_width = max(1, size // 2)
            target.blit(
                scaled,
                (cx, int(y)),
                pygame.Rect(0, 0, clip_width, size)
            )
            cx += size + gap
        scaled.set_alpha(previous_alpha)

        if stars > 10.0:
            plus = self.card_tiny_font.render("+++", True, (255, 238, 100))
            plus.set_alpha(alpha)
            target.blit(plus, (cx, int(y - 1)))

    def quantize_card_size(self, value, quantum):
        quantum = max(1, int(quantum))
        return max(quantum, int(round(float(value) / quantum)) * quantum)

    def selected_group_key(self):
        info = self._current_info()
        if info is None:
            return None
        for item in self.items:
            if item["info"].osu_file == info.osu_file:
                return item.get("group")
        return None

    def _current_info(self):
        if self.selected_info is not None:
            return self.selected_info
        if self.items:
            return self.items[self.selected_index]["info"]
        return None

    def _remember_selected_info(self, info):
        self.selected_info = info
        self.selected_osu_file = str(info.osu_file) if info is not None else None
        self.game.current_selected_osu_file = self.selected_osu_file

    def _find_index_by_osu_file(self, osu_file):
        if not osu_file:
            return None
        target = str(osu_file)
        for index, item in enumerate(self.items):
            if item["type"] != "group" and str(item["info"].osu_file) == target:
                return index
        for index, item in enumerate(self.items):
            if str(item["info"].osu_file) == target:
                return index
        return None

    def _first_difficulty_index_for_group(self, group):
        for index, item in enumerate(self.items):
            if item.get("group") == group and item["type"] == "difficulty":
                return index
        for index, item in enumerate(self.items):
            if item.get("group") == group:
                return index
        return None

    def create_ui(self):
        self._layout()

    def on_resize(self):
        self._layout()
        self.visible_items = []
        self.background_cache.clear()
        self.current_background = None
        self.previous_background = None
        self.current_background_key = None
        self.card_image_cache.clear()
        self.card_layer_cache.clear()
        self.text_cache.clear()
        self.panel_surface_cache.clear()

    def on_resume(self):
        self.score_manager.load()
        self.panel_surface_cache.clear()
        self.card_layer_cache.clear()

    def refresh_beatmaps(self):
        selected_osu_file = self.selected_osu_file
        self.infos = BeatmapParser.from_loaded_beatmaps(self.game.beatmaps)
        self.selection_play_armed = False
        self.selection_play_osu_file = None
        self._apply_filter()
        if selected_osu_file:
            index = self._find_index_by_osu_file(selected_osu_file)
            if index is not None:
                self._confirm_selection(index, play_preview=False, arm_play=False)
                return
        if self.items:
            self._confirm_selection(
                int(clamp(self.selected_index, 0, len(self.items) - 1)),
                play_preview=False,
                arm_play=False
            )

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.search_text:
                    self.search_text = ""
                    self.search_active = False
                    self._apply_filter()
                    self._center_selected_card()
                    return
                self._return_to_main_menu()
                return
            if self.pending_play_info is not None:
                return
            if event.key == pygame.K_f and pygame.key.get_mods() & pygame.KMOD_CTRL:
                self.search_active = True
                return

            if self.search_active:
                if event.key == pygame.K_BACKSPACE:
                    self.search_text = self.search_text[:-1]
                    self._apply_filter()
                    return
                if event.key == pygame.K_RETURN:
                    self._play_selected()
                    return
                if event.key == pygame.K_TAB:
                    self._cycle_sort()
                    return
                if (
                    event.unicode
                    and event.unicode.isprintable()
                    and event.unicode not in "\r\n\t"
                ):
                    self.search_text += event.unicode
                    self._apply_filter()
                    return
                if event.key == pygame.K_DOWN:
                    self._move_browse(1)
                    return
                if event.key == pygame.K_UP:
                    self._move_browse(-1)
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
            if event.key == pygame.K_TAB:
                self._cycle_sort()
                return
            if event.unicode and (self.search_active or event.unicode.strip()):
                if event.unicode.isprintable() and event.unicode not in "\r\n\t":
                    self.search_active = True
                    self.search_text += event.unicode
                    self._apply_filter()
                return

        if self.pending_play_info is not None and event.type != pygame.MOUSEBUTTONDOWN:
            return

        if event.type == pygame.MOUSEWHEEL:
            self._move_browse(-event.y)
            return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.drag_scroll_active = False
            return

        if event.type == pygame.MOUSEMOTION and self.drag_scroll_active:
            if not self.items:
                return
            delta_y = event.pos[1] - self.drag_scroll_start_y
            target = self.drag_scroll_start_index - int(round(delta_y / max(1, self.card_spacing)))
            self.browse_index = int(clamp(target, 0, len(self.items) - 1))
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            if event.button == 1 and self.delete_prompt_rect is not None:
                if self.delete_prompt_rect.collidepoint(event.pos) and self.pending_delete_record:
                    osu_file, record_index = self.pending_delete_record
                    if self.score_manager.delete_record(osu_file, record_index):
                        self.score_manager.load()
                        self.panel_surface_cache.clear()
                    self.pending_delete_record = None
                    self.pending_delete_beatmap = None
                    self.delete_prompt_rect = None
                    return
                if self.delete_prompt_rect.collidepoint(event.pos) and self.pending_delete_beatmap:
                    self._delete_selected_beatmap_folder(self.pending_delete_beatmap)
                    self.pending_delete_record = None
                    self.pending_delete_beatmap = None
                    self.delete_prompt_rect = None
                    return
                self.pending_delete_record = None
                self.pending_delete_beatmap = None
                self.delete_prompt_rect = None
            if self.back_button_rect.collidepoint(event.pos):
                self._return_to_main_menu()
                return
            if self.pending_play_info is not None:
                return
            for record_index, record_rect, record in list(self.rank_record_rects):
                if record_rect.collidepoint(event.pos) and self.items:
                    current_info = self._current_info()
                    if current_info is None:
                        return
                    osu_file = current_info.osu_file
                    if event.button == 3:
                        self.pending_delete_record = (osu_file, record_index)
                        self.delete_prompt_rect = pygame.Rect(
                            event.pos[0],
                            event.pos[1],
                            118,
                            38
                        )
                        return
                    from scenes.result_scene import ResultScene
                    self.game.scene_manager.push_scene(
                        ResultScene(
                            self.game,
                            current_info.difficulty_data,
                            record,
                            save_record=False
                        )
                    )
                    return
            if event.button == 3:
                clicked = self._card_index_at(event.pos)
                if clicked is not None:
                    self.pending_delete_record = None
                    self.pending_delete_beatmap = self._beatmap_delete_payload(
                        self.items[clicked]
                    )
                    self.delete_prompt_rect = pygame.Rect(
                        event.pos[0],
                        event.pos[1],
                        316,
                        38
                    )
                    return
            if event.button != 1:
                return
            if self._handle_search_click(event.pos):
                return
            clicked = self._card_index_at(event.pos)
            if clicked is not None:
                item = self.items[clicked]
                if item["type"] == "group" and item["count"] > 1:
                    if item["group"] in self.expanded_groups:
                        return
                    self._confirm_selection(clicked, play_preview=True, arm_play=True)
                elif clicked == self.selected_index:
                    current_info = item.get("info")
                    current_osu_file = (
                        str(current_info.osu_file)
                        if current_info is not None
                        else None
                    )
                    if (
                        self.selection_play_armed
                        and self.selection_play_osu_file == current_osu_file
                    ):
                        self._play_selected()
                    else:
                        self._confirm_selection(clicked, play_preview=True, arm_play=True)
                else:
                    self._confirm_selection(clicked, play_preview=True, arm_play=True)
                return
            self.drag_scroll_active = True
            self.drag_scroll_start_y = event.pos[1]
            self.drag_scroll_start_index = self.browse_index

    def _cancel_pending_play(self):
        if self.pending_play_info is None:
            return
        self.pending_play_info = None
        self.pending_play_elapsed = 0.0
        self.selection_play_armed = False
        self.selection_play_osu_file = None
        try:
            pygame.mixer.music.set_volume(self.preview_volume)
        except pygame.error:
            pass

    def _return_to_main_menu(self):
        self._cancel_pending_play()
        self.drag_scroll_active = False
        self.pending_delete_record = None
        self.pending_delete_beatmap = None
        self.delete_prompt_rect = None
        manager = self.game.scene_manager
        if len(getattr(manager, "scene_stack", [])) > 1:
            manager.pop_scene()
            return

        from scenes.main_menu_scene import MainMenuScene

        manager.set_scene(MainMenuScene(self.game))

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
                self.current_preview_path = None
                self.game.scene_manager.push_scene_factory(
                    lambda info=info: GameplayScene(self.game, info.difficulty_data)
                )
                return

        self._replay_preview_if_finished()

        if not self.items:
            return

        if self.drag_scroll_active:
            if not pygame.mouse.get_pressed(3)[0]:
                self.drag_scroll_active = False
            else:
                delta_y = self.game.mouse_pos[1] - self.drag_scroll_start_y
                target = self.drag_scroll_start_index - int(
                    round(delta_y / max(1, self.card_spacing))
                )
                self.browse_index = int(clamp(target, 0, len(self.items) - 1))

        self.selected_index = max(0, min(self.selected_index, len(self.items) - 1))
        self.browse_index = max(0, min(self.browse_index, len(self.items) - 1))
        selected = self._current_info()
        if self.background_load_delay > 0.0:
            self.background_load_delay = max(
                0.0,
                self.background_load_delay - dt
            )
        elif selected is not None:
            self._ensure_background(selected)
        self.background_t = min(1.0, self.background_t + dt * 3.0)
        back_hover = 1.0 if self.back_button_rect.collidepoint(self.game.mouse_pos) else 0.0
        self.back_hover_t = lerp(
            getattr(self, "back_hover_t", 0.0),
            back_hover,
            1.0 - math.exp(-dt * 16.0)
        )

        visible = self._visible_infos()
        self.visible_items = visible
        self.carousel.trim(visible)
        mouse_pos = self.game.mouse_pos
        self._handle_mouse_center_crossing(mouse_pos)
        for key, index, info in visible:
            target = self._target_for_index(index)
            card = self.carousel.card_for(key, info, target)
            card.update(dt, target, mouse_pos)

    def render(self, screen):
        self._draw_background(screen)
        self._draw_cards(screen)
        self._draw_top_band(screen)
        self._draw_search_bar(screen)
        self._draw_info_panel(screen)
        self._draw_rank_panel(screen)
        self._draw_bottom_bar(screen)
        self._draw_delete_prompt(screen)

    def destroy(self):
        pass

    def _move_browse(self, amount):
        if not self.items:
            return
        self.browse_index = int(clamp(self.browse_index + amount, 0, len(self.items) - 1))

    def _confirm_selection(self, index, play_preview=False, arm_play=False):
        if not self.items:
            return
        self._cancel_pending_play()
        index = int(clamp(index, 0, len(self.items) - 1))
        item = self.items[index]

        if item["type"] == "group" and item["count"] > 1:
            group = item["group"]
            self.expanded_groups = {group}
            self._rebuild_items()
            difficulty_index = self._first_difficulty_index_for_group(group)
            self.selected_index = (
                difficulty_index
                if difficulty_index is not None
                else min(index, len(self.items) - 1)
            )
            self.browse_index = self.selected_index
            info = self.items[self.selected_index]["info"]
            self._remember_selected_info(info)
            self.selection_play_armed = bool(arm_play)
            self.selection_play_osu_file = (
                str(info.osu_file)
                if self.selection_play_armed
                else None
            )
            self.background_load_delay = 0.04
            self._ensure_background(info)
            if play_preview:
                self._start_preview_music(info)
            return

        self.selected_index = index
        info = self.items[self.selected_index]["info"]
        self.expanded_groups = (
            {info.folder_path}
            if self._difficulty_count_for_group(info.folder_path) > 1
            else set()
        )
        self._rebuild_items()
        selected_index = self._find_index_by_osu_file(info.osu_file)
        self.selected_index = (
            selected_index
            if selected_index is not None
            else int(clamp(index, 0, max(0, len(self.items) - 1)))
        )
        self._remember_selected_info(info)
        selected_osu_file = str(info.osu_file)
        self.selection_play_armed = bool(arm_play)
        self.selection_play_osu_file = (
            selected_osu_file
            if self.selection_play_armed
            else None
        )
        self.browse_index = self.selected_index
        self.background_load_delay = 0.04
        self._ensure_background(info)
        if play_preview:
            self._start_preview_music(info)

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
            self._publish_preview_music(info, self.current_preview_path)
            return
        normalized = str(Path(music_path))
        if self.current_preview_path == normalized and pygame.mixer.music.get_busy():
            self._publish_preview_music(info, normalized)
            return
        try:
            pygame.mixer.music.load(music_path)
            mark_music_loaded(music_path)
            pygame.mixer.music.set_volume(self.preview_volume)
            pygame.mixer.music.play()
            self.current_preview_path = normalized
            self._publish_preview_music(info, normalized)
        except pygame.error:
            pass

    def _publish_preview_music(self, info, path):
        self.game.current_menu_music_path = str(path) if path else None
        self.game.current_menu_music_title = self._display_title_for_info(info)
        self.game.current_menu_music_timing_points = (
            info.difficulty_data.get("timing_points", [])
        )
        self.game.current_menu_music_paused = False

    def _display_title_for_info(self, info):
        artist = info.artist.strip()
        title = info.title.strip()
        if artist and title:
            return f"{artist} - {title}"
        return title or artist or "Menu music"

    def _replay_preview_if_finished(self):
        if (
            self.pending_play_info is not None
            or not self.current_preview_path
            or pygame.mixer.music.get_busy()
            or getattr(self.game.scene_manager, "pending_factory", None) is not None
        ):
            return

        try:
            pygame.mixer.music.load(self.current_preview_path)
            mark_music_loaded(self.current_preview_path)
            pygame.mixer.music.set_volume(self.preview_volume)
            pygame.mixer.music.play()
        except pygame.error:
            pass

    def _index_for_music_path(self, music_path):
        if not music_path or not self.items:
            return 0
        try:
            target = Path(music_path).resolve()
        except (OSError, RuntimeError):
            target = Path(music_path)

        matched_info = None
        for info in self.infos:
            candidate = find_audio_file(
                info.folder_path,
                info.difficulty_data.get("audio_filename")
            )
            if not candidate:
                continue
            try:
                candidate_path = Path(candidate).resolve()
            except (OSError, RuntimeError):
                candidate_path = Path(candidate)
            if candidate_path == target:
                matched_info = info
                break

        if matched_info is not None:
            self.expanded_groups = {matched_info.folder_path}
            self._rebuild_items()
            index = self._find_index_by_osu_file(matched_info.osu_file)
            if index is not None:
                return index

        for index, item in enumerate(self.items):
            info = item["info"]
            candidate = find_audio_file(
                info.folder_path,
                info.difficulty_data.get("audio_filename")
            )
            if not candidate:
                continue
            try:
                candidate_path = Path(candidate).resolve()
            except (OSError, RuntimeError):
                candidate_path = Path(candidate)
            if candidate_path == target:
                if item["type"] == "group" and item["count"] > 1:
                    self.expanded_groups = {item["group"]}
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
            self.expanded_groups = {item["group"]}
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
        if pos[1] < self._top_band_height():
            return None
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
        selected_osu_file = self.selected_osu_file
        if self.selected_info is not None:
            self.expanded_groups = (
                {self.selected_info.folder_path}
                if self._difficulty_count_for_group(self.selected_info.folder_path, self.filtered) > 1
                else set()
            )
        else:
            self.expanded_groups = set()
        self._rebuild_items()
        selected_index = self._find_index_by_osu_file(selected_osu_file)
        if selected_index is not None:
            self.selected_index = selected_index
            self.browse_index = selected_index
        else:
            self.selected_index = int(clamp(self.selected_index, 0, max(0, len(self.items) - 1)))
        self.browse_index = int(clamp(self.browse_index, 0, max(0, len(self.items) - 1)))

    def _difficulty_count_for_group(self, group, infos=None):
        if not group:
            return 0
        source = self.infos if infos is None else infos
        return sum(1 for info in source if info.folder_path == group)

    def _center_selected_card(self):
        if not self.items:
            return
        if self.selected_info is not None:
            self.expanded_groups = (
                {self.selected_info.folder_path}
                if self._difficulty_count_for_group(self.selected_info.folder_path, self.filtered) > 1
                else set()
            )
            self._rebuild_items()
        selected_index = self._find_index_by_osu_file(self.selected_osu_file)
        if selected_index is None:
            selected_index = int(clamp(self.selected_index, 0, len(self.items) - 1))
        self.selected_index = selected_index
        self.browse_index = selected_index

    def _handle_mouse_center_crossing(self, mouse_pos):
        previous_x = self.last_mouse_x
        self.last_mouse_x = mouse_pos[0]
        if previous_x is None or self.drag_scroll_active or self.pending_play_info is not None:
            return
        midpoint = self.game.WIDTH * 0.5
        if previous_x >= midpoint and mouse_pos[0] < midpoint:
            self._center_selected_card()

    def _beatmap_delete_payload(self, item):
        info = item.get("info")
        folder = item.get("group") or (info.folder_path if info is not None else None)
        title = "Beatmap"
        if info is not None:
            title = f"{info.artist} - {info.title}".strip(" -") or info.title or "Beatmap"
        return {
            "folder": str(folder) if folder else "",
            "title": title
        }

    def _delete_selected_beatmap_folder(self, payload):
        folder = payload.get("folder") if payload else None
        if not folder:
            return False
        target = Path(folder)
        try:
            resolved = target.resolve()
        except (OSError, RuntimeError):
            return False
        if not self._is_safe_song_folder(resolved):
            return False
        old_selected = self.selected_osu_file
        selected_was_deleted = self._path_string_inside_folder(
            old_selected,
            resolved
        )
        preview_was_deleted = self._path_string_inside_folder(
            self.current_preview_path,
            resolved
        )
        menu_music_was_deleted = self._path_string_inside_folder(
            getattr(self.game, "current_menu_music_path", None),
            resolved
        )
        if preview_was_deleted or menu_music_was_deleted:
            try:
                pygame.mixer.music.stop()
                if hasattr(pygame.mixer.music, "unload"):
                    pygame.mixer.music.unload()
            except pygame.error:
                pass
            self.current_preview_path = None
            self.game.current_menu_music_path = None
            self.game.current_menu_music_title = None
            self.game.current_menu_music_timing_points = []
        try:
            shutil.rmtree(resolved)
        except OSError:
            return False

        self.score_manager.delete_records_under(resolved)
        self.game.beatmaps = self.game.beatmap_loader.load_songs()
        self.infos = BeatmapParser.from_loaded_beatmaps(self.game.beatmaps)
        self.score_manager.load()
        self.card_layer_cache.clear()
        self.card_image_cache.clear()
        self.panel_surface_cache.clear()
        self.text_cache.clear()
        self.carousel.cards.clear()
        self.expanded_groups = set()
        self.filtered = list(self.infos)
        if selected_was_deleted:
            self.selected_info = None
            self.selected_osu_file = None
            self.selection_play_armed = False
            self.selection_play_osu_file = None
        self._apply_filter()
        if self._find_index_by_osu_file(old_selected) is None:
            self.selected_info = None
            self.selected_osu_file = None
            self.selection_play_armed = False
            self.selection_play_osu_file = None
            if self.items:
                self._confirm_selection(0, play_preview=True, arm_play=True)
            else:
                self.selected_index = 0
                self.browse_index = 0
                self.background_cache.clear()
                self.current_background = None
                self.previous_background = None
                self.current_background_key = None
        else:
            index = self._find_index_by_osu_file(old_selected)
            if index is not None:
                self._confirm_selection(index, play_preview=False, arm_play=True)
        return True

    def _path_string_inside_folder(self, path_value, folder):
        if not path_value:
            return False
        try:
            path = Path(path_value).resolve()
        except (OSError, RuntimeError):
            return False
        try:
            return path.is_relative_to(folder)
        except AttributeError:
            try:
                path.relative_to(folder)
                return True
            except ValueError:
                return False

    def _is_safe_song_folder(self, resolved):
        if not resolved.exists() or not resolved.is_dir():
            return False
        for root in discover_user_data_directories("songs"):
            try:
                root_path = Path(root).resolve()
            except (OSError, RuntimeError):
                continue
            if resolved == root_path:
                return False
            try:
                if resolved.is_relative_to(root_path):
                    return True
            except AttributeError:
                try:
                    resolved.relative_to(root_path)
                    return True
                except ValueError:
                    pass
        return False

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
            representative = difficulties[0]
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
        self.visible_items = []

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
        if self.items[index]["type"] == "difficulty":
            x += int(self.card_width * 0.075)
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
        if self.background_load_delay > 0.0:
            return

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
        scaled = pygame.transform.scale(image, scaled_size)
        result = pygame.Surface(target_size).convert()
        result.blit(scaled, ((target_w - scaled_size[0]) // 2, (target_h - scaled_size[1]) // 2))
        return result

    def _draw_search_bar(self, screen):
        rect = self._search_rect()
        text_value = f"Search: {self.search_text or 'Type to search!'}"
        cache_key = ("search", rect.size, text_value, id(self.small_font))
        surface = self.panel_surface_cache.get(cache_key)
        if surface is None:
            surface = pygame.Surface(rect.size, pygame.SRCALPHA).convert_alpha()
            local_rect = surface.get_rect()
            pygame.draw.rect(surface, (9, 12, 22, 225), local_rect, border_radius=7)
            pygame.draw.rect(surface, (96, 138, 255, 210), local_rect, 2, border_radius=7)
            text = self._text_surface(
                self.small_font,
                text_value,
                (235, 238, 255)
            )
            surface.blit(
                text,
                (16, local_rect.centery - text.get_height() // 2)
            )
            self._cache_panel_surface(cache_key, surface)
        screen.blit(surface, rect)

    def _top_band_height(self):
        return int(clamp(self.game.HEIGHT * 0.24, 160, 210))

    def _draw_top_band(self, screen):
        height = self._top_band_height()
        cache_key = ("top_band", self.game.WIDTH, height)
        surface = self.panel_surface_cache.get(cache_key)
        if surface is None:
            if self.top_band_image is not None:
                surface = pygame.transform.smoothscale(
                    self.top_band_image,
                    (self.game.WIDTH, height)
                ).convert_alpha()
            else:
                surface = pygame.Surface(
                    (self.game.WIDTH, height),
                    pygame.SRCALPHA
                ).convert_alpha()
                surface.fill((5, 10, 18, 236))
                pygame.draw.line(
                    surface,
                    (190, 0, 255, 255),
                    (0, height - 54),
                    (self.game.WIDTH, max(18, height // 3)),
                    2
                )
            self._cache_panel_surface(cache_key, surface)
        screen.blit(surface, (0, 0))

    def _search_rect(self):
        width = int(clamp(self.game.WIDTH * 0.34, 360, 560))
        return pygame.Rect(
            self.game.WIDTH - width - 18,
            22,
            width,
            42
        )

    def _left_panel_width(self):
        card_left = self.card_center_x - int(self.card_width * 0.60)
        available = card_left - (self._info_panel_x() + self.margin)
        return int(clamp(available, 420, self.game.WIDTH * 0.52))

    def _info_panel_x(self):
        return max(4, int(self.margin * 0.62))

    def _info_panel_y(self):
        return max(4, 18 - int(self._top_band_height() * 0.055))

    def _info_panel_rect(self):
        return pygame.Rect(
            self._info_panel_x(),
            self._info_panel_y(),
            self._left_panel_width(),
            int(clamp(self.game.HEIGHT * 0.205, 146, 166))
        )

    def _rank_panel_rect(self):
        info_rect = self._info_panel_rect()
        bottom_limit = self.game.HEIGHT - self.bottom_bar_height - 18
        record_count = 0
        info = self._current_info()
        if info is not None:
            record_count = min(
                5,
                len(self.score_manager.records_for(info.osu_file))
            )
        height = (
            int(clamp(54 + max(1, record_count) * 42, 92, 258))
            if record_count
            else int(clamp(self.game.HEIGHT * 0.105, 84, 104))
        )
        y = min(info_rect.bottom + 24, bottom_limit - height)
        y = max(info_rect.bottom + 16, y)
        return pygame.Rect(
            self._info_panel_x(),
            y,
            min(info_rect.width, int(clamp(self.game.WIDTH * 0.34, 350, 520))),
            height
        )

    def _draw_info_panel(self, screen):
        if not self.items:
            self._draw_empty(screen)
            return
        info = self._current_info()
        if info is None:
            self._draw_empty(screen)
            return
        rect = self._info_panel_rect()
        title_text = f"{info.artist} - {info.title} [{info.version}]"
        cache_key = (
            "info",
            rect.size,
            str(info.osu_file),
            title_text,
            id(self.medium_font),
            id(self.small_font),
            id(self.tiny_font)
        )
        surface = self.panel_surface_cache.get(cache_key)
        if surface is None:
            surface = pygame.Surface(rect.size, pygame.SRCALPHA).convert_alpha()
            text_w = max(80, rect.width - 28)
            title = self._fit_text_surface(self.medium_font, title_text, (255, 255, 255), text_w)
            mapper = self._fit_text_surface(self.small_font, f"Mapped by {info.creator}", (230, 235, 245), text_w)
            stats1 = self._fit_text_surface(
                self.small_font,
                f"Length: {info.length_text}  BPM: {info.bpm_text}  Objects: {info.object_count}",
                (238, 238, 245),
                text_w
            )
            stats2 = self._fit_text_surface(
                self.small_font,
                f"Circles: {info.circle_count}  Sliders: {info.slider_count}  Spinners: {info.spinner_count}",
                (238, 238, 245),
                text_w
            )
            stats3 = self._fit_text_surface(
                self.tiny_font,
                f"CS:{info.cs:g} AR:{info.ar:g} OD:{info.od:g} HP:{info.hp:g}  Star Rating: {info.stars:.2f}",
                (225, 230, 245),
                text_w
            )
            for surf, yy in (
                (title, 12),
                (mapper, 43),
                (stats1, 72),
                (stats2, 98),
                (stats3, 124)
            ):
                surface.blit(surf, (14, yy))
            self._cache_panel_surface(cache_key, surface)
        screen.blit(surface, rect)

    def _draw_rank_panel(self, screen):
        rect = self._rank_panel_rect()
        self.rank_record_rects = []
        records = []
        info = self._current_info()
        if info is not None:
            records = self.score_manager.records_for(info.osu_file)
        visible_records = records[:5]
        record_key = tuple(
            (
                record.get("score"),
                record.get("accuracy"),
                record.get("combo"),
                record.get("rank"),
                record.get("created_at")
            )
            for record in visible_records
        )
        cache_key = ("rank", rect.size, record_key, id(self.small_font), id(self.tiny_font))
        surface = self.panel_surface_cache.get(cache_key)
        if surface is None:
            surface = pygame.Surface(rect.size, pygame.SRCALPHA).convert_alpha()
            local_rect = surface.get_rect()
            pygame.draw.rect(surface, (6, 8, 13, 218), local_rect, border_radius=8)
            header_rect = pygame.Rect(0, 0, rect.width, 38)
            pygame.draw.rect(surface, (15, 14, 24, 230), header_rect, border_radius=8)
            pygame.draw.line(surface, (255, 220, 65, 130), (0, 38), (rect.width, 38), 1)
            title = self._text_surface(self.small_font, "Local Ranking", (255, 245, 205))
            surface.blit(title, (14, 10))
            if not records:
                body_y = 38
                body_h = rect.height - body_y
                center_y = body_y + body_h // 2
                trophy = self._text_surface(self.medium_font, "T", (255, 255, 255))
                surface.blit(trophy, trophy.get_rect(midleft=(18, center_y)))
                text = self._text_surface(self.small_font, "No records set!", (92, 220, 220))
                surface.blit(text, text.get_rect(midleft=(58, center_y)))
            else:
                row_y = 48
                for index, record in enumerate(visible_records):
                    score = int(record.get("score", 0))
                    accuracy = float(record.get("accuracy", 0.0))
                    combo = int(record.get("combo", 0))
                    rank = str(record.get("rank", "D")).upper()
                    row_rect = pygame.Rect(12, row_y, rect.width - 24, 34)
                    row_color = (18, 22, 31, 220) if index == 0 else (12, 15, 22, 198)
                    pygame.draw.rect(surface, row_color, row_rect, border_radius=7)
                    pygame.draw.line(
                        surface,
                        (92, 220, 220, 78 if index == 0 else 42),
                        (row_rect.left + 8, row_rect.bottom - 1),
                        (row_rect.right - 8, row_rect.bottom - 1),
                        1
                    )
                    rank_image = self.rank_images.get(rank)
                    if rank_image is not None:
                        icon = pygame.transform.smoothscale(rank_image, (28, 28)).convert_alpha()
                        surface.blit(icon, (22, row_y + 3))
                    else:
                        rank_text = self._text_surface(self.small_font, rank, (255, 245, 205))
                        surface.blit(rank_text, rank_text.get_rect(center=(36, row_y + 17)))
                    text = self._fit_text_surface(
                        self.tiny_font,
                        f"Score: {score:,} ({combo}x)   {accuracy:05.2f}%",
                        (232, 236, 246),
                        rect.width - 78
                    )
                    surface.blit(text, (66, row_y + 9))
                    row_y += 40
            self._cache_panel_surface(cache_key, surface)
        screen.blit(surface, rect)
        if records:
            row_y = rect.y + 48
            for index, record in enumerate(visible_records):
                self.rank_record_rects.append((
                    index,
                    pygame.Rect(rect.x + 12, row_y, rect.width - 24, 34),
                    record
                ))
                row_y += 40

    def _draw_delete_prompt(self, screen):
        if (
            self.delete_prompt_rect is None
            or (
                self.pending_delete_record is None
                and self.pending_delete_beatmap is None
            )
        ):
            return

        rect = self.delete_prompt_rect.copy()
        rect.right = min(rect.right, self.game.WIDTH - 10)
        rect.bottom = min(rect.bottom, self.game.HEIGHT - self.bottom_bar_height - 8)
        self.delete_prompt_rect = rect
        pygame.draw.rect(screen, (18, 15, 24, 242), rect, border_radius=8)
        pygame.draw.rect(screen, (255, 82, 112, 230), rect, 2, border_radius=8)
        if self.pending_delete_beatmap is not None:
            title = self._fit_text_surface(
                self.tiny_font,
                "Are you sure you want to delete this beatmap?",
                (255, 238, 242),
                rect.width - 20
            )
            screen.blit(title, title.get_rect(center=rect.center))
        else:
            text = self._text_surface(self.small_font, "Delete?", (255, 238, 242))
            screen.blit(text, text.get_rect(center=rect.center))

    def _draw_cards(self, screen):
        if not self.items:
            return
        visible = self.visible_items if self.visible_items else self._visible_infos()
        visible.sort(key=lambda item: abs(item[1] - self.browse_index), reverse=True)
        for key, index, info in visible:
            self.carousel.card_for(key, info).draw(
                screen,
                self,
                selected=index == self.selected_index,
                meta=self.items[index]
            )

    def _draw_bottom_bar(self, screen):
        h = self.bottom_bar_height
        y = self.game.HEIGHT - h
        hover_bucket = int(round(self.back_hover_t * 10))
        cache_key = ("bottom", self.game.WIDTH, h, hover_bucket)
        surface = self.panel_surface_cache.get(cache_key)
        if surface is None:
            surface = pygame.Surface((self.game.WIDTH, h), pygame.SRCALPHA).convert_alpha()
            pygame.draw.rect(surface, (0, 0, 0, 255), surface.get_rect())
            pygame.draw.line(surface, (53, 112, 210, 190), (0, 0), (self.game.WIDTH, 0), 2)
            back = self.back_button_rect.move(0, -y)
            hover = hover_bucket / 10.0
            if self.back_button_image is not None:
                image = self.back_button_image
                if hover > 0.0:
                    image = image.copy()
                    boost = int(34 * hover)
                    image.fill((boost, boost, boost, 0), special_flags=pygame.BLEND_RGB_ADD)
                surface.blit(image, back)
            else:
                draw_rect = back.inflate(int(10 * hover), int(4 * hover))
                draw_rect.x = back.x
                draw_rect.bottom = back.bottom
                pygame.draw.rect(
                    surface,
                    (247, 98, 171, 255),
                    draw_rect,
                    border_radius=4
                )
                label = self._text_surface(self.medium_font, "back", (255, 255, 255))
                surface.blit(label, label.get_rect(center=draw_rect.center))
            self._cache_panel_surface(cache_key, surface)
        screen.blit(surface, (0, y))

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

    def _fit_text_surface(self, font, text, color, max_width):
        text = str(text)
        max_width = max(24, int(max_width))
        key = ("fit", id(font), text, tuple(color), max_width)
        cached = self.text_cache.get(key)
        if cached is not None:
            return cached

        surface = font.render(text, True, color)
        if surface.get_width() <= max_width:
            self.text_cache[key] = surface
            return surface

        ellipsis = "..."
        low = 0
        high = len(text)
        best = ellipsis
        while low <= high:
            mid = (low + high) // 2
            candidate = text[:mid].rstrip() + ellipsis
            candidate_surface = font.render(candidate, True, color)
            if candidate_surface.get_width() <= max_width:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1

        surface = font.render(best, True, color)
        if len(self.text_cache) > 192:
            self.text_cache.clear()
        self.text_cache[key] = surface
        return surface

    def _cache_panel_surface(self, key, surface):
        if len(self.panel_surface_cache) > 96:
            self.panel_surface_cache.clear()
        self.panel_surface_cache[key] = surface
