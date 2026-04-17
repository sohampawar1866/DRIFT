---
phase: 02-trajectory-mission-planner
plan: 05
type: execute
wave: 3
depends_on: [02-03, 02-04]
files_modified:
  - scripts/fetch_demo_env.py
  - scripts/run_full_chain_dummy.py
  - backend/tests/integration/test_tracker_real.py
  - backend/tests/integration/test_e2e_dummy_chain.py
autonomous: true
requirements: [PHYS-02, PHYS-05]
must_haves:
  truths:
    - "scripts/fetch_demo_env.py writes data/env/cmems_currents_72h.nc and data/env/era5_winds_72h.nc each < 500 MB (D-04)"
    - "Fetch script fails loud on missing credentials (D-05) — never silent synthetic fallback"
    - "Fetch script uses copernicusmarine.open_dataset + cdsapi (D-02, D-03)"
    - "Real-data smoke: 10 particles at Gulf of Mannar (78.9 E, 9.2 N), 72h, no NaN in output, no particle stranded in Deccan Plateau (PHYS-05)"
    - "scripts/run_full_chain_dummy.py: parameterized CLI (--patch --origin) running run_inference -> forecast_drift -> plan_mission on real MARIDA patch (D-19)"
    - "E2E chain wall-clock < 20 s on CPU laptop with dummy weights"
    - "Every stage boundary passes pydantic validation"
  artifacts:
    - path: scripts/fetch_demo_env.py
      provides: "CMEMS + ERA5 one-shot fetch over union-of-4-AOIs bbox, 72 h"
      min_lines: 120
    - path: scripts/run_full_chain_dummy.py
      provides: "Parameterized E2E driver; per-stage wall-clock print"
      min_lines: 80
    - path: backend/tests/integration/test_tracker_real.py
      provides: "PHYS-05 smoke test — skipped if data/env/*.nc missing"
      min_lines: 60
    - path: backend/tests/integration/test_e2e_dummy_chain.py
      provides: "End-to-end dummy-weight chain test on one MARIDA patch"
      min_lines: 80
  key_links:
    - from: scripts/run_full_chain_dummy.py
      to: backend/ml/inference.py
      via: "run_inference(tile_path, cfg)"
      pattern: "run_inference"
    - from: scripts/run_full_chain_dummy.py
      to: backend/physics/tracker.py
      via: "forecast_drift(detections, cfg)"
      pattern: "forecast_drift"
    - from: scripts/run_full_chain_dummy.py
      to: backend/mission/planner.py
      via: "plan_mission(forecast, ...)"
      pattern: "plan_mission"
    - from: scripts/fetch_demo_env.py
      to: copernicusmarine + cdsapi
      via: "copernicusmarine.open_dataset + cdsapi.Client().retrieve"
      pattern: "copernicusmarine\\.open_dataset|cdsapi"
---

<objective>
Close Phase 2 by (a) shipping the one-shot `fetch_demo_env.py` CMEMS+ERA5 pre-stage script (PHYS-02), (b) running the PHYS-05 real-data smoke test on the Gulf of Mannar, and (c) delivering `scripts/run_full_chain_dummy.py` — the parameterized E2E driver that proves the full `run_inference → forecast_drift → plan_mission` chain works on one MARIDA patch with dummy weights + synthetic or real env data, in under 20 seconds.

Purpose: Phase 2 exit gate. The 43.2 km synthetic test (Plan 03) proves tracker correctness; this plan proves the chain glues end-to-end and real CMEMS/ERA5 data flows through cleanly.
Output: 2 scripts + 2 integration tests. PHYS-05 smoke test skips gracefully if data/env/*.nc absent (fetch is manual, requires creds).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/02-trajectory-mission-planner/02-CONTEXT.md
@.planning/phases/02-trajectory-mission-planner/02-01-env-data-config-PLAN.md
@.planning/phases/02-trajectory-mission-planner/02-03-tracker-PLAN.md
@.planning/phases/02-trajectory-mission-planner/02-04-mission-planner-PLAN.md
@backend/core/schemas.py
@backend/core/config.py
@backend/physics/env_data.py
@backend/physics/tracker.py
@backend/mission/planner.py
@backend/ml/inference.py
@backend/ml/test_inference.py

<interfaces>
Public function chain (D-19 consumes in order):
```python
from backend.ml.inference import run_inference            # tile_path, cfg -> DetectionFeatureCollection
from backend.physics.tracker import forecast_drift        # detections, cfg, env -> ForecastEnvelope
from backend.mission.planner import plan_mission          # forecast, vessel_range_km, hours, origin, cfg -> MissionPlan
```

AOI bboxes (D-04, with +2° buffer merged into `lon [68, 92], lat [5, 22]`):
  * Gulf of Mannar: lon 78-80, lat 8.5-9.5
  * Mumbai offshore: lon 72-74, lat 18-19
  * Bay of Bengal mouth: lon 87-91, lat 20-22
  * Arabian Sea gyre edge: lon 68-70, lat 15-18
  * Union with 2° buffer: lon [68, 92], lat [5, 22]
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: scripts/fetch_demo_env.py (CMEMS + ERA5 one-shot fetch)</name>
  <files>scripts/fetch_demo_env.py, scripts/__init__.py (if missing — or skip if scripts/ is not a Python package)</files>
  <read_first>
    - backend/physics/env_data.py (EnvStack expected variable names uo/vo/u10/v10, standard_name attrs)
    - .planning/phases/02-trajectory-mission-planner/02-CONTEXT.md (D-02, D-03, D-04, D-05)
  </read_first>
  <action>
    Create **scripts/fetch_demo_env.py** (no `__init__.py` needed; run as `python scripts/fetch_demo_env.py`):

    ```python
    """One-shot fetch of CMEMS surface currents + ERA5 10m winds (PHYS-02).

    Dataset choices (D-02, D-03):
      * CMEMS: GLOBAL_ANALYSISFORECAST_PHY_001_024 (global 1/12 deg hourly,
        vars uo/vo). Fetched via copernicusmarine.open_dataset + .to_netcdf.
      * ERA5: reanalysis-era5-single-levels, vars 10m_u_component_of_wind
        + 10m_v_component_of_wind. Hourly. Fetched via cdsapi.

    Bbox (D-04): lon [68, 92], lat [5, 22] -- union of 4 demo AOIs + 2deg buffer.
    Temporal: 72 h forward from --start (default "2026-04-15T00:00:00").

    Credentials (D-05, fail loud):
      * COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD
      * CDSAPI_URL / CDSAPI_KEY (or ~/.cdsapirc)

    Outputs (< 500 MB each per D-04):
      * data/env/cmems_currents_72h.nc
      * data/env/era5_winds_72h.nc

    Usage:
        python scripts/fetch_demo_env.py [--start 2026-04-15T00:00:00]
                                          [--out-dir data/env]
    """
    from __future__ import annotations
    import argparse
    import os
    import sys
    from datetime import datetime, timedelta
    from pathlib import Path


    BBOX_LON = (68.0, 92.0)
    BBOX_LAT = (5.0, 22.0)
    HORIZON_HOURS = 72
    DEFAULT_START = "2026-04-15T00:00:00"


    def _require_env(names: list[str], flow: str) -> None:
        missing = [n for n in names if not os.environ.get(n)]
        if missing:
            print(f"ERROR: missing {flow} credentials: {', '.join(missing)}", file=sys.stderr)
            print("See scripts/fetch_demo_env.py docstring for setup.", file=sys.stderr)
            sys.exit(2)


    def fetch_cmems(start: datetime, end: datetime, out_path: Path) -> None:
        _require_env(["COPERNICUSMARINE_SERVICE_USERNAME",
                      "COPERNICUSMARINE_SERVICE_PASSWORD"], "CMEMS")
        import copernicusmarine
        ds = copernicusmarine.open_dataset(
            dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
            variables=["uo", "vo"],
            minimum_longitude=BBOX_LON[0],
            maximum_longitude=BBOX_LON[1],
            minimum_latitude=BBOX_LAT[0],
            maximum_latitude=BBOX_LAT[1],
            start_datetime=start.isoformat(),
            end_datetime=end.isoformat(),
            minimum_depth=0.0,
            maximum_depth=1.0,       # surface only
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure standard_name attrs are preserved; CMEMS source already carries them.
        ds.to_netcdf(out_path)
        size_mb = out_path.stat().st_size / 1e6
        print(f"[cmems] wrote {out_path} ({size_mb:.1f} MB)")
        if size_mb > 500.0:
            print(f"WARNING: {out_path} exceeds 500 MB budget (D-04)", file=sys.stderr)


    def fetch_era5(start: datetime, end: datetime, out_path: Path) -> None:
        if not (os.environ.get("CDSAPI_KEY") or Path.home().joinpath(".cdsapirc").exists()):
            _require_env(["CDSAPI_KEY"], "ERA5")
        import cdsapi
        c = cdsapi.Client()
        # ERA5 expects date ranges as year/month/day/time lists
        days = []
        cur = start
        while cur <= end:
            days.append(cur)
            cur += timedelta(hours=1)
        years = sorted({d.strftime("%Y") for d in days})
        months = sorted({d.strftime("%m") for d in days})
        day_list = sorted({d.strftime("%d") for d in days})
        time_list = sorted({d.strftime("%H:00") for d in days})
        out_path.parent.mkdir(parents=True, exist_ok=True)
        c.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": "reanalysis",
                "variable": [
                    "10m_u_component_of_wind",
                    "10m_v_component_of_wind",
                ],
                "year": years,
                "month": months,
                "day": day_list,
                "time": time_list,
                "area": [BBOX_LAT[1], BBOX_LON[0], BBOX_LAT[0], BBOX_LON[1]],  # N W S E
                "format": "netcdf",
            },
            str(out_path),
        )
        size_mb = out_path.stat().st_size / 1e6
        print(f"[era5] wrote {out_path} ({size_mb:.1f} MB)")
        if size_mb > 500.0:
            print(f"WARNING: {out_path} exceeds 500 MB budget (D-04)", file=sys.stderr)


    def main() -> None:
        ap = argparse.ArgumentParser(prog="fetch_demo_env", description=__doc__)
        ap.add_argument("--start", default=DEFAULT_START)
        ap.add_argument("--out-dir", default="data/env")
        args = ap.parse_args()
        start = datetime.fromisoformat(args.start)
        end = start + timedelta(hours=HORIZON_HOURS)
        out_dir = Path(args.out_dir)
        fetch_cmems(start, end, out_dir / "cmems_currents_72h.nc")
        fetch_era5(start, end, out_dir / "era5_winds_72h.nc")
        print("DONE.")


    if __name__ == "__main__":
        main()
    ```

    Note: this task creates the script but does NOT run it in CI (requires creds + network). The executor should verify by running `python scripts/fetch_demo_env.py --help` and checking for missing-credential error on a dry-run invocation (without env vars set, it should exit 2).
  </action>
  <verify>
    <automated>cd C:/Users/offic/OneDrive/Desktop/DRIFT && python scripts/fetch_demo_env.py --help</automated>
  </verify>
  <acceptance_criteria>
    - `python scripts/fetch_demo_env.py --help` exits 0 with usage block
    - `grep -q "GLOBAL_ANALYSISFORECAST_PHY_001_024\|cmems_mod_glo_phy_anfc_0.083deg_PT1H-m" scripts/fetch_demo_env.py` exits 0 (D-02 dataset)
    - `grep -q "reanalysis-era5-single-levels" scripts/fetch_demo_env.py` exits 0 (D-03)
    - `grep -q "10m_u_component_of_wind" scripts/fetch_demo_env.py` exits 0
    - `grep -q "10m_v_component_of_wind" scripts/fetch_demo_env.py` exits 0
    - `grep -q "COPERNICUSMARINE_SERVICE_USERNAME" scripts/fetch_demo_env.py` exits 0
    - `grep -qE "BBOX_LON = \(68.0, 92.0\)" scripts/fetch_demo_env.py` exits 0 (D-04)
    - `grep -qE "BBOX_LAT = \(5.0, 22.0\)" scripts/fetch_demo_env.py` exits 0
    - Running with no env vars and no ~/.cdsapirc AND no cached CMEMS creds: `unset COPERNICUSMARINE_SERVICE_USERNAME; python scripts/fetch_demo_env.py --start 2026-04-15T00:00:00` exits non-zero with "missing CMEMS credentials" message (fail-loud per D-05).
  </acceptance_criteria>
  <done>fetch_demo_env.py ships, --help works, fail-loud on missing creds is provable, dataset IDs and bbox match D-02/D-03/D-04.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: scripts/run_full_chain_dummy.py + E2E integration test + real-data smoke test</name>
  <files>scripts/run_full_chain_dummy.py, backend/tests/integration/test_e2e_dummy_chain.py, backend/tests/integration/test_tracker_real.py</files>
  <read_first>
    - backend/ml/inference.py (run_inference signature)
    - backend/physics/tracker.py (forecast_drift signature, env kwarg)
    - backend/mission/planner.py (plan_mission signature)
    - backend/physics/env_data.py (load_env_stack signature)
    - backend/tests/integration/test_inference_dummy.py (MARIDA patch discovery pattern)
    - .planning/phases/02-trajectory-mission-planner/02-CONTEXT.md (D-15 beach-on-NaN, D-19 E2E chain)
  </read_first>
  <behavior>
    - **E2E test**: find first MARIDA val patch; run full chain with synthetic env (build in-test via env_data.from_synthetic with constant 0.1 m/s current + 2 m/s wind); assert each stage output validates via pydantic round-trip; assert wall-clock < 20 s.
    - **Real-data smoke (PHYS-05)**: skip if `data/env/cmems_currents_72h.nc` missing (decorator `@pytest.mark.skipif`). Otherwise, build a synthetic `DetectionFeatureCollection` with 10 tiny polygons clustered at (78.9, 9.2) Gulf of Mannar, call `forecast_drift` with `env=load_env_stack(...)`. Assert, for **every frame** (not just final) and **every alive particle**: (a) `lon`/`lat` finite (no NaN); (b) inside Indian Ocean basin `lon [68, 95]`, `lat [0, 25]`; (c) NOT inside the rectangular Deccan Plateau exclusion box `DECCAN_BBOX = (80.0, 88.0, 15.0, 24.0)` — this is the PHYS-05 "no Deccan crossings" gate. Per D-15, beached particles retain their last valid sea position, so they naturally pass this check; only a tracker bug that propagates particles across land would fail. Also require `len(final.particle_positions) >= 25` (≥ 5 of 10 detections × `particles_per_detection`/something reasonable — use cfg.physics.particles_per_detection to compute threshold).
    - **Driver script**: `python scripts/run_full_chain_dummy.py --patch <path>` prints per-stage wall-clock to stdout, validates each boundary, writes final MissionPlan JSON to stdout or `--out`.
  </behavior>
  <action>
    Create **scripts/run_full_chain_dummy.py**:

    ```python
    """End-to-end dummy-weight chain driver (D-19).

    Pipeline:
        run_inference(tile) -> DetectionFeatureCollection
        forecast_drift(detections, cfg, env) -> ForecastEnvelope
        plan_mission(forecast, vessel_range_km, hours, origin, cfg) -> MissionPlan

    Each boundary is pydantic-validated; per-stage wall-clock is printed.
    Target: < 20 s total on CPU laptop.
    """
    from __future__ import annotations
    import argparse
    import json
    import sys
    import time
    from pathlib import Path

    from backend.core.config import Settings
    from backend.core.schemas import (
        DetectionFeatureCollection,
        ForecastEnvelope,
        MissionPlan,
    )


    def _first_val_patch() -> Path:
        """Return first tile listed in MARIDA/splits/val_X.txt."""
        split_file = Path("MARIDA/splits/val_X.txt")
        if not split_file.exists():
            print("ERROR: MARIDA/splits/val_X.txt not found.", file=sys.stderr)
            sys.exit(2)
        first = split_file.read_text().splitlines()[0].strip()
        # val_X.txt entries are patch stems like "S2_1-12-19_48MYU_0"; resolve to .tif
        tif_candidates = list(Path("MARIDA/patches").rglob(f"{first}.tif"))
        if not tif_candidates:
            print(f"ERROR: no .tif found for {first}", file=sys.stderr)
            sys.exit(2)
        return tif_candidates[0]


    def main() -> None:
        ap = argparse.ArgumentParser(prog="run_full_chain_dummy")
        ap.add_argument("--patch", type=Path, default=None)
        ap.add_argument("--origin", nargs=2, type=float, default=[72.8, 18.9],
                        metavar=("LON", "LAT"))
        ap.add_argument("--vessel-range-km", type=float, default=200.0)
        ap.add_argument("--hours", type=float, default=8.0)
        ap.add_argument("--use-synth-env", action="store_true",
                        help="Build synthetic EnvStack instead of loading data/env/*.nc")
        ap.add_argument("--out", type=Path, default=None)
        args = ap.parse_args()

        patch = args.patch or _first_val_patch()
        origin = (float(args.origin[0]), float(args.origin[1]))
        cfg = Settings()

        # Stage 1: run_inference
        from backend.ml.inference import run_inference
        t0 = time.perf_counter()
        fc = run_inference(patch, cfg)
        t1 = time.perf_counter()
        assert isinstance(fc, DetectionFeatureCollection)
        DetectionFeatureCollection.model_validate_json(fc.model_dump_json(by_alias=True))
        print(f"[stage] run_inference: {t1-t0:.2f}s -- {len(fc.features)} detections", file=sys.stderr)

        # Stage 2: forecast_drift
        from backend.physics.tracker import forecast_drift
        env = None
        if args.use_synth_env:
            from backend.physics.env_data import from_synthetic
            import xarray as xr, numpy as np, pandas as pd
            t = pd.date_range("2026-04-15", periods=73, freq="h")
            lon = np.linspace(60, 95, 36)
            lat = np.linspace(0, 25, 26)
            zero = np.zeros((73, 26, 36), dtype=np.float32)
            currents = xr.Dataset(
                {"uo": (("time", "latitude", "longitude"), zero + 0.1),
                 "vo": (("time", "latitude", "longitude"), zero)},
                coords={"time": t, "latitude": lat, "longitude": lon},
            )
            currents["uo"].attrs["standard_name"] = "eastward_sea_water_velocity"
            currents["vo"].attrs["standard_name"] = "northward_sea_water_velocity"
            winds = xr.Dataset(
                {"u10": (("time", "latitude", "longitude"), zero + 2.0),
                 "v10": (("time", "latitude", "longitude"), zero)},
                coords={"time": t, "latitude": lat, "longitude": lon},
            )
            winds["u10"].attrs["standard_name"] = "eastward_wind"
            winds["v10"].attrs["standard_name"] = "northward_wind"
            env = from_synthetic(currents, winds)
        t2 = time.perf_counter()
        envelope = forecast_drift(fc, cfg, env=env)
        t3 = time.perf_counter()
        ForecastEnvelope.model_validate_json(envelope.model_dump_json())
        print(f"[stage] forecast_drift: {t3-t2:.2f}s -- {len(envelope.frames)} frames", file=sys.stderr)

        # Stage 3: plan_mission
        from backend.mission.planner import plan_mission
        t4 = time.perf_counter()
        plan = plan_mission(envelope, args.vessel_range_km, args.hours, origin, cfg)
        t5 = time.perf_counter()
        MissionPlan.model_validate_json(plan.model_dump_json())
        print(f"[stage] plan_mission: {t5-t4:.2f}s -- {len(plan.waypoints)} waypoints", file=sys.stderr)

        total = t5 - t0
        print(f"[total] {total:.2f}s (target < 20 s)", file=sys.stderr)

        text = plan.model_dump_json(by_alias=True, indent=2)
        if args.out:
            args.out.write_text(text)
        else:
            sys.stdout.write(text)


    if __name__ == "__main__":
        main()
    ```

    Create **backend/tests/integration/test_e2e_dummy_chain.py**:

    ```python
    """E2E chain test (D-19 scripted). Uses synthetic env to avoid NetCDF deps."""
    import subprocess
    import sys
    import time
    from pathlib import Path

    import pytest

    from backend.core.schemas import MissionPlan


    def _has_marida() -> bool:
        sp = Path("MARIDA/splits/val_X.txt")
        return sp.exists() and sp.read_text().strip() != ""


    @pytest.mark.skipif(not _has_marida(), reason="MARIDA val split not available")
    def test_full_chain_dummy_synth_env(tmp_path):
        out = tmp_path / "plan.json"
        t0 = time.perf_counter()
        cp = subprocess.run(
            [sys.executable, "scripts/run_full_chain_dummy.py",
             "--use-synth-env", "--out", str(out)],
            capture_output=True, text=True, timeout=120,
        )
        elapsed = time.perf_counter() - t0
        assert cp.returncode == 0, f"stderr:\n{cp.stderr}"
        assert out.exists()
        plan = MissionPlan.model_validate_json(out.read_text())
        assert plan.route.geometry.type == "LineString"
        assert elapsed < 20.0, f"wall-clock {elapsed:.2f}s exceeds 20s budget"
    ```

    Create **backend/tests/integration/test_tracker_real.py**:

    ```python
    """PHYS-05 real-data smoke test. Skips if data/env/*.nc absent."""
    from pathlib import Path

    import numpy as np
    import pytest

    from backend.core.config import Settings
    from backend.core.schemas import (
        DetectionFeature,
        DetectionFeatureCollection,
        DetectionProperties,
    )
    from backend.physics.env_data import load_env_stack
    from backend.physics.tracker import forecast_drift


    CMEMS = Path("data/env/cmems_currents_72h.nc")
    ERA5 = Path("data/env/era5_winds_72h.nc")

    # PHYS-05 Deccan Plateau exclusion box (lon_min, lon_max, lat_min, lat_max).
    # Any particle landing inside this rectangle has crossed land -- tracker bug.
    # Beached particles (D-15) retain their last valid sea position, so they
    # naturally pass this check; only propagation-across-land would fail it.
    DECCAN_BBOX = (80.0, 88.0, 15.0, 24.0)


    def _mannar_detection(lon: float, lat: float, idx: int) -> DetectionFeature:
        # Tiny square polygon (~200 m side at that latitude)
        d = 0.001
        coords = [[[lon-d, lat-d], [lon+d, lat-d],
                   [lon+d, lat+d], [lon-d, lat+d], [lon-d, lat-d]]]
        return DetectionFeature(
            type="Feature",
            geometry={"type": "Polygon", "coordinates": coords},
            properties=DetectionProperties(
                conf_raw=0.8, conf_adj=0.8, fraction_plastic=0.3,
                area_m2=400.0, age_days_est=0,
            ),
        )


    @pytest.mark.skipif(not (CMEMS.exists() and ERA5.exists()),
                        reason="data/env/*.nc not present (run scripts/fetch_demo_env.py)")
    def test_gulf_of_mannar_72h_smoke():
        # Seed 10 detections jittered around (78.9, 9.2)
        rng = np.random.default_rng(0)
        feats = []
        for i in range(10):
            dlon = rng.normal(0, 0.02)  # ~2 km
            dlat = rng.normal(0, 0.02)
            feats.append(_mannar_detection(78.9 + dlon, 9.2 + dlat, i))
        fc = DetectionFeatureCollection(type="FeatureCollection", features=feats)
        cfg = Settings()
        env = load_env_stack(CMEMS, ERA5, cfg.physics.horizon_hours)
        envelope = forecast_drift(fc, cfg, env=env)

        assert len(envelope.frames) == 73

        lon_min, lon_max, lat_min, lat_max = DECCAN_BBOX
        for frame in envelope.frames:
            for (lon, lat) in frame.particle_positions:
                # (a) finite (no NaN) -- beached particles carry last valid sea pos (D-15)
                assert np.isfinite(lon) and np.isfinite(lat), \
                    f"NaN at hour={frame.hour}: ({lon}, {lat})"
                # (b) inside Indian Ocean basin
                assert 68.0 <= lon <= 95.0, f"lon out of basin at hour={frame.hour}: {lon}"
                assert 0.0 <= lat <= 25.0, f"lat out of basin at hour={frame.hour}: {lat}"
                # (c) PHYS-05: NOT inside Deccan Plateau exclusion box
                assert not (lon_min < lon < lon_max and lat_min < lat < lat_max), \
                    f"particle entered Deccan Plateau at hour {frame.hour}: ({lon:.3f}, {lat:.3f})"

        # Final-hour sanity: beach-on-NaN may freeze some; require >= 5 of 10 detections'
        # worth of particles still alive (using cfg.physics.particles_per_detection).
        final = envelope.frames[-1]
        min_survivors = 10 * cfg.physics.particles_per_detection // 4
        assert len(final.particle_positions) >= min_survivors, \
            f"only {len(final.particle_positions)} particles survived (need >= {min_survivors})"
    ```
  </action>
  <verify>
    <automated>cd C:/Users/offic/OneDrive/Desktop/DRIFT && python -m pytest backend/tests/integration/test_e2e_dummy_chain.py backend/tests/integration/test_tracker_real.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python scripts/run_full_chain_dummy.py --help` exits 0
    - `grep -q "run_inference" scripts/run_full_chain_dummy.py` exits 0
    - `grep -q "forecast_drift" scripts/run_full_chain_dummy.py` exits 0
    - `grep -q "plan_mission" scripts/run_full_chain_dummy.py` exits 0
    - `grep -q "perf_counter" scripts/run_full_chain_dummy.py` exits 0 (per-stage timing, D-19)
    - `grep -q "use-synth-env" scripts/run_full_chain_dummy.py` exits 0
    - `grep -q "72.8" scripts/run_full_chain_dummy.py` exits 0 (Mumbai default origin)
    - `grep -q "DECCAN_BBOX" backend/tests/integration/test_tracker_real.py` exits 0 (PHYS-05 Deccan exclusion gate)
    - `grep -q "entered Deccan Plateau" backend/tests/integration/test_tracker_real.py` exits 0 (per-frame assertion message)
    - `python -m pytest backend/tests/integration/test_e2e_dummy_chain.py -x -q` — E2E test passes (under 20 s wall-clock; skips cleanly if MARIDA absent)
    - `python -m pytest backend/tests/integration/test_tracker_real.py -x -q` — either passes (if CMEMS+ERA5 fetched) OR skips with clear reason message
    - Full final phase pytest sweep: `python -m pytest backend/tests -q` exits 0 (all Phase 1 + Phase 2 tests green)
  </acceptance_criteria>
  <done>scripts/run_full_chain_dummy.py + E2E integration test + real-data smoke test all shipped. Phase 2 chain proven to round-trip pydantic-valid JSON end-to-end in < 20 s, with PHYS-05 Deccan Plateau exclusion enforced per-frame.</done>
</task>

</tasks>

<verification>
- `python -m pytest backend/tests -q` — all plans' tests green
- `python scripts/fetch_demo_env.py --help` works
- `python scripts/run_full_chain_dummy.py --use-synth-env` produces pydantic-valid MissionPlan on stdout in < 20 s on CPU laptop
- Real-data smoke either green or skipped-with-reason (never false green)
</verification>

<success_criteria>
- PHYS-02: fetch_demo_env.py ships with fail-loud creds + correct dataset IDs + bbox
- PHYS-05: real-data smoke test ready (runs when data fetched, skips cleanly otherwise), with per-frame Deccan Plateau exclusion assertion enforcing "no Deccan crossings" gate
- D-19 E2E driver + test prove the run_inference → forecast_drift → plan_mission chain works end-to-end
- Phase 2 exit criteria (ROADMAP §Phase 2 success #4 and #5) both met
</success_criteria>

<output>
After completion, create `.planning/phases/02-trajectory-mission-planner/02-05-SUMMARY.md`.
</output>
