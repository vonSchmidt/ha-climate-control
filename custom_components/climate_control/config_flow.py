"""Config flow for Climate Control integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_COMFORT_COOL,
    CONF_COMFORT_HEAT,
    CONF_ECO_COOL,
    CONF_ECO_HEAT,
    CONF_PRECONDITION_MIN,
    CONF_PRESENCE_SENSORS,
    CONF_TARGET_ENTITY,
    CONF_TEMP_SENSOR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_COMFORT_COOL,
    DEFAULT_COMFORT_HEAT,
    DEFAULT_ECO_COOL,
    DEFAULT_ECO_HEAT,
    DEFAULT_PRECONDITION,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class ClimateControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Climate Control."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    # ── Step 1 — target entity + sensors + location ───────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_presence()

        schema = vol.Schema(
            {
                vol.Required(CONF_TARGET_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Required(CONF_TEMP_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
                vol.Required(
                    CONF_LATITUDE,
                    default=self.hass.config.latitude,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step=0.0001)
                ),
                vol.Required(
                    CONF_LONGITUDE,
                    default=self.hass.config.longitude,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step=0.0001)
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ── Step 2 — presence sensors ─────────────────────────────────────────────

    async def async_step_presence(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_comfort()

        schema = vol.Schema(
            {
                vol.Optional(CONF_PRESENCE_SENSORS, default=[]): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="binary_sensor",
                        device_class=["presence", "occupancy", "motion"],
                        multiple=True,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="presence", data_schema=schema)

    # ── Step 3 — comfort / eco setpoints ─────────────────────────────────────

    async def async_step_comfort(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="Climate Control", data=self._data)

        schema = vol.Schema(
            {
                vol.Required(CONF_COMFORT_HEAT, default=DEFAULT_COMFORT_HEAT): vol.Coerce(float),
                vol.Required(CONF_COMFORT_COOL, default=DEFAULT_COMFORT_COOL): vol.Coerce(float),
                vol.Required(CONF_ECO_HEAT, default=DEFAULT_ECO_HEAT): vol.Coerce(float),
                vol.Required(CONF_ECO_COOL, default=DEFAULT_ECO_COOL): vol.Coerce(float),
                vol.Required(CONF_PRECONDITION_MIN, default=DEFAULT_PRECONDITION): vol.Coerce(int),
                vol.Required(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.Coerce(int),
            }
        )

        return self.async_show_form(step_id="comfort", data_schema=schema)

    # ── Options flow entry point ───────────────────────────────────────────────

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ClimateControlOptionsFlow:
        return ClimateControlOptionsFlow(config_entry)


class ClimateControlOptionsFlow(OptionsFlow):
    """Allow editing all settings post-setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._entry.options or self._entry.data

        schema = vol.Schema(
            {
                vol.Required(CONF_COMFORT_HEAT, default=current.get(CONF_COMFORT_HEAT, DEFAULT_COMFORT_HEAT)): vol.Coerce(float),
                vol.Required(CONF_COMFORT_COOL, default=current.get(CONF_COMFORT_COOL, DEFAULT_COMFORT_COOL)): vol.Coerce(float),
                vol.Required(CONF_ECO_HEAT, default=current.get(CONF_ECO_HEAT, DEFAULT_ECO_HEAT)): vol.Coerce(float),
                vol.Required(CONF_ECO_COOL, default=current.get(CONF_ECO_COOL, DEFAULT_ECO_COOL)): vol.Coerce(float),
                vol.Required(CONF_PRECONDITION_MIN, default=current.get(CONF_PRECONDITION_MIN, DEFAULT_PRECONDITION)): vol.Coerce(int),
                vol.Required(CONF_UPDATE_INTERVAL, default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)): vol.Coerce(int),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
