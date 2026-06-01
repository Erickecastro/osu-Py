import pygame


class SceneManager:

    def __init__(self):

        self.scene_stack = []
        self.transition_start = 0
        self.transition_duration = 220
        self.transition_overlay = None
        self.transition_overlay_size = None

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
        old_scene = self.scene_stack.pop()

        # limpa UI da cena removida
        if hasattr(old_scene, "destroy"):

            old_scene.destroy()

        # cena anterior
        current = self.current_scene

        if current:

            # recria UI da cena anterior
            if hasattr(current, "create_ui"):

                current.create_ui()
        self._start_transition()

    # -------------------------
    # SET SCENE
    # -------------------------
    def set_scene(self, scene):

        # destrói todas as cenas antigas
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

    def _start_transition(self):
        self.transition_start = pygame.time.get_ticks()

    def _draw_transition(self, screen):
        if not self.transition_start:
            return

        elapsed = pygame.time.get_ticks() - self.transition_start
        if elapsed >= self.transition_duration:
            self.transition_start = 0
            return

        progress = elapsed / self.transition_duration
        alpha = int((1.0 - progress) * 190)
        size = screen.get_size()
        if self.transition_overlay is None or self.transition_overlay_size != size:
            self.transition_overlay = pygame.Surface(size, pygame.SRCALPHA)
            self.transition_overlay_size = size

        self.transition_overlay.fill((0, 0, 0, alpha))
        screen.blit(self.transition_overlay, (0, 0))
