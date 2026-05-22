class SceneManager:

    def __init__(self):

        self.current_scene = None

    def set_scene(self, scene):

        if self.current_scene:

            if hasattr(self.current_scene, "destroy"):
                self.current_scene.destroy()

        self.current_scene = scene

    def handle_event(self, event):

        if self.current_scene:
            self.current_scene.handle_event(event)

    def update(self, dt):

        if self.current_scene:
            self.current_scene.update(dt)

    def render(self, screen):

        if self.current_scene:
            self.current_scene.render(screen)