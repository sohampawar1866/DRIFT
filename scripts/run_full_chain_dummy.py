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
import sys
import time
from pathlib import Path

# When invoked as `python scripts/run_full_chain_dummy.py`, add project root to sys.path.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.core.config import Settings
from backend.core.schemas import (
    DetectionFeatureCollection,
    ForecastEnvelope,
    MissionPlan,
)


def _first_val_patch() -> Path:
    split_file = Path("MARIDA/splits/val_X.txt")
    if not split_file.exists():
        print("ERROR: MARIDA/splits/val_X.txt not found.", file=sys.stderr)
        sys.exit(2)
    first = split_file.read_text().splitlines()[0].strip()
    # val_X.txt entries may omit the "S2_" prefix that .tif files carry.
    candidates = list(Path("MARIDA/patches").rglob(f"{first}.tif"))
    if not candidates:
        candidates = list(Path("MARIDA/patches").rglob(f"S2_{first}.tif"))
    # Filter out label/confidence tifs.
    candidates = [p for p in candidates if not p.stem.endswith(("_cl", "_conf"))]
    if not candidates:
        print(f"ERROR: no .tif found for {first}", file=sys.stderr)
        sys.exit(2)
    return candidates[0]


def _build_synth_env():
    from backend.physics.env_data import from_synthetic
    import xarray as xr
    import numpy as np
    import pandas as pd

    t = pd.date_range("2026-04-15", periods=73, freq="h")
    lon = np.linspace(60, 95, 36)
    lat = np.linspace(0, 25, 26)
    zero = np.zeros((73, 26, 36), dtype=np.float32)
    currents = xr.Dataset(
        {
            "uo": (("time", "latitude", "longitude"), zero + 0.1),
            "vo": (("time", "latitude", "longitude"), zero),
        },
        coords={"time": t, "latitude": lat, "longitude": lon},
    )
    currents["uo"].attrs["standard_name"] = "eastward_sea_water_velocity"
    currents["vo"].attrs["standard_name"] = "northward_sea_water_velocity"
    winds = xr.Dataset(
        {
            "u10": (("time", "latitude", "longitude"), zero + 2.0),
            "v10": (("time", "latitude", "longitude"), zero),
        },
        coords={"time": t, "latitude": lat, "longitude": lon},
    )
    winds["u10"].attrs["standard_name"] = "eastward_wind"
    winds["v10"].attrs["standard_name"] = "northward_wind"
    return from_synthetic(currents, winds)


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
    print(f"[stage] run_inference: {t1-t0:.2f}s -- {len(fc.features)} detections",
          file=sys.stderr)

    # Stage 2: forecast_drift
    from backend.physics.tracker import forecast_drift
    env = _build_synth_env() if args.use_synth_env else None
    t2 = time.perf_counter()
    envelope = forecast_drift(fc, cfg, env=env)
    t3 = time.perf_counter()
    ForecastEnvelope.model_validate_json(envelope.model_dump_json())
    print(f"[stage] forecast_drift: {t3-t2:.2f}s -- {len(envelope.frames)} frames",
          file=sys.stderr)

    # Stage 3: plan_mission
    from backend.mission.planner import plan_mission
    t4 = time.perf_counter()
    plan = plan_mission(envelope, args.vessel_range_km, args.hours, origin, cfg)
    t5 = time.perf_counter()
    MissionPlan.model_validate_json(plan.model_dump_json())
    print(f"[stage] plan_mission: {t5-t4:.2f}s -- {len(plan.waypoints)} waypoints",
          file=sys.stderr)

    total = t5 - t0
    print(f"[total] {total:.2f}s (target < 20 s)", file=sys.stderr)

    text = plan.model_dump_json(by_alias=True, indent=2)
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
