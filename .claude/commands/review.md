# /review — Code review checklist

## Description
Perform a thorough code review of staged or recently modified files.

## Checklist Claude should apply

### Home Assistant conventions
- [ ] No blocking I/O on the event loop (`requests`, `open`, `time.sleep`, etc.).
- [ ] Entities only read from `coordinator.data` — never call `hass.states.get()` directly.
- [ ] `async_setup_entry` forwards to platforms via `async_forward_entry_setups`.
- [ ] Config entry uses `entry.runtime_data` (not `hass.data[DOMAIN]`).
- [ ] All string constants live in `const.py`.

### Code quality
- [ ] No `print()` statements — use `_LOGGER`.
- [ ] Type annotations on all public functions and methods.
- [ ] `mypy --strict` passes with no errors.
- [ ] `ruff check` passes with no warnings.

### Tests
- [ ] New public functions have at least one unit test.
- [ ] Edge cases (empty lists, unavailable entities, API errors) are covered.
- [ ] No `time.sleep` in tests — use `freezegun` or mock `datetime`.

### Security
- [ ] No secrets or tokens committed.
- [ ] External HTTP calls use `async_get_clientsession(hass)` — not bare `aiohttp`.

## Output format
For each issue found, output:
```
[SEVERITY] file.py:line — description
```
Severities: `ERROR` | `WARNING` | `INFO`
