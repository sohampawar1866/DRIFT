"""Unit tests for backend/mission/scoring.py (REQ MISSION-01, D-12).

Covers:
- Test 1: Zero detections -> score_all returns [].
- Test 2: Single detection, empty density polygons -> finite positive score.
- Test 3: Accessibility monotonicity -> closer scores higher.
- Test 4: Convergence term = density(+72h) / density(+0h) at centroid.
- Test 5: Missing +72h frame -> convergence falls back to 1.0, score finite.
- Test 6: haversine_km sanity: zero distance and ~111.19 km/deg latitude.
"""
from __future__ import annotations

import math

import pytest
from geojson_pydantic import Feature, FeatureCollection, Polygon

from backend.core.config import Settings
from backend.core.schemas import (
    DetectionFeature,
    DetectionFeatureCollection,
    DetectionProperties,
    ForecastEnvelope,
    ForecastFrame,
)
from backend.mission.scoring import (
    convergence_ratio,
    density_at,
    detection_centroid,
    haversine_km,
    normalized_accessibility,
    priority_score,
    score_all,
)


# ---------- Helpers ----------------------------------------------------------


def _square_polygon(cx: float, cy: float, half: float = 0.01) -> Polygon:
    """Axis-aligned square polygon centered at (cx, cy) with half-width half."""
    return Polygon(
        type="Polygon",
        coordinates=[
            [
                (cx - half, cy - half),
                (cx + half, cy - half),
                (cx + half, cy + half),
                (cx - half, cy + half),
                (cx - half, cy - half),
            ]
        ],
    )


def _make_detection(
    lon: float,
    lat: float,
    conf_adj: float = 0.8,
    area_m2: float = 500.0,
    fraction_plastic: float = 0.3,
) -> DetectionFeature:
    return DetectionFeature(
        type="Feature",
        geometry=_square_polygon(lon, lat, half=0.005),
        properties=DetectionProperties(
            conf_raw=conf_adj,
            conf_adj=conf_adj,
            fraction_plastic=fraction_plastic,
            area_m2=area_m2,
            age_days_est=0,
            cls="plastic",
        ),
    )


def _empty_polygon_fc() -> FeatureCollection:
    return FeatureCollection(type="FeatureCollection", features=[])


def _density_fc(cx: float, cy: float, density: float, half: float = 0.05) -> FeatureCollection:
    feat = Feature(
        type="Feature",
        geometry=_square_polygon(cx, cy, half=half),
        properties={"density": density},
    )
    return FeatureCollection(type="FeatureCollection", features=[feat])


def _envelope(
    dets: list[DetectionFeature],
    frames: list[ForecastFrame],
) -> ForecastEnvelope:
    return ForecastEnvelope(
        source_detections=DetectionFeatureCollection(
            type="FeatureCollection", features=dets
        ),
        frames=frames,
        windage_alpha=0.02,
    )


@pytest.fixture(scope="module")
def cfg() -> Settings:
    return Settings()


# ---------- Tests ------------------------------------------------------------


def test_zero_detections_score_all_empty(cfg: Settings) -> None:
    env = _envelope([], frames=[])
    assert score_all(env, origin=(72.8, 18.9), cfg=cfg, vessel_range_km=200.0) == []


def test_single_detection_empty_density_finite_positive(cfg: Settings) -> None:
    det = _make_detection(72.8, 18.9, conf_adj=0.8, area_m2=500.0, fraction_plastic=0.3)
    env = _envelope(
        [det],
        frames=[
            ForecastFrame(hour=0, particle_positions=[(72.8, 18.9)], density_polygons=_empty_polygon_fc()),
            ForecastFrame(hour=72, particle_positions=[(72.8, 18.9)], density_polygons=_empty_polygon_fc()),
        ],
    )
    score = priority_score(det, origin=(72.8, 18.9), envelope=env, cfg=cfg, max_distance_km=200.0)
    assert math.isfinite(score)
    # base = 0.8 * 500 * 0.3 = 120. access=1.0 (origin==centroid), conv=1.0 (both empty => fallback).
    # weighted = 0.5*0 + 0.3*1 + 0.2*1 = 0.5. score = 60.
    assert score > 0.0
    assert score == pytest.approx(120.0 * (0.3 * 1.0 + 0.2 * 1.0), rel=1e-6)


def test_accessibility_monotonicity_closer_scores_higher(cfg: Settings) -> None:
    origin = (72.8, 18.9)
    near = _make_detection(72.81, 18.91)  # ~ 1.5 km away
    far = _make_detection(74.0, 18.9)     # ~ 127 km away
    env = _envelope(
        [near, far],
        frames=[
            ForecastFrame(hour=0, particle_positions=[], density_polygons=_empty_polygon_fc()),
            ForecastFrame(hour=72, particle_positions=[], density_polygons=_empty_polygon_fc()),
        ],
    )
    s_near = priority_score(near, origin, env, cfg, max_distance_km=200.0)
    s_far = priority_score(far, origin, env, cfg, max_distance_km=200.0)
    assert s_near > s_far


def test_convergence_ratio_exact(cfg: Settings) -> None:
    det = _make_detection(72.8, 18.9)
    centroid = detection_centroid(det)
    env = _envelope(
        [det],
        frames=[
            ForecastFrame(
                hour=0,
                particle_positions=[],
                density_polygons=_density_fc(centroid[0], centroid[1], density=1.0),
            ),
            ForecastFrame(
                hour=72,
                particle_positions=[],
                density_polygons=_density_fc(centroid[0], centroid[1], density=2.0),
            ),
        ],
    )
    assert convergence_ratio(centroid, env) == pytest.approx(2.0, rel=1e-9)


def test_missing_hour72_frame_convergence_fallback(cfg: Settings) -> None:
    det = _make_detection(72.8, 18.9)
    env = _envelope(
        [det],
        frames=[
            ForecastFrame(hour=0, particle_positions=[], density_polygons=_empty_polygon_fc()),
            # no hour=72 frame
        ],
    )
    centroid = detection_centroid(det)
    assert convergence_ratio(centroid, env) == 1.0
    score = priority_score(det, origin=(72.8, 18.9), envelope=env, cfg=cfg, max_distance_km=200.0)
    assert math.isfinite(score)
    assert score > 0.0


def test_haversine_sanity() -> None:
    assert haversine_km((72.8, 18.9), (72.8, 18.9)) == pytest.approx(0.0, abs=1e-9)
    # 1 degree of latitude at equator ~ 111.19 km
    d = haversine_km((0.0, 0.0), (0.0, 1.0))
    assert d == pytest.approx(111.19, abs=0.1)


def test_density_at_outside_polygon_is_zero() -> None:
    fc = _density_fc(72.8, 18.9, density=3.0, half=0.001)
    # point far from the small square => 0.0
    assert density_at((75.0, 20.0), fc) == 0.0
    # point inside => 3.0
    assert density_at((72.8, 18.9), fc) == pytest.approx(3.0)


def test_normalized_accessibility_bounds() -> None:
    assert normalized_accessibility(0.0, 100.0) == 1.0
    assert normalized_accessibility(100.0, 100.0) == 0.0
    assert normalized_accessibility(200.0, 100.0) == 0.0  # clamped
    assert normalized_accessibility(50.0, 100.0) == pytest.approx(0.5)
    assert normalized_accessibility(10.0, 0.0) == 1.0  # zero max => unity
