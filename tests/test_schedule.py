"""Tests for custom_components.climate_control.schedule (ScheduleEvaluator)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.climate_control.schedule import ScheduleEvaluator, ScheduleMode


def _make_evaluator(hass: MagicMock, comfort_state: str | None, eco_state: str | None) -> ScheduleEvaluator:
    """Build a ScheduleEvaluator whose hass.states.get returns controlled values."""
    def get_state(entity_id: str) -> MagicMock | None:
        raw = comfort_state if "comfort" in entity_id else eco_state
        if raw is None:
            return None
        s = MagicMock()
        s.state = raw
        return s

    hass.states.get.side_effect = get_state
    return ScheduleEvaluator(hass, "schedule.comfort", "schedule.eco")


class TestScheduleEvaluate:
    def test_comfort_when_comfort_on(self, mock_hass: MagicMock) -> None:
        ev = _make_evaluator(mock_hass, comfort_state="on", eco_state="off")
        assert ev.evaluate() == ScheduleMode.COMFORT

    def test_eco_when_eco_on_and_comfort_off(self, mock_hass: MagicMock) -> None:
        ev = _make_evaluator(mock_hass, comfort_state="off", eco_state="on")
        assert ev.evaluate() == ScheduleMode.ECO

    def test_off_when_both_off(self, mock_hass: MagicMock) -> None:
        ev = _make_evaluator(mock_hass, comfort_state="off", eco_state="off")
        assert ev.evaluate() == ScheduleMode.OFF

    def test_comfort_wins_when_both_on(self, mock_hass: MagicMock) -> None:
        ev = _make_evaluator(mock_hass, comfort_state="on", eco_state="on")
        assert ev.evaluate() == ScheduleMode.COMFORT

    def test_unavailable_comfort_treated_as_off(self, mock_hass: MagicMock) -> None:
        ev = _make_evaluator(mock_hass, comfort_state="unavailable", eco_state="on")
        assert ev.evaluate() == ScheduleMode.ECO

    def test_none_entity_treated_as_off(self, mock_hass: MagicMock) -> None:
        ev = _make_evaluator(mock_hass, comfort_state=None, eco_state="on")
        assert ev.evaluate() == ScheduleMode.ECO

    def test_both_unavailable_returns_off(self, mock_hass: MagicMock) -> None:
        ev = _make_evaluator(mock_hass, comfort_state="unavailable", eco_state="unavailable")
        assert ev.evaluate() == ScheduleMode.OFF
