"""Interaction logic for hover, grab, and release behavior."""

from dataclasses import dataclass
import time

from airdesk.config import GestureConfig
from airdesk.models.gesture import GestureState
from airdesk.models.interaction import InteractionState
from airdesk.core.window_manager import WindowManager
from airdesk.models.hand import PixelPoint


@dataclass(slots=True)
class InteractionController:
    """Coordinates gesture input with window interactions."""

    config: GestureConfig

    def update(
        self,
        gesture_state: GestureState,
        window_manager: WindowManager,
        interaction_state: InteractionState,
        frame_width: int,
        frame_height: int,
    ) -> InteractionState:
        """Advance interaction state by one frame."""
        cursor = self._active_cursor(gesture_state)
        current_time = time.monotonic()
        grabbed_window = self._get_grabbed_window(window_manager, interaction_state)

        if grabbed_window is not None:
            self._update_grabbed_window(
                grabbed_window=grabbed_window,
                cursor=cursor,
                gesture_state=gesture_state,
                interaction_state=interaction_state,
                frame_width=frame_width,
                frame_height=frame_height,
                current_time=current_time,
            )

        if interaction_state.grabbed_window_id is None and gesture_state.pinch_started and cursor is not None:
            hovered_window = window_manager.hit_test(cursor)
            if hovered_window is not None:
                grabbed_window = window_manager.bring_to_front(hovered_window.id)
                if grabbed_window is not None:
                    interaction_state.grabbed_window_id = grabbed_window.id
                    interaction_state.grab_offset_x = cursor[0] - grabbed_window.x
                    interaction_state.grab_offset_y = cursor[1] - grabbed_window.y
                    interaction_state.hand_missing_since = None

        hovered_window_id = self._hovered_window_id(window_manager, cursor)
        interaction_state.hovered_window_id = hovered_window_id
        window_manager.update_window_states(
            hovered_window_id=hovered_window_id,
            grabbed_window_id=interaction_state.grabbed_window_id,
        )
        return interaction_state

    @staticmethod
    def _active_cursor(gesture_state: GestureState) -> PixelPoint | None:
        if not gesture_state.tracking_stable:
            return None
        return gesture_state.cursor_px

    @staticmethod
    def _get_grabbed_window(
        window_manager: WindowManager,
        interaction_state: InteractionState,
    ):
        if interaction_state.grabbed_window_id is None:
            return None

        grabbed_window = window_manager.get_window(interaction_state.grabbed_window_id)
        if grabbed_window is None:
            interaction_state.clear_grab()
            return None

        return grabbed_window

    def _update_grabbed_window(
        self,
        *,
        grabbed_window,
        cursor: PixelPoint | None,
        gesture_state: GestureState,
        interaction_state: InteractionState,
        frame_width: int,
        frame_height: int,
        current_time: float,
    ) -> None:
        if cursor is None:
            if interaction_state.hand_missing_since is None:
                interaction_state.hand_missing_since = current_time
                return

            elapsed_ms = (current_time - interaction_state.hand_missing_since) * 1000.0
            if elapsed_ms >= self.config.hand_loss_timeout_ms:
                interaction_state.clear_grab()
            return

        interaction_state.hand_missing_since = None

        if gesture_state.pinch_ended:
            interaction_state.clear_grab()
            return

        if not gesture_state.pinch_active:
            return

        new_x = round(cursor[0] - interaction_state.grab_offset_x)
        new_y = round(cursor[1] - interaction_state.grab_offset_y)
        grabbed_window.move_to(new_x, new_y)
        grabbed_window.clamp_within(frame_width, frame_height)

    @staticmethod
    def _hovered_window_id(
        window_manager: WindowManager,
        cursor: PixelPoint | None,
    ) -> str | None:
        if cursor is None:
            return None

        hovered_window = window_manager.hit_test(cursor)
        if hovered_window is None:
            return None
        return hovered_window.id
