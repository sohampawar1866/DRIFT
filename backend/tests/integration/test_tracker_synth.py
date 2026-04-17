"""Integration tests for backend.physics.tracker.forecast_drift.

Gates Phase 2 exit: Test 1 (43.2 km / 24 h +/-1%) and Test 2 (zero-field 72 h
stays < 100 m). Both use synthetic EnvStack fixtures via from_synthetic.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from backend.core.config import Settings
from backend.core.schemas import (
    DetectionFeature,
    DetectionFeatureCollection,
    DetectionProperties,
    ForecastEnvelope,
)
from backend.physics.env_data import from_synthetic
from backend.physics.tracker import DENSITY_HOURS, forecast_drift


# ---------- helpers ----------

def _build_currents(lon, lat, n_hours=73, uo=0.0, vo=0.0, nan_east_of=None):
    t = pd.date_range("2026-04-17", periods=n_hours, freq="h").to_numpy(dtype="datetime64[ns]")
    shape = (n_hours, len(lat), len(lon))
    uo_arr = np.full(shape, uo, dtype=np.float32)
    vo_arr = np.full(shape, vo, dtype=np.float32)
    if nan_east_of is not None:
        for j, lv in enumerate(lon):
            if float(lv) > nan_east_of:
                uo_arr[:, :, j] = np.nan
                vo_arr[:, :, j] = np.nan
    ds = xr.Dataset(
        data_vars={
            "uo": (("time", "latitude", "longitude"), uo_arr),
            "vo": (("time", "latitude", "longitude"), vo_arr),
        },
        coords={"time": t, "latitude": lat, "longitude": lon},
    )
    ds["uo"].attrs["standard_name"] = "eastward_sea_water_velocity"
    ds["vo"].attrs["standard_name"] = "northward_sea_water_velocity"
    return ds


def _build_winds(lon, lat, n_hours=73, u10=0.0, v10=0.0):
    t = pd.date_range("2026-04-17", periods=n_hours, freq="h").to_numpy(dtype="datetime64[ns]")
    shape = (n_hours, len(lat), len(lon))
    u = np.full(shape, u10, dtype=np.float32)
    v = np.full(shape, v10, dtype=np.float32)
    ds = xr.Dataset(
        data_vars={
            "u10": (("time", "latitude", "longitude"), u),
            "v10": (("time", "latitude", "longitude"), v),
        },
        coords={"time": t, "latitude": lat, "longitude": lon},
    )
    ds["u10"].attrs["standard_name"] = "eastward_wind"
    ds["v10"].attrs["standard_name"] = "northward_wind"
    ds["u10"].attrs["long_name"] = "10 metre eastward wind component"
    return ds


def _tiny_detection(lon0: float, lat0: float) -> DetectionFeatureCollection:
    d = 0.003  # ~300 m square
    coords = [[
        [lon0 - d, lat0 - d],
        [lon0 + d, lat0 - d],
        [lon0 + d, lat0 + d],
        [lon0 - d, lat0 + d],
        [lon0 - d, lat0 - d],
    ]]
    feat = DetectionFeature(
        type="Feature",
        geometry={"type": "Polygon", "coordinates": coords},
        properties=DetectionProperties(
            conf_raw=0.9, conf_adj=0.9, fraction_plastic=0.3,
            area_m2=400.0, age_days_est=0,
        ),
    )
    return DetectionFeatureCollection(type="FeatureCollection", features=[feat])


def _cfg(particles: int = 50, horizon: int = 24) -> Settings:
    cfg = Settings()
    cfg = cfg.model_copy(update={
        "physics": cfg.physics.model_copy(update={
            "particles_per_detection": particles,
            "horizon_hours": horizon,
        })
    })
    return cfg


# ---------- tests ----------

def test_synthetic_43km():
    """Test 1 (GATE PHYS-04): 0.5 m/s east x 24 h -> 43.2 km mean displacement +/-1%."""
    lon = np.linspace(68.0, 78.0, 41)
    lat = np.linspace(15.0, 22.0, 29)
    currents = _build_currents(lon, lat, uo=0.5, vo=0.0)
    winds = _build_winds(lon, lat)
    env = from_synthetic(currents, winds, horizon_hours=24)

    dets = _tiny_detection(72.8, 18.9)
    cfg = _cfg(particles=50, horizon=24)
    env_out = forecast_drift(dets, cfg, env=env)

    assert len(env_out.frames) == 25  # hours 0..24

    # Compute mean eastward displacement in km via haversine along the line
    # of constant latitude. With 50 particles the jitter mean ~0.
    start_positions = env_out.frames[0].particle_positions
    end_positions = env_out.frames[-1].particle_positions
    assert len(start_positions) == 50
    assert len(end_positions) == 50

    # Haversine to compute km per particle
    R = 6371.0088
    displacements_km = []
    for (lon_s, lat_s), (lon_e, lat_e) in zip(start_positions, end_positions):
        phi1, phi2 = math.radians(lat_s), math.radians(lat_e)
        dphi = math.radians(lat_e - lat_s)
        dlam = math.radians(lon_e - lon_s)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        displacements_km.append(2 * R * math.asin(math.sqrt(a)))

    mean_km = float(np.mean(displacements_km))
    assert abs(mean_km - 43.2) / 43.2 < 0.01, (
        f"mean displacement {mean_km:.3f} km not within 1% of 43.2 km"
    )


def test_zero_field_stability():
    """Test 2 (GATE PHYS-04): zero-field 72 h -> particle stays within 100 m of start."""
    lon = np.linspace(68.0, 78.0, 41)
    lat = np.linspace(15.0, 22.0, 29)
    currents = _build_currents(lon, lat, uo=0.0, vo=0.0)
    winds = _build_winds(lon, lat, u10=0.0, v10=0.0)
    env = from_synthetic(currents, winds, horizon_hours=72)

    dets = _tiny_detection(72.8, 18.9)
    cfg = _cfg(particles=1, horizon=72)
    env_out = forecast_drift(dets, cfg, env=env)

    assert len(env_out.frames) == 73
    start = env_out.frames[0].particle_positions[0]
    end = env_out.frames[-1].particle_positions[0]

    # Same-location haversine -> should be ~ 0 (only jitter, which is set once).
    R = 6371.0088
    phi1, phi2 = math.radians(start[1]), math.radians(end[1])
    dphi = math.radians(end[1] - start[1])
    dlam = math.radians(end[0] - start[0])
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    dist_m = 2 * R * math.asin(math.sqrt(a)) * 1000.0
    assert dist_m < 100.0, f"zero-field drift {dist_m:.2f} m exceeds 100 m"


def test_beach_on_nan():
    """Test 3 (D-15): particle drifting east hits NaN cell -> freezes; final position finite."""
    lon = np.linspace(68.0, 78.0, 41)
    lat = np.linspace(15.0, 22.0, 29)
    currents = _build_currents(lon, lat, uo=1.0, vo=0.0, nan_east_of=73.0)
    winds = _build_winds(lon, lat)
    env = from_synthetic(currents, winds, horizon_hours=24)

    dets = _tiny_detection(72.8, 18.9)
    cfg = _cfg(particles=3, horizon=24)
    env_out = forecast_drift(dets, cfg, env=env)

    for frame in env_out.frames:
        for lon_p, lat_p in frame.particle_positions:
            assert math.isfinite(lon_p), f"NaN lon at hour {frame.hour}"
            assert math.isfinite(lat_p), f"NaN lat at hour {frame.hour}"


def test_schema_roundtrip_and_density_hours():
    """Test 4: 73-frame envelope; density only at {24, 48, 72}; JSON round-trip valid."""
    lon = np.linspace(68.0, 78.0, 41)
    lat = np.linspace(15.0, 22.0, 29)
    currents = _build_currents(lon, lat, uo=0.1, vo=0.05)
    winds = _build_winds(lon, lat)
    env = from_synthetic(currents, winds, horizon_hours=72)

    dets = _tiny_detection(72.8, 18.9)
    cfg = _cfg(particles=20, horizon=72)
    env_out = forecast_drift(dets, cfg, env=env)

    assert len(env_out.frames) == 73
    for frame in env_out.frames:
        if frame.hour in DENSITY_HOURS:
            assert len(frame.density_polygons.features) > 0, (
                f"hour {frame.hour} should have density polygons"
            )
        else:
            assert len(frame.density_polygons.features) == 0, (
                f"hour {frame.hour} must have empty density_polygons"
            )

    # Schema JSON round-trip
    as_json = env_out.model_dump_json()
    back = ForecastEnvelope.model_validate_json(as_json)
    assert len(back.frames) == 73


def test_windage_alpha():
    """Test 5 (D-18): zero currents + u10=10 m/s east, 24 h -> 17.28 km +/-1%."""
    lon = np.linspace(68.0, 78.0, 41)
    lat = np.linspace(15.0, 22.0, 29)
    currents = _build_currents(lon, lat, uo=0.0, vo=0.0)
    winds = _build_winds(lon, lat, u10=10.0, v10=0.0)
    env = from_synthetic(currents, winds, horizon_hours=24)

    dets = _tiny_detection(72.8, 18.9)
    cfg = _cfg(particles=50, horizon=24)
    env_out = forecast_drift(dets, cfg, env=env)

    start = env_out.frames[0].particle_positions
    end = env_out.frames[-1].particle_positions

    R = 6371.0088
    km = []
    for (s_lon, s_lat), (e_lon, e_lat) in zip(start, end):
        phi1, phi2 = math.radians(s_lat), math.radians(e_lat)
        dphi = math.radians(e_lat - s_lat)
        dlam = math.radians(e_lon - s_lon)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        km.append(2 * R * math.asin(math.sqrt(a)))

    mean_km = float(np.mean(km))
    expected = 0.02 * 10.0 * 86400.0 / 1000.0  # 17.28 km
    assert abs(mean_km - expected) / expected < 0.01, (
        f"windage displacement {mean_km:.3f} km not within 1% of {expected:.3f} km"
    )
