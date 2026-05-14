"""Constants for the Climate Control integration."""

from __future__ import annotations

DOMAIN = "climate_control"
PLATFORMS: list[str] = ["climate"]

# ── Config entry keys ──────────────────────────────────────────────────────────
CONF_TARGET_ENTITY = "target_entity"  # climate.* entity to control
CONF_TEMP_SENSOR = "temp_sensor"  # indoor temperature sensor entity
CONF_COMFORT_SCHEDULE = "comfort_schedule"  # schedule.* entity — on = comfort mode
CONF_ECO_SCHEDULE = "eco_schedule"  # schedule.* entity — on = eco mode
CONF_PRESENCE_SENSORS = "presence_sensors"  # list[str] of binary_sensor entities
CONF_PRECONDITION_MIN = "precondition_min"  # int — minutes before return to pre-condition
CONF_SOLAR_POWER_SENSOR = "solar_power_sensor"  # sensor.* inverter output (W or kW), optional
CONF_WEATHER_ENTITY = "weather_entity"  # weather.* Met.no entity, optional
CONF_COMFORT_HEAT = "comfort_heat"  # °C — occupied heating setpoint
CONF_COMFORT_COOL = "comfort_cool"  # °C — occupied cooling setpoint
CONF_ECO_HEAT = "eco_heat"  # °C — away/eco heating setpoint
CONF_ECO_COOL = "eco_cool"  # °C — away/eco cooling setpoint
CONF_UPDATE_INTERVAL = "update_interval"  # int — coordinator refresh interval (minutes)

# ── Default values ─────────────────────────────────────────────────────────────
DEFAULT_COMFORT_HEAT = 21.0  # °C
DEFAULT_COMFORT_COOL = 24.0  # °C
DEFAULT_ECO_HEAT = 18.0  # °C
DEFAULT_ECO_COOL = 28.0  # °C
DEFAULT_PRECONDITION = 30  # minutes
DEFAULT_UPDATE_INTERVAL = 10  # minutes

# ── Solar thresholds (inverter output, W) ─────────────────────────────────────
SOLAR_HIGH_W_THRESHOLD = 1000  # W — above this → aggressive pre-cool
SOLAR_LOW_W_THRESHOLD = 200  # W — above this → mild pre-cool
SOLAR_LOOKAHEAD_HOURS = 2  # hours — forecast window for look-ahead

# ── Solar setpoint offsets (subtracted from cooling target) ───────────────────
SOLAR_OFFSET_HIGH = 1.5  # °C
SOLAR_OFFSET_LOW = 0.5  # °C

# ── Weather conditions treated as "sunny" for look-ahead ─────────────────────
SUNNY_CONDITIONS: frozenset[str] = frozenset(
    {
        "sunny",
        "clearsky",
        "clearsky_day",
        "fair",
        "fair_day",
        "partlycloudy",
        "partlycloudy_day",
    }
)
