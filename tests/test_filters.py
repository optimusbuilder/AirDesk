"""Unit tests for cursor smoothing filters."""

import math

from airdesk.gestures.filters import OneEuroFilter, ema_point, ema_scalar


class TestEmaPoint:
    """Tests for the legacy EMA point helper."""

    def test_first_call_returns_current(self) -> None:
        assert ema_point((100, 200), None, 0.5) == (100, 200)

    def test_smoothing_blends_toward_current(self) -> None:
        result = ema_point((200, 200), (100, 100), 0.5)
        assert result == (150, 150)

    def test_alpha_one_snaps_to_current(self) -> None:
        result = ema_point((300, 300), (100, 100), 1.0)
        assert result == (300, 300)

    def test_alpha_zero_holds_previous(self) -> None:
        result = ema_point((300, 300), (100, 100), 0.0)
        assert result == (100, 100)


class TestEmaScalar:
    """Tests for the scalar EMA helper."""

    def test_first_call_returns_current(self) -> None:
        assert ema_scalar(42.0, None, 0.5) == 42.0

    def test_smoothing_blends(self) -> None:
        result = ema_scalar(100.0, 50.0, 0.5)
        assert math.isclose(result, 75.0)


class TestOneEuroFilter:
    """Tests for the adaptive 1€ cursor filter."""

    @staticmethod
    def _make_frozen_time():
        current = [0.0]

        def time_fn():
            return current[0]

        def advance(seconds: float):
            current[0] += seconds

        return time_fn, advance

    def test_first_point_passes_through(self) -> None:
        time_fn, _ = self._make_frozen_time()
        f = OneEuroFilter(time_fn=time_fn)
        assert f.apply((150, 200)) == (150, 200)

    def test_small_jitter_is_smoothed(self) -> None:
        time_fn, advance = self._make_frozen_time()
        f = OneEuroFilter(min_cutoff=1.0, beta=0.007, time_fn=time_fn)

        advance(0.033)
        f.apply((200, 200))

        advance(0.033)
        result = f.apply((203, 198))

        # The filter should dampen the 3px jitter significantly.
        assert abs(result[0] - 200) < 3
        assert abs(result[1] - 200) < 3

    def test_fast_movement_follows_closely(self) -> None:
        time_fn, advance = self._make_frozen_time()
        f = OneEuroFilter(min_cutoff=1.0, beta=0.007, time_fn=time_fn)

        advance(0.033)
        f.apply((100, 100))

        # Large, fast jump should follow closely.
        advance(0.033)
        result = f.apply((400, 400))

        # Should have moved substantially toward 400 (not stuck near 100).
        assert result[0] > 200
        assert result[1] > 200

    def test_reset_clears_state(self) -> None:
        time_fn, advance = self._make_frozen_time()
        f = OneEuroFilter(time_fn=time_fn)

        advance(0.033)
        f.apply((100, 100))
        advance(0.033)
        f.apply((200, 200))

        f.reset()

        # After reset, the next point should pass through like the first.
        advance(0.033)
        result = f.apply((300, 300))
        assert result == (300, 300)

    def test_identical_timestamps_uses_fallback_rate(self) -> None:
        """If two calls have the same timestamp, the filter should not crash."""
        time_fn, _ = self._make_frozen_time()
        f = OneEuroFilter(time_fn=time_fn)

        f.apply((100, 100))
        # Same timestamp — should still produce a valid result.
        result = f.apply((110, 110))
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_high_beta_makes_filter_responsive(self) -> None:
        """A very high beta should make the filter track fast movements closely."""
        time_fn, advance = self._make_frozen_time()
        f_low_beta = OneEuroFilter(min_cutoff=1.0, beta=0.0, time_fn=time_fn)
        f_high_beta = OneEuroFilter(min_cutoff=1.0, beta=1.0, time_fn=time_fn)

        # Seed both with the same starting point.
        advance(0.033)
        f_low_beta.apply((100, 100))
        f_high_beta.apply((100, 100))

        # Apply the same fast movement.
        advance(0.033)
        r_low = f_low_beta.apply((300, 300))
        r_high = f_high_beta.apply((300, 300))

        # High beta should track closer to the target.
        assert r_high[0] >= r_low[0]
