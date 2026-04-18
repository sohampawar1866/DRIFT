"""Euler Lagrangian tracker (UTM-meter integration).

Per-detection: seed N particles at polygon centroid with +/-50 m Gaussian
jitter in UTM meters. Integrate hourly in UTM meters with windage
and a small stochastic diffusion term to model sub-grid turbulence.

Coastline encounter uses beach-on-NaN: particles entering NaN-current
cells are frozen and marked as deposited/landfall. Forecast has a hard 90-day
cutoff (2160h). The dashboard can treat 15 days (360h) as the active
operational horizon while still exposing long-tail deposition risk.
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
DENSITY_INTERVAL_HOURS = 24
PER_DET_LEVEL = 0.90
GLOBAL_LEVEL = 0.75
DEPOSITION_LEVEL = 0.85
JITTER_M = 50.0
DIFFUSION_SIGMA_M = 120.0
MAX_TRACKING_HOURS = 2160


def _is_density_hour(hour: int) -> bool:
    if hour in DENSITY_HOURS:
        return True
    return hour > max(DENSITY_HOURS) and hour % DENSITY_INTERVAL_HOURS == 0


def _utm_zone_from_lonlat(lon: float, lat: float) -> int:
    """Return EPSG code for the UTM zone containing (lon, lat). Northern hemisphere only."""
    _, _, zone, _ = utm_lib.from_latlon(lat, lon)
    return 32600 + zone


def _make_transformers(utm_epsg: int) -> tuple[Transformer, Transformer]:
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
    to_wgs = Transformer.from_crs(f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True)
    return to_utm, to_wgs


def _seed_particles_utm(
    centroid_utm: tuple[float, float],
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Return (n, 2) UTM-meter array with Gaussian +/-50 m jitter."""
    cx, cy = centroid_utm
    return np.column_stack([
        rng.normal(cx, JITTER_M, size=n),
        rng.normal(cy, JITTER_M, size=n),
    ])


def _step_particle(
    p_utm: np.ndarray,
    alive: np.ndarray,
    beached: np.ndarray,
    t_hours: float,
    env: EnvStack,
    alpha: float,
    to_wgs: Transformer,
    dt_s: float,
    rng: np.random.Generator,
    diffusion_sigma_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Euler step in UTM meters. Particles hitting NaN currents freeze (beach-on-NaN)."""
    new_p = p_utm.copy()
    new_alive = alive.copy()
    new_beached = beached.copy()
    if not alive.any():
        return new_p, new_alive, new_beached
    lons, lats = to_wgs.transform(p_utm[:, 0].tolist(), p_utm[:, 1].tolist())
    for i in range(p_utm.shape[0]):
        if not alive[i]:
            continue
        uo, vo = env.interp_currents(float(lons[i]), float(lats[i]), t_hours)
        u10, v10 = env.interp_winds(float(lons[i]), float(lats[i]), t_hours)
        if not (np.isfinite(uo) and np.isfinite(vo)):
            new_alive[i] = False
            new_beached[i] = True
            continue
        if not np.isfinite(u10):
            u10 = 0.0
        if not np.isfinite(v10):
            v10 = 0.0
        vx = float(uo) + alpha * float(u10)
        vy = float(vo) + alpha * float(v10)
        if abs(vx) > 1e-8 or abs(vy) > 1e-8:
            dx = vx * dt_s + float(rng.normal(0.0, diffusion_sigma_m))
            dy = vy * dt_s + float(rng.normal(0.0, diffusion_sigma_m))
        else:
            dx = 0.0
            dy = 0.0
        new_p[i, 0] += dx
        new_p[i, 1] += dy
    return new_p, new_alive, new_beached


def _empty_fc() -> FeatureCollection:
    return FeatureCollection(type="FeatureCollection", features=[])


def _build_frame(
    hour: int,
    per_det_state: list[tuple[np.ndarray, np.ndarray, np.ndarray, int]],
    to_wgs_list: list[Transformer],
) -> ForecastFrame:
    wgs_positions: list[tuple[float, float]] = []
    for (pts, _alive, _beached, _zone), to_wgs in zip(per_det_state, to_wgs_list):
        lons, lats = to_wgs.transform(pts[:, 0].tolist(), pts[:, 1].tolist())
        for lon, lat in zip(lons, lats):
            wgs_positions.append((float(lon), float(lat)))

    if not _is_density_hour(hour):
        return ForecastFrame(
            hour=hour,
            particle_positions=wgs_positions,
            density_polygons=_empty_fc(),
        )

    features = []
    all_alive_utm: list[np.ndarray] = []
    all_beached_utm: list[np.ndarray] = []
    global_zone: int | None = None
    for (pts, alive, beached, zone) in per_det_state:
        alive_pts = pts[alive]
        if alive_pts.shape[0] >= 3:
            polys = kde_contour_polygons(alive_pts, utm_epsg=zone, level=PER_DET_LEVEL)
            for p in polys:
                features.append(Feature(
                    type="Feature",
                    geometry=mapping(p),
                    properties={
                        "density": 1.0,
                        "scope": "per_detection",
                        "level": PER_DET_LEVEL,
                        "type": "drift_density",
                        "layer": "drift_heatmap",
                    },
                ))
        if alive_pts.shape[0] > 0:
            all_alive_utm.append(alive_pts)
            if global_zone is None:
                global_zone = zone
        beached_pts = pts[beached]
        if beached_pts.shape[0] > 0:
            all_beached_utm.append(beached_pts)
            if global_zone is None:
                global_zone = zone

    if all_alive_utm and global_zone is not None:
        pooled = np.vstack(all_alive_utm)
        global_polys = kde_contour_polygons(pooled, utm_epsg=global_zone, level=GLOBAL_LEVEL)
        for p in global_polys:
            features.append(Feature(
                type="Feature",
                geometry=mapping(p),
                properties={
                    "density": 1.0,
                    "scope": "global",
                    "level": GLOBAL_LEVEL,
                    "type": "drift_density",
                    "layer": "drift_heatmap",
                },
            ))

    if all_beached_utm and global_zone is not None:
        beached = np.vstack(all_beached_utm)
        if beached.shape[0] >= 3:
            dep_polys = kde_contour_polygons(beached, utm_epsg=global_zone, level=DEPOSITION_LEVEL)
            for p in dep_polys:
                features.append(Feature(
                    type="Feature",
                    geometry=mapping(p),
                    properties={
                        "density": float(beached.shape[0]),
                        "scope": "landfall",
                        "level": DEPOSITION_LEVEL,
                        "type": "deposition_hotspot",
                        "layer": "deposition_heatmap",
                        "color": "red",
                    },
                ))

    return ForecastFrame(
        hour=hour,
        particle_positions=wgs_positions,
        density_polygons=FeatureCollection(type="FeatureCollection", features=features),
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
    horizon = min(int(cfg.physics.horizon_hours), MAX_TRACKING_HOURS)
    dt_s = float(cfg.physics.dt_seconds)
    alpha = cfg.physics.windage_alpha

    per_det_state: list[tuple[np.ndarray, np.ndarray, np.ndarray, int]] = []
    per_det_transformers: list[tuple[Transformer, Transformer]] = []
    for det in detections.features:
        poly = shape(det.geometry.model_dump())
        c = poly.centroid
        utm_epsg = _utm_zone_from_lonlat(c.x, c.y)
        to_utm, to_wgs = _make_transformers(utm_epsg)
        cx, cy = to_utm.transform(c.x, c.y)
        pts_utm = _seed_particles_utm((cx, cy), n_particles, rng)
        alive = np.ones(n_particles, dtype=bool)
        beached = np.zeros(n_particles, dtype=bool)
        per_det_state.append((pts_utm, alive, beached, utm_epsg))
        per_det_transformers.append((to_utm, to_wgs))

    to_wgs_list = [t[1] for t in per_det_transformers]

    frames: list[ForecastFrame] = [_build_frame(0, per_det_state, to_wgs_list)]

    for hour in range(1, horizon + 1):
        for i in range(len(per_det_state)):
            pts_utm, alive, beached, utm_epsg = per_det_state[i]
            _, to_wgs = per_det_transformers[i]
            new_pts, new_alive, new_beached = _step_particle(
                pts_utm,
                alive,
                beached,
                float(hour - 1),
                env,
                alpha,
                to_wgs,
                dt_s,
                rng,
                diffusion_sigma_m=DIFFUSION_SIGMA_M,
            )
            per_det_state[i] = (new_pts, new_alive, new_beached, utm_epsg)
        frames.append(_build_frame(hour, per_det_state, to_wgs_list))

        if all((not state[1].any()) for state in per_det_state):
            break

    simulated_until_hour = frames[-1].hour if frames else 0
    requested_horizon_hours = int(cfg.physics.horizon_hours)
    total_particles = int(sum(state[0].shape[0] for state in per_det_state))
    alive_particles = int(sum(int(state[1].sum()) for state in per_det_state))
    beached_particles = int(sum(int(state[2].sum()) for state in per_det_state))
    stop_track_at_90d_cap_applied = requested_horizon_hours > MAX_TRACKING_HOURS and simulated_until_hour >= MAX_TRACKING_HOURS
    never_beached_particles_remaining = int(alive_particles if beached_particles == 0 else 0)
    never_beached_until_stop = bool(beached_particles == 0 and alive_particles > 0)
    stopped_early_all_beached = bool(simulated_until_hour < horizon and alive_particles == 0)
    stop_reason = "all_particles_beached" if stopped_early_all_beached else "horizon_complete"

    return ForecastEnvelope(
        source_detections=detections,
        frames=frames,
        windage_alpha=alpha,
        tracker_metadata={
            "requested_horizon_hours": requested_horizon_hours,
            "effective_horizon_hours": int(horizon),
            "simulated_until_hour": int(simulated_until_hour),
            "total_particles": total_particles,
            "alive_particles": alive_particles,
            "beached_particles": beached_particles,
            "stop_track_at_90d_cap_applied": bool(stop_track_at_90d_cap_applied),
            "never_beached_particles_remaining": never_beached_particles_remaining,
            "never_beached_until_stop": bool(never_beached_until_stop),
            "stopped_early_all_beached": bool(stopped_early_all_beached),
            "stop_reason": stop_reason,
        },
    )
