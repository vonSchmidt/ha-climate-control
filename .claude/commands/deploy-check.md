# /deploy-check — Pre-release validation

## Description
Run all checks required before tagging a release or opening a PR.

## Steps Claude should follow

### 1 — Static analysis
```bash
ruff check custom_components/ tests/
mypy custom_components/
```

### 2 — Tests with coverage
```bash
pytest tests/ -v --cov=custom_components/climate_control --cov-report=term-missing --cov-fail-under=80
```

### 3 — Manifest validation
Verify `manifest.json`:
- `version` matches the version in `pyproject.toml`.
- `config_flow` is `true`.
- `iot_class` is set.
- `requirements` lists only PyPI packages (no git URLs).

### 4 — HACS compatibility
- `custom_components/climate_control/` directory exists.
- `manifest.json` is present with `domain`, `name`, `version`, `codeowners`.
- No files outside `custom_components/` are required for the integration to load.

### 5 — Changelog
- Confirm `CHANGELOG.md` (if present) has an entry for the new version.
- Ensure `SPEC.md` version header matches.

## Pass criteria
All steps must exit 0 / produce no errors. Report a `✅ PASS` or `❌ FAIL` summary.
