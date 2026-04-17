"""One-shot fetch of CMEMS surface currents + ERA5 10m winds (PHYS-02).

Dataset choices (D-02, D-03):
  * CMEMS: GLOBAL_ANALYSISFORECAST_PHY_001_024 (global 1/12 deg hourly,
    vars uo/vo). Fetched via copernicusmarine.open_dataset + .to_netcdf.
  * ERA5: reanalysis-era5-single-levels, vars 10m_u_component_of_wind
    + 10m_v_component_of_wind. Hourly. Fetched via cdsapi.

Bbox (D-04): lon [68, 92], lat [5, 22] -- union of 4 demo AOIs + 2deg buffer.
Temporal: 72 h forward from --start (default "2026-04-15T00:00:00").

Credentials (D-05, fail loud, NEVER silent synthetic fallback):
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

from dotenv import load_dotenv

# Load credentials from .env file if it exists
load_dotenv()


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
    _require_env(
        ["COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD"],
        "CMEMS",
    )
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
        maximum_depth=1.0,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
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
            "area": [BBOX_LAT[1], BBOX_LON[0], BBOX_LAT[0], BBOX_LON[1]],
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
