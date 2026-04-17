"""Euler Lagrangian tracker (PHYS-03, D-14 UTM-meter integration).

Per-detection: seed N particles at polygon centroid with +/-50 m Gaussian
jitter in UTM meters (D-08). Integrate hourly (dt=3600s) in UTM meters
over horizon hours (default 72). Apply windage v_total = v_current +
alpha * v_wind (D-18, alpha=0.02). Beach-on-NaN: freeze particles that
hit NaN currents, exclude from KDE (D-15).

Density polygons (D-06): at hours {24, 48, 72}, emit per-detection 90%
KDE plus global 75% KDE. All other frames carry empty FeatureCollection.
"""
from __future__ import annotations

import numpy as np
import utm as utm_lib
from geojson_pydantic import Feature, FeatureCollection
from pyproj import Transformer
from shapely.geometry import mapping, shape

from backend.core.config import Settings
from backend.core.schemas import (
    DetectionFeatureCollection,
    ForecastEnvelope,
    ForecastFrame,
)
from backend.physics.env_data import EnvStack, load_env_stack
from backend.physics.kde import kde_contour_polygons


DENSITY_HOURS = (24, 48, 72)
PER_DET_LEVEL = 0.90
GLOBAL_LEVEL = 0.75
JITTER_M = 50.0


def _utm_zone_from_lonlat(lon: float, lat: float) -> int:
    """Return EPSG code for the UTM zone containing (lon, lat). Northern hemisphere only."""
    _, _, zone, _ = utm_lib.from_latlon(lat, lon)
    return 32600 + zone  # 32643 for zone 43N (Mumbai / Arabian Sea)


def _make_transformers(utm_epsg: int) -> tuple[Transformer, Transformer]:
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    to_wgs = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
    return to_utm, to_wgs


def _seed_particles_utm(
    centroid_utm: tuple[float, float],
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Return (n, 2) UTM-meter array with Gaussian +/-50 m jitter (D-08)."""
    cx, cy = centroid_utm
    return np.column_stack([
        rng.normal(cx, JITTER_M, size=n),
        rng.normal(cy, JITTER_M, size=n),
    ])


def _step_particle(
    p_utm: np.ndarray,
    alive: np.ndarray,
    t_hours: float,
    env: EnvStack,
    alpha: float,
    to_wgs: Transformer,
    dt_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Euler step in UTM meters. Particles hitting NaN currents freeze (beach-on-NaN, D-15)."""
    new_p = p_utm.copy()
    new_alive = alive.copy()
    if not alive.any():
        return new_p, new_alive
    lons, lats = to_wgs.transform(p_utm[:, 0].tolist(), p_utm[:, 1].tolist())
    for i in range(p_utm.shape[0]):
        if not alive[i]:
            continue
        uo, vo = env.interp_currents(float(lons[i]), float(lats[i]), t_hours)
        u10, v10 = env.interp_winds(float(lons[i]), float(lats[i]), t_hours)
        if not (np.isfinite(uo) and np.isfinite(vo)):
            new_alive[i] = False
            continue
        if not np.isfinite(u10):
            u10 = 0.0
        if not np.isfinite(v10):
            v10 = 0.0
        vx = float(uo) + alpha * float(u10)
        vy = float(vo) + alpha * float(v10)
        new_p[i, 0] += vx * dt_s
        new_p[i, 1] += vy * dt_s
    return new_p, new_alive


def _empty_fc() -> dict:
    # Return a dict literal so pydantic coerces to whatever generic
    # FeatureCollection subtype the consumer field declares (e.g.
    # `FeatureCollection[Feature[Polygon, dict]]` in ForecastFrame).
    return {"type": "FeatureCollection", "features": []}


def _build_frame(
    hour: int,
    per_det_state: list[tuple[np.ndarray, np.ndarray, int]],
    to_wgs_list: list[Transformer],
) -> ForecastFrame:
    wgs_positions: list[tuple[float, float]] = []
    for (pts, _alive, _zone), to_wgs in zip(per_det_state, to_wgs_list):
        lons, lats = to_wgs.transform(pts[:, 0].tolist(), pts[:, 1].tolist())
        for lon, lat in zip(lons, lats):
            wgs_positions.append((float(lon), float(lat)))

    if hour not in DENSITY_HOURS:
        return ForecastFrame(
            hour=hour,
            particle_positions=wgs_positions,
            density_polygons=_empty_fc(),
        )

    features = []
    all_alive_utm: list[np.ndarray] = []
    global_zone: int | None = None
    for (pts, alive, zone) in per_det_state:
        alive_pts = pts[alive]
        if alive_pts.shape[0] >= 3:
            polys = kde_contour_polygons(alive_pts, utm_epsg=zone, level=PER_DET_LEVEL)
            for p in polys:
                features.append(Feature(
                    type="Feature",
                    geometry=mapping(p),
                    properties={"density": 1.0, "scope": "per_detection", "level": PER_DET_LEVEL},
                ))
        if alive_pts.shape[0] > 0:
            all_alive_utm.append(alive_pts)
            if global_zone is None:
                global_zone = zone

    if all_alive_utm and global_zone is not None:
        pooled = np.vstack(all_alive_utm)
        global_polys = kde_contour_polygons(pooled, utm_epsg=global_zone, level=GLOBAL_LEVEL)
        for p in global_polys:
            features.append(Feature(
                type="Feature",
                geometry=mapping(p),
                properties={"density": 1.0, "scope": "global", "level": GLOBAL_LEVEL},
            ))

    return ForecastFrame(
        hour=hour,
        particle_positions=wgs_positions,
        density_polygons={"type": "FeatureCollection", "features": [
            f.model_dump() if hasattr(f, "model_dump") else f for f in features
        ]},
    )


def forecast_drift(
    detections: DetectionFeatureCollection,
    cfg: Settings,
    env: EnvStack | None = None,
) -> ForecastEnvelope:
    """Euler Lagrangian tracker over horizon hours. See module docstring."""
    if env is None:
        env = load_env_stack(
            cfg.physics.cmems_path,
            cfg.physics.era5_path,
            cfg.physics.horizon_hours,
        )
    rng = np.random.default_rng(42)
    n_particles = cfg.physics.particles_per_detection
    horizon = cfg.physics.horizon_hours
    dt_s = float(cfg.physics.dt_seconds)
    alpha = cfg.physics.windage_alpha

    per_det_state: list[tuple[np.ndarray, np.ndarray, int]] = []
    per_det_transformers: list[tuple[Transformer, Transformer]] = []
    for det in detections.features:
        poly = shape(det.geometry.model_dump())
        c = poly.centroid
        utm_epsg = _utm_zone_from_lonlat(c.x, c.y)
        to_utm, to_wgs = _make_transformers(utm_epsg)
        cx, cy = to_utm.transform(c.x, c.y)
        pts_utm = _seed_particles_utm((cx, cy), n_particles, rng)
        alive = np.ones(n_particles, dtype=bool)
        per_det_state.append((pts_utm, alive, utm_epsg))
        per_det_transformers.append((to_utm, to_wgs))

    to_wgs_list = [t[1] for t in per_det_transformers]

    frames: list[ForecastFrame] = [_build_frame(0, per_det_state, to_wgs_list)]

    for hour in range(1, horizon + 1):
        for i in range(len(per_det_state)):
            pts_utm, alive, utm_epsg = per_det_state[i]
            _, to_wgs = per_det_transformers[i]
            new_pts, new_alive = _step_particle(
                pts_utm, alive, float(hour - 1), env, alpha, to_wgs, dt_s,
            )
            per_det_state[i] = (new_pts, new_alive, utm_epsg)
        frames.append(_build_frame(hour, per_det_state, to_wgs_list))

    return ForecastEnvelope(
        source_detections=detections,
        frames=frames,
        windage_alpha=alpha,
    )
