import os
from array import array
from typing import Optional

import pygame

from rendering.sprite_atlas import SpriteAtlasRegistry


def _blit_destination_rect(surface, dest, area=None):
    if surface is None:
        return pygame.Rect(0, 0, 0, 0)

    if area is not None:
        try:
            width, height = area.size
        except AttributeError:
            width, height = area[2], area[3]
    else:
        width, height = surface.get_size()

    if isinstance(dest, pygame.Rect):
        return pygame.Rect(dest.left, dest.top, width, height)

    return pygame.Rect(int(dest[0]), int(dest[1]), width, height)


def _surface_blit_visible(target, surface, dest, area=None):
    if target is None or surface is None:
        return False
    return target.get_rect().colliderect(
        _blit_destination_rect(surface, dest, area=area)
    )


class RenderCommandBatch:
    """Collects surface blit operations and flushes them to a target later."""

    __slots__ = (
        "_commands",
        "last_culled_count",
        "last_atlas_command_count",
        "last_atlas_group_count",
        "last_atlas_run_count",
        "last_batchable_command_count",
    )

    def __init__(self):
        self._commands = []
        self.last_culled_count = 0
        self.last_atlas_command_count = 0
        self.last_atlas_group_count = 0
        self.last_atlas_run_count = 0
        self.last_batchable_command_count = 0

    def add_surface(self, surface, dest, area=None, alpha=None, atlas_key=None):
        if surface is None:
            return
        if alpha is not None and int(alpha) <= 0:
            return
        self._commands.append((surface, dest, area, alpha, atlas_key))

    def clear(self):
        self._commands.clear()
        self.last_culled_count = 0
        self.last_atlas_command_count = 0
        self.last_atlas_group_count = 0
        self.last_atlas_run_count = 0
        self.last_batchable_command_count = 0

    def flush(self, target, before_blit=None):
        count = len(self._commands)
        if target is None or count <= 0:
            self.clear()
            return 0
        drawn = 0
        culled = 0
        atlas_commands = 0
        atlas_groups = set()
        atlas_runs = 0
        batchable_commands = 0
        previous_atlas_key = None
        for surface, dest, area, alpha, atlas_key in self._commands:
            if not _surface_blit_visible(target, surface, dest, area=area):
                culled += 1
                continue
            if before_blit is not None:
                before_blit(surface, atlas_key)
            if atlas_key is not None:
                atlas_commands += 1
                atlas_groups.add(atlas_key)
                if atlas_key != previous_atlas_key:
                    atlas_runs += 1
                previous_atlas_key = atlas_key
                if area is None and (alpha is None or int(alpha) >= 255):
                    batchable_commands += 1
            else:
                previous_atlas_key = None
            blit_surface_with_alpha(target, surface, dest, area=area, alpha=alpha)
            drawn += 1
        self._commands.clear()
        self.last_culled_count = culled
        self.last_atlas_command_count = atlas_commands
        self.last_atlas_group_count = len(atlas_groups)
        self.last_atlas_run_count = atlas_runs
        self.last_batchable_command_count = batchable_commands
        return drawn

    def __len__(self):
        return len(self._commands)


def blit_surface_with_alpha(target, surface, dest, area=None, alpha=None):
    if target is None or surface is None:
        return
    if alpha is None or alpha >= 255:
        target.blit(surface, dest, area=area)
        return
    alpha = max(0, min(255, int(alpha)))
    if alpha <= 0:
        return

    previous_alpha = surface.get_alpha()
    if previous_alpha != alpha:
        surface.set_alpha(alpha)
    target.blit(surface, dest, area=area)
    if previous_alpha != alpha:
        surface.set_alpha(previous_alpha)


def _surface_to_rgba_bytes(surface):
    converter = getattr(pygame.image, "tobytes", pygame.image.tostring)
    return converter(surface, "RGBA", False)


class GPUTextureCache:
    """Small ModernGL texture cache for static/cached pygame surfaces.

    The cache is intentionally independent from gameplay logic. Atlas pages
    provide a version number so mutable CPU atlases can be re-uploaded exactly
    once after they receive new sprites.
    """

    def __init__(self, ctx, moderngl_module=None, max_textures=384):
        self.ctx = ctx
        self.moderngl = moderngl_module
        self.max_textures = max(16, int(max_textures))
        self._textures = {}
        self.last_upload_count = 0
        self.total_upload_count = 0
        self.eviction_count = 0

    def reset_frame_metrics(self):
        self.last_upload_count = 0

    def clear(self):
        for texture, _stamp in self._textures.values():
            self._release_texture(texture)
        self._textures.clear()

    def _release_texture(self, texture):
        releaser = getattr(texture, "release", None)
        if callable(releaser):
            try:
                releaser()
            except Exception:
                pass

    def _stamp_for(self, surface, version):
        size = surface.get_size()
        if version is None:
            return (size[0], size[1], id(surface))
        return (size[0], size[1], int(version))

    def get_surface_texture(self, surface, key=None, version=None):
        if self.ctx is None or surface is None:
            return None

        cache_key = key if key is not None else ("surface", id(surface))
        stamp = self._stamp_for(surface, version)
        cached = self._textures.get(cache_key)
        if cached is not None and cached[1] == stamp:
            return cached[0]

        if cached is not None:
            self._release_texture(cached[0])

        width, height = surface.get_size()
        try:
            data = _surface_to_rgba_bytes(surface)
            texture = self.ctx.texture((width, height), 4, data)
            if self.moderngl is not None:
                try:
                    texture.filter = (
                        self.moderngl.LINEAR,
                        self.moderngl.LINEAR,
                    )
                except Exception:
                    pass
        except Exception:
            return None

        self._textures[cache_key] = (texture, stamp)
        self.last_upload_count += 1
        self.total_upload_count += 1
        self._prune_if_needed()
        return texture

    def _prune_if_needed(self):
        overflow = len(self._textures) - self.max_textures
        if overflow <= 0:
            return

        for key in list(self._textures.keys())[:overflow]:
            texture, _stamp = self._textures.pop(key)
            self._release_texture(texture)
            self.eviction_count += 1


class ModernGLSpriteRenderer:
    """Diagnostic sprite batch renderer for atlas/GPU rollout.

    This path is opt-in through PYOSU_ENABLE_GPU_SPRITES=1. It preserves draw
    order by batching only contiguous commands sharing the same texture.
    """

    def __init__(self, ctx, moderngl_module):
        self.ctx = ctx
        self.moderngl = moderngl_module
        self.texture_cache = GPUTextureCache(
            ctx,
            moderngl_module=moderngl_module,
            max_textures=int(os.environ.get("PYOSU_GPU_TEXTURE_CACHE", "384")),
        )
        self._program = None
        self._vbo = None
        self._vao = None
        self._buffer_capacity = 0
        self._build_pipeline()

    def _build_pipeline(self):
        vertex_shader = """
        #version 330
        in vec2 in_position;
        in vec2 in_uv;
        in float in_alpha;
        out vec2 uv;
        out float vertex_alpha;
        void main() {
            uv = in_uv;
            vertex_alpha = in_alpha;
            gl_Position = vec4(in_position, 0.0, 1.0);
        }
        """
        fragment_shader = """
        #version 330
        uniform sampler2D sampler;
        in vec2 uv;
        in float vertex_alpha;
        out vec4 f_color;
        void main() {
            vec4 color = texture(sampler, uv);
            color.a *= vertex_alpha;
            f_color = color;
        }
        """
        self._program = self.ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=fragment_shader,
        )
        self._vbo = self.ctx.buffer(reserve=16 * 1024)
        self._buffer_capacity = self._vbo.size
        self._vao = self.ctx.simple_vertex_array(
            self._program,
            self._vbo,
            "in_position",
            "in_uv",
            "in_alpha",
        )
        try:
            self.ctx.enable(self.moderngl.BLEND)
            self.ctx.blend_func = (
                self.moderngl.SRC_ALPHA,
                self.moderngl.ONE_MINUS_SRC_ALPHA,
            )
        except Exception:
            pass

    def reset_frame_metrics(self):
        self.texture_cache.reset_frame_metrics()

    def flush_batch(self, backend, batch):
        target = backend.target_surface
        if target is None or batch is None or len(batch) <= 0:
            if batch is not None:
                batch.clear()
            return 0

        commands = batch._commands
        screen_w, screen_h = target.get_size()
        try:
            self.ctx.viewport = (0, 0, screen_w, screen_h)
        except Exception:
            pass
        drawn = 0
        culled = 0
        atlas_commands = 0
        atlas_groups = set()
        atlas_runs = 0
        batchable_commands = 0
        previous_atlas_key = None
        current_texture_key = None
        current_texture = None
        vertices = []
        gpu_flushes = 0

        backend._frame_surface_tokens.clear()

        def flush_vertices():
            nonlocal vertices, current_texture, gpu_flushes
            if current_texture is None or not vertices:
                vertices = []
                return True
            try:
                payload = array("f", vertices).tobytes()
                if len(payload) > self._buffer_capacity:
                    self._vbo.orphan(len(payload))
                    self._buffer_capacity = max(self._buffer_capacity, len(payload))
                self._vbo.write(payload)
                current_texture.use(location=0)
                try:
                    self._program["sampler"].value = 0
                except Exception:
                    pass
                self._vao.render(
                    mode=self.ctx.TRIANGLES,
                    vertices=len(vertices) // 5,
                )
                gpu_flushes += 1
                vertices = []
                return True
            except Exception:
                return False

        for surface, dest, area, alpha, atlas_key in commands:
            if not _surface_blit_visible(target, surface, dest, area=area):
                culled += 1
                continue

            token = backend._register_surface(surface)
            if token:
                backend._frame_surface_tokens.add(token)

            texture_info = self._texture_info_for_command(
                backend,
                surface,
                area,
                atlas_key,
            )
            if texture_info is None:
                return None
            texture, texture_key, source_rect, texture_size = texture_info

            if atlas_key is not None:
                atlas_commands += 1
                atlas_groups.add(atlas_key)
                if atlas_key != previous_atlas_key:
                    atlas_runs += 1
                previous_atlas_key = atlas_key
                batchable_commands += 1
            else:
                previous_atlas_key = None

            if texture_key != current_texture_key:
                if not flush_vertices():
                    return None
                current_texture_key = texture_key
                current_texture = texture

            dest_rect = _blit_destination_rect(surface, dest, area=area)
            alpha_value = 1.0 if alpha is None else max(
                0.0,
                min(1.0, float(alpha) / 255.0)
            )
            self._append_quad(
                vertices,
                screen_w,
                screen_h,
                dest_rect,
                source_rect,
                texture_size,
                alpha_value,
            )
            drawn += 1

        if not flush_vertices():
            return None

        batch._commands.clear()
        batch.last_culled_count = culled
        batch.last_atlas_command_count = atlas_commands
        batch.last_atlas_group_count = len(atlas_groups)
        batch.last_atlas_run_count = atlas_runs
        batch.last_batchable_command_count = batchable_commands
        backend.last_gpu_sprite_count = drawn
        backend.last_gpu_flush_count = gpu_flushes
        backend.last_gpu_texture_upload_count = (
            self.texture_cache.last_upload_count
        )
        backend.last_gpu_fallback_count = 0
        return drawn

    def _texture_info_for_command(self, backend, surface, area, atlas_key):
        if atlas_key is not None:
            ref = backend.register_sprite_surface(surface, key=atlas_key)
            if ref is None:
                return None
            try:
                page = backend.sprite_atlas.pages[ref.page_index]
            except (IndexError, AttributeError):
                return None

            texture_key = ("atlas", ref.page_index)
            texture = self.texture_cache.get_surface_texture(
                page.surface,
                key=texture_key,
                version=getattr(page, "version", 0),
            )
            if texture is None:
                return None

            source_rect = pygame.Rect(ref.rect)
            if area is not None:
                area_rect = pygame.Rect(area)
                source_rect = pygame.Rect(
                    ref.rect.left + area_rect.left,
                    ref.rect.top + area_rect.top,
                    area_rect.width,
                    area_rect.height,
                )
            return texture, texture_key, source_rect, page.surface.get_size()

        texture_key = ("surface", id(surface))
        texture = self.texture_cache.get_surface_texture(
            surface,
            key=texture_key,
        )
        if texture is None:
            return None

        if area is not None:
            source_rect = pygame.Rect(area)
        else:
            source_rect = pygame.Rect((0, 0), surface.get_size())
        return texture, texture_key, source_rect, surface.get_size()

    def _append_quad(
        self,
        vertices,
        screen_w,
        screen_h,
        dest_rect,
        source_rect,
        texture_size,
        alpha,
    ):
        x0 = (dest_rect.left / screen_w) * 2.0 - 1.0
        y0 = 1.0 - (dest_rect.top / screen_h) * 2.0
        x1 = (dest_rect.right / screen_w) * 2.0 - 1.0
        y1 = 1.0 - (dest_rect.bottom / screen_h) * 2.0

        texture_w, texture_h = texture_size
        u0 = source_rect.left / texture_w
        v0 = source_rect.top / texture_h
        u1 = source_rect.right / texture_w
        v1 = source_rect.bottom / texture_h

        vertices.extend((
            x0, y0, u0, v0, alpha,
            x1, y0, u1, v0, alpha,
            x0, y1, u0, v1, alpha,
            x1, y0, u1, v0, alpha,
            x1, y1, u1, v1, alpha,
            x0, y1, u0, v1, alpha,
        ))


class RenderBackend:
    """Small rendering abstraction that keeps the gameplay code backend-agnostic."""

    name = "pygame"
    gpu_available = False

    def __init__(self, target_surface: Optional[pygame.Surface] = None):
        self.target_surface = target_surface
        self._batch = RenderCommandBatch()
        self._surface_tokens = {}
        self._frame_surface_tokens = set()
        self._next_surface_token = 1
        self.surface_registry_limit = 4096
        self.registered_surface_count = 0
        self.last_flush_count = 0
        self.last_unique_surface_count = 0
        self.last_culled_count = 0
        self.last_direct_culled_count = 0
        self.sprite_atlas = SpriteAtlasRegistry()
        self.last_atlas_pages = 0
        self.last_atlas_sprites = 0
        self.last_atlas_evictions = 0
        self.last_atlas_command_count = 0
        self.last_atlas_group_count = 0
        self.last_atlas_run_count = 0
        self.last_batchable_command_count = 0
        self.last_gpu_sprite_count = 0
        self.last_gpu_flush_count = 0
        self.last_gpu_texture_upload_count = 0
        self.last_gpu_fallback_count = 0

    def set_target_surface(self, target_surface: Optional[pygame.Surface]):
        self.target_surface = target_surface
        self._batch.clear()
        self.begin_frame()

    def begin_frame(self):
        self._frame_surface_tokens.clear()
        self.last_flush_count = 0
        self.last_unique_surface_count = 0
        self.last_culled_count = 0
        self.last_direct_culled_count = 0
        self.last_atlas_command_count = 0
        self.last_atlas_group_count = 0
        self.last_atlas_run_count = 0
        self.last_batchable_command_count = 0
        self.last_gpu_sprite_count = 0
        self.last_gpu_flush_count = 0
        self.last_gpu_texture_upload_count = 0
        self.last_gpu_fallback_count = 0
        self._update_atlas_metrics()

    def clear(self, color=(0, 0, 0, 0)):
        if self.target_surface is None:
            return
        self.target_surface.fill(color)

    def _register_surface(self, surface):
        if surface is None:
            return 0
        key = id(surface)
        size = surface.get_size()
        cached = self._surface_tokens.get(key)
        if cached is not None and cached[1] == size:
            return cached[0]

        if len(self._surface_tokens) >= self.surface_registry_limit:
            self._surface_tokens.clear()
            self._next_surface_token = 1

        token = self._next_surface_token
        self._next_surface_token += 1
        self._surface_tokens[key] = (token, size)
        self.registered_surface_count = len(self._surface_tokens)
        return token

    def register_sprite_surface(self, surface, key=None):
        ref = self.sprite_atlas.add(surface, key=key)
        self._update_atlas_metrics()
        return ref

    def _update_atlas_metrics(self):
        self.last_atlas_pages = self.sprite_atlas.page_count
        self.last_atlas_sprites = self.sprite_atlas.sprite_count
        self.last_atlas_evictions = self.sprite_atlas.eviction_count

    def blit_surface(self, surface, dest, area=None, alpha=None, atlas_key=None):
        if not _surface_blit_visible(self.target_surface, surface, dest, area=area):
            self.last_direct_culled_count += 1
            self.last_culled_count += 1
            return
        self._register_surface(surface)
        if atlas_key is not None:
            self.register_sprite_surface(surface, key=atlas_key)
            self.last_atlas_command_count += 1
            self.last_atlas_group_count = max(1, self.last_atlas_group_count)
            self.last_atlas_run_count += 1
            if area is None and (alpha is None or int(alpha) >= 255):
                self.last_batchable_command_count += 1
        blit_surface_with_alpha(
            self.target_surface,
            surface,
            dest,
            area=area,
            alpha=alpha
        )

    def create_batch(self):
        self._batch.clear()
        return self._batch

    def flush_batch(self, batch):
        if batch is None:
            self.last_flush_count = 0
            self.last_unique_surface_count = 0
            self.last_culled_count = 0
            self.last_direct_culled_count = 0
            self.last_atlas_command_count = 0
            self.last_atlas_group_count = 0
            self.last_atlas_run_count = 0
            self.last_batchable_command_count = 0
            self.last_gpu_sprite_count = 0
            self.last_gpu_flush_count = 0
            self.last_gpu_texture_upload_count = 0
            self.last_gpu_fallback_count = 0
            return 0
        self._frame_surface_tokens.clear()

        def register(surface, atlas_key=None):
            token = self._register_surface(surface)
            if token:
                self._frame_surface_tokens.add(token)
            if atlas_key is not None:
                self.register_sprite_surface(surface, key=atlas_key)

        self.last_flush_count = batch.flush(
            self.target_surface,
            before_blit=register
        )
        self.last_unique_surface_count = len(self._frame_surface_tokens)
        self.last_culled_count += getattr(batch, "last_culled_count", 0)
        self.last_atlas_command_count = getattr(
            batch,
            "last_atlas_command_count",
            0
        )
        self.last_atlas_group_count = getattr(
            batch,
            "last_atlas_group_count",
            0
        )
        self.last_atlas_run_count = getattr(
            batch,
            "last_atlas_run_count",
            0
        )
        self.last_batchable_command_count = getattr(
            batch,
            "last_batchable_command_count",
            0
        )
        self._update_atlas_metrics()
        return self.last_flush_count

    def present(self):
        return None


class PygameRenderBackend(RenderBackend):
    name = "pygame"


class ModernGLRenderBackend(RenderBackend):
    name = "moderngl"

    def __init__(self, target_surface: Optional[pygame.Surface] = None):
        super().__init__(target_surface)
        self._enabled = False
        self._ctx = None
        self._program = None
        self._vao = None
        self._vbo = None
        self._textures = {}
        self._moderngl = None
        self._sprite_renderer = None
        self._gpu_sprite_enabled = False
        self._gpu_commands_submitted = False
        self._initialize()
        self._gpu_sprite_enabled = (
            self._enabled
            and self._ctx is not None
            and _gpu_sprites_enabled_by_default()
        )
        if self._gpu_sprite_enabled:
            try:
                self._sprite_renderer = ModernGLSpriteRenderer(
                    self._ctx,
                    self._moderngl
                )
            except Exception:
                self._sprite_renderer = None
                self._gpu_sprite_enabled = False

    def _initialize(self):
        if self.target_surface is None:
            return
        try:
            import moderngl  # type: ignore
        except ImportError:
            return

        try:
            self._ctx = moderngl.create_context(require=330)
        except Exception:
            self._ctx = None
            self._enabled = False
            return

        if self._ctx is None:
            return

        vertex_shader = """
        #version 330
        in vec2 in_position;
        in vec2 in_uv;
        out vec2 uv;
        void main() {
            uv = in_uv;
            gl_Position = vec4(in_position, 0.0, 1.0);
        }
        """

        fragment_shader = """
        #version 330
        uniform sampler2D sampler;
        in vec2 uv;
        out vec4 f_color;
        void main() {
            f_color = texture(sampler, uv);
        }
        """

        try:
            self._program = self._ctx.program(
                vertex_shader=vertex_shader,
                fragment_shader=fragment_shader,
            )
            # dynamic vbo will be created on demand; create an empty buffer reserve
            self._vbo = self._ctx.buffer(reserve=4 * 1024)
            # vao will be created per-draw or reused when possible
            self._vao = None
            self._enabled = True
            self.gpu_available = True
            self._textures = {}
            # keep module reference for enum/consts
            self._moderngl = moderngl
        except Exception:
            self._enabled = False
            self.gpu_available = False
            self._ctx = None

    def _pack_vertices(self):
        return [
            -1.0, -1.0, 0.0, 0.0,
            1.0, -1.0, 1.0, 0.0,
            -1.0, 1.0, 0.0, 1.0,
            1.0, 1.0, 1.0, 1.0,
        ]

    def _surface_to_texture(self, surface):
        if self._ctx is None or surface is None:
            return None
        key = id(surface)
        cached = self._textures.get(key)
        w, h = surface.get_size()
        if cached is not None:
            tex, tw, th = cached
            if tw == w and th == h:
                return tex

        try:
            # Extract raw RGBA data from pygame surface
            data = _surface_to_rgba_bytes(surface)
            tex = self._ctx.texture((w, h), 4, data)
            try:
                tex.filter = (self._moderngl.LINEAR, self._moderngl.LINEAR)
            except Exception:
                pass
            self._textures[key] = (tex, w, h)
            self.last_gpu_texture_upload_count += 1
            return tex
        except Exception:
            return None

    def blit_surface(self, surface, dest, area=None, alpha=None, atlas_key=None):
        if not self._enabled or self._ctx is None:
            return super().blit_surface(
                surface,
                dest,
                area=area,
                alpha=alpha,
                atlas_key=atlas_key
            )
        if area is not None or (alpha is not None and int(alpha) < 255):
            return super().blit_surface(
                surface,
                dest,
                area=area,
                alpha=alpha,
                atlas_key=atlas_key
            )

        # Try to draw via ModernGL. Fallback to pygame on any failure.
        try:
            if not _surface_blit_visible(
                self.target_surface,
                surface,
                dest,
                area=area
            ):
                self.last_direct_culled_count += 1
                self.last_culled_count += 1
                return
            self._register_surface(surface)
            if atlas_key is not None:
                self.register_sprite_surface(surface, key=atlas_key)
                self.last_atlas_command_count += 1
                self.last_atlas_group_count = max(1, self.last_atlas_group_count)
                self.last_atlas_run_count += 1
                if area is None and (alpha is None or int(alpha) >= 255):
                    self.last_batchable_command_count += 1

            screen_w, screen_h = self.target_surface.get_size()

            # resolve dest rect and size
            if isinstance(dest, pygame.Rect):
                x, y = dest.left, dest.top
            else:
                x, y = int(dest[0]), int(dest[1])

            # area cropping
            if area is not None:
                try:
                    ax, ay, aw, ah = area.x, area.y, area.width, area.height
                except Exception:
                    ax, ay, aw, ah = area[0], area[1], area[2], area[3]
                sub_surface = surface.subsurface((ax, ay, aw, ah)).copy()
                draw_w, draw_h = aw, ah
            else:
                sub_surface = surface
                draw_w, draw_h = surface.get_size()

            tex = self._surface_to_texture(sub_surface)
            if tex is None:
                return super().blit_surface(
                    surface,
                    dest,
                    area=area,
                    alpha=alpha,
                    atlas_key=atlas_key
                )

            # compute normalized device coordinates
            x0 = (x / screen_w) * 2.0 - 1.0
            y0 = 1.0 - (y / screen_h) * 2.0
            x1 = ((x + draw_w) / screen_w) * 2.0 - 1.0
            y1 = 1.0 - ((y + draw_h) / screen_h) * 2.0

            # UVs
            u0, v0 = 0.0, 0.0
            u1, v1 = 1.0, 1.0

            # vertex order for triangle strip: (x0,y0),(x1,y0),(x0,y1),(x1,y1)
            import struct
            verts = struct.pack(
                "ffffffff",
                x0, y0, u0, v0,
                x1, y0, u1, v0,
                x0, y1, u0, v1,
                x1, y1, u1, v1,
            )

            # update vbo and vao
            if len(verts) > self._vbo.size:
                self._vbo.orphan(len(verts))
            self._vbo.write(verts)
            self._vao = self._ctx.simple_vertex_array(
                self._program,
                self._vbo,
                "in_position",
                "in_uv",
            )

            tex.use(location=0)
            try:
                self._program["sampler"].value = 0
            except Exception:
                pass

            self._vao.render(mode=self._ctx.TRIANGLE_STRIP)
            self._gpu_commands_submitted = True
            return
        except Exception:
            return super().blit_surface(
                surface,
                dest,
                area=area,
                alpha=alpha,
                atlas_key=atlas_key
            )

    def flush_batch(self, batch):
        if (
            self._sprite_renderer is not None
            and self._gpu_sprite_enabled
            and self._enabled
            and self._ctx is not None
        ):
            try:
                self._sprite_renderer.reset_frame_metrics()
                drawn = self._sprite_renderer.flush_batch(self, batch)
            except Exception:
                drawn = None

            if drawn is not None:
                self.last_flush_count = drawn
                self.last_unique_surface_count = len(self._frame_surface_tokens)
                self.last_culled_count += getattr(batch, "last_culled_count", 0)
                self.last_atlas_command_count = getattr(
                    batch,
                    "last_atlas_command_count",
                    0
                )
                self.last_atlas_group_count = getattr(
                    batch,
                    "last_atlas_group_count",
                    0
                )
                self.last_atlas_run_count = getattr(
                    batch,
                    "last_atlas_run_count",
                    0
                )
                self.last_batchable_command_count = getattr(
                    batch,
                    "last_batchable_command_count",
                    0
                )
                self._gpu_commands_submitted = drawn > 0
                self._update_atlas_metrics()
                return drawn

            self.last_gpu_fallback_count += 1

        return super().flush_batch(batch)

    def present(self):
        if (
            not self._enabled
            or self._ctx is None
            or not self._gpu_commands_submitted
        ):
            return
        try:
            self._ctx.finish()
        except Exception:
            self._enabled = False
        finally:
            self._gpu_commands_submitted = False


def _env_flag_enabled(name):
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_flag_disabled(name):
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _gpu_sprites_enabled_by_default():
    if _env_flag_disabled("PYOSU_DISABLE_GPU_SPRITES"):
        return False
    if _env_flag_enabled("PYOSU_ENABLE_GPU_SPRITES"):
        return True
    if _env_flag_enabled("PYOSU_GPU_SPRITES"):
        return True
    return True


def create_render_backend(target_surface: Optional[pygame.Surface] = None):
    if target_surface is None:
        return PygameRenderBackend(target_surface)

    if _env_flag_enabled("PYOSU_DISABLE_MODERNGL"):
        return PygameRenderBackend(target_surface)

    backend = ModernGLRenderBackend(target_surface)
    if getattr(backend, "_enabled", False):
        return backend

    if _env_flag_enabled("PYOSU_FORCE_MODERNGL"):
        return backend

    return PygameRenderBackend(target_surface)
