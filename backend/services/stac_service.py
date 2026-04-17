import os
import json
import urllib.request
import shutil
import logging
from pystac_client import Client
import datetime
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
logger = logging.getLogger(__name__)

# Grab the timeout from .env (defaults to 30 seconds if missing)
STAC_FETCH_TIMEOUT = int(os.getenv("STAC_FETCH_TIMEOUT", 30))

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")


def _required_band_paths(item_folder: str) -> dict:
    return {
        "nir": os.path.join(item_folder, "nir.tif"),
        "red": os.path.join(item_folder, "red.tif"),
        "stack": os.path.join(item_folder, "stack.tif"),
    }


def _has_required_bands(paths: dict) -> bool:
    return all(os.path.exists(paths.get(name, "")) for name in ("nir", "red"))


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
        if item.assets.get("nir") and item.assets.get("red"):
            best_item = item
            break
    if best_item is None:
        return {"error": "No Sentinel-2 item had required 'nir' and 'red' assets."}
    
    return {
        "id": best_item.id,
        "datetime": best_item.datetime.isoformat(),
        "cloud_cover": best_item.properties.get("eo:cloud_cover"),
        "assets": {
            "red": best_item.assets.get("red").href if best_item.assets.get("red") else None,
            "green": best_item.assets.get("green").href if best_item.assets.get("green") else None,
            "blue": best_item.assets.get("blue").href if best_item.assets.get("blue") else None,
            "nir": best_item.assets.get("nir").href if best_item.assets.get("nir") else None,
            "red_edge_2": best_item.assets.get("rededge2").href if best_item.assets.get("rededge2") else None,
            "swir_1": best_item.assets.get("swir16").href if best_item.assets.get("swir16") else None,
        },
        "geometry": best_item.geometry
    }


def get_live_or_cached_imagery(aoi_id: str, bbox: list) -> dict:
    """
    Core Logic:
    1. Tries to find the newest image ID from AWS STAC.
    2. Downloads it locally if we don't have it yet.
    3. If AWS fails (no internet), loads the most recent local file from the cache as a fallback!
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
        if not newest_cached_id:
            return {"error": "No internet connection, and no local fallback imagery found!"}
        logger.info("stac: using local fallback cache for %s -> %s", aoi_id, newest_cached_id)
        
        return {
            "source": "local_fallback",
            "id": newest_cached_id,
            "local_paths": _required_band_paths(os.path.join(aoi_folder, newest_cached_id)),
        }
    
    # 3. Online Success: We have a valid AWS image ID. Let's see if we already downloaded it today.
    item_id = stac_metadata["id"]
    item_folder = os.path.join(aoi_folder, item_id)
    local_paths = _required_band_paths(item_folder)
    
    # LOGICAL FIX: Check if the actual files exist, not just the folder!
    # If a previous download failed midway, the folder might exist but the .tif files are missing.
    if _has_required_bands(local_paths):
        logger.info("stac: cache hit for %s -> %s", aoi_id, item_id)
        return {
            "source": "local_cache", 
            "id": item_id, 
            "local_paths": local_paths
        }
        
    # 4. First Time Seeing This Image: window-read needed bands clipped to bbox.
    logger.info("stac: building clipped stack for %s -> %s (bbox=%s)", aoi_id, item_id, bbox)
    os.makedirs(item_folder, exist_ok=True)

    try:
        stack_path = build_clipped_stack(stac_metadata["assets"], bbox, item_folder)
        local_paths["stack"] = stack_path
        # also point nir/red at the stack so legacy callers find a file
        local_paths["nir"] = stack_path
        local_paths["red"] = stack_path
        logger.info("stac: clipped stack ready at %s", stack_path)
    except Exception as d_err:
        logger.warning("stac: clipped stack failed for %s (%s) — trying full-band download", aoi_id, d_err)
        try:
            download_band(stac_metadata["assets"]["nir"], local_paths["nir"])
            download_band(stac_metadata["assets"]["red"], local_paths["red"])
        except Exception as e2:
            logger.warning("stac: download fallback failed (%s)", e2)
            return {"error": "Failed to fetch bands"}

    return {
        "source": "aws_download",
        "id": item_id,
        "local_paths": local_paths,
    }


def build_clipped_stack(assets: dict, bbox: list, out_folder: str) -> str:
    """Window-read every band asset clipped to bbox (lon/lat) and stack
    into a single multi-band GeoTIFF. Returns the path to stack.tif.

    Uses rasterio's HTTP COG support so only the bytes inside the window
    are pulled — no 100MB tile downloads. Bands ordered to match the
    11-band MARIDA convention so feature_stack works:
        [B2 blue, B3 green, B4 red, B5 redge1, B6 redge2, B7 redge3,
         B8 nir, B8A nir2, B11 swir16, B12 swir22, SCL]
    Missing bands are zero-filled.
    """
    import numpy as np
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds, Window

    band_order = [
        ("blue", "B02"), ("green", "B03"), ("red", "B04"),
        ("rededge1", "B05"), ("rededge2", "B06"), ("rededge3", "B07"),
        ("nir", "B08"), ("nir08", "B8A"),
        ("swir16", "B11"), ("swir22", "B12"),
        ("scl", "SCL"),
    ]

    # Use the first available asset to anchor the output grid + CRS.
    anchor_href = None
    for key, _alias in band_order:
        if assets.get(key):
            anchor_href = assets[key]
            break
    if anchor_href is None:
        raise RuntimeError("no usable band assets in STAC item")

    with rasterio.open(anchor_href) as anchor:
        dst_crs = anchor.crs
        try:
            left, bottom, right, top = transform_bounds(
                "EPSG:4326", dst_crs, bbox[0], bbox[1], bbox[2], bbox[3], densify_pts=21,
            )
            win = from_bounds(left, bottom, right, top, anchor.transform)
            win = win.intersection(Window(0, 0, anchor.width, anchor.height))
            if win.width < 4 or win.height < 4:
                raise RuntimeError(f"window too small after clipping: {win}")
        except Exception:
            raise
        anchor_arr = anchor.read(1, window=win)
        H, W = anchor_arr.shape
        anchor_transform = anchor.window_transform(win)

    stack = np.zeros((len(band_order), H, W), dtype=np.float32)

    for i, (key, _alias) in enumerate(band_order):
        href = assets.get(key)
        if not href:
            continue
        try:
            with rasterio.open(href) as src:
                # Re-derive window in this band's resolution
                from rasterio.warp import reproject, Resampling
                src_left, src_bottom, src_right, src_top = transform_bounds(
                    "EPSG:4326", src.crs, bbox[0], bbox[1], bbox[2], bbox[3], densify_pts=21,
                )
                src_win = from_bounds(src_left, src_bottom, src_right, src_top, src.transform)
                src_win = src_win.intersection(Window(0, 0, src.width, src.height))
                if src_win.width < 1 or src_win.height < 1:
                    continue
                src_arr = src.read(1, window=src_win)
                src_tf = src.window_transform(src_win)
                # Resample to anchor grid
                out = np.zeros((H, W), dtype=np.float32)
                reproject(
                    source=src_arr.astype(np.float32),
                    destination=out,
                    src_transform=src_tf,
                    src_crs=src.crs,
                    dst_transform=anchor_transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.bilinear,
                )
                stack[i] = out
        except Exception as e:
            logger.info("stac: skipped band %s (%s)", key, e)

    # MARIDA convention: reflectance in [0,1]. Sentinel-2 L2A COGs are
    # uint16 with scale ~10000. Heuristic detector handles both via
    # bands.max() > 1.5 → DN rescale.
    out_path = os.path.join(out_folder, "stack.tif")
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": stack.shape[0],
        "height": H,
        "width": W,
        "crs": dst_crs,
        "transform": anchor_transform,
        "compress": "deflate",
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(stack)
    return out_path
