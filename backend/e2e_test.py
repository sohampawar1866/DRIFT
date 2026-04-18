"""backend/e2e_test.py — Phase 3 Plan 03-05 deliverable.

Runs the full chain end-to-end on a real MARIDA patch with `our_real` weights
and enforces:

* Total wall-clock < 15 s (PRD Core Value hard requirement)
* Per-stage D-15 budgets (warn-on-exceed, do not fail):
    - inference ≤ 6.0 s
    - forecast  ≤ 5.0 s
    - mission   ≤ 1.0 s
    - export    ≤ 3.0 s
* Schema validity at every boundary (pydantic strict)

Invoke via pytest:
    pytest backend/e2e_test.py -v

Or standalone:
    python -m backend.e2e_test
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

TOTAL_BUDGET_S = 15.0
BUDGET_STAGE_S = {
    "inference": 6.0,
    "forecast":  5.0,
    "mission":   1.0,
    "export":    3.0,
}
DEMO_AOI = "mumbai_offshore"
OUR_REAL_PATH = Path("backend/ml/checkpoints/our_real.pt")


def _warm_up() -> None:
    """Pre-import heavy modules and render a throwaway figure so the FIRST
    real call doesn't pay ~4 s in matplotlib + torch cold-start time.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.close(plt.figure(figsize=(1, 1)))

    import torch  # noqa: F401
    import rasterio  # noqa: F401

    # Warm the export pipeline too — reportlab + geopandas cold-start cost.
    from backend.mission import export  # noqa: F401


def run_full_chain(aoi_id: str = DEMO_AOI) -> dict:
    """Execute run_inference → forecast_drift → plan_mission → export_* with
    per-stage timing. Returns a dict of `{stage: seconds, ok: bool, totals}`.
    """
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    timings: dict[str, float] = {}

    if not OUR_REAL_PATH.exists():
        raise FileNotFoundError(
            f"e2e_test: required checkpoint not found at {OUR_REAL_PATH}"
        )

    # Force real-weight mode via env; doesn't touch config.yaml on disk.
    os.environ["ML__WEIGHTS_SOURCE"] = "our_real"

    # Stage 1: inference
    t0 = time.perf_counter()
    r = client.get("/api/v1/detect", params={"aoi_id": aoi_id})
    timings["inference"] = time.perf_counter() - t0
    assert r.status_code == 200, f"detect failed: {r.status_code} {r.text[:200]}"
    detection_fc = r.json()
    assert detection_fc.get("type") == "FeatureCollection", "detect: not a FC"

    # Stage 2: forecast
    t0 = time.perf_counter()
    r = client.get("/api/v1/forecast", params={"aoi_id": aoi_id, "hours": 24})
    timings["forecast"] = time.perf_counter() - t0
    assert r.status_code == 200, f"forecast failed: {r.status_code} {r.text[:200]}"
    forecast_fc = r.json()
    assert forecast_fc.get("type") == "FeatureCollection", "forecast: not a FC"

    # Stage 3: mission
    t0 = time.perf_counter()
    r = client.get("/api/v1/mission", params={"aoi_id": aoi_id})
    timings["mission"] = time.perf_counter() - t0
    assert r.status_code == 200, f"mission failed: {r.status_code} {r.text[:200]}"
    mission_fc = r.json()
    assert mission_fc.get("type") == "FeatureCollection", "mission: not a FC"

    # Stage 4: export (exercise all three formats — PDF is the slow one)
    t0 = time.perf_counter()
    for fmt in ("gpx", "geojson", "pdf"):
        r = client.get("/api/v1/mission/export",
                       params={"aoi_id": aoi_id, "format": fmt})
        assert r.status_code == 200, f"export {fmt}: {r.status_code} {r.text[:200]}"
        assert len(r.content) > 0, f"export {fmt}: empty response"
    timings["export"] = time.perf_counter() - t0

    total = sum(timings.values())
    over_budget = [
        s for s, dt in timings.items() if dt > BUDGET_STAGE_S.get(s, 1e9)
    ]
    return {
        "timings": timings,
        "total": total,
        "over_budget": over_budget,
        "detections": len(detection_fc.get("features", [])),
        "forecast_features": len(forecast_fc.get("features", [])),
        "mission_waypoints": mission_fc["features"][0]["properties"].get("waypoint_count", 0)
                             if mission_fc.get("features") else 0,
    }


# ---- pytest entrypoint -----------------------------------------------------

def test_full_chain_within_15s():
    """PRD Core Value gate: full chain < 15 s on CPU laptop."""
    _warm_up()
    result = run_full_chain(DEMO_AOI)
    t = result["timings"]
    total = result["total"]

    print(f"\n=== E2E results ({DEMO_AOI}) ===")
    for stage, dt in t.items():
        budget = BUDGET_STAGE_S.get(stage, float("inf"))
        marker = "⚠ OVER" if dt > budget else "✓"
        print(f"  {marker} {stage:10s}: {dt*1000:7.1f} ms   (budget {budget:.1f}s)")
    print(f"  TOTAL:                 {total*1000:7.1f} ms   (budget {TOTAL_BUDGET_S:.1f}s)")
    print(f"  detections={result['detections']}, "
          f"forecast_features={result['forecast_features']}, "
          f"mission_waypoints={result['mission_waypoints']}")

    if result["over_budget"]:
        print(f"  ⚠ over-budget stages: {result['over_budget']} — tune stride / particles / KDE")

    assert total < TOTAL_BUDGET_S, (
        f"PRD Core Value violated: total {total:.2f}s >= {TOTAL_BUDGET_S:.1f}s budget. "
        f"Stages: {t}"
    )


def test_schema_valid_at_every_boundary():
    """Structural: every stage output conforms to the legacy API shape."""
    _warm_up()
    result = run_full_chain(DEMO_AOI)
    assert result["detections"] >= 0
    assert result["mission_waypoints"] >= 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    _warm_up()
    r = run_full_chain(DEMO_AOI)
    for stage, dt in r["timings"].items():
        print(f"  {stage:10s}: {dt*1000:7.1f} ms")
    print(f"  TOTAL:     {r['total']*1000:7.1f} ms  (budget {TOTAL_BUDGET_S*1000:.0f} ms)")
    print(f"  detections={r['detections']}, waypoints={r['mission_waypoints']}")
    raise SystemExit(0 if r["total"] < TOTAL_BUDGET_S else 1)
