"""Tests for ClimateControlCoordinator — _compute logic and _async_update_data."""
from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.climate.const import HVACMode
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.climate_control.const import (
    CONF_COMFORT_COOL,
    CONF_COMFORT_HEAT,
    CONF_COMFORT_SCHEDULE,
    CONF_ECO_COOL,
    CONF_ECO_HEAT,
    CONF_ECO_SCHEDULE,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_ECO_COOL,
    DEFAULT_ECO_HEAT,
    SOLAR_OFFSET_HIGH,
    SOLAR_OFFSET_LOW,
)
from custom_components.climate_control.coordinator import (
    ClimateControlCoordinator,
    CoordinatorData,
)
from custom_components.climate_control.presence import PresenceState
from custom_components.climate_control.schedule import ScheduleMode
from custom_components.climate_control.solar import SolarState


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_coordinator(options: dict | None = None) -> ClimateControlCoordinator:
    hass = MagicMock()
    entry = MagicMock()
    entry.data = {
        CONF_COMFORT_SCHEDULE: "schedule.comfort",
        CONF_ECO_SCHEDULE: "schedule.eco",
        "presence_sensors": [],
        CONF_COMFORT_HEAT: DEFAULT_COMFORT_HEAT,
        CONF_COMFORT_COOL: DEFAULT_COMFORT_COOL,
        CONF_ECO_HEAT: DEFAULT_ECO_HEAT,
        CONF_ECO_COOL: DEFAULT_ECO_COOL,
        "precondition_min": 30,
        "update_interval": 10,
    }
    entry.options = options or {}
    return ClimateControlCoordinator(hass, entry)


def _solar(
    enabled: bool = True,
    output_w: float = 0.0,
    lookahead: bool = False,
) -> SolarState:
    return SolarState(
        current_output_w=output_w,
        lookahead_sunny=lookahead,
        solar_enabled=enabled,
        source_note="inverter" if enabled else "disabled",
    )


# ── Schedule OFF tests ────────────────────────────────────────────────────────


class TestScheduleOff:
    def test_off_schedule_sets_hvac_off(self) -> None:
        coord = _make_coordinator()
        _, _, hvac, effective, reason = coord._compute(
            ScheduleMode.OFF, PresenceState.HOME, _solar(False), None
        )
        assert hvac == HVACMode.OFF
        assert effective == ScheduleMode.OFF
        assert "off" in reason.lower()

    def test_off_schedule_ignores_presence(self) -> None:
        coord = _make_coordinator()
        _, _, hvac, _, _ = coord._compute(
            ScheduleMode.OFF, PresenceState.AWAY, _solar(False), None
        )
        assert hvac == HVACMode.OFF

    def test_off_schedule_ignores_solar(self) -> None:
        coord = _make_coordinator()
        _, _, hvac, _, _ = coord._compute(
            ScheduleMode.OFF, PresenceState.HOME, _solar(output_w=2000.0), None
        )
        assert hvac == HVACMode.OFF


# ── Presence override tests ───────────────────────────────────────────────────


class TestPresenceOverride:
    def test_comfort_home_no_override(self) -> None:
        coord = _make_coordinator()
        heat, cool, hvac, effective, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.HOME, _solar(False), None
        )
        assert effective == ScheduleMode.COMFORT
        assert heat == pytest.approx(DEFAULT_COMFORT_HEAT)
        assert cool == pytest.approx(DEFAULT_COMFORT_COOL)
        assert hvac == HVACMode.HEAT_COOL

    def test_comfort_away_downgrades_to_eco(self) -> None:
        coord = _make_coordinator()
        heat, cool, _, effective, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.AWAY, _solar(False), None
        )
        assert effective == ScheduleMode.ECO
        assert heat == pytest.approx(DEFAULT_ECO_HEAT)
        assert cool == pytest.approx(DEFAULT_ECO_COOL)

    def test_comfort_unknown_downgrades_to_eco(self) -> None:
        coord = _make_coordinator()
        _, _, _, effective, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.UNKNOWN, _solar(False), None
        )
        assert effective == ScheduleMode.ECO

    def test_eco_home_upgrades_to_comfort(self) -> None:
        coord = _make_coordinator()
        heat, cool, _, effective, _ = coord._compute(
            ScheduleMode.ECO, PresenceState.HOME, _solar(False), None
        )
        assert effective == ScheduleMode.COMFORT
        assert heat == pytest.approx(DEFAULT_COMFORT_HEAT)
        assert cool == pytest.approx(DEFAULT_COMFORT_COOL)

    def test_eco_away_within_precondition_upgrades(self) -> None:
        coord = _make_coordinator()
        _, _, _, effective, reason = coord._compute(
            ScheduleMode.ECO, PresenceState.AWAY, _solar(False), minutes_away=10.0
        )
        assert effective == ScheduleMode.COMFORT
        assert "returning" in reason.lower() or "pre-condition" in reason.lower()

    def test_eco_away_outside_precondition_stays_eco(self) -> None:
        coord = _make_coordinator()
        _, _, _, effective, _ = coord._compute(
            ScheduleMode.ECO, PresenceState.AWAY, _solar(False), minutes_away=60.0
        )
        assert effective == ScheduleMode.ECO

    def test_eco_away_no_last_seen_stays_eco(self) -> None:
        coord = _make_coordinator()
        _, _, _, effective, _ = coord._compute(
            ScheduleMode.ECO, PresenceState.AWAY, _solar(False), minutes_away=None
        )
        assert effective == ScheduleMode.ECO

    def test_eco_unknown_within_precondition_upgrades(self) -> None:
        coord = _make_coordinator()
        _, _, _, effective, _ = coord._compute(
            ScheduleMode.ECO, PresenceState.UNKNOWN, _solar(False), minutes_away=5.0
        )
        assert effective == ScheduleMode.COMFORT


# ── Solar offset tests ────────────────────────────────────────────────────────


class TestSolarOffset:
    def test_high_output_reduces_cooling_setpoint(self) -> None:
        coord = _make_coordinator()
        _, cool, _, _, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.HOME, _solar(output_w=1500.0), None
        )
        assert cool == pytest.approx(DEFAULT_COMFORT_COOL - SOLAR_OFFSET_HIGH)

    def test_moderate_output_reduces_cooling_setpoint(self) -> None:
        coord = _make_coordinator()
        _, cool, _, _, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.HOME, _solar(output_w=500.0), None
        )
        assert cool == pytest.approx(DEFAULT_COMFORT_COOL - SOLAR_OFFSET_LOW)

    def test_low_output_no_offset(self) -> None:
        coord = _make_coordinator()
        _, cool, _, _, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.HOME, _solar(output_w=50.0), None
        )
        assert cool == pytest.approx(DEFAULT_COMFORT_COOL)

    def test_lookahead_sunny_reduces_cooling_setpoint(self) -> None:
        coord = _make_coordinator()
        _, cool, _, _, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.HOME, _solar(output_w=0.0, lookahead=True), None
        )
        assert cool == pytest.approx(DEFAULT_COMFORT_COOL - SOLAR_OFFSET_LOW)

    def test_solar_disabled_no_offset(self) -> None:
        coord = _make_coordinator()
        _, cool, _, _, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.HOME, _solar(enabled=False), None
        )
        assert cool == pytest.approx(DEFAULT_COMFORT_COOL)

    def test_solar_never_modifies_heating_setpoint(self) -> None:
        coord = _make_coordinator()
        heat_no_solar, _, _, _, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.HOME, _solar(output_w=0.0), None
        )
        heat_high_solar, _, _, _, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.HOME, _solar(output_w=2000.0), None
        )
        assert heat_no_solar == pytest.approx(heat_high_solar)


# ── Options override tests ────────────────────────────────────────────────────


class TestOptionsOverride:
    def test_options_comfort_setpoints_override_data(self) -> None:
        coord = _make_coordinator(options={CONF_COMFORT_HEAT: 22.0, CONF_COMFORT_COOL: 26.0})
        heat, cool, _, _, _ = coord._compute(
            ScheduleMode.COMFORT, PresenceState.HOME, _solar(False), None
        )
        assert heat == pytest.approx(22.0)
        assert cool == pytest.approx(26.0)

    def test_options_eco_setpoints_override_data(self) -> None:
        coord = _make_coordinator(options={CONF_ECO_HEAT: 17.0, CONF_ECO_COOL: 30.0})
        heat, cool, _, _, _ = coord._compute(
            ScheduleMode.ECO, PresenceState.AWAY, _solar(False), None
        )
        assert heat == pytest.approx(17.0)
        assert cool == pytest.approx(30.0)


# ── Integration: _async_update_data ──────────────────────────────────────────


class TestAsyncUpdateData:
    async def test_returns_coordinator_data(self, sample_solar_state: SolarState) -> None:
        coord = _make_coordinator()
        coord._schedule = MagicMock()
        coord._schedule.evaluate.return_value = ScheduleMode.COMFORT
        coord._presence = MagicMock()
        coord._presence.evaluate.return_value = PresenceState.HOME
        coord._presence.minutes_since_last_seen.return_value = None
        coord._solar = MagicMock()
        coord._solar.evaluate.return_value = sample_solar_state

        data = await coord._async_update_data()

        assert isinstance(data, CoordinatorData)
        assert data.schedule_mode == ScheduleMode.COMFORT
        assert data.effective_mode == ScheduleMode.COMFORT
        assert data.presence == PresenceState.HOME
        assert data.solar is sample_solar_state
        assert data.hvac_mode == HVACMode.HEAT_COOL

    async def test_raises_update_failed_on_entity_read_error(self) -> None:
        coord = _make_coordinator()
        coord._schedule = MagicMock()
        coord._schedule.evaluate.side_effect = RuntimeError("state read failed")

        with pytest.raises(UpdateFailed):
            await coord._async_update_data()
