# /test — Run the test suite

## Description
Run the full pytest suite with coverage reporting.

## Steps Claude should follow
1. Verify that `pyproject.toml` exists and `[tool.pytest.ini_options]` is configured.
2. Run: `pytest tests/ -v --cov=custom_components/climate_control --cov-report=term-missing`
3. Report any failures with file + line references.
4. If coverage is below 80 %, suggest which functions/branches lack tests.

## Notes
- Always use `pytest-asyncio` `asyncio_mode = "auto"` — no need to decorate individual async tests.
- Mock `homeassistant.util.dt.utcnow` rather than `datetime.datetime.utcnow`.
- Use `pytest.approx` for floating-point assertions.
