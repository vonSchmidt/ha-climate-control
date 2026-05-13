# Climate Control

A Home Assistant custom integration that replaces naive thermostat schedules with a **schedule-driven, presence-aware, solar-optimised HVAC controller**.

Instead of a fixed on/off timer, Climate Control continuously adapts your target temperatures based on who is home, what your solar panels are currently producing, and what the weather forecast looks like — all configurable from the HA UI with no YAML required.

---

## Features

- **Weekly schedule** — define comfort and eco windows using native HA Schedule helpers (per-day, free time blocks)
- **Presence override** — automatically downgrades to eco when nobody is home; upgrades to comfort when someone arrives during an eco window
- **Pre-conditioning** — if you just left, the integration keeps comfort mode running for a configurable window so the house is ready when you return
- **Solar-aware cooling** — lowers the cooling setpoint when your inverter is producing above a threshold, or when a sunny forecast is incoming, to pre-cool cheaply
- **Config entry only** — fully set up and updated through the HA UI; no YAML needed
- **Fully local** — reads only HA entity states; no external API calls

---

## Requirements

- Home Assistant 2024.1.0 or later
- A `climate.*` entity (the HVAC device to control)
- A `sensor.*` temperature entity (indoor temperature)
- Two `schedule.*` helpers — one for comfort windows, one for eco windows (create these under **Settings → Helpers → Schedule**)

Optional but recommended:
- One or more `binary_sensor.*` presence/occupancy/motion sensors
- A `sensor.*` solar inverter power sensor (W or kW)
- A `weather.*` entity (Met.no works out of the box)

---

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/vonSchmidt/ha-climate-control` with category **Integration**
3. Search for **Climate Control** and install it
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/climate_control/` folder into your HA config directory under `custom_components/`
2. Restart Home Assistant

---

## Configuration

After restarting, go to **Settings → Devices & Services → Add Integration** and search for **Climate Control**. The setup flow has four steps:

### Step 1 — Devices
| Field | Description |
|---|---|
| Target climate entity | The `climate.*` entity this integration will control |
| Temperature sensor | Indoor `sensor.*` entity used to read current temperature |

### Step 2 — Schedule
| Field | Description |
|---|---|
| Comfort schedule | `schedule.*` entity — when `on`, comfort mode is active |
| Eco schedule | `schedule.*` entity — when `on`, eco mode is active |

When both are `off`, the HVAC is turned off. If both are `on` simultaneously, comfort wins.

### Step 3 — Presence
| Field | Default | Description |
|---|---|---|
| Presence sensors | *(none)* | One or more `binary_sensor.*` entities (presence, occupancy, or motion) |
| Pre-conditioning window | 30 min | How long after leaving to keep comfort mode running |

### Step 4 — Setpoints & Solar
| Field | Default | Description |
|---|---|---|
| Comfort heating setpoint | 21.0 °C | Target heat setpoint in comfort mode |
| Comfort cooling setpoint | 24.0 °C | Target cool setpoint in comfort mode |
| Eco heating setpoint | 18.0 °C | Target heat setpoint in eco mode |
| Eco cooling setpoint | 28.0 °C | Target cool setpoint in eco mode |
| Solar power sensor | *(none)* | `sensor.*` inverter output in W or kW |
| Weather entity | *(none)* | `weather.*` entity for hourly solar look-ahead |
| Update interval | 10 min | How often the coordinator re-evaluates state |

All setpoints and solar/presence options can be changed later via **Configure** on the integration card without removing and re-adding the entry.

---

## How it works

Each update cycle the integration evaluates three layers in order:

**1. Schedule** — reads the two schedule helpers to determine the base mode: `comfort`, `eco`, or `off`. `off` is absolute and cannot be overridden.

**2. Presence override**
| Schedule | Presence | Result |
|---|---|---|
| Comfort | Home | Comfort |
| Comfort | Away / Unknown | → Eco (nobody home) |
| Eco | Home | → Comfort (someone arrived) |
| Eco | Away, within pre-conditioning window | → Comfort (just left, returning soon) |
| Eco | Away, outside window | Eco |

**3. Solar offset** (cooling only — heating setpoint is never adjusted by solar)
| Condition | Cooling setpoint adjustment |
|---|---|
| Inverter output > 1000 W | −1.5 °C |
| Inverter output > 200 W | −0.5 °C |
| Sunny forecast within 2 h | −0.5 °C |

---

## Entity

The integration creates one `climate` entity per config entry. Its state attributes expose the full decision trace:

| Attribute | Example |
|---|---|
| `schedule_mode` | `"comfort"` |
| `effective_mode` | `"eco"` |
| `presence` | `"away"` |
| `solar_output_w` | `1240.0` |
| `solar_lookahead_sunny` | `true` |
| `reason` | `"Schedule comfort, but nobody home → eco \| High inverter output → pre-cool -1.5°C"` |

---

## Issues & contributions

Please open issues and pull requests at [github.com/vonSchmidt/ha-climate-control](https://github.com/vonSchmidt/ha-climate-control/issues).
