"""Pre-bake 4-AOI fallback JSONs + MANIFEST per CONTEXT D-13, D-16, D-18.

Runs the real chain (`run_inference → forecast_drift → plan_mission`)
deterministically on CPU for each canonical AOI and writes:

    data/prebaked/{aoi}_detections.json     (DetectionFeatureCollection JSON)
    data/prebaked/{aoi}_forecast.json        (ForecastEnvelope JSON)
    data/prebaked/{aoi}_mission.json         (MissionPlan JSON)
    data/prebaked/MANIFEST.json              (generated_at, git_sha, parity hashes)

These are loaded as silent fallback by `scripts/run_full_chain_real.py`
(CONTEXT D-12) if live inference fails mid-demo.

Runs with whatever weights `backend/config.yaml::ml.weights_source` is set
to — `dummy` now (before the trained checkpoint arrives), `our_real` once
you drop `backend/ml/checkpoints/our_real.pt` and flip the YAML. Re-run this
script after the weight flip to refresh the baked artifacts.

Gate (D-18):
    HARD — gulf_of_mannar must have all 3 stages baked.
    SOFT — the other 3 AOIs warn if missing but never fail the script.

Invoke:
    python -m scripts.prebake_demo           # bake all 4 AOIs
    python -m scripts.prebake_demo gulf_of_mannar  # bake one
"""
from __future__ import annotations

import json
import logging
import os
import random
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

PREBAKE_DIR = Path("data/prebaked")
AOIS = (
    "gulf_of_mannar",
    "mumbai_offshore",
    "bay_of_bengal_mouth",
    "arabian_sea_gyre_edge",
)
PRIMARY_AOI = "gulf_of_mannar"
SEED = 1410


def _seed_all(seed: int = SEED) -> None:
    """CPU-only determinism per D-14."""
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        torch.set_num_threads(1)
        try:
            torch.use_deterministic_algorithms(True)
        except RuntimeError:
            pass
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    except ImportError:
        pass


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return out
    except Exception:
        return "unknown"


def _weights_source() -> str:
    try:
        from backend.core.config import Settings
        return Settings().ml.weights_source
    except Exception:
        return "unknown"


def _write_json(path: Path, payload: dict | str) -> int:
    """Write canonical JSON (sort_keys). Returns bytes written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def bake_aoi(aoi_id: str) -> dict:
    """Run the real chain for one AOI; write its 3 fallback JSONs.

    Returns a dict entry suitable for MANIFEST.json (aoi, paths, hashes, counts,
    status). Never raises — any failure is captured as status='failed' so
    the caller can fail the HARD gate cleanly.
    """
    from scripts.parity_hash import parity_hash_json

    from backend.core.config import Settings
    from backend.services.ai_detector import detect_macroplastic
    from backend.services.drift_engine import simulate_drift
    from backend.services.mission_planner import (
        calculate_cleanup_mission_plan,
    )

    _seed_all()
    cfg = Settings()  # noqa: F841 — keeps import chain real

    det_path = PREBAKE_DIR / f"{aoi_id}_detections.json"
    fc_path  = PREBAKE_DIR / f"{aoi_id}_forecast.json"
    ms_path  = PREBAKE_DIR / f"{aoi_id}_mission.json"

    entry: dict = {
        "aoi": aoi_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weights_source": _weights_source(),
        "files": {},
        "hashes": {},
        "stages": {},
        "status": "in_progress",
    }

    try:
        # Stage 1: detections (legacy API shape — fits the fallback contract).
        det_api = detect_macroplastic(aoi_id)
        det_bytes = _write_json(det_path, det_api)
        det_hash = parity_hash_json(json.dumps(det_api, sort_keys=True, default=str))
        entry["files"]["detections"] = str(det_path.as_posix())
        entry["hashes"]["detections"] = det_hash
        entry["stages"]["detections"] = {
            "features": len(det_api.get("features", [])),
            "bytes": det_bytes,
        }

        # Stage 2: forecast (+72 h horizon for the richest fallback).
        fc_api = simulate_drift(det_api, aoi_id, 72)
        fc_bytes = _write_json(fc_path, fc_api)
        fc_hash = parity_hash_json(json.dumps(fc_api, sort_keys=True, default=str))
        entry["files"]["forecast"] = str(fc_path.as_posix())
        entry["hashes"]["forecast"] = fc_hash
        entry["stages"]["forecast"] = {
            "features": len(fc_api.get("features", [])),
            "bytes": fc_bytes,
        }

        # Stage 3: mission (real MissionPlan → canonical JSON via pydantic).
        plan = calculate_cleanup_mission_plan(det_api, aoi_id)
        if plan is None:
            entry["stages"]["mission"] = {"waypoints": 0, "note": "degenerate (out-of-range)"}
            entry["files"]["mission"] = str(ms_path.as_posix())
            # Still write an empty-but-valid placeholder so fallback loaders don't 404.
            placeholder = {"waypoints": [], "route": {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": []},
                "properties": {},
            }, "total_distance_km": 0.0, "total_hours": 0.0, "origin": [0.0, 0.0]}
            ms_bytes = _write_json(ms_path, placeholder)
            entry["hashes"]["mission"] = parity_hash_json(
                json.dumps(placeholder, sort_keys=True, default=str))
            entry["stages"]["mission"]["bytes"] = ms_bytes
        else:
            ms_json = plan.model_dump_json(indent=2)
            ms_bytes = _write_json(ms_path, ms_json)
            entry["files"]["mission"] = str(ms_path.as_posix())
            entry["hashes"]["mission"] = parity_hash_json(ms_json)
            entry["stages"]["mission"] = {
                "waypoints": len(plan.waypoints),
                "total_distance_km": round(plan.total_distance_km, 2),
                "total_hours": round(plan.total_hours, 2),
                "bytes": ms_bytes,
            }

        entry["status"] = "ok"
        return entry
    except Exception as e:
        entry["status"] = "failed"
        entry["error"] = str(e)
        return entry


def bake_all(aois: tuple[str, ...] = AOIS) -> dict:
    """Run the bake for every AOI; write MANIFEST; return the manifest dict."""
    PREBAKE_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for aoi in aois:
        logger.info("prebake: baking %s", aoi)
        entry = bake_aoi(aoi)
        entries.append(entry)
        logger.info("  status=%s, stages=%s", entry["status"], list(entry.get("stages", {}).keys()))

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "weights_source": _weights_source(),
        "seed": SEED,
        "entries": entries,
    }
    manifest_path = PREBAKE_DIR / "MANIFEST.json"
    _write_json(manifest_path, manifest)
    logger.info("prebake: wrote MANIFEST.json with %d entries", len(entries))

    _enforce_gates(manifest)
    return manifest


def _enforce_gates(manifest: dict) -> None:
    """HARD gate: primary AOI must have all 3 stages OK. SOFT gate: warn."""
    entries_by_aoi = {e["aoi"]: e for e in manifest.get("entries", [])}
    primary = entries_by_aoi.get(PRIMARY_AOI)

    if primary is None or primary.get("status") != "ok":
        raise SystemExit(
            f"HARD gate violated: primary AOI '{PRIMARY_AOI}' did not bake "
            f"(status={primary.get('status') if primary else 'missing'}, "
            f"error={primary.get('error') if primary else 'n/a'})"
        )
    required_stages = {"detections", "forecast", "mission"}
    if not required_stages.issubset(primary.get("stages", {}).keys()):
        raise SystemExit(
            f"HARD gate violated: primary AOI '{PRIMARY_AOI}' missing stages. "
            f"Present: {list(primary.get('stages', {}).keys())}"
        )

    for aoi in AOIS:
        if aoi == PRIMARY_AOI:
            continue
        e = entries_by_aoi.get(aoi)
        if e is None or e.get("status") != "ok":
            warnings.warn(
                f"prebake SOFT gate: AOI '{aoi}' did not bake "
                f"(status={e.get('status') if e else 'missing'})",
                UserWarning, stacklevel=2,
            )


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if len(argv) > 1:
        aois = tuple(argv[1:])
        invalid = [a for a in aois if a not in AOIS]
        if invalid:
            print(f"unknown AOI(s): {invalid}; valid: {AOIS}", file=sys.stderr)
            return 2
    else:
        aois = AOIS
    bake_all(aois)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
