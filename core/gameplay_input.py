import pygame


class GameplayInputController:
    HIT_KEYS = (pygame.K_z, pygame.K_x)
    HIT_MOUSE_BUTTONS = (1, 3)

    def __init__(self, scene):
        self.scene = scene

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            return self._handle_key_down(event)
        if event.type == pygame.KEYUP:
            return self._handle_key_up(event)
        if event.type == pygame.MOUSEBUTTONDOWN:
            return self._handle_mouse_down(event)
        if event.type == pygame.MOUSEBUTTONUP:
            return self._handle_mouse_up(event)
        return False

    def _hit_position_now(self):
        sampler = getattr(self.scene.game, "sample_mouse_now", None)
        if sampler is not None:
            return sampler()
        return self.scene.game.mouse_pos

    def _handle_key_down(self, event):
        if event.key == pygame.K_ESCAPE:
            self.scene.game.scene_manager.pop_scene()
            return True

        if event.key in self.HIT_KEYS:
            self.scene.hit_keys_held.add(event.key)
            self.scene._try_hit_at(
                self._hit_position_now(),
                input_time=self.scene.event_music_time(event)
            )
            return True

        return False

    def _handle_key_up(self, event):
        if event.key in self.HIT_KEYS:
            self.scene.hit_keys_held.discard(event.key)
            return True
        return False

    def _handle_mouse_down(self, event):
        if event.button in self.HIT_MOUSE_BUTTONS:
            self.scene.hit_mouse_buttons_held.add(event.button)
            self.scene._try_hit_at(
                self._hit_position_now(),
                input_time=self.scene.event_music_time(event)
            )
            return True
        return False

    def _handle_mouse_up(self, event):
        if event.button in self.HIT_MOUSE_BUTTONS:
            self.scene.hit_mouse_buttons_held.discard(event.button)
            return True
        return False
