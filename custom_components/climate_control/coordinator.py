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
    CONF_ECO_OFFSET,
    CONF_ECO_SCHEDULE,
    CONF_PRECONDITION_MIN,
    CONF_PRESENCE_SENSORS,
    CONF_SOLAR_POWER_SENSOR,
    CONF_TARGET_ENTITY,
    CONF_TEMP_SENSOR,
    CONF_UPDATE_INTERVAL,
    CONF_WEATHER_ENTITY,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_ECO_OFFSET,
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

    schedule_mode: ScheduleMode
    presence: PresenceState
    solar: SolarState
    effective_mode: ScheduleMode  # after presence override
    target_setpoint_heat: float  # °C
    target_setpoint_cool: float  # °C, after solar offset
    hvac_mode: HVACMode
    reason: str


class ClimateControlCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Reads HA entity states and runs the setpoint algorithm.

    One coordinator per config entry. Entities must only read from
    ``coordinator.data`` and never perform their own I/O.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self._override_hvac_mode: HVACMode | None = None

        # For editable entity fields, prefer options (set via options flow) over data.
        def _ev(key: str, default: object = None) -> object:
            return entry.options.get(key, entry.data.get(key, default))

        self._schedule = ScheduleEvaluator(
            hass,
            _ev(CONF_COMFORT_SCHEDULE),  # type: ignore[arg-type]
            _ev(CONF_ECO_SCHEDULE),  # type: ignore[arg-type]
        )
        self._presence = PresenceEvaluator(
            hass,
            _ev(CONF_PRESENCE_SENSORS, []),  # type: ignore[arg-type]
        )
        self._solar = SolarAdvisor(
            hass,
            _ev(CONF_SOLAR_POWER_SENSOR),  # type: ignore[arg-type]
            _ev(CONF_WEATHER_ENTITY),  # type: ignore[arg-type]
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

    # ── Manual override ───────────────────────────────────────────────────────

    def set_manual_override(self, hvac_mode: HVACMode) -> None:
        """Store a manual mode; cleared when user sets OFF (returns to schedule)."""
        if hvac_mode == HVACMode.OFF:
            self._override_hvac_mode = None
            _LOGGER.info("Manual override cleared — returning to schedule control")
        else:
            self._override_hvac_mode = hvac_mode
            _LOGGER.info("Manual override → %s", hvac_mode.value)

    # ── DataUpdateCoordinator protocol ───────────────────────────────────────

    async def _async_update_data(self) -> CoordinatorData:
        """Read HA entity states and compute setpoints."""
        try:
            schedule_mode = self._schedule.evaluate()
            presence = self._presence.evaluate()
            solar_state = self._solar.evaluate()
            minutes_away = self._presence.minutes_since_last_seen()
        except Exception as exc:
            raise UpdateFailed(f"Error reading entity states: {exc}") from exc

        current_temp = self._read_temperature()

        heat_sp, cool_sp, hvac_mode, effective_mode, reason = self._compute(
            schedule_mode, presence, solar_state, minutes_away, current_temp
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

        await self._apply_to_target(hvac_mode, heat_sp, cool_sp)

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

    def _read_temperature(self) -> float | None:
        """Read current indoor temperature from the configured sensor."""
        sensor_id: str | None = self._entry.data.get(CONF_TEMP_SENSOR)
        if not sensor_id:
            return None
        state = self.hass.states.get(sensor_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def map_hvac_mode(self, hvac_mode: HVACMode, target: str) -> HVACMode:
        """Return the best equivalent HVACMode the target device actually supports.

        Handles devices that expose 'auto' instead of 'heat_cool'.
        """
        if hvac_mode == HVACMode.OFF:
            return HVACMode.OFF
        state = self.hass.states.get(target)
        if state is None:
            return hvac_mode
        supported: list[str] = state.attributes.get("hvac_modes", [])
        if hvac_mode in supported:
            return hvac_mode
        if hvac_mode == HVACMode.HEAT_COOL and HVACMode.AUTO in supported:
            return HVACMode.AUTO
        return hvac_mode

    async def _apply_to_target(self, hvac_mode: HVACMode, heat_sp: float, cool_sp: float) -> None:
        """Push computed mode and setpoints to the real AC entity, only on change."""
        target: str | None = self._entry.data.get(CONF_TARGET_ENTITY)
        if not target:
            return

        mapped_mode = self.map_hvac_mode(hvac_mode, target)

        prev = self.data  # None on first run
        mode_changed = prev is None or prev.hvac_mode != hvac_mode
        sp_changed = prev is None or (
            prev.target_setpoint_heat != heat_sp or prev.target_setpoint_cool != cool_sp
        )

        if not mode_changed and not sp_changed:
            return

        try:
            if mode_changed:
                await self.hass.services.async_call(
                    "climate",
                    "set_hvac_mode",
                    {"entity_id": target, "hvac_mode": mapped_mode},
                    blocking=True,
                )
                _LOGGER.debug("%s hvac_mode → %s (was %s)", target, mapped_mode, hvac_mode)

            if sp_changed and hvac_mode != HVACMode.OFF:
                if hvac_mode == HVACMode.HEAT:
                    temp_payload: dict[str, object] = {"entity_id": target, "temperature": heat_sp}
                elif hvac_mode == HVACMode.COOL:
                    temp_payload = {"entity_id": target, "temperature": cool_sp}
                else:
                    temp_payload = {
                        "entity_id": target,
                        "target_temp_low": heat_sp,
                        "target_temp_high": cool_sp,
                    }
                await self.hass.services.async_call(
                    "climate", "set_temperature", temp_payload, blocking=True
                )
                _LOGGER.debug("Set %s temperature → heat=%.1f cool=%.1f", target, heat_sp, cool_sp)
        except Exception as exc:
            _LOGGER.error("Failed to update target entity %s: %s", target, exc)

    def _get_option(self, key: str, default: float | int) -> float:
        """Return option from options flow, falling back to data then default."""
        return float(self._entry.options.get(key, self._entry.data.get(key, default)))

    def _compute(
        self,
        schedule_mode: ScheduleMode,
        presence: PresenceState,
        solar_state: SolarState,
        minutes_away: float | None,
        current_temp: float | None,
    ) -> tuple[float, float, HVACMode, ScheduleMode, str]:
        """Compute setpoints; return (heat, cool, hvac_mode, effective_mode, reason)."""
        comfort_heat = self._get_option(CONF_COMFORT_HEAT, DEFAULT_COMFORT_HEAT)
        comfort_cool = self._get_option(CONF_COMFORT_COOL, DEFAULT_COMFORT_COOL)
        eco_offset = self._get_option(CONF_ECO_OFFSET, DEFAULT_ECO_OFFSET)
        eco_heat = comfort_heat - eco_offset
        eco_cool = comfort_cool + eco_offset
        precondition = int(self._get_option(CONF_PRECONDITION_MIN, DEFAULT_PRECONDITION))

        # ── Manual override: beats schedule, presence, and temperature logic ──
        if self._override_hvac_mode is not None:
            return (
                comfort_heat,
                comfort_cool,
                self._override_hvac_mode,
                ScheduleMode.COMFORT,
                f"Manual override: {self._override_hvac_mode.value}",
            )

        # ── Step 1: OFF is absolute — no overrides ────────────────────────────
        if schedule_mode == ScheduleMode.OFF:
            return (
                comfort_heat,
                comfort_cool,
                HVACMode.OFF,
                ScheduleMode.OFF,
                "Schedule: off",
            )

        # ── Step 2: presence override ─────────────────────────────────────────
        away = presence in (PresenceState.AWAY, PresenceState.UNKNOWN)
        approaching_return = away and minutes_away is not None and minutes_away <= precondition

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

        cool_sp = base_cool - solar_offset

        # ── Step 5: temperature-based mode selection ──────────────────────────
        if current_temp is None:
            hvac_mode = HVACMode.OFF
            reason += " | No temperature reading → off"
        elif current_temp < base_heat:
            hvac_mode = HVACMode.HEAT
            reason += f" | {current_temp:.1f}°C < {base_heat:.1f}°C → heat"
        elif current_temp > cool_sp:
            hvac_mode = HVACMode.COOL
            reason += f" | {current_temp:.1f}°C > {cool_sp:.1f}°C → cool"
        else:
            hvac_mode = HVACMode.OFF
            reason += f" | {current_temp:.1f}°C in range [{base_heat:.1f}–{cool_sp:.1f}°C] → off"

        return (base_heat, cool_sp, hvac_mode, effective_mode, reason)
