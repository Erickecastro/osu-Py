import os
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
    )

    def __init__(self):
        self._commands = []
        self.last_culled_count = 0
        self.last_atlas_command_count = 0
        self.last_atlas_group_count = 0

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

    def flush(self, target, before_blit=None):
        count = len(self._commands)
        if target is None or count <= 0:
            self.clear()
            return 0
        drawn = 0
        culled = 0
        atlas_commands = 0
        atlas_groups = set()
        for surface, dest, area, alpha, atlas_key in self._commands:
            if not _surface_blit_visible(target, surface, dest, area=area):
                culled += 1
                continue
            if before_blit is not None:
                before_blit(surface, atlas_key)
            if atlas_key is not None:
                atlas_commands += 1
                atlas_groups.add(atlas_key)
            blit_surface_with_alpha(target, surface, dest, area=area, alpha=alpha)
            drawn += 1
        self._commands.clear()
        self.last_culled_count = culled
        self.last_atlas_command_count = atlas_commands
        self.last_atlas_group_count = len(atlas_groups)
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

    def blit_surface(self, surface, dest, area=None, alpha=None):
        if not _surface_blit_visible(self.target_surface, surface, dest, area=area):
            self.last_direct_culled_count += 1
            self.last_culled_count += 1
            return
        self._register_surface(surface)
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
        self._gpu_commands_submitted = False
        self._initialize()

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
            data = pygame.image.tostring(surface, "RGBA", False)
            tex = self._ctx.texture((w, h), 4, data)
            try:
                tex.filter = (self._moderngl.LINEAR, self._moderngl.LINEAR)
            except Exception:
                pass
            self._textures[key] = (tex, w, h)
            return tex
        except Exception:
            return None

    def blit_surface(self, surface, dest, area=None, alpha=None):
        if not self._enabled or self._ctx is None:
            return super().blit_surface(surface, dest, area=area, alpha=alpha)

        # Try to draw via ModernGL. Fallback to pygame on any failure.
        try:
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
                return super().blit_surface(surface, dest, area=area, alpha=alpha)

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
            return super().blit_surface(surface, dest, area=area, alpha=alpha)

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
