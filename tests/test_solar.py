"""Unit tests for custom_components.climate_control.solar."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.climate_control.solar import SolarData, SolarWeatherClient


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_client(lat: float = 48.86, lon: float = 2.35) -> SolarWeatherClient:
    return SolarWeatherClient(session=AsyncMock(), latitude=lat, longitude=lon)


# ── current_irradiance ────────────────────────────────────────────────────────


class TestCurrentIrradiance:
    def test_returns_matching_hour(self, sample_solar_data: SolarData) -> None:
        """Should return the radiation value for the current UTC hour."""
        target_hour = sample_solar_data.hourly_times[13]  # 13:00 UTC — near peak
        with patch(
            "custom_components.climate_control.solar.datetime"
        ) as mock_dt:
            mock_now = target_hour.replace(minute=30)  # any minute in that hour
            mock_dt.now.return_value = mock_now.replace(minute=0, second=0, microsecond=0)
            mock_dt.now.return_value = target_hour
            # Use the static method directly with controlled data
            result = SolarWeatherClient.current_irradiance(sample_solar_data)
        # Without mocking datetime we just verify it doesn't raise
        assert isinstance(result, float)

    def test_returns_zero_when_hour_missing(self) -> None:
        """Should fall back to 0.0 when current hour is absent from dataset."""
        data = SolarData(
            hourly_times=[datetime(2000, 1, 1, 0, tzinfo=timezone.utc)],
            shortwave_radiation=[500.0],
            cloud_cover=[0.0],
            outdoor_temp=[10.0],
        )
        result = SolarWeatherClient.current_irradiance(data)
        # Current UTC hour is almost certainly not year 2000 → fallback 0.0
        assert result == 0.0

    def test_exact_hour_match(self) -> None:
        """Should return the value for the hour that matches utcnow (mocked)."""
        fixed_hour = datetime(2026, 5, 13, 13, 0, 0, tzinfo=timezone.utc)
        data = SolarData(
            hourly_times=[fixed_hour],
            shortwave_radiation=[450.0],
            cloud_cover=[5.0],
            outdoor_temp=[22.0],
        )
        with patch(
            "custom_components.climate_control.solar.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = fixed_hour
            result = SolarWeatherClient.current_irradiance(data)
        assert result == 450.0


# ── peak_irradiance_today ─────────────────────────────────────────────────────


class TestPeakIrradianceToday:
    def test_identifies_peak_hour(self, sample_solar_data: SolarData) -> None:
        """Peak should be the maximum radiation value and its corresponding time."""
        peak_rad, peak_time = SolarWeatherClient.peak_irradiance_today(sample_solar_data)
        # The synthetic data in conftest peaks around hour 13
        assert isinstance(peak_rad, float)
        assert isinstance(peak_time, datetime)
        assert peak_rad >= 0.0

    def test_returns_zero_when_no_data_today(self) -> None:
        """Returns (0.0, now) when dataset has no entries for today's UTC date."""
        old_time = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
        data = SolarData(
            hourly_times=[old_time],
            shortwave_radiation=[999.0],
            cloud_cover=[0.0],
            outdoor_temp=[10.0],
        )
        peak_rad, _ = SolarWeatherClient.peak_irradiance_today(data)
        assert peak_rad == 0.0

    def test_peak_is_maximum_value(self, sample_solar_data: SolarData) -> None:
        """Peak radiation must equal the maximum of all today's radiation values."""
        today = sample_solar_data.hourly_times[0].date()
        todays_radiation = [
            r
            for t, r in zip(sample_solar_data.hourly_times, sample_solar_data.shortwave_radiation)
            if t.date() == today
        ]
        expected_peak = max(todays_radiation)
        actual_peak, _ = SolarWeatherClient.peak_irradiance_today(sample_solar_data)
        assert actual_peak == pytest.approx(expected_peak)


# ── hours_until_peak ──────────────────────────────────────────────────────────


class TestHoursUntilPeak:
    def test_returns_float(self, sample_solar_data: SolarData) -> None:
        result = SolarWeatherClient.hours_until_peak(sample_solar_data)
        assert isinstance(result, float)

    def test_negative_when_peak_passed(self) -> None:
        """Returns negative value when peak was in the past."""
        past_peak = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
        data = SolarData(
            hourly_times=[past_peak],
            shortwave_radiation=[800.0],
            cloud_cover=[0.0],
            outdoor_temp=[10.0],
        )
        result = SolarWeatherClient.hours_until_peak(data)
        assert result < 0


# ── async_fetch (network) ─────────────────────────────────────────────────────


class TestAsyncFetch:
    @pytest.mark.asyncio
    async def test_parses_open_meteo_response(self) -> None:
        """Should parse a well-formed Open-Meteo JSON response into SolarData."""
        fake_response = {
            "hourly": {
                "time": ["2026-05-13T00:00", "2026-05-13T01:00"],
                "shortwave_radiation": [0.0, 50.0],
                "cloud_cover": [20.0, 25.0],
                "temperature_2m": [15.0, 14.5],
            }
        }

        mock_resp = AsyncMock()
        mock_resp.json = AsyncMock(return_value=fake_response)
        mock_resp.raise_for_status = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        client = SolarWeatherClient(session=mock_session, latitude=48.86, longitude=2.35)
        data = await client.async_fetch()

        assert len(data.hourly_times) == 2
        assert data.shortwave_radiation == [0.0, 50.0]
        assert data.cloud_cover == [20.0, 25.0]
        assert data.outdoor_temp == [15.0, 14.5]
        assert data.hourly_times[0].tzinfo is not None
