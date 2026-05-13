"""Config flow for Climate Control integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

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
    CONF_TARGET_ENTITY,
    CONF_TEMP_SENSOR,
    CONF_UPDATE_INTERVAL,
    CONF_WEATHER_ENTITY,
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

    # ── Step 1 — target devices ───────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_schedule()

        schema = vol.Schema(
            {
                vol.Required(CONF_TARGET_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Required(CONF_TEMP_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    # ── Step 2 — schedule entities ────────────────────────────────────────────

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONF_COMFORT_SCHEDULE] == user_input[CONF_ECO_SCHEDULE]:
                errors["base"] = "same_entity"
            else:
                self._data.update(user_input)
                return await self.async_step_presence()

        schema = vol.Schema(
            {
                vol.Required(CONF_COMFORT_SCHEDULE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="schedule")
                ),
                vol.Required(CONF_ECO_SCHEDULE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="schedule")
                ),
            }
        )

        return self.async_show_form(step_id="schedule", data_schema=schema, errors=errors)

    # ── Step 3 — presence & pre-conditioning ─────────────────────────────────

    async def async_step_presence(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_settings()

        schema = vol.Schema(
            {
                vol.Optional(CONF_PRESENCE_SENSORS, default=[]): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="binary_sensor",
                        device_class=["presence", "occupancy", "motion"],
                        multiple=True,
                    )
                ),
                vol.Required(
                    CONF_PRECONDITION_MIN, default=DEFAULT_PRECONDITION
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=120, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )

        return self.async_show_form(step_id="presence", data_schema=schema)

    # ── Step 4 — setpoints & solar ────────────────────────────────────────────

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_setpoints(user_input)
            if not errors:
                self._data.update(user_input)
                return self.async_create_entry(title="Climate Control", data=self._data)

        schema = vol.Schema(
            {
                vol.Required(CONF_COMFORT_HEAT, default=DEFAULT_COMFORT_HEAT): vol.Coerce(float),
                vol.Required(CONF_COMFORT_COOL, default=DEFAULT_COMFORT_COOL): vol.Coerce(float),
                vol.Required(CONF_ECO_HEAT, default=DEFAULT_ECO_HEAT): vol.Coerce(float),
                vol.Required(CONF_ECO_COOL, default=DEFAULT_ECO_COOL): vol.Coerce(float),
                vol.Optional(CONF_SOLAR_POWER_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
                ),
                vol.Required(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=60, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )

        return self.async_show_form(step_id="settings", data_schema=schema, errors=errors)

    # ── Options flow entry point ──────────────────────────────────────────────

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ClimateControlOptionsFlow:
        return ClimateControlOptionsFlow(config_entry)


class ClimateControlOptionsFlow(OptionsFlow):
    """Allow editing all editable settings post-setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_setpoints(user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        current = self._entry.options or self._entry.data

        # Comfort/eco schedule fields
        schedule_schema = {
            vol.Required(
                CONF_COMFORT_SCHEDULE,
                default=current.get(CONF_COMFORT_SCHEDULE, ""),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="schedule")),
            vol.Required(
                CONF_ECO_SCHEDULE,
                default=current.get(CONF_ECO_SCHEDULE, ""),
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="schedule")),
        }

        # Presence fields
        presence_schema = {
            vol.Optional(
                CONF_PRESENCE_SENSORS,
                default=current.get(CONF_PRESENCE_SENSORS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="binary_sensor",
                    device_class=["presence", "occupancy", "motion"],
                    multiple=True,
                )
            ),
            vol.Required(
                CONF_PRECONDITION_MIN,
                default=current.get(CONF_PRECONDITION_MIN, DEFAULT_PRECONDITION),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=120, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
        }

        # Setpoints + solar fields
        settings_schema = {
            vol.Required(
                CONF_COMFORT_HEAT, default=current.get(CONF_COMFORT_HEAT, DEFAULT_COMFORT_HEAT)
            ): vol.Coerce(float),
            vol.Required(
                CONF_COMFORT_COOL, default=current.get(CONF_COMFORT_COOL, DEFAULT_COMFORT_COOL)
            ): vol.Coerce(float),
            vol.Required(
                CONF_ECO_HEAT, default=current.get(CONF_ECO_HEAT, DEFAULT_ECO_HEAT)
            ): vol.Coerce(float),
            vol.Required(
                CONF_ECO_COOL, default=current.get(CONF_ECO_COOL, DEFAULT_ECO_COOL)
            ): vol.Coerce(float),
            vol.Optional(CONF_SOLAR_POWER_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=current.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5, max=60, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
        }

        schema = vol.Schema({**schedule_schema, **presence_schema, **settings_schema})
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)


# ── Shared validation ─────────────────────────────────────────────────────────


def _validate_setpoints(data: dict[str, Any]) -> dict[str, str]:
    """Return an errors dict (empty = valid) for the setpoint fields."""
    errors: dict[str, str] = {}

    comfort_heat = float(data.get(CONF_COMFORT_HEAT, DEFAULT_COMFORT_HEAT))
    comfort_cool = float(data.get(CONF_COMFORT_COOL, DEFAULT_COMFORT_COOL))
    eco_heat     = float(data.get(CONF_ECO_HEAT, DEFAULT_ECO_HEAT))
    eco_cool     = float(data.get(CONF_ECO_COOL, DEFAULT_ECO_COOL))

    if comfort_heat >= comfort_cool:
        errors["base"] = "comfort_heat_gte_cool"
    elif eco_heat > comfort_heat:
        errors["base"] = "eco_heat_gt_comfort"
    elif eco_cool < comfort_cool:
        errors["base"] = "eco_cool_lt_comfort"

    return errors
