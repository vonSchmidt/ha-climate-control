"""Solar input layer for Climate Control — reads HA sensor.* and weather.* entities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from homeassistant.core import HomeAssistant

from .const import SOLAR_LOOKAHEAD_HOURS, SUNNY_CONDITIONS

_LOGGER = logging.getLogger(__name__)


@dataclass
class SolarState:
    """Snapshot of current solar conditions derived from HA entity states."""

    current_output_w: float  # 0.0 when inverter sensor absent or unavailable
    lookahead_sunny: bool  # True when a sunny forecast slot is within the look-ahead window
    solar_enabled: bool  # False when neither source is configured
    source_note: str  # human-readable description of active sources


class SolarAdvisor:
    """Evaluates solar conditions from HA entity state reads.

    All reads are synchronous ``hass.states.get()`` calls — no async I/O.
    Both sources are optional; if neither is configured ``solar_enabled`` is
    ``False`` and the coordinator applies no solar offset.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        power_sensor: str | None,
        weather_entity: str | None,
    ) -> None:
        self._hass = hass
        self._power_sensor = power_sensor
        self._weather_entity = weather_entity

    def evaluate(self) -> SolarState:
        """Return a ``SolarState`` snapshot based on current HA entity states."""
        if self._power_sensor is None and self._weather_entity is None:
            return SolarState(
                current_output_w=0.0,
                lookahead_sunny=False,
                solar_enabled=False,
                source_note="disabled",
            )

        current_output_w = self._read_inverter()
        lookahead_sunny = self._read_forecast()

        sources: list[str] = []
        if self._power_sensor is not None:
            sources.append("inverter")
        if self._weather_entity is not None:
            sources.append("forecast")
        source_note = "+".join(sources)

        return SolarState(
            current_output_w=current_output_w,
            lookahead_sunny=lookahead_sunny,
            solar_enabled=True,
            source_note=source_note,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _read_inverter(self) -> float:
        """Return current inverter output in W, or 0.0 on unavailability."""
        if self._power_sensor is None:
            return 0.0

        state = self._hass.states.get(self._power_sensor)
        if state is None or state.state in ("unavailable", "unknown"):
            _LOGGER.warning("Solar power sensor %s unavailable; assuming 0 W", self._power_sensor)
            return 0.0

        try:
            value = float(state.state)
        except ValueError:
            _LOGGER.warning(
                "Solar power sensor %s has non-numeric state %r; assuming 0 W",
                self._power_sensor,
                state.state,
            )
            return 0.0

        unit = state.attributes.get("unit_of_measurement", "W")
        if unit in ("kW", "kw"):
            value *= 1000.0

        return value

    def _read_forecast(self) -> bool:
        """Return True when a sunny condition is forecast within the look-ahead window."""
        if self._weather_entity is None:
            return False

        state = self._hass.states.get(self._weather_entity)
        if state is None or state.state in ("unavailable", "unknown"):
            _LOGGER.warning(
                "Weather entity %s unavailable; look-ahead disabled", self._weather_entity
            )
            return False

        forecast: list[dict] = state.attributes.get("forecast", [])
        now = datetime.now(UTC)

        for slot in forecast:
            raw_dt = slot.get("datetime")
            if raw_dt is None:
                continue
            try:
                slot_dt = datetime.fromisoformat(str(raw_dt))
            except ValueError:
                continue

            if slot_dt.tzinfo is None:
                slot_dt = slot_dt.replace(tzinfo=UTC)

            hours_until = (slot_dt - now).total_seconds() / 3600
            if (
                0 < hours_until <= SOLAR_LOOKAHEAD_HOURS
                and slot.get("condition") in SUNNY_CONDITIONS
            ):
                return True

        return False
