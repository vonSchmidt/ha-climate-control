"""Solar irradiance and weather input layer for Climate Control."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiohttp

from .const import (
    OPEN_METEO_BASE_URL,
    OPEN_METEO_FORECAST_DAYS,
    OPEN_METEO_HOURLY_PARAMS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SolarData:
    """Immutable snapshot of Open-Meteo hourly forecast data."""

    hourly_times: list[datetime]
    shortwave_radiation: list[float]   # W/m²
    cloud_cover: list[float]           # %
    outdoor_temp: list[float]          # °C
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SolarWeatherClient:
    """Fetches solar irradiance and weather data from the Open-Meteo API.

    All public methods are pure functions given a ``SolarData`` snapshot so
    they are straightforward to unit-test without network access.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        latitude: float,
        longitude: float,
    ) -> None:
        self._session = session
        self._latitude = latitude
        self._longitude = longitude

    # ── Network ───────────────────────────────────────────────────────────────

    async def async_fetch(self) -> SolarData:
        """Fetch the hourly forecast from Open-Meteo and return a ``SolarData``."""
        params: dict[str, str | int] = {
            "latitude": self._latitude,
            "longitude": self._longitude,
            "hourly": OPEN_METEO_HOURLY_PARAMS,
            "forecast_days": OPEN_METEO_FORECAST_DAYS,
            "timezone": "auto",
        }

        _LOGGER.debug("Fetching Open-Meteo forecast for (%s, %s)", self._latitude, self._longitude)

        async with self._session.get(OPEN_METEO_BASE_URL, params=params) as resp:
            resp.raise_for_status()
            raw: dict = await resp.json()

        hourly = raw["hourly"]
        times = [
            datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
            for t in hourly["time"]
        ]

        return SolarData(
            hourly_times=times,
            shortwave_radiation=[float(v) for v in hourly["shortwave_radiation"]],
            cloud_cover=[float(v) for v in hourly["cloud_cover"]],
            outdoor_temp=[float(v) for v in hourly["temperature_2m"]],
        )

    # ── Pure helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def current_irradiance(data: SolarData) -> float:
        """Return W/m² for the current UTC hour.

        Falls back to 0.0 if the current hour is not present in the dataset.
        """
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        try:
            idx = data.hourly_times.index(now)
        except ValueError:
            _LOGGER.warning("Current hour %s not found in solar forecast; returning 0 W/m²", now)
            return 0.0
        return data.shortwave_radiation[idx]

    @staticmethod
    def peak_irradiance_today(data: SolarData) -> tuple[float, datetime]:
        """Return the (peak W/m², datetime) for today (UTC date).

        Returns (0.0, now) when no data is available for today.
        """
        today = datetime.now(timezone.utc).date()
        todays_pairs = [
            (rad, t)
            for t, rad in zip(data.hourly_times, data.shortwave_radiation)
            if t.date() == today
        ]
        if not todays_pairs:
            return 0.0, datetime.now(timezone.utc)
        peak_rad, peak_time = max(todays_pairs, key=lambda p: p[0])
        return peak_rad, peak_time

    @staticmethod
    def hours_until_peak(data: SolarData) -> float:
        """Return fractional hours from now until today's peak irradiance hour.

        Negative values indicate the peak has already passed.
        """
        _, peak_time = SolarWeatherClient.peak_irradiance_today(data)
        now = datetime.now(timezone.utc)
        delta = peak_time - now
        return delta.total_seconds() / 3600
