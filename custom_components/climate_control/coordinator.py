"""DataUpdateCoordinator — main decision engine for Climate Control."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components.climate.const import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_COMFORT_COOL,
    CONF_COMFORT_HEAT,
    CONF_ECO_COOL,
    CONF_ECO_HEAT,
    CONF_PRECONDITION_MIN,
    CONF_PRESENCE_SENSORS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_ECO_COOL,
    DEFAULT_ECO_HEAT,
    DEFAULT_PRECONDITION,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SOLAR_HIGH_THRESHOLD,
    SOLAR_LOW_THRESHOLD,
    SOLAR_OFFSET_HIGH,
    SOLAR_OFFSET_LOW,
    SOLAR_OFFSET_NONE,
)
from .presence import PresenceEvaluator, PresenceState
from .solar import SolarData, SolarWeatherClient

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


@dataclass
class CoordinatorData:
    """Snapshot of computed state produced by each coordinator refresh."""

    presence: PresenceState
    solar: SolarData
    current_irradiance: float
    target_setpoint_heat: float
    target_setpoint_cool: float
    hvac_mode: HVACMode
    reason: str


class ClimateControlCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Fetches solar/weather data and runs the setpoint algorithm.

    One coordinator per config entry.  Entities must only read from
    ``coordinator.data`` and never perform their own I/O.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        solar_client: SolarWeatherClient,
    ) -> None:
        self._entry = entry
        self._solar_client = solar_client
        self._presence = PresenceEvaluator(
            hass,
            entry.data.get(CONF_PRESENCE_SENSORS, []),
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
        """Fetch fresh data and compute setpoints."""
        try:
            solar_data = await self._solar_client.async_fetch()
        except Exception as exc:
            raise UpdateFailed(f"Error fetching Open-Meteo data: {exc}") from exc

        irradiance = SolarWeatherClient.current_irradiance(solar_data)
        presence   = self._presence.evaluate()

        heat_sp, cool_sp, reason = self._compute_setpoints(irradiance, presence)
        hvac_mode = self._decide_hvac_mode(heat_sp, cool_sp)

        return CoordinatorData(
            presence=presence,
            solar=solar_data,
            current_irradiance=irradiance,
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

    def _compute_setpoints(
        self, irradiance: float, presence: PresenceState
    ) -> tuple[float, float, str]:
        """Apply the setpoint algorithm and return (heat_sp, cool_sp, reason)."""
        comfort_heat    = self._get_option(CONF_COMFORT_HEAT, DEFAULT_COMFORT_HEAT)
        comfort_cool    = self._get_option(CONF_COMFORT_COOL, DEFAULT_COMFORT_COOL)
        eco_heat        = self._get_option(CONF_ECO_HEAT, DEFAULT_ECO_HEAT)
        eco_cool        = self._get_option(CONF_ECO_COOL, DEFAULT_ECO_COOL)
        precondition    = int(self._get_option(CONF_PRECONDITION_MIN, DEFAULT_PRECONDITION))

        minutes_away = self._presence.minutes_since_last_seen()
        approaching_return = (
            minutes_away is not None and minutes_away <= precondition
        )

        if presence == PresenceState.HOME:
            base_heat, base_cool = comfort_heat, comfort_cool
            reason = "Occupied — comfort setpoints active"
        elif approaching_return:
            base_heat, base_cool = comfort_heat, comfort_cool
            reason = (
                f"Away but returning soon (<{precondition} min) — pre-conditioning"
            )
        else:
            base_heat, base_cool = eco_heat, eco_cool
            reason = "Away — eco setpoints active"

        # Solar adjustment on cooling target only
        if irradiance > SOLAR_HIGH_THRESHOLD:
            solar_offset = SOLAR_OFFSET_HIGH
            reason += f" | High solar ({irradiance:.0f} W/m²) → pre-cool -{solar_offset}°C"
        elif irradiance > SOLAR_LOW_THRESHOLD:
            solar_offset = SOLAR_OFFSET_LOW
            reason += f" | Moderate solar ({irradiance:.0f} W/m²) → pre-cool -{solar_offset}°C"
        else:
            solar_offset = SOLAR_OFFSET_NONE

        adjusted_cool = base_cool - solar_offset

        _LOGGER.debug(
            "Setpoints → heat=%.1f cool=%.1f | %s", base_heat, adjusted_cool, reason
        )
        return base_heat, adjusted_cool, reason

    @staticmethod
    def _decide_hvac_mode(heat_sp: float, cool_sp: float) -> HVACMode:
        """Placeholder — actual mode is driven by the target climate entity."""
        return HVACMode.HEAT_COOL
