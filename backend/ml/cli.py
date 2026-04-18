"""CLI entrypoint: python -m backend.ml <tile.tif>

Reads a Sentinel-2 tile, runs real-checkpoint inference, and writes a
schema-valid DetectionFeatureCollection to stdout (or --out path).

NOTE: `run_inference` is imported LAZILY inside main() because this plan
(01-04, Wave 2) runs BEFORE Plan 01-05 (Wave 3) creates
`backend/ml/inference.py`. A top-level import would break
`python -m backend.ml --help` in Wave 2. The lazy import only triggers on
non-help invocations.
"""
import argparse
import sys
from pathlib import Path

from backend.core.config import Settings


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m backend.ml")
    ap.add_argument("tile", type=Path, help="Path to Sentinel-2 tile (.tif)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Write FeatureCollection JSON to this path (default: stdout)")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = Settings()
    # Lazy import: `backend.ml.inference` is created in Plan 01-05 (Wave 3).
    # This CLI exists in Plan 01-04 (Wave 2), so --help must work even without
    # inference.py. The import only runs on actual invocation, not on --help.
    try:
        from backend.ml.inference import run_inference
    except ImportError as e:
        print(f"Error: inference module not available yet: {e}", file=sys.stderr)
        sys.exit(2)
    fc = run_inference(args.tile, cfg)
    text = fc.model_dump_json(by_alias=True, indent=2)

    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
