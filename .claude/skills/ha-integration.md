# Skill: Home Assistant Custom Integration Development

## Overview
This skill covers patterns and idioms required to write a high-quality Home Assistant custom integration, targeting **HA Core ≥ 2024.1** and **Python ≥ 3.12**.

---

## Entry Point Pattern

```python
# __init__.py
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = MyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator                       # ← preferred over hass.data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

---

## Coordinator Pattern

```python
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

class MyCoordinator(DataUpdateCoordinator[MyData]):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name=DOMAIN,
                         update_interval=timedelta(minutes=10))

    async def _async_update_data(self) -> MyData:
        try:
            return await self._fetch()
        except SomeApiError as exc:
            raise UpdateFailed(str(exc)) from exc
```

---

## CoordinatorEntity Pattern

```python
from homeassistant.helpers.update_coordinator import CoordinatorEntity

class MySensor(CoordinatorEntity[MyCoordinator], SensorEntity):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_sensor"

    @property
    def native_value(self):
        return self.coordinator.data.some_value
```

---

## Config Flow Skeleton

```python
class MyConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="My Integration", data=user_input)
        return self.async_show_form(step_id="user", data_schema=vol.Schema({...}))

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return MyOptionsFlow(entry)
```

---

## Testing Patterns

### Mock hass states
```python
hass.states.get.return_value = State("sensor.temp", "21.5")
```

### Freeze time
```python
from unittest.mock import patch
with patch("custom_components.myintegration.solar.datetime") as mock_dt:
    mock_dt.now.return_value = datetime(2026, 5, 13, 13, 0, tzinfo=timezone.utc)
    result = my_function()
```

### Async test (pytest-asyncio auto mode)
```python
async def test_something():          # no decorator needed in asyncio_mode=auto
    result = await my_coroutine()
    assert result == expected
```

---

## Common Pitfalls
| Pitfall | Fix |
|---|---|
| `hass.states.get()` inside entity | Read from `coordinator.data` instead |
| `datetime.utcnow()` | Use `homeassistant.util.dt.utcnow()` |
| `requests.get()` | Use `async_get_clientsession(hass)` + `aiohttp` |
| `hass.data[DOMAIN]` | Use `entry.runtime_data` |
| Bare `except Exception` | Catch specific exceptions; wrap in `UpdateFailed` |
