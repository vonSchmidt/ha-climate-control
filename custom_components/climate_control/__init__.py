"""Climate Control integration setup."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_LATITUDE, CONF_LONGITUDE, DOMAIN, PLATFORMS
from .coordinator import ClimateControlCoordinator
from .solar import SolarWeatherClient

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

type ClimateControlConfigEntry = ConfigEntry[ClimateControlCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> bool:
    """Set up Climate Control from a config entry."""
    session = async_get_clientsession(hass)

    solar_client = SolarWeatherClient(
        session=session,
        latitude=entry.data[CONF_LATITUDE],
        longitude=entry.data[CONF_LONGITUDE],
    )

    coordinator = ClimateControlCoordinator(hass, entry, solar_client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(p) for p in PLATFORMS]
    )

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(
        entry, [Platform(p) for p in PLATFORMS]
    )


async def async_reload_entry(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
