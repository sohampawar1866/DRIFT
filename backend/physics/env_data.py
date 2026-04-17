"""Environment data loader for the Phase 2 Lagrangian tracker.

Provides a single `EnvStack` that exposes `(u, v) = interp_currents(lon, lat, t)`
and `(u10, v10) = interp_winds(lon, lat, t)` backed by either a real NetCDF
pair (CMEMS currents + ERA5 winds) or inline synthetic `xr.Dataset` fixtures
built in tests via `from_synthetic(...)`.

All CMEMS/ERA5 pitfalls are handled at load time so downstream code can trust
the interpolators:

- **PITFALL M3** (time coverage): `_assert_time_coverage` asserts each
  dataset's time axis spans at least `horizon_hours` hours; shorter coverage
  raises `ValueError("... time coverage ...")`.
- **PITFALL M4** (lon convention): `_normalize_longitude` detects
  `[0, 360]` convention via `longitude.max() > 180` and remaps via
  `((lon + 180) % 360) - 180`, then sorts ascending.
- **PITFALL M5** (wind/current vector components): `_assert_standard_names`
  verifies `uo.attrs["standard_name"] == "eastward_sea_water_velocity"` and
  that `u10` is an eastward wind component (via `standard_name="eastward_wind"`
  or long_name containing "eastward").

NaN passthrough is intentional: `interp_currents` may return `(nan, nan)` at
coastal cells. The tracker (Plan 03) owns beach-on-NaN (PITFALL M2).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xarray as xr


@dataclass(frozen=True)
class EnvStack:
    """Container for CMEMS currents + ERA5 winds with bilinear interpolation.

    `currents` must expose `uo` (eastward m/s) and `vo` (northward m/s) on
    (time, latitude, longitude). `winds` must expose `u10` (eastward m/s) and
    `v10` (northward m/s) on (time, latitude, longitude). Both datasets must
    have `time` as a datetime64 coordinate sorted ascending; longitudes must
    already be in the `[-180, 180]` convention (enforced at load).

    `t0_hours` is the origin hour (0.0) anchored to `currents.time[0]`; all
    `t_hours` arguments to interpolators are offsets from this origin.
    """

    currents: xr.Dataset
    winds: xr.Dataset
    t0_hours: float = 0.0

    # ---- interpolators ----

    def _t_offset(self, ds: xr.Dataset, t_hours: float) -> np.datetime64:
        t0 = ds["time"].values[0]
        return t0 + np.timedelta64(int(round(t_hours * 3600)), "s")

    def interp_currents(self, lon: float, lat: float, t_hours: float) -> tuple[float, float]:
        """Bilinear interpolation of (uo, vo) at (lon, lat, t_hours).

        May return `(nan, nan)` at coastal cells — caller owns beach-on-NaN.
        """
        t = self._t_offset(self.currents, t_hours)
        pt = self.currents[["uo", "vo"]].interp(
            longitude=lon, latitude=lat, time=t, method="linear"
        )
        return float(pt["uo"].values), float(pt["vo"].values)

    def interp_sst(self, lon: float, lat: float, t_hours: float) -> float:
        """Bilinear interpolation of thetao (SST) at (lon, lat, t_hours)."""
        if "thetao" not in self.currents:
            return 25.0  # fallback
        t = self._t_offset(self.currents, t_hours)
        pt = self.currents["thetao"].interp(
            longitude=lon, latitude=lat, time=t, method="linear"
        )
        return float(pt.values)

    def interp_winds(self, lon: float, lat: float, t_hours: float) -> tuple[float, float]:
        """Bilinear interpolation of (u10, v10) at (lon, lat, t_hours)."""
        t = self._t_offset(self.winds, t_hours)
        pt = self.winds[["u10", "v10"]].interp(
            longitude=lon, latitude=lat, time=t, method="linear"
        )
        return float(pt["u10"].values), float(pt["v10"].values)

    # ---- diagnostics ----

    @property
    def lon_min(self) -> float:
        return float(self.currents["longitude"].min())

    @property
    def lon_max(self) -> float:
        return float(self.currents["longitude"].max())


# ---- invariant helpers ----

def _normalize_longitude(ds: xr.Dataset) -> xr.Dataset:
    """Remap longitude from [0, 360] to [-180, 180] if needed and sort (PITFALL M4).

    Detects convention via `longitude.max() > 180`. No-op if already normalized.
    """
    lon = ds["longitude"]
    if float(lon.max()) > 180.0:
        ds = ds.assign_coords(
            longitude=(((ds["longitude"] + 180.0) % 360.0) - 180.0)
        ).sortby("longitude")
    return ds


def _assert_time_coverage(ds: xr.Dataset, horizon_hours: int, label: str) -> None:
    """Ensure the time axis spans >= horizon_hours (PITFALL M3)."""
    t = ds["time"].values
    if len(t) < 2:
        raise ValueError(f"{label} time coverage 0h < horizon {horizon_hours}h")
    span_hours = float((t[-1] - t[0]) / np.timedelta64(1, "h"))
    if span_hours < horizon_hours:
        raise ValueError(
            f"{label} time coverage {span_hours:.1f}h < horizon {horizon_hours}h"
        )


def _assert_standard_names(currents: xr.Dataset, winds: xr.Dataset) -> None:
    """Verify uo is eastward_sea_water_velocity and u10 is eastward wind (PITFALL M5)."""
    uo_std = currents["uo"].attrs.get("standard_name", "")
    if uo_std != "eastward_sea_water_velocity":
        raise ValueError(
            "currents uo standard_name must be eastward_sea_water_velocity "
            f"(PITFALL M5); got {uo_std!r}"
        )
    u10_std = winds["u10"].attrs.get("standard_name", "")
    u10_long = winds["u10"].attrs.get("long_name", "").lower()
    if u10_std != "eastward_wind" and "eastward" not in u10_long:
        raise ValueError(
            "winds u10 must be eastward wind component (PITFALL M5); "
            f"got standard_name={u10_std!r} long_name={u10_long!r}"
        )


# ---- constructors ----

def _finalize(currents: xr.Dataset, winds: xr.Dataset, horizon_hours: int) -> EnvStack:
    """Shared path for load_env_stack and from_synthetic: normalize + assert + wrap."""
    currents = _normalize_longitude(currents)
    winds = _normalize_longitude(winds)
    _assert_time_coverage(currents, horizon_hours, label="cmems")
    _assert_time_coverage(winds, horizon_hours, label="era5")
    _assert_standard_names(currents, winds)
    return EnvStack(currents=currents, winds=winds, t0_hours=0.0)


def load_env_stack(
    cmems_path: Path,
    era5_path: Path,
    horizon_hours: int = 72,
) -> EnvStack:
    """Open CMEMS + ERA5 NetCDFs, normalize + validate, return an EnvStack.

    Reads via `xr.open_dataset(..., decode_times=True)`. All PITFALL checks
    (M3 time coverage, M4 lon convention, M5 standard_names) run before return.
    """
    currents = xr.open_dataset(Path(cmems_path), decode_times=True)
    winds = xr.open_dataset(Path(era5_path), decode_times=True)
    return _finalize(currents, winds, horizon_hours)


def from_synthetic(
    currents: xr.Dataset,
    winds: xr.Dataset,
    horizon_hours: int = 72,
) -> EnvStack:
    """Test helper: skip file I/O, run all invariant checks.

    Identical to `load_env_stack` minus the `xr.open_dataset` calls, so tests
    exercise the exact same normalization and assertion path as production.
    """
    return _finalize(currents, winds, horizon_hours)
