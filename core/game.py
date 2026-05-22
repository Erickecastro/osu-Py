import pygame

class Game:

    WIDTH = 1280
    HEIGHT = 720
    FPS = 144

    def __init__(self):

        pygame.init()

        self.screen = pygame.display.set_mode(
            (self.WIDTH, self.HEIGHT)
        )

        pygame.display.set_caption("PyOsu")

        self.clock = pygame.time.Clock()

        self.running = True

    def run(self):

        while self.running:

            dt = self.clock.tick(self.FPS) / 1000

            self.events()

            self.update(dt)

            self.render()

        pygame.quit()

    def events(self):

        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                self.running = False

    def update(self, dt):

        pass

    def render(self):

        self.screen.fill((20, 20, 20))

        pygame.display.flip()