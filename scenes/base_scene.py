class BaseScene:

    def __init__(self, game):

        self.game = game

    def handle_event(self, event):

        pass

    def update(self, dt):

        pass

    def render(self, screen):

        pass

    def destroy(self):
        pass