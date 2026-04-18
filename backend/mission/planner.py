"""plan_mission: priority-scored greedy + 2-opt TSP with budget enforcement.

Behavior:
  * 0 detections / all-out-of-range / top_k==0 -> empty waypoints, degenerate
    LineString at origin, zero distance, zero hours.
  * Budget exhausted mid-tour -> return visited prefix; partial route returns
    from last reachable waypoint to origin.
  * Route is always closed (origin -> waypoints -> origin).
"""
from __future__ import annotations

from backend.core.config import Settings
from backend.core.schemas import (
    ForecastEnvelope,
    MissionPlan,
    MissionWaypoint,
)
from backend.mission.scoring import (
    detection_centroid,
    haversine_km,
    score_all,
)
from backend.mission.tsp import (
    greedy_nearest_neighbor,
    two_opt,
)


def _degenerate_plan(origin: tuple[float, float]) -> MissionPlan:
    lon, lat = origin
    return MissionPlan(
        waypoints=[],
        route={
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat], [lon, lat]],
            },
            "properties": {},
        },
        total_distance_km=0.0,
        total_hours=0.0,
        origin=(lon, lat),
    )


def _build_plan_from_order(
    origin: tuple[float, float],
    detections_and_scores: list[tuple[tuple[float, float], float]],
    order: list[int],
    avg_speed_kmh: float,
) -> MissionPlan:
    waypoints: list[MissionWaypoint] = []
    coords: list[list[float]] = [[origin[0], origin[1]]]
    cumulative_km = 0.0
    prev = origin
    for k, idx in enumerate(order):
        centroid, score = detections_and_scores[idx]
        leg = haversine_km(prev, centroid)
        cumulative_km += leg
        waypoints.append(MissionWaypoint(
            order=k,
            lon=centroid[0],
            lat=centroid[1],
            arrival_hour=cumulative_km / avg_speed_kmh,
            priority_score=score,
        ))
        coords.append([centroid[0], centroid[1]])
        prev = centroid
    # Return-to-origin leg (route always closed)
    if order:
        cumulative_km += haversine_km(prev, origin)
        coords.append([origin[0], origin[1]])
    else:
        coords.append([origin[0], origin[1]])

    total_hours = cumulative_km / avg_speed_kmh
    return MissionPlan(
        waypoints=waypoints,
        route={
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {},
        },
        total_distance_km=float(cumulative_km),
        total_hours=float(total_hours),
        origin=origin,
    )


def _truncate_to_budget(
    origin: tuple[float, float],
    points: list[tuple[float, float]],
    order: list[int],
    vessel_range_km: float,
    hours: float,
    avg_speed_kmh: float,
) -> list[int]:
    """Walk the tour; stop when adding next waypoint + return-home would
    exceed either budget. Returns the visited prefix (possibly empty).
    """
    if not order:
        return []
    budget_km_time = hours * avg_speed_kmh
    budget_km = min(vessel_range_km, budget_km_time)
    kept: list[int] = []
    prev = origin
    cumulative = 0.0
    for idx in order:
        leg = haversine_km(prev, points[idx])
        return_leg = haversine_km(points[idx], origin)
        if cumulative + leg + return_leg > budget_km:
            break
        kept.append(idx)
        cumulative += leg
        prev = points[idx]
    return kept


def plan_mission(
    forecast: ForecastEnvelope,
    vessel_range_km: float = 200.0,
    hours: float = 8.0,
    origin: tuple[float, float] = (0.0, 0.0),
    cfg: Settings | None = None,
) -> MissionPlan:
    cfg = cfg or Settings()
    avg_speed = cfg.mission.avg_speed_kmh

    # Never raise on empty input.
    if not forecast.source_detections.features:
        return _degenerate_plan(origin)

    # Score all detections.
    scored = score_all(forecast, origin, cfg, vessel_range_km)
    # Drop non-positive scores (e.g., fraction_plastic==0 or out-of-range).
    scored = [(det, s) for det, s in scored if s > 0.0]
    if not scored:
        return _degenerate_plan(origin)

    # Top-K filter (knob from config).
    scored.sort(key=lambda t: t[1], reverse=True)
    top_k = cfg.mission.top_k
    if top_k is not None and top_k >= 0:
        scored = scored[:top_k]
    if not scored:
        return _degenerate_plan(origin)

    candidates = [(detection_centroid(det), s) for det, s in scored]
    points = [c for c, _ in candidates]

    # Greedy + 2-opt TSP.
    order = greedy_nearest_neighbor(origin, points)
    order = two_opt(origin, points, order)

    # Enforce dual budget: drop tail that exceeds vessel_range_km OR time budget.
    order = _truncate_to_budget(origin, points, order,
                                vessel_range_km, hours, avg_speed)
    if not order:
        return _degenerate_plan(origin)

    return _build_plan_from_order(origin, candidates, order, avg_speed)
