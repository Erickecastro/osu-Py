from core.game import Game
from core.utils import ensure_application_cwd


def main():
    ensure_application_cwd()

    game = Game()
    game.run()

if __name__ == "__main__":
    main()
