"""Climate entity for Climate Control integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_AREA, CONF_TEMP_SENSOR
from .coordinator import ClimateControlCoordinator, CoordinatorData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Climate Control climate entity from a config entry."""
    coordinator: ClimateControlCoordinator = entry.runtime_data
    async_add_entities([ClimateControlEntity(coordinator, entry)], update_before_add=True)


class ClimateControlEntity(CoordinatorEntity[ClimateControlCoordinator], ClimateEntity):
    """Represents the climate_control virtual thermostat.

    Reads setpoints from the coordinator and never performs its own I/O.
    """

    _attr_has_entity_name = True
    _attr_name = "Climate Control"
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: ClimateControlCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_climate"

    # ── Properties derived from coordinator data ──────────────────────────────

    @property
    def suggested_area(self) -> str | None:
        """Return area name so HA auto-assigns this entity on first registration."""
        area_id: str | None = self._entry.data.get(CONF_AREA)
        if not area_id:
            return None
        area = ar.async_get(self.hass).async_get_area(area_id)
        return area.name if area else None

    @property
    def _data(self) -> CoordinatorData:
        return self.coordinator.data

    @property
    def hvac_mode(self) -> HVACMode:
        return self._data.hvac_mode

    @property
    def target_temperature_low(self) -> float:
        """Heating setpoint."""
        return self._data.target_setpoint_heat

    @property
    def target_temperature_high(self) -> float:
        """Cooling setpoint."""
        return self._data.target_setpoint_cool

    @property
    def current_temperature(self) -> float | None:
        """Indoor temperature from the configured sensor."""
        sensor_id: str | None = self._entry.data.get(CONF_TEMP_SENSOR)
        if sensor_id is None:
            return None
        state = self.hass.states.get(sensor_id)
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "schedule_mode": self._data.schedule_mode.value,
            "effective_mode": self._data.effective_mode.value,
            "presence": self._data.presence.value,
            "solar_output_w": self._data.solar.current_output_w,
            "solar_lookahead_sunny": self._data.solar.lookahead_sunny,
            "reason": self._data.reason,
        }

    # ── Service call handlers ─────────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Store manual override then refresh; OFF clears override and returns to schedule."""
        self.coordinator.set_manual_override(hvac_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Manual setpoint override is a no-op; coordinator owns setpoints."""
        _LOGGER.warning(
            "Manual temperature set ignored — coordinator controls setpoints. "
            "Adjust comfort/eco values via integration options."
        )
