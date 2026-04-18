import os
import json
import urllib.request
import shutil
import logging
from pathlib import Path
from pystac_client import Client
import datetime
from datetime import timedelta
from dotenv import load_dotenv
import rasterio

# Load backend .env explicitly so behavior is stable across cwd values.
REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / "backend" / ".env")
logger = logging.getLogger(__name__)


def _log_fallback(message: str) -> None:
    logger.warning("stac fallback: %s", message)
    print(f"[DRIFT_FALLBACK] stac_service: {message}")

# Grab the timeout from .env (defaults to 300 seconds if missing)
STAC_FETCH_TIMEOUT = int(os.getenv("STAC_FETCH_TIMEOUT", 300))

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")

S2_BAND_ORDER: tuple[str, ...] = (
    "b2",   # blue
    "b3",   # green
    "b4",   # red
    "b5",   # rededge1
    "b6",   # rededge2
    "b7",   # rededge3
    "b8",   # nir
    "b8a",  # nir08
    "b11",  # swir16
    "b12",  # swir22
    "scl",  # scene classification layer
)

STAC_ASSET_BY_BAND = {
    "b2": "blue",
    "b3": "green",
    "b4": "red",
    "b5": "rededge1",
    "b6": "rededge2",
    "b7": "rededge3",
    "b8": "nir",
    "b8a": "nir08",
    "b11": "swir16",
    "b12": "swir22",
    "scl": "scl",
}


def _required_band_paths(item_folder: str) -> dict:
    return {
        **{band: os.path.join(item_folder, f"{band}.tif") for band in S2_BAND_ORDER},
        "stack": os.path.join(item_folder, "stack_11band.tif"),
    }


# Bands that are absolutely required (model feature computation needs these)
_CORE_BANDS: tuple[str, ...] = ("b2", "b3", "b4", "b5", "b6", "b7", "b8", "b8a", "b11")


def _has_required_bands(paths: dict) -> bool:
    """Check that at least the core bands exist on disk."""
    return all(os.path.exists(paths.get(name, "")) for name in _CORE_BANDS)


def _ensure_optional_bands(paths: dict) -> None:
    """Create zero-fill placeholders for b12 and scl if missing.

    The model's feature_stack uses bands 0-8 (B2..B11) plus spectral indices.
    B12 (index 9) and SCL (index 10) are included in the stack for completeness
    but contribute minimally. When these bands weren't downloaded, we fill them
    with zeros so the stack builder doesn't fail.
    """
    ref_band = paths.get(_CORE_BANDS[0])
    if ref_band is None or not os.path.exists(ref_band):
        return

    for band in ("b12", "scl"):
        if os.path.exists(paths.get(band, "")):
            continue
        logger.info("stac: creating zero-fill placeholder for missing band %s", band)
        with rasterio.open(ref_band) as src:
            profile = src.profile.copy()
            profile.update(dtype="float32", nodata=0.0)
            with rasterio.open(paths[band], "w", **profile) as dst:
                import numpy as np
                dst.write(np.zeros((1, src.height, src.width), dtype="float32"))


def _build_stack_tif(paths: dict) -> None:
    stack_path = paths["stack"]
    first_path = paths[S2_BAND_ORDER[0]]

    with rasterio.open(first_path) as first:
        profile = first.profile.copy()
        width = first.width
        height = first.height
        crs = first.crs
        transform = first.transform

    profile.update(
        count=len(S2_BAND_ORDER),
        dtype="float32",
        compress="deflate",
        nodata=None,
    )

    Path(stack_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(stack_path, "w", **profile) as dst:
        for idx, band in enumerate(S2_BAND_ORDER, start=1):
            with rasterio.open(paths[band]) as src:
                if src.width != width or src.height != height:
                    raise RuntimeError(f"stac: band shape mismatch for {band}")
                if src.crs != crs or src.transform != transform:
                    raise RuntimeError(f"stac: band grid mismatch for {band}")
                dst.write(src.read(1).astype("float32"), idx)


def _ensure_stack(paths: dict) -> None:
    if not _has_required_bands(paths):
        raise RuntimeError("stac: required core band files are missing")
    _ensure_optional_bands(paths)
    if not os.path.exists(paths["stack"]):
        _build_stack_tif(paths)


def _newest_valid_cache_dir(aoi_folder: str) -> str | None:
    if not os.path.isdir(aoi_folder):
        return None
    valid: list[tuple[float, str]] = []
    for entry in os.listdir(aoi_folder):
        folder = os.path.join(aoi_folder, entry)
        if not os.path.isdir(folder):
            continue
        if _has_required_bands(_required_band_paths(folder)):
            valid.append((os.path.getmtime(folder), entry))
    if not valid:
        return None
    valid.sort(key=lambda t: t[0], reverse=True)
    return valid[0][1]


def _global_fallback_cache() -> tuple[str, str] | None:
    """Search ALL AOI cache folders for any usable tile (demo fallback).

    Returns (aoi_folder, item_id) or None.
    """
    if not os.path.isdir(CACHE_DIR):
        return None
    for aoi_name in os.listdir(CACHE_DIR):
        aoi_folder = os.path.join(CACHE_DIR, aoi_name)
        if not os.path.isdir(aoi_folder):
            continue
        item_id = _newest_valid_cache_dir(aoi_folder)
        if item_id is not None:
            return aoi_folder, item_id
    return None


def download_band(url: str, save_path: str):
    """Downloads a file if it doesn't already exist using atomic writes."""
    if not os.path.exists(save_path):
        tmp_path = save_path + ".tmp"
        logger.info("stac: downloading %s -> %s", url, tmp_path)
        try:
            with urllib.request.urlopen(url, timeout=STAC_FETCH_TIMEOUT) as response, open(tmp_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            os.replace(tmp_path, save_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise


def query_sentinel2_l2a_aws(bbox: list, max_cloud_cover: int = 15, days_back: int = 14) -> dict:
    """
    Queries the AWS Earth Search STAC API for Sentinel-2 L2A imagery.
    
    Args:
        bbox (list): [min_lon, min_lat, max_lon, max_lat]
        max_cloud_cover (int): Maximum allowed cloud cover percentage.
        days_back (int): The time window to look back for an image.
        
    Returns:
        dict: A dictionary containing metadata and pre-signed S3 hrefs for the needed bands.
    """
    api_url = "https://earth-search.aws.element84.com/v1"
    client = Client.open(api_url)
    
    end_date = datetime.datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)
    date_range = f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
    
    search = client.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": max_cloud_cover}}
    )
    
    items = [
        it for it in search.items()
        if it.datetime is not None
    ]

    if not items:
        return {"error": "No low-cloud Sentinel-2 imagery found for this period and bbox."}

    # Select the most recent item with required bands.
    items.sort(key=lambda it: it.datetime, reverse=True)
    best_item = None
    for item in items:
        if all(item.assets.get(STAC_ASSET_BY_BAND[b]) for b in S2_BAND_ORDER):
            best_item = item
            break
    if best_item is None:
        return {"error": "No Sentinel-2 item had full required assets for model inference."}
    
    return {
        "id": best_item.id,
        "datetime": best_item.datetime.isoformat(),
        "cloud_cover": best_item.properties.get("eo:cloud_cover"),
        "assets": {
            band: best_item.assets[asset_name].href
            for band, asset_name in STAC_ASSET_BY_BAND.items()
            if best_item.assets.get(asset_name)
        },
        "geometry": best_item.geometry
    }


def get_live_or_cached_imagery(aoi_id: str, bbox: list) -> dict:
    """
    Core Logic:
    1. Tries to find the newest image ID from AWS STAC.
    2. Downloads all required bands locally if not already cached.
    3. Builds an 11-band stack used directly by inference.
    4. If AWS fails, attempts local cache only.
    """
    aoi_folder = os.path.join(CACHE_DIR, aoi_id)
    os.makedirs(aoi_folder, exist_ok=True)
    
    stac_metadata = None
    try:
        # 1. Ask STAC for the newest image bounds
        stac_metadata = query_sentinel2_l2a_aws(bbox, max_cloud_cover=20, days_back=7)
    except Exception as e:
        logger.warning("stac: network error querying catalog for %s: %s", aoi_id, e)
    
    # 2. Offline Fallback Logic: Did we completely fail to talk to the internet?
    if stac_metadata is None or "error" in stac_metadata:
        newest_cached_id = _newest_valid_cache_dir(aoi_folder)
        if newest_cached_id:
            logger.info("stac: using local fallback cache for %s -> %s", aoi_id, newest_cached_id)
            _log_fallback(
                f"using local cached imagery for {aoi_id} (item_id={newest_cached_id})"
            )
            local_paths = _required_band_paths(os.path.join(aoi_folder, newest_cached_id))
            try:
                _ensure_stack(local_paths)
            except Exception as e:
                return {"error": f"Cached imagery exists but stack build failed: {e}"}
            return {
                "source": "local_fallback",
                "id": newest_cached_id,
                "local_paths": local_paths,
            }

        # Try ANY cached tile from a different AOI as demo fallback
        global_hit = _global_fallback_cache()
        if global_hit:
            fb_folder, fb_item_id = global_hit
            logger.info("stac: using global demo fallback for %s -> %s/%s", aoi_id, fb_folder, fb_item_id)
            _log_fallback(
                f"using global demo fallback imagery for {aoi_id} (source={fb_folder}, item_id={fb_item_id})"
            )
            local_paths = _required_band_paths(os.path.join(fb_folder, fb_item_id))
            try:
                _ensure_stack(local_paths)
            except Exception as e:
                return {"error": f"Global fallback stack build failed: {e}"}
            return {
                "source": "global_demo_fallback",
                "id": fb_item_id,
                "local_paths": local_paths,
            }

        return {"error": "No internet connection, and no local fallback imagery found!"}
    
    # 3. Online Success: We have a valid AWS image ID. Let's see if we already downloaded it today.
    item_id = stac_metadata["id"]
    item_folder = os.path.join(aoi_folder, item_id)
    local_paths = _required_band_paths(item_folder)
    
    # LOGICAL FIX: Check if the actual files exist, not just the folder!
    # If a previous download failed midway, the folder might exist but the .tif files are missing.
    if _has_required_bands(local_paths):
        try:
            _ensure_stack(local_paths)
        except Exception as e:
            return {"error": f"Cache stack build failed: {e}"}
        logger.info("stac: cache hit for %s -> %s", aoi_id, item_id)
        return {
            "source": "local_cache", 
            "id": item_id, 
            "local_paths": local_paths
        }
        
    # 4. First Time Seeing This Image: We must download it!
    logger.info("stac: downloading new tile for %s -> %s", aoi_id, item_id)
    os.makedirs(item_folder, exist_ok=True)
    
    try:
        for band in S2_BAND_ORDER:
            href = stac_metadata["assets"].get(band)
            if not href:
                raise RuntimeError(f"Missing STAC asset URL for band {band}")
            download_band(href, local_paths[band])
        _ensure_stack(local_paths)
        logger.info("stac: download success for %s at %s", aoi_id, item_folder)
    except Exception as d_err:
        logger.warning("stac: download failed for %s (%s)", aoi_id, d_err)
        return {"error": "Failed to download bands"}
        
    return {
        "source": "aws_download",
        "id": item_id,
        "local_paths": local_paths
    }
