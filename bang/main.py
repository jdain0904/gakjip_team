"""Entry point for Bang! game."""
import sys
import pygame

from constants import WIN_W, WIN_H, FPS
from ui_utils import init_fonts
from game_state import GameState
from screens.menu    import MenuScreen
from screens.setup   import SetupScreen
from screens.handoff import HandoffScreen
from screens.game    import GameScreen


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("BANG! 카드 게임")
    clock = pygame.time.Clock()

    init_fonts()

    state  = "menu"
    mode   = None
    menu   = MenuScreen(screen)
    setup  = None
    game   = None
    handoff = None

    while True:
        dt = clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            # ── Menu ──────────────────────────────────────────────────────
            if state == "menu":
                result = menu.handle(event)
                if result in ("local", "ai"):
                    mode  = result
                    setup = SetupScreen(screen, mode)
                    state = "setup"

            # ── Setup ─────────────────────────────────────────────────────
            elif state == "setup":
                result = setup.handle(event)
                if result:
                    if result["action"] == "back":
                        state = "menu"
                    elif result["action"] == "start":
                        gs   = GameState.new_game(
                            num_players=result["n"],
                            human_ids=result["human_ids"],
                            mode=result["mode"],
                            names=result["names"],
                        )
                        game  = GameScreen(screen, gs)
                        state = "game"
                        # Show first handoff if local mode
                        if game.needs_handoff():
                            info    = game.consume_handoff()
                            handoff = HandoffScreen(screen, info)
                            state   = "handoff"

            # ── Handoff ───────────────────────────────────────────────────
            elif state == "handoff":
                if handoff and handoff.handle(event):
                    state = "game"

            # ── Game ──────────────────────────────────────────────────────
            elif state == "game" and game:
                result = game.handle(event)
                if result == "menu":
                    menu  = MenuScreen(screen)
                    state = "menu"
                    game  = None

        # ── Updates ───────────────────────────────────────────────────────
        if state == "game" and game:
            game.update(dt)
            # Check if handoff is needed after AI/auto step
            if game.needs_handoff():
                info    = game.consume_handoff()
                handoff = HandoffScreen(screen, info)
                state   = "handoff"

        # ── Draw ──────────────────────────────────────────────────────────
        if state == "menu":
            menu.draw()
        elif state == "setup" and setup:
            setup.draw()
        elif state == "handoff" and handoff:
            handoff.draw()
        elif state == "game" and game:
            game.draw()


if __name__ == "__main__":
    main()
