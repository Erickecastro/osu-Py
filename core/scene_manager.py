import pygame


class SceneManager:

    def __init__(self):

        self.scene_stack = []
        self.transition_start = 0
        self.transition_duration = 260
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

    # -------------------------
    # EVENTS
    # -------------------------
    def handle_event(self, event):

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

    # -------------------------
    # RENDER
    # -------------------------
    def render(self, screen):

        current = self.current_scene

        if current:

            current.render(screen)

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

    def _start_transition(self):
        self.transition_start = pygame.time.get_ticks()

    def _draw_transition(self, screen):
        if not self.transition_start:
            return

        elapsed = pygame.time.get_ticks() - self.transition_start
        if elapsed >= self.transition_duration:
            self.transition_start = 0
            self.transition_snapshot = None
            self.transition_snapshot_size = None
            return

        progress = elapsed / self.transition_duration
        size = screen.get_size()
        eased = 1.0 - pow(1.0 - progress, 3)
        snapshot_alpha = int((1.0 - eased) * 255)
        if (
            self.transition_snapshot is not None
            and self.transition_snapshot_size == size
            and snapshot_alpha > 0
        ):
            if self.transition_snapshot.get_alpha() != snapshot_alpha:
                self.transition_snapshot.set_alpha(snapshot_alpha)
            screen.blit(self.transition_snapshot, (0, 0))
            return

        alpha = int((1.0 - eased) * 70)
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
