"""Unit tests for backend.mission.planner.plan_mission.

Covers MISSION-02 gate (PITFALL M10) — 5 TSP edge cases:
  E1: 0 detections
  E2: 1 detection
  E3: all out of range
  E4: budget exhausted mid-tour
  E5: singleton top_k
All must return schema-valid MissionPlan with never-raise contract (D-09).
"""
from __future__ import annotations

from backend.core.config import Settings
from backend.core.schemas import (
    DetectionFeature,
    DetectionFeatureCollection,
    DetectionProperties,
    ForecastEnvelope,
    MissionPlan,
)
from backend.mission.planner import plan_mission


def _det(lon: float, lat: float) -> DetectionFeature:
    d = 0.001
    coords = [[
        [lon - d, lat - d], [lon + d, lat - d],
        [lon + d, lat + d], [lon - d, lat + d],
        [lon - d, lat - d],
    ]]
    return DetectionFeature(
        type="Feature",
        geometry={"type": "Polygon", "coordinates": coords},
        properties=DetectionProperties(
            conf_raw=0.9, conf_adj=0.8, fraction_plastic=0.3,
            area_m2=400.0, age_days_est=0,
        ),
    )


def _envelope(dets: list[DetectionFeature]) -> ForecastEnvelope:
    fc = DetectionFeatureCollection(type="FeatureCollection", features=dets)
    return ForecastEnvelope(
        source_detections=fc, frames=[], windage_alpha=0.02,
    )


# ---------- edge case tests ----------

def test_E1_zero_detections():
    """Empty detections -> degenerate plan, never raises."""
    env = _envelope([])
    plan = plan_mission(env, origin=(72.8, 18.9))
    assert isinstance(plan, MissionPlan)
    assert plan.waypoints == []
    coords = plan.route.geometry.coordinates
    assert list(coords[0]) == [72.8, 18.9]
    assert list(coords[-1]) == [72.8, 18.9]
    assert len(coords) == 2
    assert plan.total_distance_km == 0.0
    assert plan.total_hours == 0.0


def test_E2_single_detection():
    """1 detection -> 1 waypoint, route = origin -> wp -> origin."""
    origin = (72.8, 18.9)
    env = _envelope([_det(72.9, 18.9)])  # ~10.5 km east of Mumbai
    plan = plan_mission(env, vessel_range_km=200.0, hours=8.0, origin=origin)

    assert len(plan.waypoints) == 1
    assert plan.waypoints[0].order == 0
    coords = plan.route.geometry.coordinates
    assert len(coords) == 3
    assert list(coords[0]) == [72.8, 18.9]
    assert list(coords[-1]) == [72.8, 18.9]
    assert plan.total_distance_km > 0.0

    cfg = Settings()
    assert abs(plan.total_hours - plan.total_distance_km / cfg.mission.avg_speed_kmh) < 1e-6


def test_E3_all_out_of_range():
    """vessel_range_km=10, all detections ~55 km away -> empty plan (budget can't reach any)."""
    origin = (72.8, 18.9)
    # 0.5 deg east at lat 18.9 is ~52 km
    dets = [_det(73.3 + 0.01 * i, 18.9) for i in range(5)]
    env = _envelope(dets)
    plan = plan_mission(env, vessel_range_km=10.0, hours=1.0, origin=origin)

    assert plan.waypoints == []
    assert plan.total_distance_km == 0.0
    coords = plan.route.geometry.coordinates
    assert len(coords) == 2
    assert list(coords[0]) == [72.8, 18.9]
    assert list(coords[-1]) == [72.8, 18.9]


def test_E4_budget_exhausted_mid_tour():
    """10 detections spaced ~30 km apart, vessel_range_km=120 and hours=4 (time budget = 80 km at 20 km/h).
    Budget = min(120, 80) = 80 km. Should fit ~1-2 waypoints; extras dropped."""
    origin = (72.8, 18.9)
    # Each step ~0.3 deg east ~= 31 km
    dets = [_det(72.8 + 0.3 * (i + 1), 18.9) for i in range(10)]
    env = _envelope(dets)
    plan = plan_mission(env, vessel_range_km=120.0, hours=4.0, origin=origin)

    cfg = Settings()
    assert plan.total_distance_km <= 120.0 + 1e-6
    assert plan.total_distance_km / cfg.mission.avg_speed_kmh <= 4.0 + 1e-6
    assert plan.total_hours <= 4.0 + 1e-6
    assert len(plan.waypoints) < 10  # at least some were dropped
    # Route remains closed
    coords = plan.route.geometry.coordinates
    assert list(coords[0]) == [72.8, 18.9]
    assert list(coords[-1]) == [72.8, 18.9]


def test_E5_singleton_top_k():
    """top_k=1 -> at most 1 waypoint even with 10 detections."""
    origin = (72.8, 18.9)
    dets = [_det(72.8 + 0.01 * (i + 1), 18.9) for i in range(10)]
    env = _envelope(dets)

    cfg = Settings()
    cfg = cfg.model_copy(update={
        "mission": cfg.mission.model_copy(update={"top_k": 1}),
    })
    plan = plan_mission(env, vessel_range_km=200.0, hours=8.0, origin=origin, cfg=cfg)

    assert len(plan.waypoints) <= 1
    # Route shape still closed
    coords = plan.route.geometry.coordinates
    assert list(coords[0]) == [72.8, 18.9]
    assert list(coords[-1]) == [72.8, 18.9]
