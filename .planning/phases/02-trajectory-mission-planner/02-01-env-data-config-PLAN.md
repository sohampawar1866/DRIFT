---
phase: 02-trajectory-mission-planner
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/requirements.txt
  - backend/config.yaml
  - backend/core/config.py
  - backend/physics/env_data.py
  - backend/tests/unit/test_env_data.py
  - .gitignore
  - backend/ml/checkpoints/.gitkeep
autonomous: true
requirements: [INFRA-05, PHYS-01]
must_haves:
  truths:
    - "backend.physics.env_data.load_env_stack() returns an object that exposes interp_currents(lon, lat, t_hours) -> (u, v) and interp_winds(lon, lat, t_hours) -> (u10, v10)"
    - "Longitude convention is normalized to [-180, 180] at load (PITFALL M4)"
    - "Time-axis coverage >= horizon_hours is asserted at load (PITFALL M3); clipped horizon returned when shorter"
    - "u/v CMEMS standard_name is verified at load (PITFALL M5)"
    - "mission.avg_speed_kmh is readable via Settings().mission.avg_speed_kmh (default 20.0)"
    - "backend/ml/checkpoints/ exists, .gitkeep tracked, *.pth/*.ckpt ignored (INFRA-05 prep)"
  artifacts:
    - path: backend/physics/env_data.py
      provides: "EnvStack class + load_env_stack(cfg) + interp_currents + interp_winds"
      min_lines: 100
    - path: backend/config.yaml
      provides: "mission.avg_speed_kmh=20.0"
      contains: "avg_speed_kmh"
    - path: backend/core/config.py
      provides: "MissionSettings.avg_speed_kmh field"
      contains: "avg_speed_kmh"
    - path: backend/tests/unit/test_env_data.py
      provides: "Unit tests for synthetic xarray fixtures (lon normalization, time clip, NaN handling)"
      min_lines: 80
    - path: backend/ml/checkpoints/.gitkeep
      provides: "Directory placeholder for Phase 3 kagglehub downloads"
  key_links:
    - from: backend/physics/env_data.py
      to: backend/core/config.py
      via: "Settings().physics.cmems_path / era5_path"
      pattern: "cfg\\.physics\\.cmems_path"
    - from: backend/physics/env_data.py
      to: xarray
      via: "xr.open_dataset + bilinear .interp"
      pattern: "xr\\.open_dataset|\\.interp\\("
---

<objective>
Wire the environment-data loader that both the tracker (Plan 03) and the E2E smoke test (Plan 05) consume. Add the mission vessel-speed config knob (D-13) and prepare INFRA-05 (checkpoints dir + gitignore). All CMEMS/ERA5 pitfalls (M3 time-axis, M4 lon convention, M5 wind vector component) are handled at load time inside a single EnvStack class so downstream code can trust the interpolators.

Purpose: Unblock Plan 03 (tracker) by giving it a clean `(u, v) = env.interp_currents(lon, lat, t)` API backed by either a real NetCDF or a synthetic xarray Dataset built inline in tests.
Output: backend/physics/env_data.py, updated config, checkpoints dir, env_data unit tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/02-trajectory-mission-planner/02-CONTEXT.md
@backend/core/schemas.py
@backend/core/config.py
@backend/config.yaml

<interfaces>
From backend/core/config.py:
```python
class PhysicsSettings(BaseModel):
    windage_alpha: float = Field(default=0.02, ge=0.0, le=0.1)
    horizon_hours: int = 72
    dt_seconds: int = 3600
    particles_per_detection: int = 20
    cmems_path: Path = Path("data/env/cmems_currents_72h.nc")
    era5_path: Path = Path("data/env/era5_winds_72h.nc")

class MissionSettings(BaseModel):
    top_k: int = 10
    weight_density: float = 0.5
    weight_accessibility: float = 0.3
    weight_convergence: float = 0.2
    # TASK 1 adds: avg_speed_kmh: float = 20.0
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Extend config + requirements + gitignore + checkpoints dir</name>
  <files>backend/requirements.txt, backend/config.yaml, backend/core/config.py, .gitignore, backend/ml/checkpoints/.gitkeep</files>
  <read_first>
    - backend/requirements.txt
    - backend/config.yaml
    - backend/core/config.py
    - .gitignore
    - .planning/phases/02-trajectory-mission-planner/02-CONTEXT.md (D-13, INFRA-05)
  </read_first>
  <action>
    1. **backend/requirements.txt** — append (one per line, preserve existing lines):
       ```
       xarray==2024.2.0
       netcdf4==1.6.5
       numpy==1.26.4
       pyproj==3.6.1
       scikit-learn==1.4.1.post1
       scikit-image==0.22.0
       utm==0.7.0
       copernicusmarine==1.2.2
       cdsapi==0.6.1
       pytest==8.1.1
       ```
       (torch / rasterio / segmentation_models_pytorch are already installed from Phase 1.)
    2. **backend/config.yaml** — under the existing `mission:` block add a new key (keep YAML indentation 2 spaces):
       ```yaml
         avg_speed_kmh: 20.0
       ```
       Per D-13: ~11 kt Indian Coast Guard cruise.
    3. **backend/core/config.py** — add exactly one new field to `MissionSettings`:
       ```python
       avg_speed_kmh: float = Field(default=20.0, gt=0.0, le=60.0)
       ```
       Place it immediately after `weight_convergence`. Do NOT touch `weight_density`, `weight_accessibility`, `weight_convergence` (lock their defaults).
    4. **.gitignore** — ensure the following lines are present (append if missing, dedupe on re-run):
       ```
       backend/ml/checkpoints/*.pth
       backend/ml/checkpoints/*.ckpt
       backend/ml/checkpoints/*.pt
       data/env/*.nc
       ```
       Rationale: INFRA-05 — checkpoints transferred via kagglehub, never git-committed; NetCDFs are 100s of MB, never committed.
    5. **backend/ml/checkpoints/.gitkeep** — create empty file so the directory tracks in git.
  </action>
  <verify>
    <automated>python -c "from backend.core.config import Settings; s=Settings(); assert s.mission.avg_speed_kmh == 20.0; print('OK avg_speed_kmh=', s.mission.avg_speed_kmh)"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "avg_speed_kmh: 20.0" backend/config.yaml` exits 0
    - `grep -q "avg_speed_kmh: float = Field(default=20.0" backend/core/config.py` exits 0
    - `grep -qE "^xarray==2024" backend/requirements.txt` exits 0
    - `grep -qE "^copernicusmarine==1" backend/requirements.txt` exits 0
    - `grep -qE "^pyproj==3" backend/requirements.txt` exits 0
    - `grep -qE "backend/ml/checkpoints/\*\.pth" .gitignore` exits 0
    - `test -f backend/ml/checkpoints/.gitkeep` exits 0
    - `MISSION__AVG_SPEED_KMH=30 python -c "from backend.core.config import Settings; assert Settings().mission.avg_speed_kmh == 30.0"` exits 0 (env override works)
  </acceptance_criteria>
  <done>avg_speed_kmh readable via Settings(), env override works, gitignore covers *.pth and *.nc, checkpoints dir committed.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: backend/physics/env_data.py EnvStack + synthetic fixture tests</name>
  <files>backend/physics/env_data.py, backend/tests/unit/test_env_data.py, backend/tests/__init__.py (if missing), backend/tests/unit/__init__.py (if missing)</files>
  <read_first>
    - backend/physics/tracker.py (stub — to understand downstream consumer)
    - backend/core/config.py
    - backend/core/schemas.py
    - .planning/phases/02-trajectory-mission-planner/02-CONTEXT.md (D-02, D-03, D-16, D-17, D-18)
    - backend/ml/inference.py (pattern for module layout + docstrings)
  </read_first>
  <behavior>
    - Test 1 (synthetic constant-field): build a 3D xarray Dataset with uo=0.5 m/s constant, vo=0, over lon [60, 95], lat [0, 25], time 73 hourly frames; EnvStack.interp_currents(lon=75.0, lat=10.0, t_hours=0) returns (0.5, 0.0) within 1e-6.
    - Test 2 (lon normalization): build dataset with longitude in [0, 360] convention; EnvStack loader normalizes so `env.lon_min >= -180 and env.lon_max <= 180`; interpolation at lon=-75 works and matches source at lon=285.
    - Test 3 (NaN passthrough): inject NaN at a coastal grid cell; interp_currents at that location returns (nan, nan) — caller (tracker) is responsible for beach-on-NaN (PITFALL M2 handled in Plan 03, not here).
    - Test 4 (time-axis coverage assertion): if source time-axis < horizon_hours, load_env_stack raises ValueError containing "time coverage".
    - Test 5 (wind standard_name check): if dataset missing required attr, loader raises ValueError containing "eastward" (PITFALL M5).
  </behavior>
  <action>
    1. Create **backend/physics/env_data.py** with this exact public surface:
       ```python
       from dataclasses import dataclass
       from pathlib import Path
       import numpy as np
       import xarray as xr

       @dataclass(frozen=True)
       class EnvStack:
           currents: xr.Dataset   # vars: uo, vo; dims: time, latitude, longitude
           winds: xr.Dataset      # vars: u10, v10; dims: time, latitude, longitude
           t0_hours: float        # origin hour (0) anchored to currents.time[0]

           def interp_currents(self, lon: float, lat: float, t_hours: float) -> tuple[float, float]:
               ...
           def interp_winds(self, lon: float, lat: float, t_hours: float) -> tuple[float, float]:
               ...

       def _normalize_longitude(ds: xr.Dataset) -> xr.Dataset:
           """If longitude in [0, 360], remap to [-180, 180] and sort (PITFALL M4)."""
           lon = ds["longitude"]
           if float(lon.max()) > 180.0:
               ds = ds.assign_coords(longitude=(((ds.longitude + 180) % 360) - 180)).sortby("longitude")
           return ds

       def _assert_time_coverage(ds: xr.Dataset, horizon_hours: int, label: str) -> None:
           t = ds["time"].values
           span_hours = float((t[-1] - t[0]) / np.timedelta64(1, "h"))
           if span_hours < horizon_hours:
               raise ValueError(f"{label} time coverage {span_hours:.1f}h < horizon {horizon_hours}h")

       def _assert_standard_names(currents: xr.Dataset, winds: xr.Dataset) -> None:
           if currents["uo"].attrs.get("standard_name", "") != "eastward_sea_water_velocity":
               raise ValueError("currents uo standard_name must be eastward_sea_water_velocity (PITFALL M5)")
           # ERA5 conventional name for 10m_u_component_of_wind:
           if "eastward" not in winds["u10"].attrs.get("long_name", "").lower() and \
              winds["u10"].attrs.get("standard_name", "") != "eastward_wind":
               raise ValueError("winds u10 must be eastward wind component (PITFALL M5)")

       def load_env_stack(cmems_path: Path, era5_path: Path, horizon_hours: int = 72) -> EnvStack:
           ...

       def from_synthetic(currents: xr.Dataset, winds: xr.Dataset) -> EnvStack:
           """Test helper: skip file I/O, still runs all invariant checks."""
           ...
       ```
       - `interp_currents` uses `ds[["uo","vo"]].interp(longitude=lon, latitude=lat, time=t_offset, method="linear")` where `t_offset = currents.time[0] + np.timedelta64(int(t_hours*3600), "s")`. Return `(float(ds.uo), float(ds.vo))` — may be NaN (beach-on-NaN handled in tracker).
       - `interp_winds` identical shape for `u10`, `v10`.
       - `load_env_stack` reads files via `xr.open_dataset(..., decode_times=True)`, applies `_normalize_longitude` to both, runs `_assert_time_coverage(..., horizon_hours, "cmems"/"era5")`, runs `_assert_standard_names`, then returns `EnvStack(...)`.
       - `from_synthetic` runs the same invariant checks as `load_env_stack` (minus file I/O) and returns the `EnvStack`. Tests use this.
    2. Create **backend/tests/unit/test_env_data.py** implementing Tests 1-5 above. Use `xr.Dataset` constructors with pandas `date_range("2026-04-17", periods=73, freq="h")` for the time axis. Set `uo.attrs["standard_name"] = "eastward_sea_water_velocity"`, `vo.attrs["standard_name"] = "northward_sea_water_velocity"`, `u10.attrs["standard_name"] = "eastward_wind"`, `v10.attrs["standard_name"] = "northward_wind"`.
    3. Create `backend/tests/__init__.py` and `backend/tests/unit/__init__.py` as empty files if missing (enables pytest discovery under the `backend.tests` package, consistent with Phase 1).
  </action>
  <verify>
    <automated>cd C:/Users/offic/OneDrive/Desktop/DRIFT && python -m pytest backend/tests/unit/test_env_data.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python -m pytest backend/tests/unit/test_env_data.py -x -q` — all 5 tests pass
    - `grep -q "class EnvStack" backend/physics/env_data.py` exits 0
    - `grep -q "def interp_currents" backend/physics/env_data.py` exits 0
    - `grep -q "def interp_winds" backend/physics/env_data.py` exits 0
    - `grep -q "_normalize_longitude" backend/physics/env_data.py` exits 0
    - `grep -q "standard_name" backend/physics/env_data.py` exits 0
    - `grep -q "time coverage" backend/physics/env_data.py` exits 0
    - `python -c "from backend.physics.env_data import EnvStack, load_env_stack, from_synthetic; print('OK')"` exits 0
  </acceptance_criteria>
  <done>EnvStack loads, normalizes lon to [-180,180], asserts 72h time coverage, asserts wind/current standard names, exposes interp_currents/interp_winds. All 5 unit tests green.</done>
</task>

</tasks>

<verification>
- `python -m pytest backend/tests/unit/test_env_data.py backend/tests/unit/test_config.py -q` — all green
- `grep -rn "avg_speed_kmh" backend/` returns matches in both config.py and config.yaml
- `test -f backend/ml/checkpoints/.gitkeep` and `git check-ignore backend/ml/checkpoints/foo.pth` succeeds
</verification>

<success_criteria>
- EnvStack API is the single contract Plan 03 (tracker) consumes
- PITFALLS M3 (time coverage), M4 (lon), M5 (wind components) all handled at load, not in tracker
- `mission.avg_speed_kmh` readable via Settings() with env override
- INFRA-05 dir + gitignore prep complete (kagglehub flow wires in Phase 3)
</success_criteria>

<output>
After completion, create `.planning/phases/02-trajectory-mission-planner/02-01-SUMMARY.md` following the template.
</output>
