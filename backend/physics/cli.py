"""CLI: python -m backend.physics <detections.json>

Phase 1: passes detections through the stub forecast_drift and emits an
empty-frames ForecastEnvelope.
"""
import argparse
import sys
from pathlib import Path

from backend.core.config import Settings
from backend.core.schemas import DetectionFeatureCollection
from backend.physics.tracker import forecast_drift


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m backend.physics")
    ap.add_argument("detections", type=Path,
                    help="DetectionFeatureCollection JSON (from `python -m backend.ml`)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    fc = DetectionFeatureCollection.model_validate_json(args.detections.read_text())
    cfg = Settings()
    envelope = forecast_drift(fc, cfg)
    text = envelope.model_dump_json(by_alias=True, indent=2)

    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
