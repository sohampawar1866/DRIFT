"""Dynamic environmental data ingestion (OceanTrace).

Bbox-aware fetcher for CMEMS currents + chlorophyll, ERA5 winds + SST.
Disk-caches NetCDF subsets keyed by hash(bbox + t0 + horizon) so repeated
forecasts for the same AOI don't re-hit the upstream APIs.

Auth: env vars `COPERNICUSMARINE_USERNAME`, `COPERNICUSMARINE_PASSWORD`,
`CDSAPI_URL`, `CDSAPI_KEY`. If unset, raises `EnvCredentialsMissing` —
service callers must catch and silently fall back to the prebaked static
NetCDFs already used by `env_data.load_env_stack`.

Returns an `EnvBundle` exposing the four xarray Datasets plus a
`.to_envstack()` adapter so the existing tracker code path needs no
edits — only `density_polygons`/landfall code that wants Chl/SST reaches
into the new fields.
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import xarray as xr

from backend.physics.env_data import EnvStack, _finalize

logger = logging.getLogger(__name__)

CMEMS_CURRENTS_DATASET = "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m"
CMEMS_BGC_DATASET = "cmems_mod_glo_bgc-pft_anfc_0.25deg_P1D-m"
ERA5_DATASET = "reanalysis-era5-single-levels"
ERA5_VARS = (
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "sea_surface_temperature",
)


class EnvCredentialsMissing(RuntimeError):
    """Raised when one of CMEMS/CDS credentials is unset.

    Caller (services layer) catches and silently falls back to prebaked
    static NetCDFs so the demo never crashes on missing keys.
    """


@dataclass
class EnvBundle:
    """Four xarray datasets bundled per-AOI per-time-window.

    `currents_ds` and `winds_ds` are compatible with the existing
    `EnvStack` shape via `.to_envstack()`. `sst_ds` and `chl_ds` are new
    — bio_fouling.py + dashboard endpoints reach into them via
    `.interp(longitude=..., latitude=..., time=...)`.
    """
    currents_ds: xr.Dataset
    winds_ds: xr.Dataset
    sst_ds: xr.Dataset
    chl_ds: xr.Dataset
    bbox: tuple[float, float, float, float]
    t0: str

    def to_envstack(self, horizon_hours: int = 72) -> EnvStack:
        return _finalize(self.currents_ds, self.winds_ds, horizon_hours)

    def _sample(self, ds, var: str, lon: float, lat: float, t_iso: str | None) -> float | None:
        import numpy as np
        try:
            da = ds[var]
            sel = {}
            for ax_name, val in (("longitude", lon), ("latitude", lat), ("lon", lon), ("lat", lat)):
                if ax_name in da.coords:
                    sel[ax_name] = val
            arr = da.interp(**sel, method="linear")
            if "time" in arr.dims:
                if t_iso is not None and "time" in arr.coords:
                    arr = arr.sel(time=t_iso, method="nearest")
                else:
                    arr = arr.mean(dim="time", skipna=True)
            if "depth" in arr.dims:
                arr = arr.isel(depth=0)
            v = float(arr.values)
            if not np.isfinite(v):
                return None
            return v
        except Exception:
            return None

    def sample_chl(self, lon: float, lat: float, t_iso: str | None = None) -> float:
        v = self._sample(self.chl_ds, "chl", lon, lat, t_iso)
        return v if v is not None else 0.3

    def sample_sst(self, lon: float, lat: float, t_iso: str | None = None) -> float:
        for var in ("sst", "analysed_sst", "sea_surface_temperature"):
            if var in self.sst_ds.data_vars:
                v = self._sample(self.sst_ds, var, lon, lat, t_iso)
                if v is None:
                    continue
                return v - 273.15 if v > 100 else v
        return 27.5


def _cache_key(bbox: tuple[float, float, float, float], t0: str, horizon_days: int) -> str:
    raw = f"{bbox[0]:.4f}_{bbox[1]:.4f}_{bbox[2]:.4f}_{bbox[3]:.4f}_{t0}_{horizon_days}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _check_creds() -> None:
    missing = []
    cmems_user = (
        os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME")
        or os.environ.get("COPERNICUSMARINE_USERNAME")
    )
    cmems_pass = (
        os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD")
        or os.environ.get("COPERNICUSMARINE_PASSWORD")
    )
    if not cmems_user:
        missing.append("COPERNICUSMARINE_SERVICE_USERNAME")
    if not cmems_pass:
        missing.append("COPERNICUSMARINE_SERVICE_PASSWORD")
    if not os.environ.get("CDSAPI_KEY") and not Path.home().joinpath(".cdsapirc").exists():
        missing.append("CDSAPI_KEY (or ~/.cdsapirc)")
    if missing:
        raise EnvCredentialsMissing(
            f"missing env vars: {', '.join(missing)} — silent fallback expected"
        )


def _fetch_cmems_currents(bbox, t0_iso, t1_iso, out_path: Path) -> xr.Dataset:
    import copernicusmarine
    copernicusmarine.subset(
        dataset_id=CMEMS_CURRENTS_DATASET,
        variables=["uo", "vo"],
        minimum_longitude=bbox[0], maximum_longitude=bbox[2],
        minimum_latitude=bbox[1], maximum_latitude=bbox[3],
        start_datetime=t0_iso, end_datetime=t1_iso,
        minimum_depth=0, maximum_depth=1,
        output_filename=str(out_path), force_download=True,
    )
    return xr.open_dataset(out_path, decode_times=True)


def _fetch_cmems_chl(bbox, t0_iso, t1_iso, out_path: Path) -> xr.Dataset:
    import copernicusmarine
    copernicusmarine.subset(
        dataset_id=CMEMS_BGC_DATASET,
        variables=["chl"],
        minimum_longitude=bbox[0], maximum_longitude=bbox[2],
        minimum_latitude=bbox[1], maximum_latitude=bbox[3],
        start_datetime=t0_iso, end_datetime=t1_iso,
        minimum_depth=0, maximum_depth=1,
        output_filename=str(out_path), force_download=True,
    )
    return xr.open_dataset(out_path, decode_times=True)


def _fetch_era5(bbox, t0: datetime, horizon_hours: int, out_path: Path) -> xr.Dataset:
    import cdsapi
    days = []
    cur = t0
    end = t0 + timedelta(hours=horizon_hours)
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    c = cdsapi.Client()
    c.retrieve(
        ERA5_DATASET,
        {
            "product_type": "reanalysis",
            "format": "netcdf",
            "variable": list(ERA5_VARS),
            "year": sorted({d.strftime("%Y") for d in days}),
            "month": sorted({d.strftime("%m") for d in days}),
            "day": sorted({d.strftime("%d") for d in days}),
            "time": [f"{h:02d}:00" for h in range(0, 24, 3)],
            "area": [bbox[3], bbox[0], bbox[1], bbox[2]],
        },
        str(out_path),
    )
    ds = xr.open_dataset(out_path, decode_times=True)
    rename = {}
    if "u10" not in ds and "10m_u_component_of_wind" in ds:
        rename["10m_u_component_of_wind"] = "u10"
    if "v10" not in ds and "10m_v_component_of_wind" in ds:
        rename["10m_v_component_of_wind"] = "v10"
    if "sst" not in ds and "sea_surface_temperature" in ds:
        rename["sea_surface_temperature"] = "sst"
    if rename:
        ds = ds.rename(rename)
    return ds


def _synthetic_era5(bbox, t0, horizon_hours: int) -> xr.Dataset:
    """Synthesize a small (u10, v10, sst) dataset on a 3x3 lat/lon grid
    when ERA5 isn't accessible. Constant 5 m/s eastward wind, 27.5°C SST."""
    import numpy as np
    n_lat = 3
    n_lon = 3
    # Cover horizon + 12h buffer so _assert_time_coverage passes.
    n_time = max(3, (horizon_hours // 6) + 3)
    lats = np.linspace(bbox[1], bbox[3], n_lat)
    lons = np.linspace(bbox[0], bbox[2], n_lon)
    times = [t0 + timedelta(hours=h * 6) for h in range(n_time)]
    times_np = np.array([np.datetime64(t.replace(microsecond=0).isoformat()) for t in times])
    u10 = xr.DataArray(
        np.full((n_time, n_lat, n_lon), 5.0, dtype="float32"),
        coords={"time": times_np, "latitude": lats, "longitude": lons},
        dims=("time", "latitude", "longitude"),
        attrs={"standard_name": "eastward_wind", "long_name": "10 m eastward wind"},
    )
    v10 = xr.DataArray(
        np.zeros((n_time, n_lat, n_lon), dtype="float32"),
        coords={"time": times_np, "latitude": lats, "longitude": lons},
        dims=("time", "latitude", "longitude"),
        attrs={"standard_name": "northward_wind"},
    )
    sst = xr.DataArray(
        np.full((n_time, n_lat, n_lon), 27.5, dtype="float32"),
        coords={"time": times_np, "latitude": lats, "longitude": lons},
        dims=("time", "latitude", "longitude"),
        attrs={"units": "celsius"},
    )
    return xr.Dataset({"u10": u10, "v10": v10, "sst": sst})


def fetch_env_for_bbox(
    bbox: tuple[float, float, float, float],
    t0: str,
    horizon_days: int = 7,
    cache_dir: str | Path = "data/env_cache",
) -> EnvBundle:
    """Fetch (or load from cache) currents+chl+winds+sst for bbox over [t0, t0+horizon_days].

    bbox = (min_lon, min_lat, max_lon, max_lat). t0 ISO date string.
    Raises EnvCredentialsMissing if API credentials absent — caller is
    expected to silently fall back to prebaked static NetCDFs.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(bbox, t0, horizon_days)

    currents_p = cache_dir / f"{key}_currents.nc"
    chl_p = cache_dir / f"{key}_chl.nc"
    era5_p = cache_dir / f"{key}_era5.nc"

    cache_hit = currents_p.exists() and chl_p.exists() and era5_p.exists()
    if not cache_hit:
        _check_creds()

    t0_dt = datetime.fromisoformat(t0)
    t1_dt = t0_dt + timedelta(days=horizon_days)
    t0_iso = t0_dt.strftime("%Y-%m-%dT%H:%M:%S")
    t1_iso = t1_dt.strftime("%Y-%m-%dT%H:%M:%S")

    if cache_hit:
        logger.info("env_service: cache hit %s for bbox=%s t0=%s", key, bbox, t0)
        currents = xr.open_dataset(currents_p, decode_times=True)
        chl = xr.open_dataset(chl_p, decode_times=True)
        try:
            era5 = xr.open_dataset(era5_p, decode_times=True)
        except Exception:
            era5 = _synthetic_era5(bbox, t0_dt, horizon_days * 24)
    else:
        logger.info("env_service: cache miss %s — fetching upstream", key)
        currents = _fetch_cmems_currents(bbox, t0_iso, t1_iso, currents_p)
        chl = _fetch_cmems_chl(bbox, t0_iso, t1_iso, chl_p)
        try:
            era5 = _fetch_era5(bbox, t0_dt, horizon_days * 24, era5_p)
        except Exception as e:
            logger.warning(
                "env_service: ERA5 fetch failed (%s) — synthesizing winds+SST. "
                "Accept license at https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download to enable real ERA5.",
                e,
            )
            era5 = _synthetic_era5(bbox, t0_dt, horizon_days * 24)

    winds = era5[["u10", "v10"]] if "u10" in era5 else era5
    sst = era5[["sst"]] if "sst" in era5 else era5
    return EnvBundle(
        currents_ds=currents,
        winds_ds=winds,
        sst_ds=sst,
        chl_ds=chl,
        bbox=bbox,
        t0=t0,
    )
