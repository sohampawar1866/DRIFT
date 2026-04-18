"""Alerting helpers for deposition hotspot escalation."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

_NGO_DIRECTORY = [
    {"name": "Tree Foundation", "lat": 13.0827, "lon": 80.2707, "contact": "alerts+treefoundation@example.org"},
    {"name": "ReefWatch Marine Trust", "lat": 11.0168, "lon": 76.9558, "contact": "alerts+reefwatch@example.org"},
    {"name": "Blue Coast Collective", "lat": 19.0760, "lon": 72.8777, "contact": "alerts+bluecoast@example.org"},
]

COASTAL_SEGMENT_KM = 5.0
REPO_ROOT = Path(__file__).resolve().parents[2]
COASTLINE_PATH = REPO_ROOT / "backend" / "data" / "india_coastline_segmented.geojson"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _nearest_ngo(lat: float, lon: float) -> dict[str, Any]:
    ranked = sorted(
        (
            {
                **ngo,
                "distance_km": round(_haversine_km(lat, lon, ngo["lat"], ngo["lon"]), 2),
            }
            for ngo in _NGO_DIRECTORY
        ),
        key=lambda x: x["distance_km"],
    )
    return ranked[0]


def _iter_points(coords: Any):
    if not isinstance(coords, (list, tuple)):
        return
    if len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        yield float(coords[0]), float(coords[1])
        return
    for part in coords:
        yield from _iter_points(part)


def _point_at_distance(points: list[tuple[float, float]], cumulative: list[float], target_km: float) -> tuple[float, float]:
    if target_km <= 0.0:
        return points[0]
    if target_km >= cumulative[-1]:
        return points[-1]
    for i in range(1, len(cumulative)):
        if cumulative[i] >= target_km:
            prev_d = cumulative[i - 1]
            seg_d = max(cumulative[i] - prev_d, 1e-9)
            ratio = (target_km - prev_d) / seg_d
            lon0, lat0 = points[i - 1]
            lon1, lat1 = points[i]
            return (lon0 + (lon1 - lon0) * ratio, lat0 + (lat1 - lat0) * ratio)
    return points[-1]


def _segment_line_5km(points: list[tuple[float, float]], source_segment_id: Any) -> list[dict[str, Any]]:
    if len(points) < 2:
        return []

    cumulative = [0.0]
    for i in range(1, len(points)):
        lon0, lat0 = points[i - 1]
        lon1, lat1 = points[i]
        cumulative.append(cumulative[-1] + _haversine_km(lat0, lon0, lat1, lon1))

    total_km = cumulative[-1]
    if total_km <= 0.0:
        return []

    segments: list[dict[str, Any]] = []
    segment_idx = 0
    start_km = 0.0
    while start_km < total_km:
        end_km = min(start_km + COASTAL_SEGMENT_KM, total_km)
        mid_km = (start_km + end_km) * 0.5
        center_lon, center_lat = _point_at_distance(points, cumulative, mid_km)
        segments.append(
            {
                "segment_key": f"{source_segment_id}:{segment_idx}",
                "source_segment_id": source_segment_id,
                "bin_index": segment_idx,
                "center": [round(center_lon, 6), round(center_lat, 6)],
                "length_km": round(end_km - start_km, 3),
            }
        )
        segment_idx += 1
        start_km = end_km
    return segments


@lru_cache(maxsize=1)
def _load_coastal_bins() -> list[dict[str, Any]]:
    if not COASTLINE_PATH.exists():
        return []
    try:
        with COASTLINE_PATH.open("r", encoding="utf-8") as f:
            geojson = json.load(f)
    except Exception:
        return []

    bins: list[dict[str, Any]] = []
    for feature_idx, feature in enumerate(geojson.get("features", [])):
        props = feature.get("properties") or {}
        source_segment_id = props.get("segment_id", feature_idx + 1)
        geom = feature.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []

        lines: list[list[tuple[float, float]]] = []
        if gtype == "LineString":
            line_points = list(_iter_points(coords))
            if line_points:
                lines.append(line_points)
        elif gtype == "MultiLineString":
            for line in coords:
                line_points = list(_iter_points(line))
                if line_points:
                    lines.append(line_points)

        for line in lines:
            bins.extend(_segment_line_5km(line, source_segment_id))
    return bins


def _feature_center(feature: dict[str, Any]) -> tuple[float, float] | None:
    geom = feature.get("geometry") or {}
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "Point" and len(coords) >= 2:
        return float(coords[0]), float(coords[1])

    try:
        if gtype == "Polygon" and coords and coords[0]:
            ring = coords[0]
        elif gtype == "MultiPolygon" and coords and coords[0] and coords[0][0]:
            ring = coords[0][0]
        else:
            return None
        lon = sum(float(pt[0]) for pt in ring) / len(ring)
        lat = sum(float(pt[1]) for pt in ring) / len(ring)
        return lon, lat
    except Exception:
        return None


def _nearest_coastal_bin(lon: float, lat: float, bins: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float | None]:
    if not bins:
        return None, None
    best: dict[str, Any] | None = None
    best_km = float("inf")
    for segment in bins:
        center = segment.get("center")
        if not isinstance(center, list) or len(center) != 2:
            continue
        seg_lon, seg_lat = float(center[0]), float(center[1])
        dist_km = _haversine_km(lat, lon, seg_lat, seg_lon)
        if dist_km < best_km:
            best = segment
            best_km = dist_km
    if best is None:
        return None, None
    return best, best_km


def evaluate_deposition_alerts(
    forecast_fc: dict[str, Any],
    *,
    aoi_id: str,
    forecast_hours: int,
    density_threshold_per_segment: int = 3,
    persistence_hours_threshold: int = 72,
) -> dict[str, Any]:
    """Evaluate deposition hotspots using explicit 5 km coastal segmentation."""
    feats = forecast_fc.get("features", [])
    deposition = [
        f for f in feats
        if (f.get("properties") or {}).get("type") == "deposition_hotspot"
    ]

    coastal_bins = _load_coastal_bins()
    segment_stats: dict[str, dict[str, Any]] = {}

    for feature in deposition:
        center = _feature_center(feature)
        if center is None:
            continue

        lon, lat = center
        props = feature.get("properties") or {}
        density = float(props.get("density", 1.0))
        hotspot_hour = int(props.get("forecast_hour", forecast_hours))
        segment, coast_distance_km = _nearest_coastal_bin(lon, lat, coastal_bins)

        if segment is None:
            segment_key = "offshore_unsegmented"
            source_segment_id = None
            bin_index = None
            segment_center = [round(lon, 6), round(lat, 6)]
            length_km = COASTAL_SEGMENT_KM
        else:
            segment_key = str(segment["segment_key"])
            source_segment_id = segment.get("source_segment_id")
            bin_index = segment.get("bin_index")
            segment_center = list(segment.get("center", [round(lon, 6), round(lat, 6)]))
            length_km = float(segment.get("length_km", COASTAL_SEGMENT_KM))

        entry = segment_stats.setdefault(
            segment_key,
            {
                "segment_key": segment_key,
                "source_segment_id": source_segment_id,
                "bin_index": bin_index,
                "segment_center": segment_center,
                "segment_length_km": round(length_km, 3),
                "hotspot_count": 0,
                "density_score": 0.0,
                "persistence_hours": 0,
                "min_coast_distance_km": None,
            },
        )
        entry["hotspot_count"] += 1
        entry["density_score"] = round(float(entry["density_score"]) + density, 3)
        entry["persistence_hours"] = max(int(entry["persistence_hours"]), hotspot_hour)
        if coast_distance_km is not None:
            prev = entry["min_coast_distance_km"]
            entry["min_coast_distance_km"] = round(
                coast_distance_km if prev is None else min(float(prev), coast_distance_km),
                3,
            )

    segment_alerts: list[dict[str, Any]] = []
    notifications: list[dict[str, Any]] = []

    for segment_key in sorted(segment_stats.keys()):
        entry = segment_stats[segment_key]
        density_score = float(entry["density_score"])
        persistence_hours = int(entry["persistence_hours"])
        segment_triggered = (
            density_score >= float(density_threshold_per_segment)
            and persistence_hours >= int(persistence_hours_threshold)
        )
        segment_alert = {
            **entry,
            "triggered": segment_triggered,
            "threshold_density": float(density_threshold_per_segment),
            "threshold_persistence_hours": int(persistence_hours_threshold),
        }

        if segment_triggered:
            center_lon, center_lat = float(entry["segment_center"][0]), float(entry["segment_center"][1])
            ngo = _nearest_ngo(center_lat, center_lon)
            segment_alert["nearest_ngo"] = {
                "organization": ngo["name"],
                "contact": ngo["contact"],
                "distance_km": ngo["distance_km"],
            }
            notifications.append(
                {
                    "organization": ngo["name"],
                    "contact": ngo["contact"],
                    "distance_km": ngo["distance_km"],
                    "hotspot_center": [round(center_lon, 6), round(center_lat, 6)],
                    "segment_key": segment_key,
                    "channel": "webhook_placeholder",
                }
            )

        segment_alerts.append(segment_alert)

    triggered_count = sum(1 for s in segment_alerts if s.get("triggered"))
    triggered = triggered_count > 0

    return {
        "aoi_id": aoi_id,
        "forecast_hours": int(forecast_hours),
        "deposition_hotspots": len(deposition),
        "coastal_segment_km": COASTAL_SEGMENT_KM,
        "coastal_segments_evaluated": len(segment_alerts),
        "coastal_segments_triggered": triggered_count,
        "threshold_density": float(density_threshold_per_segment),
        "threshold_persistence_hours": int(persistence_hours_threshold),
        "triggered": triggered,
        "segment_alerts": segment_alerts,
        "notifications": notifications if triggered else [],
        "status": "alert_triggered" if triggered else "monitoring",
    }
