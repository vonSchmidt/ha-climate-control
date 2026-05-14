"""Tests for custom_components.climate_control.presence (PresenceEvaluator)."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.climate_control.presence import PresenceEvaluator, PresenceState


def _state(val: str) -> MagicMock:
    s = MagicMock()
    s.state = val
    return s


class TestPresenceEvaluate:
    def test_home_when_any_sensor_on(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.side_effect = lambda eid: _state("on" if "s2" in eid else "off")
        ev = PresenceEvaluator(mock_hass, ["binary_sensor.s1", "binary_sensor.s2"])
        assert ev.evaluate() == PresenceState.HOME

    def test_away_when_all_sensors_off(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("off")
        ev = PresenceEvaluator(mock_hass, ["binary_sensor.s1", "binary_sensor.s2"])
        assert ev.evaluate() == PresenceState.AWAY

    def test_unknown_when_no_sensors_configured(self, mock_hass: MagicMock) -> None:
        ev = PresenceEvaluator(mock_hass, [])
        assert ev.evaluate() == PresenceState.UNKNOWN

    def test_unknown_when_all_sensors_return_none(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = None
        ev = PresenceEvaluator(mock_hass, ["binary_sensor.s1"])
        assert ev.evaluate() == PresenceState.UNKNOWN

    def test_minutes_since_last_seen_none_before_any_home_event(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("off")
        ev = PresenceEvaluator(mock_hass, ["binary_sensor.s1"])
        ev.evaluate()
        assert ev.minutes_since_last_seen() is None

    def test_minutes_since_last_seen_positive_after_home_event(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("on")
        ev = PresenceEvaluator(mock_hass, ["binary_sensor.s1"])
        ev.evaluate()
        result = ev.minutes_since_last_seen()
        assert result is not None
        assert result >= 0.0

    def test_last_seen_updates_on_repeated_home_events(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("on")
        ev = PresenceEvaluator(mock_hass, ["binary_sensor.s1"])
        ev.evaluate()
        first = ev.minutes_since_last_seen()
        ev.evaluate()
        second = ev.minutes_since_last_seen()
        assert first is not None
        assert second is not None
        assert second <= first
