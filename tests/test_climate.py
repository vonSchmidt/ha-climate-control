"""Tests for custom_components.climate_control.climate (ClimateControlEntity)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate.const import HVACMode

from custom_components.climate_control.climate import ClimateControlEntity
from custom_components.climate_control.coordinator import CoordinatorData


def _make_entity(
    coordinator_data: CoordinatorData,
    temp_sensor: str | None = "sensor.indoor_temp",
) -> tuple[ClimateControlEntity, MagicMock]:
    """Instantiate ClimateControlEntity with mocked coordinator, entry, and hass."""
    coordinator = MagicMock()
    coordinator.data = coordinator_data

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {"temp_sensor": temp_sensor}

    entity = ClimateControlEntity(coordinator, entry)

    mock_hass = MagicMock()
    entity.hass = mock_hass
    return entity, mock_hass


class TestProperties:
    def test_hvac_mode_from_coordinator_data(self, coordinator_data: CoordinatorData) -> None:
        entity, _ = _make_entity(coordinator_data)
        assert entity.hvac_mode == HVACMode.HEAT_COOL

    def test_target_temperature_low_matches_heat_setpoint(
        self, coordinator_data: CoordinatorData
    ) -> None:
        entity, _ = _make_entity(coordinator_data)
        assert entity.target_temperature_low == pytest.approx(21.0)

    def test_target_temperature_high_matches_cool_setpoint(
        self, coordinator_data: CoordinatorData
    ) -> None:
        entity, _ = _make_entity(coordinator_data)
        assert entity.target_temperature_high == pytest.approx(24.0)

    def test_unique_id_is_stable(self, coordinator_data: CoordinatorData) -> None:
        entity, _ = _make_entity(coordinator_data)
        assert entity.unique_id == "test_entry_climate"


class TestCurrentTemperature:
    def test_valid_sensor_state_returns_float(self, coordinator_data: CoordinatorData) -> None:
        entity, mock_hass = _make_entity(coordinator_data)
        temp_state = MagicMock()
        temp_state.state = "22.5"
        mock_hass.states.get.return_value = temp_state
        assert entity.current_temperature == pytest.approx(22.5)

    def test_unavailable_sensor_returns_none(self, coordinator_data: CoordinatorData) -> None:
        entity, mock_hass = _make_entity(coordinator_data)
        temp_state = MagicMock()
        temp_state.state = "unavailable"
        mock_hass.states.get.return_value = temp_state
        assert entity.current_temperature is None

    def test_unknown_sensor_state_returns_none(self, coordinator_data: CoordinatorData) -> None:
        entity, mock_hass = _make_entity(coordinator_data)
        temp_state = MagicMock()
        temp_state.state = "unknown"
        mock_hass.states.get.return_value = temp_state
        assert entity.current_temperature is None

    def test_missing_entity_returns_none(self, coordinator_data: CoordinatorData) -> None:
        entity, mock_hass = _make_entity(coordinator_data)
        mock_hass.states.get.return_value = None
        assert entity.current_temperature is None

    def test_no_sensor_configured_returns_none(self, coordinator_data: CoordinatorData) -> None:
        entity, _ = _make_entity(coordinator_data, temp_sensor=None)
        assert entity.current_temperature is None


class TestExtraStateAttributes:
    def test_contains_all_required_keys(self, coordinator_data: CoordinatorData) -> None:
        entity, _ = _make_entity(coordinator_data)
        attrs = entity.extra_state_attributes
        assert set(attrs.keys()) == {
            "schedule_mode",
            "effective_mode",
            "presence",
            "solar_output_w",
            "solar_lookahead_sunny",
            "reason",
        }

    def test_values_match_coordinator_data(self, coordinator_data: CoordinatorData) -> None:
        entity, _ = _make_entity(coordinator_data)
        attrs = entity.extra_state_attributes
        assert attrs["schedule_mode"] == "comfort"
        assert attrs["effective_mode"] == "comfort"
        assert attrs["presence"] == "home"
        assert attrs["solar_output_w"] == pytest.approx(500.0)
        assert attrs["solar_lookahead_sunny"] is False
        assert "comfort" in attrs["reason"].lower()


class TestServiceHandlers:
    async def test_set_temperature_does_not_raise(self, coordinator_data: CoordinatorData) -> None:
        entity, _ = _make_entity(coordinator_data)
        await entity.async_set_temperature(temperature=25.0)

    async def test_set_hvac_mode_triggers_coordinator_refresh(
        self, coordinator_data: CoordinatorData
    ) -> None:
        entity, _ = _make_entity(coordinator_data)
        entity.coordinator.async_request_refresh = AsyncMock()
        await entity.async_set_hvac_mode(HVACMode.COOL)
        entity.coordinator.async_request_refresh.assert_called_once()
