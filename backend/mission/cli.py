"""CLI: python -m backend.mission <forecast.json>

Runs the mission planner on a forecast envelope and emits a MissionPlan.
"""
import argparse
import sys
from pathlib import Path

from backend.core.config import Settings
from backend.core.schemas import ForecastEnvelope
from backend.mission.planner import plan_mission


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m backend.mission")
    ap.add_argument("forecast", type=Path,
                    help="ForecastEnvelope JSON (from `python -m backend.physics`)")
    ap.add_argument("--vessel-range-km", type=float, default=200.0)
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--origin", type=str, default="0.0,0.0",
                    help="Origin as 'lon,lat'")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    fe = ForecastEnvelope.model_validate_json(args.forecast.read_text())
    cfg = Settings()
    lon_s, lat_s = args.origin.split(",")
    plan = plan_mission(
        fe,
        vessel_range_km=args.vessel_range_km,
        hours=args.hours,
        origin=(float(lon_s), float(lat_s)),
        cfg=cfg,
    )
    text = plan.model_dump_json(by_alias=True, indent=2)

    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
