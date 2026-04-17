---
phase: 02-trajectory-mission-planner
plan: 01
subsystem: physics
tags: [xarray, cmems, era5, netcdf, pydantic-settings, pyproj, tdd, infra]

# Dependency graph
requires:
  - phase: 01-schema-foundation-dummy-inference
    provides: "Settings (pydantic-settings YAML+env), MissionSettings/PhysicsSettings, frozen schemas, pytest layout under backend/tests/unit"
provides:
  - "backend.physics.env_data.EnvStack — frozen dataclass with interp_currents(lon,lat,t)->(u,v) and interp_winds(lon,lat,t)->(u10,v10)"
  - "load_env_stack(cmems_path, era5_path, horizon_hours=72) — file-backed loader with full invariant path"
  - "from_synthetic(currents, winds, horizon_hours=72) — test helper that runs identical invariants on in-memory xr.Datasets"
  - "_normalize_longitude (PITFALL M4), _assert_time_coverage (PITFALL M3), _assert_standard_names (PITFALL M5)"
  - "mission.avg_speed_kmh=20.0 config knob (D-13), readable via Settings().mission.avg_speed_kmh, env-overridable as MISSION__AVG_SPEED_KMH"
  - "backend/ml/checkpoints/ directory with .gitkeep (INFRA-05) + ignore rules for *.pth/*.ckpt/*.pt and data/env/*.nc"
affects: [02-trajectory-lagrangian-tracker, 02-mission-planner-tsp, 02-env-fetch-script, 02-e2e-chain-smoke, 03-real-training-kaggle]

# Tech tracking
tech-stack:
  added: [xarray==2024.2.0, netcdf4==1.6.5, numpy==1.26.4, pyproj==3.6.1, scikit-learn==1.4.1.post1, scikit-image==0.22.0, utm==0.7.0, copernicusmarine==1.2.2, cdsapi==0.6.1, pytest==8.1.1]
  patterns:
    - "Shared `_finalize(currents, winds, horizon_hours)` so `load_env_stack` and `from_synthetic` exercise the exact same normalization/assertion path — tests and production share invariants."
    - "All PITFALL checks at load time, not at interpolation time — downstream tracker consumes a validated EnvStack."
    - "Frozen dataclass for EnvStack aligns with pydantic frozen=True discipline established in Phase 1."

key-files:
  created:
    - backend/physics/env_data.py
    - backend/tests/unit/test_env_data.py
    - backend/ml/checkpoints/.gitkeep
  modified:
    - backend/requirements.txt
    - backend/config.yaml
    - backend/core/config.py
    - .gitignore

key-decisions:
  - "from_synthetic shares _finalize with load_env_stack so tests exercise identical invariant path (not a shortcut)"
  - "Time coverage check uses (t[-1] - t[0]) / np.timedelta64(1, 'h') rather than len(time); robust to non-hourly grids"
  - "Longitude normalization triggers only when max>180 so already-normalized datasets remain no-op"
  - "Wind eastward check accepts either standard_name='eastward_wind' or long_name containing 'eastward' (ERA5 GRIB vs NetCDF variance)"

patterns-established:
  - "EnvStack API contract: (u, v) = env.interp_currents(lon, lat, t_hours) — the single entry point Plan 03 (tracker) will consume"
  - "PITFALL handling at load (M3/M4/M5), beach-on-NaN (M2) deferred to tracker — clear separation of concerns"
  - "INFRA-05 gitignore idiom: *.pth + explicit backend/ml/checkpoints/*.{pth,ckpt,pt} + data/env/*.nc"

requirements-completed: [INFRA-05, PHYS-01]

# Metrics
duration: 3min
completed: 2026-04-17
---

# Phase 2 Plan 01: Environment Data Config Summary

**xarray-backed EnvStack loader with PITFALL M3/M4/M5 invariants handled at load time, plus D-13 vessel-speed config knob and INFRA-05 checkpoints scaffolding — unblocks the Phase 2 tracker.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-04-17T13:09:36Z
- **Completed:** 2026-04-17T13:12:20Z
- **Tasks:** 2 (both auto, Task 2 was TDD)
- **Files modified:** 7 (4 modified, 3 created)
- **Tests added:** 6 (all green)

## Accomplishments

- `EnvStack` class with `interp_currents` / `interp_winds` — the single contract Plan 03 (tracker) and Plan 05 (E2E smoke) will consume.
- All three CMEMS/ERA5 pitfalls handled **at load, not at interpolation**: M3 (time coverage assertion), M4 (lon normalization [0,360]→[-180,180]), M5 (eastward_sea_water_velocity / eastward_wind standard_name verification).
- `from_synthetic(currents, winds)` test helper — enables decoupled tracker development before CMEMS/ERA5 NetCDFs arrive (per D-01 parallel-track decision).
- D-13 `mission.avg_speed_kmh=20.0` wired into YAML + pydantic-settings + env override (`MISSION__AVG_SPEED_KMH=30`).
- INFRA-05 scaffolding: `backend/ml/checkpoints/` exists with `.gitkeep`, `*.pth/*.ckpt/*.pt` in .gitignore, `data/env/*.nc` ignored.

## Task Commits

Each task was committed atomically with `--no-verify` (parallel wave executor convention):

1. **Task 1: Extend config + requirements + gitignore + checkpoints dir** — `9fd7f89` (chore)
2. **Task 2 RED: Failing EnvStack tests** — `396e54e` (test)
3. **Task 2 GREEN: EnvStack implementation** — `78e5e96` (feat)

_TDD produced two commits for Task 2 (RED then GREEN); no refactor commit was needed — implementation was clean on first pass._

## Files Created/Modified

- `backend/physics/env_data.py` — EnvStack + load_env_stack + from_synthetic + three invariant helpers (169 LOC, created)
- `backend/tests/unit/test_env_data.py` — 6 tests covering constant-field, lon normalization, NaN passthrough, time coverage, and both standard_name branches (172 LOC, created)
- `backend/ml/checkpoints/.gitkeep` — empty tracker for kagglehub download directory (INFRA-05, created)
- `backend/requirements.txt` — appended 10 Phase 2 pins (xarray, netcdf4, numpy, pyproj, sklearn, skimage, utm, copernicusmarine, cdsapi, pytest)
- `backend/config.yaml` — added `mission.avg_speed_kmh: 20.0`
- `backend/core/config.py` — added `MissionSettings.avg_speed_kmh: float = Field(default=20.0, gt=0.0, le=60.0)`
- `.gitignore` — appended `backend/ml/checkpoints/*.{pth,ckpt,pt}` and `data/env/*.nc`

## Decisions Made

- **Shared `_finalize` path** between `load_env_stack` and `from_synthetic`: tests exercise the exact same normalization + assertion code that production uses. Prevents "tests pass but prod fails" divergence on the invariant helpers.
- **Time coverage via timedelta span**, not `len(time)`: robust to non-hourly source grids (e.g., 3-hourly ERA5 re-interpolated to hourly downstream).
- **Wind eastward check via OR of standard_name and long_name**: CMEMS NetCDF typically sets `standard_name`; ERA5-from-GRIB sometimes only sets `long_name`. Accepting both avoids false-positive ValueError on live ERA5 pulls.
- **Added a 6th test** (`test_standard_name_check_currents_eastward`) beyond the 5 specified in the plan: symmetric coverage of both PITFALL M5 branches (wind *and* current). Cheap insurance; matches the defensive posture of the plan.

## Deviations from Plan

None — plan executed exactly as written. The 6th test is a supplementary symmetric case, not a deviation; all 5 plan-specified tests are present and green.

## Issues Encountered

- Harmless `UserWarning` from pandas re numexpr/bottleneck version mismatch and from xarray re non-nanosecond datetime precision in synthetic fixtures. Neither affects correctness; deferred (not in scope for this plan).

## CLAUDE.md Compliance

- snake_case module names ✓ (`env_data.py`)
- pydantic `frozen=True` (EnvStack is a frozen dataclass; MissionSettings unchanged) ✓
- No Hydra/Lightning/W&B/torch.compile introduced ✓
- Python 3.10–3.12 compatible (uses `from __future__ import annotations`, tuple[float, float], `|` unions gated by annotations import) ✓
- `backend/core/schemas.py` untouched ✓
- `backend/api/routes.py` and `backend/services/mock_data.py` untouched ✓

## Next Phase Readiness

- **Plan 02 (env-fetch script)** can now import `from backend.physics.env_data import load_env_stack` for round-trip validation of freshly-downloaded NetCDFs.
- **Plan 03 (tracker)** can consume `EnvStack` directly; beach-on-NaN (PITFALL M2) is its responsibility per the load-vs-integrate separation established here.
- **Plan 04 (mission planner)** can read `cfg.mission.avg_speed_kmh` immediately (D-13 wired).
- **Plan 05 (E2E smoke)** has a synthetic xarray fallback path via `from_synthetic(...)` in case CMEMS/ERA5 pulls slip the schedule.

## Self-Check: PASSED

**Files verified present:**
- FOUND: backend/physics/env_data.py
- FOUND: backend/tests/unit/test_env_data.py
- FOUND: backend/ml/checkpoints/.gitkeep

**Commits verified on main branch:**
- FOUND: 9fd7f89 (Task 1)
- FOUND: 396e54e (Task 2 RED)
- FOUND: 78e5e96 (Task 2 GREEN)

**Invariant acceptance:**
- `python -m pytest backend/tests/unit/test_env_data.py backend/tests/unit/test_config.py -q` → 10 passed ✓
- `git check-ignore backend/ml/checkpoints/foo.pth` → exits 0 ✓
- `Settings().mission.avg_speed_kmh == 20.0` ✓
- `MISSION__AVG_SPEED_KMH=30 → Settings().mission.avg_speed_kmh == 30.0` ✓

---
*Phase: 02-trajectory-mission-planner*
*Completed: 2026-04-17*
