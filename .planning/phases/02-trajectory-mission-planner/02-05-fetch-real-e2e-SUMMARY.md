---
plan: 02-05-fetch-real-e2e
phase: 02-trajectory-mission-planner
status: complete
completed: 2026-04-17
requirements_addressed: [PHYS-02, PHYS-05]
---

# Plan 02-05: fetch-real-e2e — SUMMARY

## One-liner

Closed Phase 2: shipped `scripts/fetch_demo_env.py` (PHYS-02 CMEMS + ERA5 one-shot fetcher, fail-loud on missing creds), `scripts/run_full_chain_dummy.py` (parameterized E2E driver for `run_inference → forecast_drift → plan_mission`), and the PHYS-05 Gulf of Mannar real-data smoke test with per-frame Deccan Plateau exclusion — E2E wall-clock 16.79 s (under 20 s target), full backend/tests sweep 53 passed / 1 skipped (real-data smoke skips cleanly without NetCDFs).

## What shipped

- `scripts/fetch_demo_env.py` — one-shot CMEMS + ERA5 fetcher.
  - CMEMS: `cmems_mod_glo_phy_anfc_0.083deg_PT1H-m` (GLOBAL_ANALYSISFORECAST_PHY_001_024 product, D-02) via `copernicusmarine.open_dataset`.
  - ERA5: `reanalysis-era5-single-levels` with `10m_u_component_of_wind` / `10m_v_component_of_wind` (D-03) via `cdsapi.Client().retrieve`.
  - Bbox: `lon [68, 92]`, `lat [5, 22]` union-of-4-AOIs + 2° buffer; 72 h from `--start` (D-04).
  - Fail-loud: exits 2 with clear message on missing COPERNICUSMARINE_* creds OR missing CDSAPI_KEY / ~/.cdsapirc (D-05). Never silently falls back to synthetic.
  - Size budget warning printed if NetCDF exceeds 500 MB.
- `scripts/run_full_chain_dummy.py` — parameterized E2E driver (D-19).
  - CLI: `--patch`, `--origin LON LAT`, `--vessel-range-km`, `--hours`, `--use-synth-env`, `--out`.
  - Defaults: first tile in `MARIDA/splits/val_X.txt` (handles `S2_` prefix variance, filters out `_cl`/`_conf` masks), Mumbai origin `72.8 18.9`.
  - Per-stage wall-clock printed to stderr; pydantic round-trip validation after each stage boundary; final MissionPlan JSON to stdout or `--out`.
- `backend/tests/integration/test_e2e_dummy_chain.py` — subprocess-runs the driver with `--use-synth-env`, asserts wall-clock < 20 s and schema-valid MissionPlan at output. Skips if MARIDA absent.
- `backend/tests/integration/test_tracker_real.py` — PHYS-05 Gulf of Mannar smoke.
  - Skips if `data/env/*.nc` missing (never false green).
  - Seeds 10 detections jittered around (78.9, 9.2); runs full 72 h tracker with real `load_env_stack`.
  - Asserts per-frame, per-particle: finite lon/lat (D-15 beach-on-NaN means frozen particles carry last sea position), inside Indian Ocean basin `lon [68, 95]` / `lat [0, 25]`, and **NOT inside `DECCAN_BBOX = (80.0, 88.0, 15.0, 24.0)`** (PHYS-05 "no Deccan crossings" gate).

## Tests

```
backend/tests/integration/test_e2e_dummy_chain.py::test_full_chain_dummy_synth_env  ← PASS (16.79s)
backend/tests/integration/test_tracker_real.py::test_gulf_of_mannar_72h_smoke       ← SKIP (no data/env/*.nc)
```

**Full phase sweep:** `pytest backend/tests -q` → 53 passed, 1 skipped.

## Key decisions honored

- **D-02/D-03** exact CMEMS + ERA5 dataset IDs + variable names.
- **D-04** bbox + 72 h temporal window + size budget warning.
- **D-05** fail-loud on missing creds.
- **D-19** parameterized CLI with Mumbai + val[0] defaults; per-stage wall-clock + validation.
- **D-15** beach-on-NaN compatibility: smoke test uses finite-position assertion that tolerates frozen particles.

## Commits

- `feat(02-05): ship fetch_demo_env.py + run_full_chain_dummy.py`
- `test(02-05): add E2E dummy chain test + PHYS-05 real-data smoke`

## Files

**Created:**
- `scripts/fetch_demo_env.py`
- `scripts/run_full_chain_dummy.py`
- `backend/tests/integration/test_e2e_dummy_chain.py`
- `backend/tests/integration/test_tracker_real.py`

## Invariants preserved

- `backend/core/schemas.py` — untouched (FROZEN).
- `backend/api/routes.py`, `backend/services/mock_data.py` — untouched (out of scope).
- No new deps required beyond existing pins (copernicusmarine + cdsapi are imported lazily inside the fetcher, only needed when actually running the script).

## Phase 2 exit status

All five ROADMAP Phase 2 success criteria addressed:
1. ✓ PHYS-04 synthetic 43.2 km gate (plan 02-03).
2. ⧗ PHYS-05 real-data smoke — test ready, skips cleanly; runs when user executes `scripts/fetch_demo_env.py` with creds.
3. ✓ TSP 5 edge cases (plan 02-04).
4. ✓ Fetch script (this plan).
5. ✓ E2E dummy chain < 20 s (this plan, 16.79 s measured).
