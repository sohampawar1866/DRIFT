"""Phase 1 stub for plan_mission. Returns a schema-valid empty MissionPlan
with a degenerate LineString at origin. Real greedy+2-opt TSP planner with
priority scoring and vessel-range/time-budget constraints lands in Phase 2.
"""
from backend.core.config import Settings
from backend.core.schemas import ForecastEnvelope, MissionPlan


def plan_mission(
    forecast: ForecastEnvelope,
    vessel_range_km: float = 200.0,
    hours: float = 8.0,
    origin: tuple[float, float] = (72.8, 18.9),  # Mumbai default
    cfg: Settings | None = None,
) -> MissionPlan:
    """Phase 1 stub. Empty waypoints + degenerate LineString at origin."""
    lon, lat = origin
    return MissionPlan(
        waypoints=[],
        route={
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                # Degenerate: two identical points at origin (valid GeoJSON LineString).
                "coordinates": [[lon, lat], [lon, lat]],
            },
            "properties": {},
        },
        total_distance_km=0.0,
        total_hours=0.0,
        origin=(lon, lat),
    )
