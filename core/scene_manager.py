class SceneManager:

    def __init__(self):

        self.scene_stack = []

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