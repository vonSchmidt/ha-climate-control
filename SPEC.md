# SPEC.md — Climate Control Integration — Full Module Specification

**Version:** 2.0.0  
**Date:** 2026-05-13  
**Status:** Active — implementation reference

---

## 0. How to Use This Spec

This file is the single source of truth for the `climate_control` HA custom integration.  
When starting an implementation session, load this file first. Every design decision, algorithm detail, config field, entity contract, and test requirement is documented here. Code should match this spec; if you change the code, update the spec.

---

## 1. Purpose & Goals

`climate_control` is a Home Assistant custom integration that replaces naive thermostat schedules with a **schedule-driven, presence-aware, solar-optimised controller**.

| Input | Source |
|---|---|
| Weekly time schedule | Native HA `schedule.*` entities (UI-configured) |
| Occupancy / presence | HA `binary_sensor.*` entities |
| Current solar output | HA `sensor.*` entity (inverter power, W or kW) — optional |
| Solar look-ahead forecast | HA `weather.*` entity (Met.no) — optional |
| Current indoor temperature | HA `sensor.*` entity (temperature) |
| HVAC target | HA `climate.*` entity |

**Goals:**
1. Give users an "AC remote with weekly timers, but smarter" experience — fully configurable in HA UI.
2. Reduce HVAC energy use via solar-aware pre-cooling.
3. Maintain comfort when occupied; relax to eco when away; respect `off` blocks absolutely.
4. Be testable without a live HA instance — no external network calls anywhere.

**Non-Goals (v1.0):**
- Multi-zone support (one target climate entity per config entry).
- Learning / ML-based scheduling.
- Humidity control.
- Push notifications or alerts.
- Heating setpoint adjustment based on solar (insulation makes this unreliable).

---

## 2. Module Architecture

### 2.1 File Layout

```
custom_components/climate_control/
├── __init__.py       Integration setup/teardown
├── manifest.json     HA integration manifest
├── const.py          All string constants, numeric defaults, thresholds
├── config_flow.py    4-step UI config flow + options flow
├── coordinator.py    DataUpdateCoordinator — reads HA state, runs decision engine
├── solar.py          SolarAdvisor — reads inverter sensor + weather entity
├── presence.py       PresenceEvaluator + PresenceState enum
├── schedule.py       ScheduleEvaluator — reads schedule.* entities → ScheduleMode
└── climate.py        ClimateControlEntity (ClimateEntity + CoordinatorEntity)
```

### 2.2 Dependency Graph

```
HA weather.* entity (Met.no)          HA sensor.* (inverter)
          │                                    │
          └──────────────┬─────────────────────┘
                         ▼
                      solar.py
                    SolarAdvisor
                    SolarState (dataclass)
                         │
HA schedule.* entities   │    HA binary_sensor.* entities
          │              │              │
          ▼              │              ▼
     schedule.py         │         presence.py
  ScheduleEvaluator      │      PresenceEvaluator
  ScheduleMode (enum)    │      PresenceState (enum)
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                   coordinator.py
               ClimateControlCoordinator
               CoordinatorData (dataclass)
                         │
                         ▼
                    climate.py
               ClimateControlEntity
                         │  (reads coordinator.data only)
                         ▼
               HA climate.* entity (target device)
```

### 2.3 Data Flow — Refresh Cycle

```
Every UPDATE_INTERVAL minutes:
  1. coordinator._async_update_data() triggered by HA scheduler
  2. → schedule_evaluator.evaluate()        → ScheduleMode
  3. → presence_evaluator.evaluate()        → PresenceState
  4. → solar_advisor.evaluate()             → SolarState
  5. → coordinator._compute_setpoints()     → (heat_sp, cool_sp, hvac_mode, reason)
  6. → stores CoordinatorData
  7. → HA notifies listeners
  8. → ClimateControlEntity.async_write_ha_state() called automatically
```

### 2.4 Entry Point (`__init__.py`)

```python
async def async_setup_entry(hass, entry) -> bool:
    coordinator = ClimateControlCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True

async def async_unload_entry(hass, entry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

**Rules:**
- Always use `entry.runtime_data` — never `hass.data[DOMAIN]`.
- No `aiohttp` sessions — all data comes from HA entity state reads.
- `async_config_entry_first_refresh()` raises `ConfigEntryNotReady` on failure; HA retries automatically.

---

## 3. Config Schema

### 3.1 All Fields

| Key | Type | Step | Editable | Description |
|---|---|---|---|---|
| `target_entity` | `str` | 1 | No | `climate.*` entity to control |
| `temp_sensor` | `str` | 1 | No | `sensor.*` indoor temperature entity |
| `comfort_schedule` | `str` | 2 | Yes | `schedule.*` entity — `on` = comfort mode active |
| `eco_schedule` | `str` | 2 | Yes | `schedule.*` entity — `on` = eco mode active |
| `presence_sensors` | `list[str]` | 3 | Yes | Zero or more `binary_sensor.*` entity IDs |
| `precondition_min` | `int` | 3 | Yes | Minutes after last-seen to pre-condition. Default `30` |
| `solar_power_sensor` | `str \| None` | 4 | Yes | `sensor.*` inverter output (W or kW). Optional |
| `weather_entity` | `str \| None` | 4 | Yes | `weather.*` Met.no entity for look-ahead. Optional |
| `comfort_heat` | `float` | 4 | Yes | Comfort heating setpoint °C. Default `21.0` |
| `comfort_cool` | `float` | 4 | Yes | Comfort cooling setpoint °C. Default `24.0` |
| `eco_heat` | `float` | 4 | Yes | Eco heating setpoint °C. Default `18.0` |
| `eco_cool` | `float` | 4 | Yes | Eco cooling setpoint °C. Default `28.0` |
| `update_interval` | `int` | 4 | Yes | Coordinator refresh rate minutes. Default `10` |

### 3.2 Validation Rules

- `comfort_heat` < `comfort_cool`.
- `eco_heat` ≤ `comfort_heat`.
- `eco_cool` ≥ `comfort_cool`.
- `precondition_min` ∈ [0, 120].
- `update_interval` ∈ [5, 60].
- `comfort_schedule` ≠ `eco_schedule` (must be different entities).

### 3.3 Options Flow

Re-presents all "Editable" fields. On submit → triggers config-entry reload via update listener.

---

## 4. Schedule Layer (`schedule.py`)

### 4.1 Design

The user creates **two native HA `schedule.*` entities** using HA's built-in schedule UI (Settings → Helpers → Schedule). Each supports per-day-of-week free time blocks.

| Entity | Role |
|---|---|
| `comfort_schedule` | When `on` → comfort mode |
| `eco_schedule` | When `on` → eco mode |
| Both `off` | → `off` (HVAC disabled) |

### 4.2 `ScheduleMode` Enum

```python
class ScheduleMode(Enum):
    COMFORT = "comfort"
    ECO     = "eco"
    OFF     = "off"
```

### 4.3 `ScheduleEvaluator`

```python
class ScheduleEvaluator:
    def __init__(self, hass: HomeAssistant, comfort_entity: str, eco_entity: str) -> None: ...
    def evaluate(self) -> ScheduleMode: ...
```

#### Priority logic

```
comfort_state = hass.states.get(comfort_entity).state   # "on" or "off"
eco_state     = hass.states.get(eco_entity).state

if comfort_state == "on":   → COMFORT   # comfort always wins if both on
elif eco_state == "on":     → ECO
else:                       → OFF
```

- If either entity is unavailable → treat that entity as `"off"` and log a WARNING.
- `OFF` is absolute — presence and solar have no effect when schedule is `OFF`.

---

## 5. Presence Layer (`presence.py`)

### 5.1 `PresenceState` Enum

```python
class PresenceState(Enum):
    HOME    = "home"
    AWAY    = "away"
    UNKNOWN = "unknown"
```

### 5.2 `PresenceEvaluator` Behaviour

- Any configured sensor with `state == "on"` → `HOME`; records `_last_seen = utcnow()`.
- All sensors `"off"` → `AWAY`.
- No sensors configured, or all unavailable → `UNKNOWN`.
- `minutes_since_last_seen() → float | None` — `None` if `_last_seen` is `None` (no home event this session).

### 5.3 Presence Override Rules

| Schedule mode | Presence | Effective mode |
|---|---|---|
| `COMFORT` | `HOME` | Comfort ✅ |
| `COMFORT` | `AWAY` / `UNKNOWN` | Eco (downgrade) |
| `ECO` | `HOME` | Comfort (upgrade) |
| `ECO` | `AWAY` / `UNKNOWN` | Eco ✅ |
| `OFF` | any | Off — no override |

### 5.4 Pre-conditioning

When schedule = `ECO` and presence = `AWAY`, pre-conditioning upgrades to `COMFORT` if **all** true:
1. `_last_seen` is not `None`
2. `minutes_since_last_seen() ≤ precondition_min`

Rationale: user just left; they'll likely be back within the precondition window.  
Cold-start note: `_last_seen` is `None` on integration start, so pre-conditioning never triggers on first boot — intentional.

---

## 6. Solar Layer (`solar.py`)

### 6.1 Data Sources

| Source | Config field | HA entity type | Used for |
|---|---|---|---|
| Inverter power sensor | `solar_power_sensor` | `sensor.*` (W or kW) | Current solar output — adjust present setpoint |
| Met.no weather | `weather_entity` | `weather.*` | Hourly forecast — look-ahead pre-cool |

Both are optional. If neither is configured → solar feature fully disabled.

### 6.2 `SolarState` Dataclass

```python
@dataclass
class SolarState:
    current_output_w: float        # 0.0 if sensor absent/unavailable
    lookahead_sunny:  bool         # True if sunny forecast within SOLAR_LOOKAHEAD_HOURS
    solar_enabled:    bool         # False if no sources configured
    source_note:      str          # e.g. "inverter+forecast", "forecast only", "disabled"
```

### 6.3 `SolarAdvisor`

```python
class SolarAdvisor:
    def __init__(self, hass: HomeAssistant, power_sensor: str | None, weather_entity: str | None) -> None: ...
    def evaluate(self) -> SolarState: ...
```

All reads are synchronous `hass.states.get()` calls — no async I/O.

#### Inverter reading

```
state = hass.states.get(solar_power_sensor)
if unavailable or None → current_output_w = 0.0, log WARNING
else:
    value = float(state.state)
    unit  = state.attributes.get("unit_of_measurement", "W")
    if unit in ("kW", "kw") → current_output_w = value * 1000
    else                    → current_output_w = value
```

#### Met.no look-ahead

```
state = hass.states.get(weather_entity)
forecast = state.attributes.get("forecast", [])   # list of hourly dicts
now = utcnow()
lookahead_window = [f for f in forecast
                    if 0 < hours_until(f["datetime"]) <= SOLAR_LOOKAHEAD_HOURS]
SUNNY_CONDITIONS = {"sunny", "clearsky", "partlycloudy", "fair",
                    "clearsky_day", "fair_day", "partlycloudy_day"}
lookahead_sunny = any(f["condition"] in SUNNY_CONDITIONS for f in lookahead_window)
```

#### Fallback behaviour

| Scenario | Behaviour |
|---|---|
| `solar_power_sensor` unavailable | `current_output_w = 0.0`; fall back to Met.no only |
| `weather_entity` unavailable | `lookahead_sunny = False`; use inverter only |
| Both absent/unavailable | `solar_enabled = False`; no solar effect |

### 6.4 Solar Constants (`const.py`)

```python
SOLAR_LOOKAHEAD_HOURS   = 2      # hours — code constant, not UI-configurable in v1.0
SOLAR_HIGH_W_THRESHOLD  = 1000   # W — inverter output above this → high solar
SOLAR_LOW_W_THRESHOLD   = 200    # W — inverter output above this → moderate solar
SOLAR_OFFSET_HIGH       = 1.5    # °C reduction to cooling setpoint
SOLAR_OFFSET_LOW        = 0.5    # °C reduction to cooling setpoint
SUNNY_CONDITIONS: frozenset[str] = frozenset({
    "sunny", "clearsky", "clearsky_day",
    "fair", "fair_day",
    "partlycloudy", "partlycloudy_day",
})
```

---

## 7. Decision Engine (`coordinator.py`)

### 7.1 `CoordinatorData` Dataclass

```python
@dataclass
class CoordinatorData:
    schedule_mode:        ScheduleMode
    presence:             PresenceState
    solar:                SolarState
    effective_mode:       ScheduleMode    # after presence override
    target_setpoint_heat: float           # °C
    target_setpoint_cool: float           # °C, after solar offset
    hvac_mode:            HVACMode
    reason:               str
```

### 7.2 Full Setpoint Algorithm

```
INPUT: schedule_mode, presence, solar_state

# Step 1 — presence override
if schedule_mode == OFF:
    effective_mode = OFF
    → return (heat=N/A, cool=N/A, hvac=OFF, reason="Schedule: off")

if schedule_mode == COMFORT and presence in (AWAY, UNKNOWN):
    effective_mode = ECO
    reason = "Schedule comfort, but nobody home → eco"

elif schedule_mode == ECO and presence == HOME:
    effective_mode = COMFORT
    reason = "Schedule eco, but someone home → comfort"

elif schedule_mode == ECO and presence in (AWAY, UNKNOWN)
     and minutes_since_last_seen is not None
     and minutes_since_last_seen <= precondition_min:
    effective_mode = COMFORT
    reason = "Pre-conditioning — returning soon"

else:
    effective_mode = schedule_mode   # no override needed

# Step 2 — pick base setpoints
if effective_mode == COMFORT:
    base_heat, base_cool = comfort_heat, comfort_cool
else:  # ECO
    base_heat, base_cool = eco_heat, eco_cool

# Step 3 — solar offset (cooling only, never heating, never when OFF)
solar_offset = 0.0
if solar_state.solar_enabled:
    if solar_state.current_output_w > SOLAR_HIGH_W_THRESHOLD:
        solar_offset = SOLAR_OFFSET_HIGH
        reason += " | High inverter output → pre-cool -1.5°C"
    elif solar_state.current_output_w > SOLAR_LOW_W_THRESHOLD:
        solar_offset = SOLAR_OFFSET_LOW
        reason += " | Moderate inverter output → pre-cool -0.5°C"
    elif solar_state.lookahead_sunny:
        solar_offset = SOLAR_OFFSET_LOW
        reason += " | Sunny forecast incoming → pre-cool -0.5°C"

adjusted_cool = base_cool - solar_offset

OUTPUT: (base_heat, adjusted_cool, HVACMode.HEAT_COOL, reason)
```

**Key rules:**
- Solar offset applies to **cooling only**. `base_heat` is never modified by solar.
- Look-ahead pre-cool offset is `SOLAR_OFFSET_LOW` (0.5 °C) — conservative, since it's predictive.
- `OFF` blocks are absolute — no solar, no presence override, HVAC mode set to `HVACMode.OFF`.
- `UNKNOWN` presence is always treated as `AWAY` — fail-safe to eco.

---

## 8. HA Entity Definitions (`climate.py`)

### 8.1 `ClimateControlEntity`

| Attribute | Value |
|---|---|
| Base classes | `CoordinatorEntity[ClimateControlCoordinator]`, `ClimateEntity` |
| `_attr_has_entity_name` | `True` |
| `_attr_name` | `"Climate Control"` |
| `_attr_unique_id` | `f"{entry.entry_id}_climate"` |
| `_attr_temperature_unit` | `UnitOfTemperature.CELSIUS` |
| `_attr_hvac_modes` | `[OFF, HEAT, COOL, HEAT_COOL]` |
| `_attr_supported_features` | `TARGET_TEMPERATURE \| TARGET_TEMPERATURE_RANGE` |

### 8.2 Properties

| Property | Source |
|---|---|
| `hvac_mode` | `coordinator.data.hvac_mode` |
| `target_temperature_low` | `coordinator.data.target_setpoint_heat` |
| `target_temperature_high` | `coordinator.data.target_setpoint_cool` |
| `current_temperature` | `hass.states.get(CONF_TEMP_SENSOR)` — only permitted direct state read |

### 8.3 `extra_state_attributes`

```python
{
    "schedule_mode":         str,    # "comfort" / "eco" / "off"
    "effective_mode":        str,    # after presence override
    "presence":              str,    # "home" / "away" / "unknown"
    "solar_output_w":        float,
    "solar_lookahead_sunny": bool,
    "reason":                str,
}
```

### 8.4 Service Handlers

| Method | Behaviour |
|---|---|
| `async_set_hvac_mode` | Logs override; coordinator re-asserts on next refresh |
| `async_set_temperature` | Logs warning; ignored — use options flow to change setpoints |

---

## 9. Config Flow (`config_flow.py`)

### Step 1 — `user` — Devices
- `target_entity` — entity selector, domain `climate`
- `temp_sensor` — entity selector, domain `sensor`, device_class `temperature`

### Step 2 — `schedule` — Schedule Entities
- `comfort_schedule` — entity selector, domain `schedule`
- `eco_schedule` — entity selector, domain `schedule`
- Validation: `comfort_schedule ≠ eco_schedule`

### Step 3 — `presence` — Presence & Pre-conditioning
- `presence_sensors` — entity selector, domain `binary_sensor`, device_class `[presence, occupancy, motion]`, multiple, optional
- `precondition_min` — number, default `30`

### Step 4 — `settings` — Setpoints & Solar
- `comfort_heat`, `comfort_cool`, `eco_heat`, `eco_cool` — numbers with defaults
- `solar_power_sensor` — entity selector, domain `sensor`, optional
- `weather_entity` — entity selector, domain `weather`, optional
- `update_interval` — number, default `10`
- Validation: setpoint relational rules from §3.2

On submit → `async_create_entry(title="Climate Control", data=merged_data)`

---

## 10. Test Coverage Requirements

### 10.1 Target

**Minimum 80 %** line coverage. Enforced in CI with `--cov-fail-under=80`.

### 10.2 Required Test Files

| File | Module |
|---|---|
| `tests/test_solar.py` | `solar.py` |
| `tests/test_presence.py` | `presence.py` |
| `tests/test_schedule.py` | `schedule.py` |
| `tests/test_coordinator.py` | `coordinator.py` |
| `tests/test_climate.py` | `climate.py` |
| `tests/test_config_flow.py` | `config_flow.py` |

### 10.3 `test_solar.py`
- Returns `current_output_w` from inverter sensor correctly (W and kW units).
- Returns `0.0` when inverter sensor unavailable → falls back to Met.no.
- `lookahead_sunny=True` when a sunny condition appears within `SOLAR_LOOKAHEAD_HOURS`.
- `lookahead_sunny=False` when all forecast conditions are non-sunny.
- `solar_enabled=False` when neither source is configured.
- kW unit correctly multiplied to W.

### 10.4 `test_presence.py`
- `HOME` when any sensor is `"on"`.
- `AWAY` when all sensors `"off"`.
- `UNKNOWN` when no sensors configured.
- `UNKNOWN` when all sensors unavailable.
- `minutes_since_last_seen()` returns `None` before first home event.
- `minutes_since_last_seen()` returns positive float after home event.

### 10.5 `test_schedule.py`
- `COMFORT` when comfort schedule is `"on"`.
- `ECO` when eco schedule is `"on"` and comfort is `"off"`.
- `OFF` when both are `"off"`.
- `COMFORT` wins when both schedules are `"on"` simultaneously.
- Unavailable schedule entity treated as `"off"` with WARNING logged.

### 10.6 `test_coordinator.py`
- `COMFORT` schedule + `HOME` → comfort setpoints, no override.
- `COMFORT` schedule + `AWAY` → eco setpoints (downgrade).
- `ECO` schedule + `HOME` → comfort setpoints (upgrade).
- `ECO` schedule + `AWAY` within precondition window → comfort (pre-condition).
- `ECO` schedule + `AWAY` outside precondition window → eco.
- `OFF` schedule → `HVACMode.OFF`, setpoints irrelevant, solar ignored.
- High inverter output → cooling setpoint reduced by `SOLAR_OFFSET_HIGH`.
- Moderate inverter output → cooling setpoint reduced by `SOLAR_OFFSET_LOW`.
- No inverter output but lookahead sunny → cooling reduced by `SOLAR_OFFSET_LOW`.
- `solar_enabled=False` → no solar offset applied.
- Solar never modifies heating setpoint.
- Options take precedence over data dict.

### 10.7 `test_climate.py`
- `current_temperature` from valid sensor state.
- `current_temperature` is `None` when sensor unavailable.
- `target_temperature_low/high` match coordinator data.
- `extra_state_attributes` contains all required keys.
- `async_set_temperature` logs warning and does not raise.
- `unique_id` is stable.

### 10.8 `test_config_flow.py`
- Happy path: step 1 → 2 → 3 → 4 → entry created with title `"Climate Control"`.
- Validation error when `comfort_schedule == eco_schedule`.
- Validation error when `comfort_heat >= comfort_cool`.
- Options flow updates fields and triggers reload.

### 10.9 Fixtures (`conftest.py`)

| Fixture | Returns | Notes |
|---|---|---|
| `mock_hass` | `MagicMock` | States dict, config lat/lon |
| `mock_inverter_state` | `MagicMock` | Sensor state `"500"`, unit `"W"` |
| `mock_weather_state` | `MagicMock` | Weather state with hourly forecast |
| `mock_comfort_schedule_on` | `MagicMock` | Schedule entity state `"on"` |
| `mock_eco_schedule_on` | `MagicMock` | Schedule entity state `"on"` |

### 10.10 Testing Rules
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio`.
- Mock `datetime.now(timezone.utc)` via `unittest.mock.patch` — never call `utcnow()` directly.
- No live HTTP calls anywhere — all data from mocked `hass.states.get()`.
- `pytest.approx` for all float assertions.
- Use `pytest-homeassistant-custom-component` for config flow and entity integration tests.

---

## 11. CI Pipeline

See `.github/workflows/ci.yml`. Required jobs:

1. **lint** — `ruff check .`, `ruff format --check .`, `mypy custom_components/`
2. **test** — `pytest tests/ -v --cov=custom_components/climate_control --cov-fail-under=80` (matrix: Python 3.12, 3.13)
3. **validate-manifest** — required fields present, version matches `pyproject.toml`

All jobs must pass before merge to `main`.
