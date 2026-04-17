"""Phase 3 E2E driver: run_inference -> forecast_drift -> plan_mission with
silent auto-fallback at each stage boundary (D-12).

Usage:
    python scripts/run_full_chain_real.py --tile path.tif --aoi gulf_of_mannar \
        --origin 78.9 9.2 [--no-fallback] [--out-dir out/]

Exits 0 on success (either live or via fallback). Exits 2 if a stage fails
AND no fallback is available (--no-fallback OR prebake missing).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Callable, Type, TypeVar

# When invoked as `python scripts/run_full_chain_real.py`, add project root to sys.path.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pydantic import BaseModel

from backend.core.config import Settings
from backend.core.schemas import (
    DetectionFeatureCollection,
    ForecastEnvelope,
    MissionPlan,
)

log = logging.getLogger("drift.e2e")

PREBAKE_DIR = Path("data/prebaked")

T = TypeVar("T", bound=BaseModel)


class StageFailed(Exception):
    """Raised when a stage fails AND fallback is unavailable/invalid."""


def _with_fallback(
    stage_name: str,
    aoi: str,
    live_fn: Callable[[], T],
    schema_cls: Type[T],
    *,
    no_fallback: bool = False,
) -> tuple[T, float, str]:
    """Returns (result, elapsed_s, source) where source in {'live','fallback'}."""
    t0 = time.perf_counter()
    try:
        result = live_fn()
        elapsed = time.perf_counter() - t0
        log.info(f"[OK] stage={stage_name} elapsed={elapsed:.2f}s aoi={aoi}")
        return result, elapsed, "live"
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        if no_fallback:
            raise
        fallback_path = PREBAKE_DIR / f"{aoi}_{stage_name}.json"
        log.warning(
            f"[FALLBACK] stage={stage_name} aoi={aoi} "
            f"reason={type(exc).__name__}: {exc}"
        )
        if not fallback_path.exists():
            raise StageFailed(
                f"stage={stage_name} aoi={aoi} failed AND no prebaked fallback "
                f"at {fallback_path}"
            ) from exc
        try:
            payload = json.loads(fallback_path.read_text(encoding="utf-8"))
            validated = schema_cls.model_validate(payload)
        except Exception as v_exc:
            raise StageFailed(
                f"stage={stage_name} aoi={aoi}: live failed ({exc}) "
                f"AND fallback schema invalid ({v_exc})"
            ) from v_exc
        return validated, elapsed, "fallback"


def run_chain(
    aoi: str,
    tile_path: Path,
    origin: tuple[float, float],
    cfg: Settings,
    *,
    no_fallback: bool = False,
) -> dict:
    """Returns a dict: {detections, forecast, mission, timings, sources}."""
    # Lazy imports: avoid heavy startup when only --help is requested.
    from backend.ml.inference import run_inference
    from backend.physics.tracker import forecast_drift
    from backend.mission.planner import plan_mission

    detections, t_det, src_det = _with_fallback(
        "detections", aoi,
        lambda: run_inference(tile_path, cfg),
        DetectionFeatureCollection,
        no_fallback=no_fallback,
    )
    forecast, t_fc, src_fc = _with_fallback(
        "forecast", aoi,
        lambda: forecast_drift(detections, cfg),
        ForecastEnvelope,
        no_fallback=no_fallback,
    )
    mission, t_ms, src_ms = _with_fallback(
        "mission", aoi,
        lambda: plan_mission(forecast, 200.0, 8.0, origin, cfg),
        MissionPlan,
        no_fallback=no_fallback,
    )
    return {
        "detections": detections,
        "forecast": forecast,
        "mission": mission,
        "timings": {"detections": t_det, "forecast": t_fc, "mission": t_ms},
        "sources": {"detections": src_det, "forecast": src_fc, "mission": src_ms},
    }


def _main() -> int:
    ap = argparse.ArgumentParser(prog="run_full_chain_real")
    ap.add_argument("--tile", type=Path, required=True,
                    help="Path to Sentinel-2 tile .tif")
    ap.add_argument("--aoi", required=True,
                    help="AOI id (e.g., gulf_of_mannar) -- used to select fallback JSON")
    ap.add_argument("--origin", type=float, nargs=2, required=True,
                    metavar=("LON", "LAT"), help="Vessel origin (lon lat)")
    ap.add_argument("--no-fallback", action="store_true",
                    help="Disable silent fallback (useful for debugging)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="If set, write stage JSONs here")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    cfg = Settings()
    try:
        result = run_chain(
            args.aoi, args.tile, tuple(args.origin), cfg,
            no_fallback=args.no_fallback,
        )
    except StageFailed as e:
        log.error(str(e))
        return 2

    total = sum(result["timings"].values())
    log.info(
        f"total elapsed={total:.2f}s "
        f"sources=detections:{result['sources']['detections']} "
        f"forecast:{result['sources']['forecast']} "
        f"mission:{result['sources']['mission']}"
    )
    if args.out_dir is not None:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / f"{args.aoi}_detections.json").write_text(
            result["detections"].model_dump_json(indent=2), encoding="utf-8")
        (args.out_dir / f"{args.aoi}_forecast.json").write_text(
            result["forecast"].model_dump_json(indent=2), encoding="utf-8")
        (args.out_dir / f"{args.aoi}_mission.json").write_text(
            result["mission"].model_dump_json(indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
