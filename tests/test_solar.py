"""Tests for custom_components.climate_control.solar (SolarAdvisor)."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from unittest.mock import MagicMock

import pytest

from custom_components.climate_control.solar import SolarAdvisor


def _advisor(
    hass: MagicMock, power_sensor: str | None = None, weather_entity: str | None = None
) -> SolarAdvisor:
    return SolarAdvisor(hass, power_sensor, weather_entity)


def _state(val: str, attrs: dict | None = None) -> MagicMock:
    s = MagicMock()
    s.state = val
    s.attributes = attrs or {}
    return s


class TestSolarDisabled:
    def test_disabled_when_no_sources_configured(self, mock_hass: MagicMock) -> None:
        result = _advisor(mock_hass).evaluate()
        assert result.solar_enabled is False
        assert result.current_output_w == pytest.approx(0.0)
        assert result.lookahead_sunny is False
        assert result.source_note == "disabled"


class TestInverterReading:
    def test_reads_watts(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("500", {"unit_of_measurement": "W"})
        result = _advisor(mock_hass, power_sensor="sensor.inv").evaluate()
        assert result.current_output_w == pytest.approx(500.0)
        assert result.solar_enabled is True

    def test_reads_kw_and_converts_to_watts(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("1.5", {"unit_of_measurement": "kW"})
        result = _advisor(mock_hass, power_sensor="sensor.inv").evaluate()
        assert result.current_output_w == pytest.approx(1500.0)

    def test_lowercase_kw_also_converts(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("2.0", {"unit_of_measurement": "kw"})
        result = _advisor(mock_hass, power_sensor="sensor.inv").evaluate()
        assert result.current_output_w == pytest.approx(2000.0)

    def test_unavailable_state_returns_zero(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("unavailable")
        result = _advisor(mock_hass, power_sensor="sensor.inv").evaluate()
        assert result.current_output_w == pytest.approx(0.0)

    def test_missing_entity_returns_zero(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = None
        result = _advisor(mock_hass, power_sensor="sensor.inv").evaluate()
        assert result.current_output_w == pytest.approx(0.0)

    def test_non_numeric_state_returns_zero(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("error")
        result = _advisor(mock_hass, power_sensor="sensor.inv").evaluate()
        assert result.current_output_w == pytest.approx(0.0)


class TestForecastLookahead:
    def _weather(self, slots: list[dict]) -> MagicMock:
        return _state("cloudy", {"forecast": slots})

    def test_lookahead_sunny_when_condition_within_window(self, mock_hass: MagicMock) -> None:
        soon = datetime.now(UTC) + timedelta(hours=1)
        mock_hass.states.get.return_value = self._weather(
            [{"datetime": soon.isoformat(), "condition": "sunny"}]
        )
        result = _advisor(mock_hass, weather_entity="weather.home").evaluate()
        assert result.lookahead_sunny is True

    def test_lookahead_false_when_condition_unsunny(self, mock_hass: MagicMock) -> None:
        soon = datetime.now(UTC) + timedelta(hours=1)
        mock_hass.states.get.return_value = self._weather(
            [{"datetime": soon.isoformat(), "condition": "rainy"}]
        )
        result = _advisor(mock_hass, weather_entity="weather.home").evaluate()
        assert result.lookahead_sunny is False

    def test_lookahead_false_when_slot_beyond_window(self, mock_hass: MagicMock) -> None:
        far = datetime.now(UTC) + timedelta(hours=5)
        mock_hass.states.get.return_value = self._weather(
            [{"datetime": far.isoformat(), "condition": "sunny"}]
        )
        result = _advisor(mock_hass, weather_entity="weather.home").evaluate()
        assert result.lookahead_sunny is False

    def test_lookahead_false_when_slot_in_past(self, mock_hass: MagicMock) -> None:
        past = datetime.now(UTC) - timedelta(hours=1)
        mock_hass.states.get.return_value = self._weather(
            [{"datetime": past.isoformat(), "condition": "sunny"}]
        )
        result = _advisor(mock_hass, weather_entity="weather.home").evaluate()
        assert result.lookahead_sunny is False

    def test_lookahead_false_when_weather_entity_unavailable(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("unavailable")
        result = _advisor(mock_hass, weather_entity="weather.home").evaluate()
        assert result.lookahead_sunny is False

    def test_lookahead_false_when_weather_entity_missing(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = None
        result = _advisor(mock_hass, weather_entity="weather.home").evaluate()
        assert result.lookahead_sunny is False


class TestSourceNote:
    def test_source_note_inverter_only(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("300", {"unit_of_measurement": "W"})
        result = _advisor(mock_hass, power_sensor="sensor.inv").evaluate()
        assert result.source_note == "inverter"

    def test_source_note_forecast_only(self, mock_hass: MagicMock) -> None:
        mock_hass.states.get.return_value = _state("cloudy", {"forecast": []})
        result = _advisor(mock_hass, weather_entity="weather.home").evaluate()
        assert result.source_note == "forecast"

    def test_source_note_both_sources(self, mock_hass: MagicMock) -> None:
        def side_effect(eid: str) -> MagicMock:
            if "sensor" in eid:
                return _state("300", {"unit_of_measurement": "W"})
            return _state("sunny", {"forecast": []})

        mock_hass.states.get.side_effect = side_effect
        result = _advisor(
            mock_hass, power_sensor="sensor.inv", weather_entity="weather.home"
        ).evaluate()
        assert result.source_note == "inverter+forecast"
