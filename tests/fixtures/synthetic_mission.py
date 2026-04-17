"""Reusable synthetic MissionPlan + ForecastEnvelope fixtures for export tests.

No disk I/O, no random seeds, no real weights -- pure pydantic construction.
"""
from __future__ import annotations

from backend.core.schemas import (
    DetectionFeatureCollection,
    ForecastEnvelope,
    ForecastFrame,
    MissionPlan,
    MissionWaypoint,
)


def make_mission_plan(n_waypoints: int = 15,
                      origin: tuple[float, float] = (72.83, 18.94)) -> MissionPlan:
    """15 waypoints walking roughly northwest from Mumbai origin."""
    waypoints: list[MissionWaypoint] = []
    coords: list[list[float]] = [[origin[0], origin[1]]]
    cum_km = 0.0
    for i in range(n_waypoints):
        lon = origin[0] + 0.05 * (i + 1)
        lat = origin[1] + 0.04 * (i + 1)
        leg_km = 6.2  # approx km per 0.05 deg at this latitude
        cum_km += leg_km
        waypoints.append(MissionWaypoint(
            order=i,
            lon=lon,
            lat=lat,
            arrival_hour=cum_km / 20.0,              # avg_speed_kmh=20 per D-13
            priority_score=round(1.0 - i * 0.05, 4),  # descending
        ))
        coords.append([lon, lat])
    coords.append([origin[0], origin[1]])            # close loop
    return MissionPlan(
        waypoints=waypoints,
        route={
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {},
        },
        total_distance_km=float(cum_km),
        total_hours=float(cum_km / 20.0),
        origin=origin,
    )


def make_forecast_envelope(origin: tuple[float, float] = (72.83, 18.94)) -> ForecastEnvelope:
    """Minimal 4-frame ForecastEnvelope (0, 24, 48, 72) with one trivial density polygon at +72.

    Particle positions drift east over time so the currents-table has a
    non-zero magnitude to render (M5).
    """
    empty_fc: DetectionFeatureCollection = DetectionFeatureCollection(
        type="FeatureCollection", features=[],
    )
    frames = []
    for hour in (0, 24, 48, 72):
        density_features = []
        if hour == 72:
            lon, lat = origin
            ring = [[lon - 0.1, lat - 0.1], [lon + 0.1, lat - 0.1],
                    [lon + 0.1, lat + 0.1], [lon - 0.1, lat + 0.1], [lon - 0.1, lat - 0.1]]
            density_features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"density": 0.8, "level": "p90"},
            })
        # Each particle drifts 0.01 deg east per 24h
        dlon = 0.01 * (hour / 24.0)
        particles = [(origin[0] + 0.01 * i + dlon, origin[1]) for i in range(5)]
        frames.append(ForecastFrame(
            hour=hour,
            particle_positions=particles,
            density_polygons={"type": "FeatureCollection", "features": density_features},
        ))
    return ForecastEnvelope(
        source_detections=empty_fc,
        frames=frames,
        windage_alpha=0.02,
    )
