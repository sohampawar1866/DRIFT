import os
import json
import urllib.request
import shutil
<<<<<<< HEAD
import logging
from pystac_client import Client
=======
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
import datetime
from datetime import timedelta
from pathlib import Path
from pystac_client import Client
import stackstac
import xarray as xr
import rioxarray
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

STAC_FETCH_TIMEOUT = int(os.getenv("STAC_FETCH_TIMEOUT", 30))
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")

<<<<<<< HEAD

def _required_band_paths(item_folder: str) -> dict:
    return {
        "nir": os.path.join(item_folder, "nir.tif"),
        "red": os.path.join(item_folder, "red.tif"),
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
=======
def query_sentinel2_l2a_aws(bbox: list, max_cloud_cover: int = 20, days_back: int = 30) -> dict:
    """Queries for Sentinel-2 L2A with all required bands for MARIDA-style inference."""
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
    api_url = "https://earth-search.aws.element84.com/v1"
    client = Client.open(api_url)
    
    end_date = datetime.datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)
    date_range = f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
    
    print(f"[STAC] Searching AWS Earth Search: BBox={bbox}, Cloud<{max_cloud_cover}%, Days={days_back}...")
    
    search = client.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": max_cloud_cover}},
        sortby=[{"field": "properties.datetime", "direction": "desc"}]
    )
    
<<<<<<< HEAD
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
=======
    items = list(search.items())
    if not items:
        # Fallback search: loosen constraints
        if days_back < 60 or max_cloud_cover < 50:
             print("[STAC] Warning: No items found in sharp window. Attempting resilient fallback (Cloud<50%, Days=60)...")
             return query_sentinel2_l2a_aws(bbox, max_cloud_cover=50, days_back=60)
        
        print(f"[STAC] Critical: No Sentinel-2 imagery found at {bbox} even with loose constraints.")
        return {"error": "No Sentinel-2 imagery found."}
        
    best_item = items[0]
    print(f"[STAC] Match Found: {best_item.id} from {best_item.datetime} (Cloud: {best_item.properties.get('eo:cloud_cover')}%)")
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
    
    # MARIDA mapping for 10 bands + Visual (TCI)
    bands_mapping = {
        "B02": "blue",
        "B03": "green",
        "B04": "red",
        "B05": "rededge1",
        "B06": "rededge2",
        "B07": "rededge3",
        "B08": "nir",
        "B8A": "nir08",
        "B11": "swir16",
        "B12": "swir22",
        "visual": "visual"
    }
    
    assets = {}
    for b_name, asset_key in bands_mapping.items():
        asset = best_item.assets.get(asset_key)
        if asset:
            assets[b_name] = asset.href
            
    return {
        "id": best_item.id,
        "datetime": best_item.datetime.isoformat(),
        "cloud_cover": best_item.properties.get("eo:cloud_cover"),
        "assets": assets,
        "item": best_item 
    }


def get_live_or_cached_imagery(aoi_id: str, bbox: list) -> dict:
    """Fetch, stack, and cache live multi-band imagery."""
    aoi_folder = os.path.join(CACHE_DIR, aoi_id)
    os.makedirs(aoi_folder, exist_ok=True)
    
    try:
        stac_result = query_sentinel2_l2a_aws(bbox)
        if "error" in stac_result:
            return stac_result
            
        item_id = stac_result["id"]
        item_folder = os.path.join(aoi_folder, item_id)
        os.makedirs(item_folder, exist_ok=True)
        
        stack_path = os.path.join(item_folder, "stack.tif")
        
        if os.path.exists(stack_path):
            return {"source": "cache", "id": item_id, "local_path": stack_path}
            
        print(f"[STAC] FETCHING LIVE STACK: {item_id}")
        
        # Use stackstac to handle the heavy lifting (lazy loading + resampling)
        # We need the pystac item for stackstac
        item = stac_result["item"]
        
        # Filter for the 10 bands we mapped
        bands = list(stac_result["assets"].keys())
        # stackstac expects the asset keys (e.g. 'blue', 'red')
        assets_to_load = [stac_result["item"].assets[k.lower() if k != 'B8A' else 'nir08'].key for k in ["B02","B03","B04","B05","B06","B07","B08","B8A","B11","B12"]]
        # Actually, let's just use stackstac's assets filter
        asset_keys = ["blue", "green", "red", "rededge1", "rededge2", "rededge3", "nir", "nir08", "swir16", "swir22"]
        
        stack = stackstac.stack(
            item,
            assets=asset_keys,
            bounds_latlon=bbox,
            resolution=10, # Force MARIDA standard 10m
            epsg=32633 # Default UTM, we'll refine if needed or let rioxarray handle
        ).squeeze()
        
        # Convert to numpy and save
        stack_data = stack.compute()
        # Ensure ordering: MARIDA expects [B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12]
        # stackstac appends 'band' coord
        
        stack_data.rio.to_raster(stack_path)
        print(f"[STAC] LIVE STACK CREATED: {stack_path}")
        
        return {
            "source": "aws_live",
            "id": item_id,
            "local_path": stack_path,
            "bands": asset_keys
        }
        
    except Exception as e:
<<<<<<< HEAD
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
        
    # 4. First Time Seeing This Image: We must download it!
    logger.info("stac: downloading new tile for %s -> %s", aoi_id, item_id)
    os.makedirs(item_folder, exist_ok=True)
    
    try:
        # Download only the subset of bands we actually need for FDI and basics to save time (NIR, Red)
        download_band(stac_metadata["assets"]["nir"], local_paths["nir"])
        download_band(stac_metadata["assets"]["red"], local_paths["red"])
        logger.info("stac: download success for %s at %s", aoi_id, item_folder)
    except Exception as d_err:
        logger.warning("stac: download failed for %s (%s)", aoi_id, d_err)
        return {"error": "Failed to download bands"}
        
    return {
        "source": "aws_download",
        "id": item_id,
        "local_paths": local_paths
    }
=======
        print(f"Live STAC pipeline failed: {e}")
        return {"error": str(e)}
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
