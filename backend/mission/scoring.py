"""Priority scoring primitives for mission waypoint ranking.

Implements REQ MISSION-01 + D-12 (02-CONTEXT.md) in isolation from the planner
so Plan 04 can consume a single `priority_score(det, origin, envelope, cfg, max_d_km)`
float without re-deriving KDE / distance math.

D-12 formula:

    base      = conf_adj * area_m2 * fraction_plastic       # detection intrinsic
    density   = density_at(centroid, frame@+72h)            # concentration bonus
    access    = 1 - clamp(haversine_km(origin, centroid) / max_distance_km)
    conv      = density_at(centroid, +72h) / density_at(centroid, +0h), fallback 1.0
    weighted  = w_d * density + w_a * access + w_c * conv
    priority  = base * weighted

Weights come from `cfg.mission.weight_density/weight_accessibility/weight_convergence`
(config.yaml default 0.5 / 0.3 / 0.2).

Edge cases (must never raise, must never return NaN):
    - empty density_polygons                -> density_at returns 0.0
    - missing +72h frame                    -> convergence_ratio returns 1.0
    - missing or zero-density +0h frame     -> convergence_ratio returns 1.0
    - origin == centroid                    -> access == 1.0
    - distance >= max_distance_km           -> access == 0.0
    - max_distance_km <= 0                  -> access == 1.0 (degenerate, ignore)

Dependencies are intentionally light: pure numpy-free; shapely + math only, so this
module is importable without torch / rasterio / xarray.
"""
from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Point, shape

from backend.core.config import Settings
from backend.core.schemas import DetectionFeature, ForecastEnvelope

__all__ = [
    "EARTH_RADIUS_KM",
    "haversine_km",
    "detection_centroid",
    "density_at",
    "convergence_ratio",
    "normalized_accessibility",
    "priority_score",
    "score_all",
]

# Mean Earth radius, IUGG (per pyproj / Haversine convention).
EARTH_RADIUS_KM: float = 6371.0088


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lon, lat) points in kilometers.

    Args:
        a: (lon, lat) in degrees.
        b: (lon, lat) in degrees.

    Returns:
        Non-negative float kilometers. Zero when a == b.
    """
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    h = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    )
    # Guard against tiny negative floats from rounding before sqrt.
    h = min(1.0, max(0.0, h))
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def detection_centroid(det: DetectionFeature) -> tuple[float, float]:
    """Return (lon, lat) WGS84 centroid of a DetectionFeature's polygon."""
    poly = shape(det.geometry.model_dump())
    c = poly.centroid
    return (float(c.x), float(c.y))


def _density_from_properties(props: Any) -> float:
    """Read `density` from a polygon feature's properties, default 1.0.

    Accepts dict or pydantic-like object with `.get`.
    """
    if props is None:
        return 1.0
    if isinstance(props, dict):
        value = props.get("density", 1.0)
    else:
        # pydantic BaseModel instance or similar.
        value = getattr(props, "density", 1.0)
    try:
        return float(value) if value is not None else 1.0
    except (TypeError, ValueError):
        return 1.0


def density_at(point: tuple[float, float], frame_polygons: Any) -> float:
    """Sum of `properties.density` across frame polygons containing `point`.

    Each feature may carry a scalar `density` (float); missing -> 1.0.
    Returns 0.0 when no polygon covers the point (including empty collections).

    Args:
        point: (lon, lat) WGS84.
        frame_polygons: geojson FeatureCollection[Feature[Polygon, dict]] per
            ForecastFrame.density_polygons schema.
    """
    features = getattr(frame_polygons, "features", None) or []
    if not features:
        return 0.0
    p = Point(point[0], point[1])
    total = 0.0
    for feat in features:
        poly = shape(feat.geometry.model_dump())
        if poly.covers(p):
            total += _density_from_properties(feat.properties)
    return total


def convergence_ratio(
    point: tuple[float, float],
    envelope: ForecastEnvelope,
) -> float:
    """D-12 convergence term: density(+72h) / density(+0h) at `point`.

    Fallbacks (never NaN, never raise):
        - No +72h frame            -> 1.0
        - No +0h frame             -> treat reference as 1.0 (so ratio == density(+72h))
        - density(+0h) <= 0        -> 1.0 (avoid divide-by-zero, no signal)
    """
    hour_to_frame = {f.hour: f for f in envelope.frames}
    f72 = hour_to_frame.get(72)
    if f72 is None:
        return 1.0
    d72 = density_at(point, f72.density_polygons)
    f0 = hour_to_frame.get(0)
    if f0 is None:
        d0 = 1.0
    else:
        d0 = density_at(point, f0.density_polygons)
    if d0 <= 0.0:
        # No baseline reference -> no meaningful ratio; neutral bonus.
        return 1.0
    return d72 / d0


def normalized_accessibility(distance_km: float, max_distance_km: float) -> float:
    """Linear 1->0 over [0, max_distance_km], clamped to [0, 1].

    Closer waypoints score higher. `max_distance_km <= 0` degenerates to 1.0
    (accessibility disabled) so the caller never has to pre-check vessel range.
    """
    if max_distance_km <= 0.0:
        return 1.0
    d = max(0.0, distance_km)
    if d >= max_distance_km:
        return 0.0
    return 1.0 - (d / max_distance_km)


def priority_score(
    det: DetectionFeature,
    origin: tuple[float, float],
    envelope: ForecastEnvelope,
    cfg: Settings,
    max_distance_km: float,
) -> float:
    """D-12 priority = base * weighted(density, access, convergence).

    Args:
        det: DetectionFeature (polygon geometry + DetectionProperties).
        origin: (lon, lat) vessel departure point.
        envelope: ForecastEnvelope; only frames @ hour in {0, 72} are used.
        cfg: Settings; reads cfg.mission.weight_density/accessibility/convergence.
        max_distance_km: reference distance for accessibility normalization
            (typically `vessel_range_km`).

    Returns:
        Finite non-negative float. Never NaN, never raises on degenerate inputs.
    """
    centroid = detection_centroid(det)

    hour_to_frame = {f.hour: f for f in envelope.frames}
    f72 = hour_to_frame.get(72)
    density72 = density_at(centroid, f72.density_polygons) if f72 is not None else 0.0

    distance_km = haversine_km(origin, centroid)
    access = normalized_accessibility(distance_km, max_distance_km)

    conv = convergence_ratio(centroid, envelope)

    w_d = cfg.mission.weight_density
    w_a = cfg.mission.weight_accessibility
    w_c = cfg.mission.weight_convergence
    weighted = w_d * density72 + w_a * access + w_c * conv

    props = det.properties
    base = float(props.conf_adj) * float(props.area_m2) * float(props.fraction_plastic)

    score = base * weighted
    # Defensive: clamp to non-negative finite. base and all terms are >= 0 by construction,
    # but guard against NaN leaks from malformed input.
    if not math.isfinite(score) or score < 0.0:
        return 0.0
    return score


def score_all(
    envelope: ForecastEnvelope,
    origin: tuple[float, float],
    cfg: Settings,
    vessel_range_km: float,
) -> list[tuple[DetectionFeature, float]]:
    """Rank every source detection in `envelope` by D-12 priority.

    Returned order matches `envelope.source_detections.features` (no sort applied;
    caller - Plan 04 planner - handles selection). Empty envelope -> empty list.
    """
    dets = envelope.source_detections.features
    if not dets:
        return []
    return [
        (det, priority_score(det, origin, envelope, cfg, vessel_range_km))
        for det in dets
    ]
