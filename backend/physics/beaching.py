"""Long-horizon beaching tracker + landfall KDE (OceanTrace).

The /forecast API stays at 72h (frozen schema). This module runs the
*active* 15-day forecast with a *90-day absolute beaching cutoff* used
to populate the deposition_heatmap layer on the dashboard. Particles
flip DRIFTING → BEACHED on:
  - NaN current sample (existing beach-on-NaN heuristic), OR
  - global_land_mask says position is on land

Beached positions enter `deposited` and are frozen at landfall time.
After integration, gaussian_kde over `deposited` (lon, lat) produces
the Landfall Impact Zones FeatureCollection.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import utm as utm_lib
from geojson_pydantic import Feature
from pyproj import Transformer
from shapely.geometry import Polygon, mapping, shape

from backend.physics.env_data import EnvStack

logger = logging.getLogger(__name__)

ACTIVE_HOURS: int = 15 * 24
BEACHING_CUTOFF_HOURS: int = 90 * 24
JITTER_M: float = 50.0
COAST_THRESHOLD_M: float = 500.0


@dataclass
class BeachingResult:
    deposited_lonlat: list[tuple[float, float, float]] = field(default_factory=list)
    final_drifting_lonlat: list[tuple[float, float]] = field(default_factory=list)
    landfall_features: list[dict] = field(default_factory=list)


def _utm_zone(lon: float, lat: float) -> int:
    _, _, zone, _ = utm_lib.from_latlon(lat, lon)
    return 32600 + zone


def _is_on_land(lon: float, lat: float) -> bool:
    try:
        from global_land_mask import globe
        return bool(globe.is_land(lat, lon))
    except Exception:
        return False


def run_beaching_forecast(
    detection_centroids_lonlat: list[tuple[float, float]],
    env: EnvStack,
    n_particles: int = 30,
    active_hours: int = ACTIVE_HOURS,
    cutoff_hours: int = BEACHING_CUTOFF_HOURS,
    windage_alpha: float = 0.02,
    dt_s: float = 3600.0,
    rng: np.random.Generator | None = None,
) -> BeachingResult:
    """Run Lagrangian integrator with beaching state machine.

    Stops integrating particle once it beaches; absolute termination at
    cutoff_hours (drop from result). Returns deposited positions +
    landfall KDE polygons.
    """
    if rng is None:
        rng = np.random.default_rng(42)

    deposited: list[tuple[float, float, float]] = []
    drifting_final: list[tuple[float, float]] = []

    horizon = min(cutoff_hours, max(active_hours, 1))

    for (lon0, lat0) in detection_centroids_lonlat:
        utm_epsg = _utm_zone(lon0, lat0)
        to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
        to_wgs = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
        cx, cy = to_utm.transform(lon0, lat0)

        pts = np.column_stack([
            rng.normal(cx, JITTER_M, size=n_particles),
            rng.normal(cy, JITTER_M, size=n_particles),
        ])
        alive = np.ones(n_particles, dtype=bool)
        beach_time = np.full(n_particles, -1.0)

        for hour in range(1, horizon + 1):
            if not alive.any():
                break
            lons, lats = to_wgs.transform(pts[:, 0].tolist(), pts[:, 1].tolist())
            for i in range(n_particles):
                if not alive[i]:
                    continue
                lon_i, lat_i = float(lons[i]), float(lats[i])
                t_h = float(hour - 1)
                try:
                    uo, vo = env.interp_currents(lon_i, lat_i, t_h)
                except Exception:
                    uo, vo = float("nan"), float("nan")
                try:
                    u10, v10 = env.interp_winds(lon_i, lat_i, t_h)
                except Exception:
                    u10, v10 = 0.0, 0.0

                if not (np.isfinite(uo) and np.isfinite(vo)) or _is_on_land(lon_i, lat_i):
                    alive[i] = False
                    beach_time[i] = float(hour)
                    deposited.append((lon_i, lat_i, float(hour)))
                    continue

                if not np.isfinite(u10):
                    u10 = 0.0
                if not np.isfinite(v10):
                    v10 = 0.0
                vx = float(uo) + windage_alpha * float(u10)
                vy = float(vo) + windage_alpha * float(v10)
                pts[i, 0] += vx * dt_s
                pts[i, 1] += vy * dt_s

            if hour > active_hours:
                continue

        lons_f, lats_f = to_wgs.transform(pts[alive, 0].tolist(), pts[alive, 1].tolist())
        for lo, la in zip(lons_f, lats_f):
            drifting_final.append((float(lo), float(la)))

    landfall = _landfall_kde_features(deposited)
    return BeachingResult(
        deposited_lonlat=deposited,
        final_drifting_lonlat=drifting_final,
        landfall_features=landfall,
    )


def _landfall_kde_features(deposited: list[tuple[float, float, float]]) -> list[dict]:
    if len(deposited) < 2:
        return []
    try:
        from scipy.stats import gaussian_kde
    except Exception as e:
        logger.info("landfall KDE skipped: scipy unavailable: %s", e)
        return []

    pts = np.array([(d[0], d[1]) for d in deposited]).T
    if pts.shape[1] < 2:
        return []
    try:
        kde = gaussian_kde(pts)
    except Exception as e:
        logger.info("landfall KDE failed: %s", e)
        return []

    lon_min, lon_max = pts[0].min() - 0.1, pts[0].max() + 0.1
    lat_min, lat_max = pts[1].min() - 0.1, pts[1].max() + 0.1
    grid_lon, grid_lat = np.mgrid[lon_min:lon_max:60j, lat_min:lat_max:60j]
    coords = np.vstack([grid_lon.ravel(), grid_lat.ravel()])
    z = kde(coords).reshape(grid_lon.shape)
    z_max = float(z.max()) if z.size else 0.0
    if z_max <= 0:
        return []

    levels = [0.5, 0.75, 0.9]
    features = []
    try:
        from skimage import measure
    except Exception:
        return _bounding_box_landfall(pts, z_max)
    for lvl in levels:
        contours = measure.find_contours(z, lvl * z_max)
        for c in contours:
            ring = []
            for r, col in c:
                lon = lon_min + (lon_max - lon_min) * (r / (grid_lon.shape[0] - 1))
                lat = lat_min + (lat_max - lat_min) * (col / (grid_lon.shape[1] - 1))
                ring.append((float(lon), float(lat)))
            if len(ring) < 3:
                continue
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            try:
                poly = Polygon(ring)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                features.append({
                    "type": "Feature",
                    "geometry": mapping(poly),
                    "properties": {
                        "intensity": lvl,
                        "scope": "landfall",
                        "particle_count": len(deposited),
                    },
                })
            except Exception:
                continue
    return features


def _bounding_box_landfall(pts: np.ndarray, z_max: float) -> list[dict]:
    lon_min, lon_max = float(pts[0].min()), float(pts[0].max())
    lat_min, lat_max = float(pts[1].min()), float(pts[1].max())
    poly = Polygon([
        (lon_min, lat_min), (lon_max, lat_min),
        (lon_max, lat_max), (lon_min, lat_max),
        (lon_min, lat_min),
    ])
    return [{
        "type": "Feature",
        "geometry": mapping(poly),
        "properties": {"intensity": 0.5, "scope": "landfall_bbox"},
    }]


def landfall_feature_collection(deposited: list[tuple[float, float, float]]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": _landfall_kde_features(deposited),
    }
