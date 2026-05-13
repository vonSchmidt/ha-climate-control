"""Constants for the Climate Control integration."""
from __future__ import annotations

DOMAIN = "climate_control"
PLATFORMS: list[str] = ["climate"]

# ── Config entry keys ──────────────────────────────────────────────────────────
CONF_TARGET_ENTITY    = "target_entity"       # climate.* entity to control
CONF_TEMP_SENSOR      = "temp_sensor"         # indoor temperature sensor entity
CONF_PRESENCE_SENSORS = "presence_sensors"    # list[str] of binary_sensor entities
CONF_COMFORT_HEAT     = "comfort_heat"        # °C — occupied heating setpoint
CONF_COMFORT_COOL     = "comfort_cool"        # °C — occupied cooling setpoint
CONF_ECO_HEAT         = "eco_heat"            # °C — away/eco heating setpoint
CONF_ECO_COOL         = "eco_cool"            # °C — away/eco cooling setpoint
CONF_PRECONDITION_MIN = "precondition_min"    # int — minutes before return to pre-condition
CONF_LATITUDE         = "latitude"
CONF_LONGITUDE        = "longitude"
CONF_UPDATE_INTERVAL  = "update_interval"     # int — coordinator refresh interval (minutes)

# ── Default values ─────────────────────────────────────────────────────────────
DEFAULT_COMFORT_HEAT    = 21.0   # °C
DEFAULT_COMFORT_COOL    = 24.0   # °C
DEFAULT_ECO_HEAT        = 18.0   # °C
DEFAULT_ECO_COOL        = 28.0   # °C
DEFAULT_PRECONDITION    = 30     # minutes
DEFAULT_UPDATE_INTERVAL = 10     # minutes

# ── Solar irradiance thresholds (W/m²) ────────────────────────────────────────
SOLAR_HIGH_THRESHOLD = 400.0   # above this → aggressive pre-cool offset (+1.5 °C)
SOLAR_LOW_THRESHOLD  = 100.0   # above this → mild pre-cool offset (+0.5 °C)

# Solar setpoint offsets applied to cooling target (subtracted = cooler target)
SOLAR_OFFSET_HIGH = 1.5   # °C
SOLAR_OFFSET_LOW  = 0.5   # °C
SOLAR_OFFSET_NONE = 0.0   # °C

# ── Open-Meteo ─────────────────────────────────────────────────────────────────
OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_HOURLY_PARAMS = "shortwave_radiation,cloud_cover,temperature_2m"
OPEN_METEO_FORECAST_DAYS = 2

# ── Misc ───────────────────────────────────────────────────────────────────────
ATTRIBUTION = "Weather data provided by Open-Meteo (https://open-meteo.com)"
