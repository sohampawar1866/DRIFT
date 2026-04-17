"""Unit tests for backend.physics.env_data (EnvStack + loaders).

Covers:
- Test 1: synthetic constant-field interp_currents round-trip.
- Test 2: longitude normalization from [0, 360] to [-180, 180] (PITFALL M4).
- Test 3: NaN passthrough at coastal cells (caller owns beach-on-NaN).
- Test 4: time-axis coverage assertion < horizon_hours raises (PITFALL M3).
- Test 5: standard_name check on wind/current vectors (PITFALL M5).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from backend.physics.env_data import (
    EnvStack,
    _normalize_longitude,
    from_synthetic,
    load_env_stack,
)


# ---------- helpers ----------

def _build_currents(
    lon_vals: np.ndarray,
    lat_vals: np.ndarray,
    n_hours: int = 73,
    uo_const: float = 0.5,
    vo_const: float = 0.0,
    uo_standard: str = "eastward_sea_water_velocity",
    vo_standard: str = "northward_sea_water_velocity",
    nan_cell: tuple[int, int] | None = None,  # (lat_idx, lon_idx)
) -> xr.Dataset:
    t = pd.date_range("2026-04-17", periods=n_hours, freq="h")
    shape = (n_hours, len(lat_vals), len(lon_vals))
    uo = np.full(shape, uo_const, dtype=np.float32)
    vo = np.full(shape, vo_const, dtype=np.float32)
    if nan_cell is not None:
        la, lo = nan_cell
        uo[:, la, lo] = np.nan
        vo[:, la, lo] = np.nan
    ds = xr.Dataset(
        data_vars={
            "uo": (("time", "latitude", "longitude"), uo),
            "vo": (("time", "latitude", "longitude"), vo),
        },
        coords={"time": t, "latitude": lat_vals, "longitude": lon_vals},
    )
    ds["uo"].attrs["standard_name"] = uo_standard
    ds["vo"].attrs["standard_name"] = vo_standard
    return ds


def _build_winds(
    lon_vals: np.ndarray,
    lat_vals: np.ndarray,
    n_hours: int = 73,
    u10_const: float = 1.0,
    v10_const: float = 0.0,
    u10_standard: str = "eastward_wind",
    v10_standard: str = "northward_wind",
    u10_long: str = "10 metre eastward wind component",
) -> xr.Dataset:
    t = pd.date_range("2026-04-17", periods=n_hours, freq="h")
    shape = (n_hours, len(lat_vals), len(lon_vals))
    u10 = np.full(shape, u10_const, dtype=np.float32)
    v10 = np.full(shape, v10_const, dtype=np.float32)
    ds = xr.Dataset(
        data_vars={
            "u10": (("time", "latitude", "longitude"), u10),
            "v10": (("time", "latitude", "longitude"), v10),
        },
        coords={"time": t, "latitude": lat_vals, "longitude": lon_vals},
    )
    ds["u10"].attrs["standard_name"] = u10_standard
    ds["v10"].attrs["standard_name"] = v10_standard
    ds["u10"].attrs["long_name"] = u10_long
    return ds


# ---------- tests ----------

def test_synthetic_constant_field_interp_currents():
    """Test 1: constant-field uo=0.5, vo=0 → interp returns (0.5, 0.0)."""
    lon = np.linspace(60.0, 95.0, 36)
    lat = np.linspace(0.0, 25.0, 26)
    currents = _build_currents(lon, lat)
    winds = _build_winds(lon, lat)
    env = from_synthetic(currents, winds)
    u, v = env.interp_currents(lon=75.0, lat=10.0, t_hours=0.0)
    assert math.isclose(u, 0.5, abs_tol=1e-6), f"expected 0.5, got {u}"
    assert math.isclose(v, 0.0, abs_tol=1e-6), f"expected 0.0, got {v}"

    # Also verify interp_winds returns constants.
    uw, vw = env.interp_winds(lon=75.0, lat=10.0, t_hours=0.0)
    assert math.isclose(uw, 1.0, abs_tol=1e-6)
    assert math.isclose(vw, 0.0, abs_tol=1e-6)


def test_longitude_normalization_0_to_360():
    """Test 2: lon in [0, 360] is remapped to [-180, 180] and wraps correctly."""
    # Sentinel dataset with lon spanning 250..300 (i.e., Atlantic at -60..-110ish).
    # Include lon=285 which should map to -75.
    lon_360 = np.linspace(250.0, 310.0, 61)  # covers 285
    lat = np.linspace(0.0, 25.0, 26)
    currents = _build_currents(lon_360, lat, uo_const=0.3)
    winds = _build_winds(lon_360, lat)

    # After normalization via from_synthetic, lon should be in [-180, 180].
    env = from_synthetic(currents, winds)
    lon_after = env.currents["longitude"].values
    assert lon_after.min() >= -180.0
    assert lon_after.max() <= 180.0

    # Query at the normalized longitude (-75 === 285 in source).
    u, v = env.interp_currents(lon=-75.0, lat=10.0, t_hours=0.0)
    assert math.isclose(u, 0.3, abs_tol=1e-6), f"expected 0.3 at lon=-75, got {u}"
    assert math.isclose(v, 0.0, abs_tol=1e-6)


def test_nan_passthrough_at_coastal_cell():
    """Test 3: NaN at a grid cell propagates through interp (caller handles beach-on-NaN)."""
    lon = np.linspace(60.0, 95.0, 36)
    lat = np.linspace(0.0, 25.0, 26)
    # Pick an interior cell (lat_idx=10, lon_idx=15) and NaN it in all time frames.
    currents = _build_currents(lon, lat, nan_cell=(10, 15))
    winds = _build_winds(lon, lat)
    env = from_synthetic(currents, winds)

    # Query exactly at the NaN cell coordinates.
    lat_q = float(lat[10])
    lon_q = float(lon[15])
    u, v = env.interp_currents(lon=lon_q, lat=lat_q, t_hours=0.0)
    assert math.isnan(u), f"expected NaN at coastal cell, got u={u}"
    assert math.isnan(v), f"expected NaN at coastal cell, got v={v}"


def test_time_coverage_too_short_raises():
    """Test 4: source time-axis shorter than horizon_hours raises ValueError (PITFALL M3)."""
    lon = np.linspace(60.0, 95.0, 36)
    lat = np.linspace(0.0, 25.0, 26)
    # Only 25 hours of coverage — shorter than 72 h horizon.
    currents = _build_currents(lon, lat, n_hours=25)
    winds = _build_winds(lon, lat, n_hours=25)
    with pytest.raises(ValueError, match="time coverage"):
        from_synthetic(currents, winds, horizon_hours=72)


def test_standard_name_check_wind_eastward():
    """Test 5: wind u10 missing eastward standard/long_name raises ValueError (PITFALL M5)."""
    lon = np.linspace(60.0, 95.0, 36)
    lat = np.linspace(0.0, 25.0, 26)
    currents = _build_currents(lon, lat)
    # Intentionally wrong attrs on u10.
    winds = _build_winds(lon, lat, u10_standard="bogus", u10_long="unknown")
    with pytest.raises(ValueError, match="eastward"):
        from_synthetic(currents, winds)


def test_standard_name_check_currents_eastward():
    """Also exercise the CMEMS uo standard_name branch of PITFALL M5."""
    lon = np.linspace(60.0, 95.0, 36)
    lat = np.linspace(0.0, 25.0, 26)
    currents = _build_currents(lon, lat, uo_standard="not_a_valid_name")
    winds = _build_winds(lon, lat)
    with pytest.raises(ValueError, match="eastward_sea_water_velocity"):
        from_synthetic(currents, winds)
