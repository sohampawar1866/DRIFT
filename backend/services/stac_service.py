import os
import json
import urllib.request
import shutil
from pystac_client import Client
import datetime
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Grab the timeout from .env (defaults to 30 seconds if missing)
STAC_FETCH_TIMEOUT = int(os.getenv("STAC_FETCH_TIMEOUT", 30))

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")

def download_band(url: str, save_path: str):
    """Downloads a file if it doesn't already exist using atomic writes."""
    if not os.path.exists(save_path):
        tmp_path = save_path + ".tmp"
        print(f"Downloading {url} to {tmp_path}...")
        try:
            with urllib.request.urlopen(url, timeout=STAC_FETCH_TIMEOUT) as response, open(tmp_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            os.rename(tmp_path, save_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise e

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
    
    items = list(search.items())
    
    if not items:
        return {"error": "No low-cloud Sentinel-2 imagery found for this period and bbox."}
        
    # Select the most recent clean image
    best_item = items[0]
    
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
        print(f"Network error asking AWS STAC: {e}. Attempting Fallback...")
    
    # 2. Offline Fallback Logic: Did we completely fail to talk to the internet?
    if stac_metadata is None or "error" in stac_metadata:
        cached_dirs = [d for d in os.listdir(aoi_folder) if os.path.isdir(os.path.join(aoi_folder, d))]
        if not cached_dirs:
            return {"error": "No internet connection, and no local fallback imagery found!"}
        # Sort magically finds newest string ID if AWS naming conventions hold, else just pop one
        newest_cached_id = sorted(cached_dirs)[-1]
        print(f"🔥 NO INTERNET: successfully falling back to local cache: {newest_cached_id}")
        
        return {
            "source": "local_fallback",
            "id": newest_cached_id,
            "local_paths": {
                "nir": os.path.join(aoi_folder, newest_cached_id, "nir.tif"),
                "red": os.path.join(aoi_folder, newest_cached_id, "red.tif")
            }
        }
    
    # 3. Online Success: We have a valid AWS image ID. Let's see if we already downloaded it today.
    item_id = stac_metadata["id"]
    item_folder = os.path.join(aoi_folder, item_id)
    
    local_paths = {
        "nir": os.path.join(item_folder, "nir.tif"),
        "red": os.path.join(item_folder, "red.tif")
    }
    
    # LOGICAL FIX: Check if the actual files exist, not just the folder!
    # If a previous download failed midway, the folder might exist but the .tif files are missing.
    if os.path.exists(local_paths["nir"]) and os.path.exists(local_paths["red"]):
        print(f"⚡ INSTANT CACHE HIT: Already downloaded {item_id} previously. Skipping download!")
        return {
            "source": "local_cache", 
            "id": item_id, 
            "local_paths": local_paths
        }
        
    # 4. First Time Seeing This Image: We must download it!
    print(f"⬇️ DOWNLOADING NEW STAC TILE: {item_id}")
    os.makedirs(item_folder, exist_ok=True)
    
    try:
        # Download only the subset of bands we actually need for FDI and basics to save time (NIR, Red)
        download_band(stac_metadata["assets"]["nir"], local_paths["nir"])
        download_band(stac_metadata["assets"]["red"], local_paths["red"])
        print(f"✅ DOWNLOAD SUCCESS: Cached at {item_folder}")
    except Exception as d_err:
        print(f"Download failed midway: {d_err}")
        return {"error": "Failed to download bands"}
        
    return {
        "source": "aws_download",
        "id": item_id,
        "local_paths": local_paths
    }
