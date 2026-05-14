"""Presence / occupancy detection for Climate Control."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import Enum

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class PresenceState(Enum):
    """Occupancy state as determined by the configured binary sensors."""

    HOME = "home"
    AWAY = "away"
    UNKNOWN = "unknown"


class PresenceEvaluator:
    """Evaluates occupancy from one or more HA binary_sensor entities.

    A sensor with state ``"on"`` is treated as *home*.  All others (``"off"``,
    ``"unavailable"``, ``None``) are treated as *away* or *unknown*.
    """

    def __init__(self, hass: HomeAssistant, sensor_entity_ids: list[str]) -> None:
        self._hass = hass
        self._entity_ids = sensor_entity_ids
        self._last_seen: datetime | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def evaluate(self) -> PresenceState:
        """Return the current ``PresenceState`` based on all configured sensors.

        Any sensor reporting ``"on"`` → HOME.
        All sensors reporting ``"off"`` → AWAY.
        All sensors unavailable / unconfigured → UNKNOWN.
        """
        if not self._entity_ids:
            return PresenceState.UNKNOWN

        states = [self._hass.states.get(eid) for eid in self._entity_ids]
        valid_states = [s for s in states if s is not None]

        if not valid_states:
            return PresenceState.UNKNOWN

        if any(s.state == "on" for s in valid_states):
            self._last_seen = datetime.now(UTC)
            return PresenceState.HOME

        return PresenceState.AWAY

    def minutes_since_last_seen(self) -> float | None:
        """Return minutes since any presence sensor was last ``on``.

        Returns ``None`` if no *home* event has been recorded this session.
        """
        if self._last_seen is None:
            return None
        delta = datetime.now(UTC) - self._last_seen
        return delta.total_seconds() / 60
