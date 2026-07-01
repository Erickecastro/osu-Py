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
        return tuple(getattr(self.scene.game, "mouse_pos", (0.0, 0.0)))

    def _hit_keys(self):
        return tuple(getattr(self.scene.game, "hit_keys", self.HIT_KEYS))

    def _mouse_buttons_blocked(self):
        return bool(
            getattr(self.scene.game, "block_mouse_buttons_in_gameplay", False)
        )

    def _handle_key_down(self, event):
        if event.key == pygame.K_ESCAPE:
            self.scene.game.scene_manager.pop_scene()
            return True

        if event.key in self._hit_keys():
            self.scene.hit_keys_held.add(event.key)
            self.scene._try_hit_at(
                self._hit_position_now(),
                input_time=self.scene.event_music_time(event)
            )
            return True

        return False

    def _handle_key_up(self, event):
        if event.key in self._hit_keys():
            self.scene.hit_keys_held.discard(event.key)
            if not self.scene._hit_input_held():
                self.scene._handle_hit_input_release(
                    self.scene.event_music_time(event)
                )
            return True
        return False

    def _handle_mouse_down(self, event):
        if event.button in self.HIT_MOUSE_BUTTONS:
            if self._mouse_buttons_blocked():
                self.scene.hit_mouse_buttons_held.discard(event.button)
                return True
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
            if self._mouse_buttons_blocked():
                return True
            if not self.scene._hit_input_held():
                self.scene._handle_hit_input_release(
                    self.scene.event_music_time(event)
                )
            return True
        return False
