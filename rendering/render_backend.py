import os
from typing import Optional

import pygame


class RenderCommandBatch:
    """Collects surface blit operations and flushes them to a target later."""

    def __init__(self):
        self._commands = []

    def add_surface(self, surface, dest, area=None, alpha=None):
        if surface is None:
            return
        self._commands.append((surface, dest, area, alpha))

    def clear(self):
        self._commands.clear()

    def flush(self, target):
        if target is None:
            return
        for surface, dest, area, alpha in self._commands:
            blit_surface_with_alpha(target, surface, dest, area=area, alpha=alpha)
        self.clear()

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

    def __init__(self, target_surface: Optional[pygame.Surface] = None):
        self.target_surface = target_surface

    def clear(self, color=(0, 0, 0, 0)):
        if self.target_surface is None:
            return
        self.target_surface.fill(color)

    def blit_surface(self, surface, dest, area=None, alpha=None):
        blit_surface_with_alpha(
            self.target_surface,
            surface,
            dest,
            area=area,
            alpha=alpha
        )

    def create_batch(self):
        return RenderCommandBatch()

    def flush_batch(self, batch):
        if batch is None:
            return
        batch.flush(self.target_surface)

    def present(self):
        return None


class PygameRenderBackend(RenderBackend):
    pass


class ModernGLRenderBackend(RenderBackend):
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
            self._vbo = self._ctx.buffer(
                self._pack_vertices()
            )
            self._vao = self._ctx.simple_vertex_array(
                self._program,
                self._vbo,
                "in_position",
                "in_uv",
            )
            self._enabled = True
        except Exception:
            self._enabled = False
            self._ctx = None

    def _pack_vertices(self):
        return [
            -1.0, -1.0, 0.0, 0.0,
            1.0, -1.0, 1.0, 0.0,
            -1.0, 1.0, 0.0, 1.0,
            1.0, 1.0, 1.0, 1.0,
        ]

    def blit_surface(self, surface, dest, area=None, alpha=None):
        # ModernGL is initialized by default as a capability probe and future
        # upload path, but pygame blits remain authoritative until the sprite
        # pipeline can draw destinations/areas with exact parity. This keeps the
        # renderer opt-in-safe without changing gameplay visuals.
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
