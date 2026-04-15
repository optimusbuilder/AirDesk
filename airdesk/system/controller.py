"""Translate gesture state into backend-agnostic system intents."""

from dataclasses import dataclass

from airdesk.models.gesture import GestureState
from airdesk.models.hand import PixelPoint
from airdesk.system.intents import PointerPhase, SystemControlState


@dataclass(slots=True)
class SystemIntentController:
    """Produce pointer-style system intents from the gesture stream."""

    enabled: bool = False
    previous_button_down: bool = False

    def reset(self) -> None:
        """Clear any remembered button state."""
        self.previous_button_down = False

    def update(
        self,
        gesture_state: GestureState,
        frame_width: int,
        frame_height: int,
    ) -> SystemControlState:
        """Return the current system-control intent for this frame."""
        if not self.enabled:
            self.previous_button_down = False
            return SystemControlState()

        cursor = self._active_cursor(gesture_state)
        normalized_cursor = self._normalize_cursor(cursor, frame_width, frame_height)

        if cursor is None:
            if self.previous_button_down:
                self.previous_button_down = False
                return SystemControlState(
                    enabled=True,
                    phase=PointerPhase.RELEASE,
                    effect_label="Tracking lost - would force button release",
                )
            return SystemControlState(
                enabled=True,
                phase=PointerPhase.LOST,
                effect_label="Show one hand to start shadow control",
            )

        if gesture_state.pinch_started:
            self.previous_button_down = True
            return SystemControlState(
                enabled=True,
                phase=PointerPhase.PRESS,
                frame_cursor_px=cursor,
                normalized_cursor=normalized_cursor,
                button_down=True,
                effect_label="Would press the primary button",
            )

        if gesture_state.pinch_ended:
            self.previous_button_down = False
            return SystemControlState(
                enabled=True,
                phase=PointerPhase.RELEASE,
                frame_cursor_px=cursor,
                normalized_cursor=normalized_cursor,
                button_down=False,
                effect_label="Would release the primary button",
            )

        if gesture_state.pinch_active or self.previous_button_down:
            self.previous_button_down = True
            return SystemControlState(
                enabled=True,
                phase=PointerPhase.DRAG,
                frame_cursor_px=cursor,
                normalized_cursor=normalized_cursor,
                button_down=True,
                effect_label="Would drag the system pointer",
            )

        self.previous_button_down = False
        return SystemControlState(
            enabled=True,
            phase=PointerPhase.MOVE,
            frame_cursor_px=cursor,
            normalized_cursor=normalized_cursor,
            button_down=False,
            effect_label="Would move the system pointer",
        )

    @staticmethod
    def _active_cursor(gesture_state: GestureState) -> PixelPoint | None:
        if not gesture_state.tracking_stable:
            return None
        return gesture_state.cursor_px

    @staticmethod
    def _normalize_cursor(
        cursor: PixelPoint | None,
        frame_width: int,
        frame_height: int,
    ) -> tuple[float, float] | None:
        if cursor is None:
            return None

        width = max(frame_width - 1, 1)
        height = max(frame_height - 1, 1)
        return (
            min(max(cursor[0] / width, 0.0), 1.0),
            min(max(cursor[1] / height, 0.0), 1.0),
        )
