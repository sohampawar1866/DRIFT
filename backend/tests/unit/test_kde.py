"""Unit tests for backend.physics.kde.kde_contour_polygons (D-06, D-07).

Covers:
- Test 1: single tight cluster -> >=1 polygon; polygon contains cluster centroid in WGS84.
- Test 2: two clusters 50 km apart -> 90% isodensity yields >=2 polygons.
- Test 3: <3 particles -> returns empty list (KDE undefined).
"""
from __future__ import annotations

import numpy as np
import pytest
from pyproj import Transformer
from shapely.geometry import Point

from backend.physics.kde import kde_contour_polygons


# UTM zone 43N covers Mumbai / Arabian Sea (lon 72..78 E).
UTM_EPSG_ZONE43N = 32643


def _to_utm(lon: float, lat: float) -> tuple[float, float]:
    t = Transformer.from_crs("EPSG:4326", f"EPSG:{UTM_EPSG_ZONE43N}", always_xy=True)
    x, y = t.transform(lon, lat)
    return float(x), float(y)


def test_single_tight_cluster_returns_polygon_containing_centroid():
    """Test 1: 100 particles jittered ~100 m around a UTM point; returned
    polygon (in WGS84) should contain the original WGS84 centroid.
    """
    # Seed at (72.8, 18.9) -> convert to UTM 43N, jitter by sigma=100 m.
    lon0, lat0 = 72.8, 18.9
    cx, cy = _to_utm(lon0, lat0)
    rng = np.random.default_rng(7)
    pts = np.column_stack([
        rng.normal(cx, 100.0, size=100),
        rng.normal(cy, 100.0, size=100),
    ])

    polys = kde_contour_polygons(pts, utm_epsg=UTM_EPSG_ZONE43N, level=0.90)

    assert len(polys) >= 1, "expected >=1 polygon for a tight cluster"
    centroid_wgs = Point(lon0, lat0)
    assert any(p.contains(centroid_wgs) or p.buffer(1e-4).contains(centroid_wgs)
               for p in polys), (
        "no returned polygon contains the WGS84 cluster centroid"
    )


def test_two_clusters_50km_apart_returns_two_or_more_polygons():
    """Test 2: two distinct clusters 50 km east-apart -> 90% isodensity
    should resolve >=2 polygons.
    """
    lon0, lat0 = 72.8, 18.9
    cx1, cy1 = _to_utm(lon0, lat0)
    # Second cluster 50 km east in UTM meters (x increases eastward).
    cx2, cy2 = cx1 + 50_000.0, cy1

    rng = np.random.default_rng(11)
    sigma = 500.0  # tight clusters so the KDE can clearly separate them.
    pts1 = np.column_stack([
        rng.normal(cx1, sigma, size=80),
        rng.normal(cy1, sigma, size=80),
    ])
    pts2 = np.column_stack([
        rng.normal(cx2, sigma, size=80),
        rng.normal(cy2, sigma, size=80),
    ])
    pts = np.vstack([pts1, pts2])

    polys = kde_contour_polygons(
        pts, utm_epsg=UTM_EPSG_ZONE43N, level=0.90, pad_m=5000.0
    )
    assert len(polys) >= 2, (
        f"expected >=2 polygons for two 50 km-separated clusters, got {len(polys)}"
    )


def test_fewer_than_three_particles_returns_empty_list():
    """Test 3: N<3 -> empty list (KDE undefined)."""
    # 0, 1, 2 particles all must return [].
    assert kde_contour_polygons(np.empty((0, 2)), utm_epsg=UTM_EPSG_ZONE43N) == []
    assert kde_contour_polygons(
        np.array([[500_000.0, 2_000_000.0]]), utm_epsg=UTM_EPSG_ZONE43N
    ) == []
    assert kde_contour_polygons(
        np.array([[500_000.0, 2_000_000.0], [500_100.0, 2_000_050.0]]),
        utm_epsg=UTM_EPSG_ZONE43N,
    ) == []
