"""Shared pytest fixtures for Climate Control tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.climate.const import HVACMode

from custom_components.climate_control.coordinator import CoordinatorData
from custom_components.climate_control.presence import PresenceState
from custom_components.climate_control.schedule import ScheduleMode
from custom_components.climate_control.solar import SolarState


def make_state(state_val: str, attributes: dict | None = None) -> MagicMock:
    """Return a minimal HA state object mock."""
    s = MagicMock()
    s.state = state_val
    s.attributes = attributes or {}
    return s


@pytest.fixture
def mock_hass() -> MagicMock:
    """Return a minimal Home Assistant mock with a configurable states store."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.states.get.return_value = None
    return hass


@pytest.fixture
def sample_solar_state() -> SolarState:
    """A solar state fixture with moderate inverter output, solar enabled."""
    return SolarState(
        current_output_w=500.0,
        lookahead_sunny=False,
        solar_enabled=True,
        source_note="inverter",
    )


@pytest.fixture
def mock_entry() -> MagicMock:
    """Config entry mock with all required fields set to sensible defaults."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "target_entity": "climate.ac",
        "temp_sensor": "sensor.indoor_temp",
        "comfort_schedule": "schedule.comfort",
        "eco_schedule": "schedule.eco",
        "presence_sensors": [],
        "comfort_heat": 21.0,
        "comfort_cool": 24.0,
        "eco_heat": 18.0,
        "eco_cool": 28.0,
        "precondition_min": 30,
        "update_interval": 10,
    }
    entry.options = {}
    return entry


@pytest.fixture
def coordinator_data(sample_solar_state: SolarState) -> CoordinatorData:
    """A CoordinatorData snapshot suitable for climate entity tests."""
    return CoordinatorData(
        schedule_mode=ScheduleMode.COMFORT,
        presence=PresenceState.HOME,
        solar=sample_solar_state,
        effective_mode=ScheduleMode.COMFORT,
        target_setpoint_heat=21.0,
        target_setpoint_cool=24.0,
        hvac_mode=HVACMode.HEAT_COOL,
        reason="Schedule: comfort",
    )
