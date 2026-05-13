"""Shared pytest fixtures for Climate Control tests."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.climate_control.solar import SolarData


@pytest.fixture
def mock_hass() -> MagicMock:
    """Return a minimal Home Assistant mock."""
    hass = MagicMock()
    hass.states = MagicMock()
    hass.config.latitude  = 48.8566
    hass.config.longitude = 2.3522
    return hass


@pytest.fixture
def mock_aiohttp_session() -> AsyncMock:
    """Return a mock aiohttp ClientSession."""
    return AsyncMock()


@pytest.fixture
def sample_solar_data() -> SolarData:
    """Return a deterministic SolarData fixture spanning 48 hours from 2026-05-13 00:00 UTC."""
    base = datetime(2026, 5, 13, 0, 0, 0, tzinfo=timezone.utc)
    hours = [base.replace(hour=h % 24) for h in range(48)]

    # Synthetic irradiance: bell curve peaking around 13:00 UTC
    def irradiance(h: int) -> float:
        hour_of_day = h % 24
        if hour_of_day < 6 or hour_of_day > 20:
            return 0.0
        return max(0.0, 600 * (1 - ((hour_of_day - 13) / 7) ** 2))

    radiation = [irradiance(i) for i in range(48)]
    cloud     = [10.0] * 48
    temp      = [15.0 + 5.0 * (i % 24 > 10 and i % 24 < 20) for i in range(48)]

    return SolarData(
        hourly_times=hours,
        shortwave_radiation=radiation,
        cloud_cover=cloud,
        outdoor_temp=temp,
        fetched_at=base,
    )
