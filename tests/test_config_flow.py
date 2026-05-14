"""Config flow integration tests for Climate Control."""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_control.const import (
    CONF_COMFORT_COOL,
    CONF_COMFORT_HEAT,
    CONF_COMFORT_SCHEDULE,
    CONF_ECO_SCHEDULE,
    DOMAIN,
)

# ── Shared step data ──────────────────────────────────────────────────────────

_STEP1 = {
    "target_entity": "climate.ac",
    "temp_sensor": "sensor.indoor_temp",
}
_STEP2 = {
    "comfort_schedule": "schedule.comfort",
    "eco_schedule": "schedule.eco",
}
_STEP3 = {
    "presence_sensors": [],
    "precondition_min": 30,
}
_STEP4 = {
    "comfort_heat": 21.0,
    "comfort_cool": 24.0,
    "eco_heat": 18.0,
    "eco_cool": 28.0,
    "update_interval": 10,
}
_ALL_DATA = {**_STEP1, **_STEP2, **_STEP3, **_STEP4}


# ── Config flow tests ─────────────────────────────────────────────────────────


async def test_happy_path_creates_entry(hass: object) -> None:
    """Complete 4-step flow should create an entry titled 'Climate Control'."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], _STEP1)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "schedule"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], _STEP2)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "presence"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], _STEP3)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "settings"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], _STEP4)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Climate Control"
    data = result["data"]
    assert data[CONF_COMFORT_SCHEDULE] == "schedule.comfort"
    assert data[CONF_ECO_SCHEDULE] == "schedule.eco"
    assert data[CONF_COMFORT_HEAT] == pytest.approx(21.0)


async def test_schedule_same_entity_shows_error(hass: object) -> None:
    """comfort_schedule == eco_schedule must be rejected with a form error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _STEP1)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"comfort_schedule": "schedule.same", "eco_schedule": "schedule.same"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "schedule"
    assert result["errors"].get("base") == "same_entity"


async def test_setpoints_comfort_heat_gte_cool_shows_error(hass: object) -> None:
    """comfort_heat >= comfort_cool must be rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _STEP1)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _STEP2)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], _STEP3)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**_STEP4, "comfort_heat": 25.0, "comfort_cool": 24.0},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "settings"
    assert "base" in result["errors"]


# ── Options flow tests ────────────────────────────────────────────────────────


async def test_options_flow_saves_updated_setpoints(hass: object) -> None:
    """Options flow should persist new setpoint values to entry.options."""
    entry = MockConfigEntry(domain=DOMAIN, data=_ALL_DATA, options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    updated = {
        **_STEP2,
        **_STEP3,
        **_STEP4,
        "comfort_heat": 22.0,
        "comfort_cool": 25.0,
    }
    result = await hass.config_entries.options.async_configure(result["flow_id"], updated)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_COMFORT_HEAT] == pytest.approx(22.0)
    assert entry.options[CONF_COMFORT_COOL] == pytest.approx(25.0)
