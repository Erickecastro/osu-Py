import pygame


class SceneManager:

    def __init__(self):

        self.scene_stack = []
        self.transition_start = 0
        self.transition_duration = 430
        self.transition_out_start = 0
        self.transition_out_duration = 390
        self.pending_factory = None
        self.pending_factory_mode = None
        self.transition_from_black = False
        self.transition_overlay = None
        self.transition_overlay_size = None
        self.transition_snapshot = None
        self.transition_snapshot_size = None

    # -------------------------
    # CURRENT SCENE
    # -------------------------
    @property
    def current_scene(self):

        if len(self.scene_stack) > 0:

            return self.scene_stack[-1]

        return None

    # -------------------------
    # PUSH SCENE
    # -------------------------
    def push_scene(self, scene):

        # remove UI da cena atual
        current = self.current_scene
        self._capture_transition_snapshot()

        if current:

            if hasattr(current, "destroy"):

                current.destroy()

        # adiciona nova cena
        self.scene_stack.append(scene)
        self._start_transition()

    def push_scene_factory(self, factory):
        self._begin_factory_transition(factory, "push")

    # -------------------------
    # POP SCENE
    # -------------------------
    def pop_scene(self):

        # impede fechar última cena
        if len(self.scene_stack) <= 1:

            return

        # remove cena atual
        self._capture_transition_snapshot()
        old_scene = self.scene_stack.pop()

        # limpa UI da cena removida
        if hasattr(old_scene, "destroy"):

            old_scene.destroy()

        # cena anterior
        current = self.current_scene

        if current:

            if hasattr(current, "on_resume"):

                current.on_resume()

            # recria UI da cena anterior
            elif hasattr(current, "create_ui"):

                current.create_ui()
        self._start_transition()

    # -------------------------
    # SET SCENE
    # -------------------------
    def set_scene(self, scene):

        # destrói todas as cenas antigas
        self._capture_transition_snapshot()
        while len(self.scene_stack) > 0:

            old_scene = self.scene_stack.pop()

            if hasattr(old_scene, "destroy"):

                old_scene.destroy()

        # adiciona nova cena
        self.scene_stack.append(scene)
        self._start_transition()

    def set_scene_factory(self, factory):
        self._begin_factory_transition(factory, "set")

    # -------------------------
    # EVENTS
    # -------------------------
    def handle_event(self, event):
        if self.pending_factory is not None:
            return

        current = self.current_scene

        if current:

            current.handle_event(event)

    # -------------------------
    # UPDATE
    # -------------------------
    def update(self, dt):

        current = self.current_scene

        if current:

            current.update(dt)

        if self.pending_factory is not None and self.transition_out_start:
            elapsed = pygame.time.get_ticks() - self.transition_out_start
            if elapsed >= self.transition_out_duration:
                self._complete_factory_transition()

    # -------------------------
    # RENDER
    # -------------------------
    def render(self, screen):

        current = self.current_scene

        if current:

            current.render(screen)

        if self.pending_factory is not None:
            self._draw_transition_out(screen)
        else:
            self._draw_transition(screen)

    def on_resize(self):
        self.transition_overlay = None
        self.transition_overlay_size = None
        self.transition_snapshot = None
        self.transition_snapshot_size = None

        current = self.current_scene
        for scene in self.scene_stack:
            if scene is current and getattr(scene, "uses_ui", True):
                if hasattr(scene, "destroy"):
                    scene.destroy()
                if hasattr(scene, "create_ui"):
                    scene.create_ui()
            elif hasattr(scene, "on_resize"):
                scene.on_resize()

    def _start_transition(self, from_black=False):
        self.transition_start = pygame.time.get_ticks()
        self.transition_from_black = bool(from_black)

    def _begin_factory_transition(self, factory, mode):
        if self.pending_factory is not None:
            return
        self.pending_factory = factory
        self.pending_factory_mode = mode
        self.transition_out_start = pygame.time.get_ticks()
        self.transition_start = 0
        self.transition_from_black = False
        self.transition_snapshot = None
        self.transition_snapshot_size = None

    def _complete_factory_transition(self):
        factory = self.pending_factory
        mode = self.pending_factory_mode
        self.pending_factory = None
        self.pending_factory_mode = None
        self.transition_out_start = 0

        if factory is None:
            return

        scene = factory()
        if mode == "push":
            current = self.current_scene
            if current and hasattr(current, "destroy"):
                current.destroy()
            self.scene_stack.append(scene)
        else:
            while len(self.scene_stack) > 0:
                old_scene = self.scene_stack.pop()
                if hasattr(old_scene, "destroy"):
                    old_scene.destroy()
            self.scene_stack.append(scene)

        self.transition_snapshot = None
        self.transition_snapshot_size = None
        self._start_transition(from_black=True)

    def _draw_blocking_loading_frame(self):
        screen = pygame.display.get_surface()
        if screen is None:
            return
        try:
            screen.fill((0, 0, 0))
            pygame.display.flip()
            self.transition_snapshot = screen.copy().convert()
            self.transition_snapshot_size = screen.get_size()
            pygame.event.pump()
        except pygame.error:
            pass

    def _draw_transition(self, screen):
        if not self.transition_start:
            return

        elapsed = pygame.time.get_ticks() - self.transition_start
        if elapsed >= self.transition_duration:
            self.transition_start = 0
            self.transition_snapshot = None
            self.transition_snapshot_size = None
            self.transition_from_black = False
            return

        progress = elapsed / self.transition_duration
        size = screen.get_size()
        eased = progress * progress * (3.0 - (2.0 * progress))
        snapshot_alpha = int((1.0 - eased) * 255)
        if (
            not self.transition_from_black
            and
            self.transition_snapshot is not None
            and self.transition_snapshot_size == size
            and snapshot_alpha > 0
        ):
            if self.transition_snapshot.get_alpha() != snapshot_alpha:
                self.transition_snapshot.set_alpha(snapshot_alpha)
            screen.blit(self.transition_snapshot, (0, 0))
            return

        alpha = int((1.0 - eased) * (255 if self.transition_from_black else 70))
        if self.transition_overlay is None or self.transition_overlay_size != size:
            self.transition_overlay = pygame.Surface(size).convert()
            self.transition_overlay.fill((0, 0, 0))
            self.transition_overlay_size = size

        if self.transition_overlay.get_alpha() != alpha:
            self.transition_overlay.set_alpha(alpha)
        screen.blit(self.transition_overlay, (0, 0))

    def _draw_transition_out(self, screen):
        if not self.transition_out_start:
            return
        elapsed = pygame.time.get_ticks() - self.transition_out_start
        progress = min(1.0, max(0.0, elapsed / max(1, self.transition_out_duration)))
        eased = progress * progress * (3.0 - (2.0 * progress))
        alpha = int(eased * 255)
        size = screen.get_size()
        if self.transition_overlay is None or self.transition_overlay_size != size:
            self.transition_overlay = pygame.Surface(size).convert()
            self.transition_overlay.fill((0, 0, 0))
            self.transition_overlay_size = size
        if self.transition_overlay.get_alpha() != alpha:
            self.transition_overlay.set_alpha(alpha)
        screen.blit(self.transition_overlay, (0, 0))

    def _capture_transition_snapshot(self):
        screen = pygame.display.get_surface()
        if screen is None:
            self.transition_snapshot = None
            self.transition_snapshot_size = None
            return

        try:
            self.transition_snapshot = screen.copy().convert()
            self.transition_snapshot_size = screen.get_size()
        except pygame.error:
            self.transition_snapshot = None
            self.transition_snapshot_size = None
