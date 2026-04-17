"""Integration test for plan_mission happy path (I1).

15 detections on a 5x3 grid around Mumbai, vessel_range_km=200, hours=8.
Asserts closed route, strict ordering, budgets honored, LineString shape.
"""
from __future__ import annotations

from backend.core.schemas import (
    DetectionFeature,
    DetectionFeatureCollection,
    DetectionProperties,
    ForecastEnvelope,
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
            area_m2=500.0, age_days_est=0,
        ),
    )


def test_I1_fifteen_detection_happy_path():
    origin = (72.8, 18.9)
    # 5x3 grid spanning 0.3 deg x 0.2 deg around Mumbai
    dets = []
    for i in range(5):
        for j in range(3):
            lon = 72.8 + 0.06 * (i + 1)  # ~6 km steps
            lat = 18.9 + 0.04 * (j - 1)  # center row at lat=18.9
            dets.append(_det(lon, lat))
    assert len(dets) == 15

    fc = DetectionFeatureCollection(type="FeatureCollection", features=dets)
    env = ForecastEnvelope(source_detections=fc, frames=[], windage_alpha=0.02)

    plan = plan_mission(env, vessel_range_km=200.0, hours=8.0, origin=origin)

    assert len(plan.waypoints) >= 3, f"expected >=3 waypoints, got {len(plan.waypoints)}"
    assert plan.total_distance_km <= 200.0 + 1e-6
    assert plan.total_hours <= 8.0 + 1e-6
    assert plan.waypoints[0].order == 0
    # Strict monotonic integer ordering 0..N-1
    for idx, wp in enumerate(plan.waypoints):
        assert wp.order == idx

    assert plan.route.geometry.type == "LineString"
    coords = plan.route.geometry.coordinates
    assert list(coords[0]) == [72.8, 18.9]
    assert list(coords[-1]) == [72.8, 18.9]
    # coords = origin + waypoints + origin
    assert len(coords) == len(plan.waypoints) + 2
