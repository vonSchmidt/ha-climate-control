# HA Climate Control Module

## Project
Home Assistant custom integration. Python 3.12. Runs on Raspberry Pi (Raspberry Pi OS).
See SPEC.md for full module design.

## Stack
- HA custom integration (custom_components/)
- homeassistant>=2024.1.0
- pytest + pytest-homeassistant-custom-component for testing
- pyproject.toml for deps

## Commands
- Run tests: `pytest tests/ -v`
- Type check: `mypy custom_components/`
- Lint: `ruff check . && ruff format --check .`
- HA validator: `python -m script.hassfest`

## Code rules
- All HA entities must extend the correct HA base class
- Use DataUpdateCoordinator for all polling — never poll in entity update()
- Config entries only — no YAML setup (use config_flow.py)
- All external I/O (weather API, inverter sensor) must be async
- Never hardcode entity IDs — always use config entry values

## Testing
- Every module in custom_components/ needs a corresponding test file
- Use pytest-homeassistant-custom-component fixtures (hass, mock_config_entry)
- Mock all external HTTP calls — no live API calls in tests
- Min coverage target: 80%

## Git
- Conventional commits: feat/fix/test/refactor/docs
- Never commit secrets or API keys
- Branch: feature/* → main via PR
