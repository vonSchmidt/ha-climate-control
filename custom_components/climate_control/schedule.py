"""Schedule layer for Climate Control — reads native HA schedule.* entities."""

from __future__ import annotations

import logging
from enum import Enum

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class ScheduleMode(Enum):
    """Operating mode derived from the two configured schedule entities."""

    COMFORT = "comfort"
    ECO = "eco"
    OFF = "off"


class ScheduleEvaluator:
    """Reads two HA schedule.* entities and returns the active ScheduleMode.

    Priority: COMFORT wins if both schedules are on simultaneously.
    An unavailable or missing entity is treated as ``"off"`` with a WARNING.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        comfort_entity: str,
        eco_entity: str,
    ) -> None:
        self._hass = hass
        self._comfort_entity = comfort_entity
        self._eco_entity = eco_entity

    def evaluate(self) -> ScheduleMode:
        """Return the current ScheduleMode based on the configured schedule entities."""
        comfort_state = self._read_entity(self._comfort_entity)
        eco_state = self._read_entity(self._eco_entity)

        if comfort_state == "on":
            return ScheduleMode.COMFORT
        if eco_state == "on":
            return ScheduleMode.ECO
        return ScheduleMode.OFF

    def _read_entity(self, entity_id: str) -> str:
        """Return the state string of an entity, treating unavailable/missing as 'off'."""
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            _LOGGER.warning("Schedule entity %s is unavailable; treating as 'off'", entity_id)
            return "off"
        return state.state
