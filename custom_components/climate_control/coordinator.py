"""DataUpdateCoordinator — schedule/presence/solar decision engine for Climate Control."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.climate.const import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_COMFORT_COOL,
    CONF_COMFORT_HEAT,
    CONF_COMFORT_SCHEDULE,
    CONF_ECO_COOL,
    CONF_ECO_HEAT,
    CONF_ECO_SCHEDULE,
    CONF_PRECONDITION_MIN,
    CONF_PRESENCE_SENSORS,
    CONF_SOLAR_POWER_SENSOR,
    CONF_UPDATE_INTERVAL,
    CONF_WEATHER_ENTITY,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_ECO_COOL,
    DEFAULT_ECO_HEAT,
    DEFAULT_PRECONDITION,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SOLAR_HIGH_W_THRESHOLD,
    SOLAR_LOW_W_THRESHOLD,
    SOLAR_OFFSET_HIGH,
    SOLAR_OFFSET_LOW,
)
from .presence import PresenceEvaluator, PresenceState
from .schedule import ScheduleEvaluator, ScheduleMode
from .solar import SolarAdvisor, SolarState

_LOGGER = logging.getLogger(__name__)


@dataclass
class CoordinatorData:
    """Snapshot of computed state produced by each coordinator refresh."""

    schedule_mode:        ScheduleMode
    presence:             PresenceState
    solar:                SolarState
    effective_mode:       ScheduleMode    # after presence override
    target_setpoint_heat: float           # °C
    target_setpoint_cool: float           # °C, after solar offset
    hvac_mode:            HVACMode
    reason:               str


class ClimateControlCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Reads HA entity states and runs the setpoint algorithm.

    One coordinator per config entry. Entities must only read from
    ``coordinator.data`` and never perform their own I/O.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry

        # For editable entity fields, prefer options (set via options flow) over data.
        def _ev(key: str, default: object = None) -> object:
            return entry.options.get(key, entry.data.get(key, default))

        self._schedule = ScheduleEvaluator(
            hass,
            _ev(CONF_COMFORT_SCHEDULE),  # type: ignore[arg-type]
            _ev(CONF_ECO_SCHEDULE),       # type: ignore[arg-type]
        )
        self._presence = PresenceEvaluator(
            hass,
            _ev(CONF_PRESENCE_SENSORS, []),  # type: ignore[arg-type]
        )
        self._solar = SolarAdvisor(
            hass,
            _ev(CONF_SOLAR_POWER_SENSOR),    # type: ignore[arg-type]
            _ev(CONF_WEATHER_ENTITY),         # type: ignore[arg-type]
        )

        interval_minutes: int = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval_minutes),
        )

    # ── DataUpdateCoordinator protocol ───────────────────────────────────────

    async def _async_update_data(self) -> CoordinatorData:
        """Read HA entity states and compute setpoints."""
        try:
            schedule_mode = self._schedule.evaluate()
            presence      = self._presence.evaluate()
            solar_state   = self._solar.evaluate()
            minutes_away  = self._presence.minutes_since_last_seen()
        except Exception as exc:
            raise UpdateFailed(f"Error reading entity states: {exc}") from exc

        heat_sp, cool_sp, hvac_mode, effective_mode, reason = self._compute(
            schedule_mode, presence, solar_state, minutes_away
        )

        _LOGGER.debug(
            "Update: schedule=%s presence=%s effective=%s heat=%.1f cool=%.1f | %s",
            schedule_mode.value,
            presence.value,
            effective_mode.value,
            heat_sp,
            cool_sp,
            reason,
        )

        return CoordinatorData(
            schedule_mode=schedule_mode,
            presence=presence,
            solar=solar_state,
            effective_mode=effective_mode,
            target_setpoint_heat=heat_sp,
            target_setpoint_cool=cool_sp,
            hvac_mode=hvac_mode,
            reason=reason,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_option(self, key: str, default: float | int) -> float:
        """Return option from options flow, falling back to data then default."""
        return float(
            self._entry.options.get(key, self._entry.data.get(key, default))
        )

    def _compute(
        self,
        schedule_mode: ScheduleMode,
        presence: PresenceState,
        solar_state: SolarState,
        minutes_away: float | None,
    ) -> tuple[float, float, HVACMode, ScheduleMode, str]:
        """Compute setpoints; return (heat, cool, hvac_mode, effective_mode, reason)."""
        comfort_heat = self._get_option(CONF_COMFORT_HEAT, DEFAULT_COMFORT_HEAT)
        comfort_cool = self._get_option(CONF_COMFORT_COOL, DEFAULT_COMFORT_COOL)
        eco_heat     = self._get_option(CONF_ECO_HEAT, DEFAULT_ECO_HEAT)
        eco_cool     = self._get_option(CONF_ECO_COOL, DEFAULT_ECO_COOL)
        precondition = int(self._get_option(CONF_PRECONDITION_MIN, DEFAULT_PRECONDITION))

        # ── Step 1: OFF is absolute — no overrides ────────────────────────────
        if schedule_mode == ScheduleMode.OFF:
            return (
                comfort_heat, comfort_cool,
                HVACMode.OFF,
                ScheduleMode.OFF,
                "Schedule: off",
            )

        # ── Step 2: presence override ─────────────────────────────────────────
        away = presence in (PresenceState.AWAY, PresenceState.UNKNOWN)
        approaching_return = (
            away
            and minutes_away is not None
            and minutes_away <= precondition
        )

        if schedule_mode == ScheduleMode.COMFORT and away:
            effective_mode = ScheduleMode.ECO
            reason = "Schedule comfort, but nobody home → eco"

        elif schedule_mode == ScheduleMode.ECO and presence == PresenceState.HOME:
            effective_mode = ScheduleMode.COMFORT
            reason = "Schedule eco, but someone home → comfort"

        elif schedule_mode == ScheduleMode.ECO and approaching_return:
            effective_mode = ScheduleMode.COMFORT
            reason = "Pre-conditioning — returning soon"

        else:
            effective_mode = schedule_mode
            reason = f"Schedule: {schedule_mode.value}"

        # ── Step 3: base setpoints ────────────────────────────────────────────
        if effective_mode == ScheduleMode.COMFORT:
            base_heat, base_cool = comfort_heat, comfort_cool
        else:
            base_heat, base_cool = eco_heat, eco_cool

        # ── Step 4: solar offset (cooling only) ──────────────────────────────
        solar_offset = 0.0
        if solar_state.solar_enabled:
            if solar_state.current_output_w > SOLAR_HIGH_W_THRESHOLD:
                solar_offset = SOLAR_OFFSET_HIGH
                reason += (
                    f" | High inverter output ({solar_state.current_output_w:.0f} W)"
                    f" → pre-cool -{SOLAR_OFFSET_HIGH}°C"
                )
            elif solar_state.current_output_w > SOLAR_LOW_W_THRESHOLD:
                solar_offset = SOLAR_OFFSET_LOW
                reason += (
                    f" | Moderate inverter output ({solar_state.current_output_w:.0f} W)"
                    f" → pre-cool -{SOLAR_OFFSET_LOW}°C"
                )
            elif solar_state.lookahead_sunny:
                solar_offset = SOLAR_OFFSET_LOW
                reason += f" | Sunny forecast incoming → pre-cool -{SOLAR_OFFSET_LOW}°C"

        return (
            base_heat,
            base_cool - solar_offset,
            HVACMode.HEAT_COOL,
            effective_mode,
            reason,
        )
