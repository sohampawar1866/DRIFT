"""Dynamic environment ingestion + summary service with disk caching.

Capabilities:
- Fetch currents + SST + chlorophyll from Copernicus Marine subsets.
- Fetch 10m winds from ERA5 CDS subsets.
- Cache NetCDF assets on disk by AOI+bbox+window to avoid repeat downloads.
- Provide robust environmental summaries for API consumers.
- Optional synthetic fallback is allowed only when ensure_live=False.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import xarray as xr
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
# Load repo-root .env explicitly so behavior is stable across cwd values.
load_dotenv(REPO_ROOT / ".env")

CACHE_ROOT = REPO_ROOT / "backend" / "data" / "cache"
ENV_DATA_DIRS = [
    REPO_ROOT / "data" / "env",
    REPO_ROOT / "backend" / "data" / "env",
]
ENV_CACHE_TTL_HOURS = int(os.environ.get("DRIFT_ENV_CACHE_TTL_HOURS", "6"))
LIVE_ENV_ENABLED_BY_DEFAULT = os.environ.get("DRIFT_ENABLE_LIVE_ENV", "1")

CMEMS_PHY_DATASET_ID = os.environ.get(
    "DRIFT_CMEMS_PHY_DATASET_ID",
    "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
)
CMEMS_BGC_DATASET_ID = os.environ.get(
    "DRIFT_CMEMS_BGC_DATASET_ID",
    "cmems_mod_glo_bgc_anfc_0.25deg_P1D-m",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _live_env_enabled() -> bool:
    return _truthy(LIVE_ENV_ENABLED_BY_DEFAULT)


def _cmems_credentials_available() -> bool:
    return bool(
        os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME")
        and os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD")
    )


def _cds_credentials_available() -> bool:
    return bool(
        os.environ.get("CDSAPI_KEY")
        or Path.home().joinpath(".cdsapirc").exists()
    )


def _bbox_key(bbox: list[float]) -> str:
    rounded = ",".join(f"{v:.4f}" for v in bbox)
    return hashlib.sha1(rounded.encode("utf-8")).hexdigest()[:12]


def _window_anchor() -> datetime:
    now = _utc_now().replace(minute=0, second=0, microsecond=0)
    bucket_hour = (now.hour // 6) * 6
    return now.replace(hour=bucket_hour)


def _asset_cache_dir(aoi_id: str, bbox: list[float], horizon_hours: int) -> Path:
    anchor = _window_anchor().strftime("%Y%m%dT%H")
    key = _bbox_key(bbox)
    return CACHE_ROOT / aoi_id / "env" / f"{anchor}_h{int(horizon_hours)}_{key}"


def _asset_paths(cache_dir: Path) -> dict[str, Path]:
    return {
        "currents": cache_dir / "cmems_currents.nc",
        "winds": cache_dir / "era5_winds.nc",
        "sst": cache_dir / "cmems_sst.nc",
        "chlorophyll": cache_dir / "cmems_chlorophyll.nc",
        "meta": cache_dir / "meta.json",
    }


def _meta_is_fresh(meta: dict[str, Any]) -> bool:
    try:
        ts = datetime.fromisoformat(str(meta.get("fetched_at", "")).replace("Z", "+00:00"))
        return _utc_now() - ts <= timedelta(hours=ENV_CACHE_TTL_HOURS)
    except Exception:
        return False


def _read_meta(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_meta(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def _fetch_cmems_subset(
    *,
    dataset_id: str,
    variables: list[str],
    bbox: list[float],
    start: datetime,
    end: datetime,
    out_path: Path,
    use_surface_depth: bool,
) -> tuple[bool, str | None]:
    try:
        import copernicusmarine
    except Exception as exc:
        return False, f"copernicusmarine import failed: {exc}"

    kwargs: dict[str, Any] = {
        "dataset_id": dataset_id,
        "variables": variables,
        "minimum_longitude": float(bbox[0]),
        "maximum_longitude": float(bbox[2]),
        "minimum_latitude": float(bbox[1]),
        "maximum_latitude": float(bbox[3]),
        "start_datetime": start.isoformat(),
        "end_datetime": end.isoformat(),
    }
    if use_surface_depth:
        kwargs["minimum_depth"] = 0.0
        kwargs["maximum_depth"] = 1.0

    try:
        ds = copernicusmarine.open_dataset(**kwargs)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ds.to_netcdf(out_path)
        return out_path.exists(), None
    except Exception as exc:
        return False, f"cmems fetch failed ({dataset_id}, vars={variables}): {exc}"


def _fetch_era5_subset(
    *,
    bbox: list[float],
    start: datetime,
    end: datetime,
    out_path: Path,
) -> tuple[bool, str | None]:
    try:
        import cdsapi
    except Exception as exc:
        return False, f"cdsapi import failed: {exc}"

    try:
        c = cdsapi.Client()
        hours: list[datetime] = []
        cur = start
        while cur <= end:
            hours.append(cur)
            cur += timedelta(hours=1)
        years = sorted({h.strftime("%Y") for h in hours})
        months = sorted({h.strftime("%m") for h in hours})
        days = sorted({h.strftime("%d") for h in hours})
        time_list = sorted({h.strftime("%H:00") for h in hours})

        out_path.parent.mkdir(parents=True, exist_ok=True)
        c.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": "reanalysis",
                "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
                "year": years,
                "month": months,
                "day": days,
                "time": time_list,
                # area order: N, W, S, E
                "area": [float(bbox[3]), float(bbox[0]), float(bbox[1]), float(bbox[2])],
                "format": "netcdf",
            },
            str(out_path),
        )
        return out_path.exists(), None
    except Exception as exc:
        return False, f"era5 fetch failed: {exc}"


def fetch_or_load_env_assets(
    aoi_id: str,
    bbox: list[float],
    *,
    horizon_hours: int,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Fetch or load cached env assets for currents/winds/sst/chlorophyll."""
    if len(bbox) != 4:
        raise ValueError("bbox must contain exactly 4 values")

    cache_dir = _asset_cache_dir(aoi_id, bbox, horizon_hours)
    paths = _asset_paths(cache_dir)

    meta = _read_meta(paths["meta"])
    if not force_refresh and meta is not None and _meta_is_fresh(meta):
        return {
            "source": "asset_cache",
            "cache_dir": str(cache_dir),
            "paths": {
                "currents": str(paths["currents"]) if paths["currents"].exists() else None,
                "winds": str(paths["winds"]) if paths["winds"].exists() else None,
                "sst": str(paths["sst"]) if paths["sst"].exists() else None,
                "chlorophyll": str(paths["chlorophyll"]) if paths["chlorophyll"].exists() else None,
            },
            "meta": meta,
        }

    if not _live_env_enabled():
        return {
            "source": "live_disabled",
            "cache_dir": str(cache_dir),
            "paths": {
                "currents": str(paths["currents"]) if paths["currents"].exists() else None,
                "winds": str(paths["winds"]) if paths["winds"].exists() else None,
                "sst": str(paths["sst"]) if paths["sst"].exists() else None,
                "chlorophyll": str(paths["chlorophyll"]) if paths["chlorophyll"].exists() else None,
            },
            "meta": {"reason": "DRIFT_ENABLE_LIVE_ENV is not enabled"},
        }

    start = _window_anchor() - timedelta(hours=1)
    end = start + timedelta(hours=max(24, int(horizon_hours)) + 2)

    errors: list[str] = []
    results: dict[str, bool] = {"currents": False, "winds": False, "sst": False, "chlorophyll": False}

    if _cmems_credentials_available():
        ok, err = _fetch_cmems_subset(
            dataset_id=CMEMS_PHY_DATASET_ID,
            variables=["uo", "vo"],
            bbox=bbox,
            start=start,
            end=end,
            out_path=paths["currents"],
            use_surface_depth=True,
        )
        results["currents"] = ok
        if err:
            errors.append(err)

        ok, err = _fetch_cmems_subset(
            dataset_id=CMEMS_PHY_DATASET_ID,
            variables=["thetao"],
            bbox=bbox,
            start=start,
            end=end,
            out_path=paths["sst"],
            use_surface_depth=True,
        )
        results["sst"] = ok
        if err:
            errors.append(err)

        ok, err = _fetch_cmems_subset(
            dataset_id=CMEMS_BGC_DATASET_ID,
            variables=["chl"],
            bbox=bbox,
            start=start,
            end=end,
            out_path=paths["chlorophyll"],
            use_surface_depth=False,
        )
        results["chlorophyll"] = ok
        if err:
            errors.append(err)
    else:
        errors.append("Copernicus credentials unavailable")

    if _cds_credentials_available():
        ok, err = _fetch_era5_subset(
            bbox=bbox,
            start=start,
            end=end,
            out_path=paths["winds"],
        )
        results["winds"] = ok
        if err:
            errors.append(err)
    else:
        errors.append("CDS credentials unavailable")

    meta_payload = {
        "aoi_id": aoi_id,
        "bbox": [float(v) for v in bbox],
        "horizon_hours": int(horizon_hours),
        "fetched_at": _utc_now().isoformat().replace("+00:00", "Z"),
        "window_start": start.isoformat().replace("+00:00", "Z"),
        "window_end": end.isoformat().replace("+00:00", "Z"),
        "datasets": {
            "currents": {"path": str(paths["currents"]), "ok": results["currents"]},
            "winds": {"path": str(paths["winds"]), "ok": results["winds"]},
            "sst": {"path": str(paths["sst"]), "ok": results["sst"]},
            "chlorophyll": {"path": str(paths["chlorophyll"]), "ok": results["chlorophyll"]},
        },
        "errors": errors,
    }
    _write_meta(paths["meta"], meta_payload)

    any_ok = any(results.values())
    all_ok = all(results.values())
    if all_ok:
        live_source = "live_fetch"
    elif any_ok:
        live_source = "live_fetch_partial"
    else:
        live_source = "live_unavailable"

    return {
        "source": live_source,
        "cache_dir": str(cache_dir),
        "paths": {
            "currents": str(paths["currents"]) if paths["currents"].exists() else None,
            "winds": str(paths["winds"]) if paths["winds"].exists() else None,
            "sst": str(paths["sst"]) if paths["sst"].exists() else None,
            "chlorophyll": str(paths["chlorophyll"]) if paths["chlorophyll"].exists() else None,
        },
        "meta": meta_payload,
    }


def _summary_cache_path(aoi_id: str, bbox: list[float]) -> Path:
    return CACHE_ROOT / aoi_id / f"env_summary_{_bbox_key(bbox)}.json"


def _read_summary_cached(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        ts = datetime.fromisoformat(payload.get("generated_at", "").replace("Z", "+00:00"))
        if _utc_now() - ts <= timedelta(hours=ENV_CACHE_TTL_HOURS):
            return payload
    except Exception:
        return None
    return None


def _write_summary_cached(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def _sample_dataset_value(ds: xr.Dataset, var_candidates: list[str], lon: float, lat: float) -> float | None:
    for name in var_candidates:
        if name not in ds:
            continue
        try:
            da = ds[name]
            coords = da.coords
            if "time" in coords:
                da = da.isel(time=0)
            if "latitude" in coords and "longitude" in coords:
                value = da.interp(latitude=lat, longitude=lon, method="nearest").values
            elif "lat" in coords and "lon" in coords:
                value = da.interp(lat=lat, lon=lon, method="nearest").values
            else:
                continue
            scalar = float(value)
            if math.isfinite(scalar):
                return scalar
        except Exception:
            continue
    return None


def _try_local_environment_sample(
    lon: float,
    lat: float,
    *,
    preferred_sst: str | None = None,
    preferred_chl: str | None = None,
) -> tuple[float | None, float | None, str | None]:
    sst_files: list[Path] = []
    chl_files: list[Path] = []
    if preferred_sst:
        sst_files.append(Path(preferred_sst))
    if preferred_chl:
        chl_files.append(Path(preferred_chl))

    for env_dir in ENV_DATA_DIRS:
        if env_dir.exists():
            sst_files.extend(sorted(env_dir.glob("*sst*.nc")) + sorted(env_dir.glob("*temp*.nc")))
            chl_files.extend(sorted(env_dir.glob("*chl*.nc")) + sorted(env_dir.glob("*chlorophyll*.nc")))

    sst_seen: set[Path] = set()
    chl_seen: set[Path] = set()
    sst_files = [p for p in sst_files if (p not in sst_seen and not sst_seen.add(p))]
    chl_files = [p for p in chl_files if (p not in chl_seen and not chl_seen.add(p))]

    water_temp = None
    for file_path in sst_files:
        try:
            with xr.open_dataset(file_path, decode_times=True) as ds:
                water_temp = _sample_dataset_value(
                    ds,
                    ["thetao", "sst", "analysed_sst", "sea_surface_temperature", "temperature"],
                    lon,
                    lat,
                )
            if water_temp is not None:
                break
        except Exception:
            continue

    chlorophyll = None
    for file_path in chl_files:
        try:
            with xr.open_dataset(file_path, decode_times=True) as ds:
                chlorophyll = _sample_dataset_value(
                    ds,
                    ["chl", "chlorophyll", "chla", "CHL"],
                    lon,
                    lat,
                )
            if chlorophyll is not None:
                break
        except Exception:
            continue

    if water_temp is not None or chlorophyll is not None:
        return water_temp, chlorophyll, "local_netcdf"
    return None, None, None


def _synthetic_environment(lon: float, lat: float) -> tuple[float, float, str]:
    # Deterministic fallback keeps output stable for the same AOI center.
    temp = 26.0 + 2.5 * math.sin(math.radians(lat))
    chl = 0.22 + 0.12 * (0.5 + 0.5 * math.cos(math.radians(lon)))
    return round(temp, 3), round(chl, 4), "synthetic_fallback"


def _decay_k_from_env(temp_c: float, chlorophyll_mg_m3: float) -> float:
    # Higher productivity and warmer water accelerate confidence decay.
    t_norm = min(max((temp_c - 15.0) / 20.0, 0.0), 1.0)
    c_norm = min(max(chlorophyll_mg_m3 / 1.5, 0.0), 1.0)
    k = 0.030 * (1.0 + 0.45 * c_norm + 0.30 * t_norm)
    return round(k, 6)


def get_environment_summary(
    aoi_id: str,
    bbox: list[float],
    *,
    horizon_hours: int = 72,
    ensure_live: bool = False,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return water-temp/chlorophyll summary for an AOI bbox.

    Uses disk cache first, then local/live NetCDF sampling.
    Synthetic fallback is only allowed when ensure_live=False.
    """
    if len(bbox) != 4:
        raise ValueError("bbox must contain exactly 4 values")

    cache = _summary_cache_path(aoi_id, bbox)
    if not force_refresh:
        cached = _read_summary_cached(cache)
        if cached is not None:
            if ensure_live and cached.get("source") == "synthetic_fallback":
                # Do not serve synthetic cache when caller explicitly requires real env.
                pass
            else:
                return cached

    lon = (bbox[0] + bbox[2]) / 2.0
    lat = (bbox[1] + bbox[3]) / 2.0

    live_assets: dict[str, Any] | None = None
    preferred_sst: str | None = None
    preferred_chl: str | None = None
    if ensure_live:
        live_assets = fetch_or_load_env_assets(
            aoi_id,
            bbox,
            horizon_hours=horizon_hours,
            force_refresh=force_refresh,
        )
        paths = live_assets.get("paths", {}) if isinstance(live_assets, dict) else {}
        preferred_sst = paths.get("sst") if isinstance(paths, dict) else None
        preferred_chl = paths.get("chlorophyll") if isinstance(paths, dict) else None

    temp, chl, source = _try_local_environment_sample(
        lon,
        lat,
        preferred_sst=preferred_sst,
        preferred_chl=preferred_chl,
    )
    if temp is None or chl is None:
        if ensure_live:
            live_detail = "no live asset metadata"
            if isinstance(live_assets, dict):
                live_src = live_assets.get("source")
                meta = live_assets.get("meta") if isinstance(live_assets.get("meta"), dict) else {}
                errors = meta.get("errors") if isinstance(meta, dict) else None
                if isinstance(errors, list) and errors:
                    live_detail = "; ".join(str(e) for e in errors)
                else:
                    live_detail = f"live_source={live_src}"
            raise RuntimeError(
                "Environment summary unavailable in ensure_live mode. "
                "Provide valid CMEMS/ERA5 credentials or local env NetCDF files. "
                f"Details: {live_detail}"
            )
        syn_temp, syn_chl, syn_source = _synthetic_environment(lon, lat)
        temp = syn_temp if temp is None else temp
        chl = syn_chl if chl is None else chl
        source = source or syn_source

    live_source = None
    if isinstance(live_assets, dict):
        live_source = live_assets.get("source")

    payload = {
        "aoi_id": aoi_id,
        "bbox": [float(v) for v in bbox],
        "horizon_hours": int(horizon_hours),
        "water_temp_c": round(float(temp), 3),
        "chlorophyll_mg_m3": round(float(chl), 4),
        "confidence_decay_k": _decay_k_from_env(float(temp), float(chl)),
        "generated_at": _utc_now().isoformat().replace("+00:00", "Z"),
        "source": source,
        "live_source": live_source,
    }
    _write_summary_cached(cache, payload)
    return payload
