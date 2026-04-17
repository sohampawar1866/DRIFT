from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
import os
import random
import math
import uuid
import threading
import shutil
from datetime import datetime

router = APIRouter(prefix="/api/v1/tracker")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
COASTLINE_FILE = os.path.join(DATA_DIR, "india_coastline_segmented.geojson")
DB_FILE = os.path.join(DATA_DIR, "search_history_db.json")

db_lock = threading.Lock()

class SearchBox(BaseModel):
    coordinates: list # list of [lon, lat] pairs

# Initialize DB if it doesn't exist
if not os.path.exists(DB_FILE):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DB_FILE, "w") as f:
        json.dump([], f)

def get_history():
    if not os.path.exists(DB_FILE):
        return []
    with db_lock:
        with open(DB_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception as e:
                # Corrupted file, rename to .bak and return empty safely
                shutil.copy(DB_FILE, DB_FILE + ".bak")
                return []

def save_history(history):
    with db_lock:
        with open(DB_FILE, "w") as f:
            json.dump(history, f, indent=2)

@router.get("/coastline")
async def get_coastline():
    history = get_history()
    
    if not os.path.exists(COASTLINE_FILE):
        return {"type": "FeatureCollection", "features": []}
        
    with open(COASTLINE_FILE, "r") as f:
        coastline_data = json.load(f)
        
    # Build list of coastal hit points from history
    hit_locations = [h.get("driftVector") for h in history if "driftVector" in h]
    
    # Increase intensity based on proximity to hit locations
    for i, feature in enumerate(coastline_data["features"]):
        coords = feature.get("geometry", {}).get("coordinates", [])
        intensity = 0.0
        
        if len(coords) > 0:
            seg_center = coords[0] # taking first point of segment for simplicity
            lat_rad = math.radians(seg_center[1])
            for hit in hit_locations:
                # Euclidean distance proxy scaled by cosine of latitude
                dx = (seg_center[0] - hit[0]) * math.cos(lat_rad)
                dy = seg_center[1] - hit[1]
                dist = math.hypot(dx, dy)
                if dist < 1.0: # Roughly ~100km radius 
                    # Multiply by 5 so visuals spike aggressively
                    intensity += max(0, (1.0 - dist) * 5.0)
                
        # Cap at 1.0
        feature["properties"]["intensity"] = min(intensity * 0.5, 1.0)
        
    return coastline_data

@router.post("/search")
async def add_search(box: SearchBox):
    if not box.coordinates:
        raise HTTPException(status_code=400, detail="Coordinates array cannot be empty.")
        
    # Calculate center of box
    lon_sum = sum([pt[0] for pt in box.coordinates])
    lat_sum = sum([pt[1] for pt in box.coordinates])
    center = [lon_sum / len(box.coordinates), lat_sum / len(box.coordinates)]
    lat_rad = math.radians(center[1])
    
    # Calculate actual drift towards nearest coastline
    drift_vector = [center[0] + 1.0, center[1] + 1.0] # Default
    if os.path.exists(COASTLINE_FILE):
        with open(COASTLINE_FILE, "r") as f:
            c_data = json.load(f)
            min_dist = float('inf')
            nearest_pt = None
            for feature in c_data.get("features", []):
                coords = feature.get("geometry", {}).get("coordinates", [])
                for pt in coords:
                    dx = (center[0]-pt[0]) * math.cos(lat_rad)
                    dy = center[1]-pt[1]
                    dist = math.hypot(dx, dy)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_pt = pt
            if nearest_pt:
                drift_vector = nearest_pt
    
    density = random.uniform(0.3, 0.95)
    
    record = {
        "id": f"S-{uuid.uuid4().hex[:8]}",
        "coordinates": box.coordinates,
        "center": center,
        "driftVector": drift_vector,
        "density": density,
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    
    # Save to global JSON DB
    history = get_history()
    history.append(record)
    save_history(history)
    
    return record

@router.get("/search")
async def get_searches():
    return get_history()

@router.post("/revisit/{record_id}")
async def reactivate_search(record_id: str):
    history = get_history()
    target_idx = None
    for i, rec in enumerate(history):
        if rec.get("id") == record_id:
            target_idx = i
            break
            
    if target_idx is None:
        raise HTTPException(status_code=404, detail="Record not found")
        
    # Re-insert at the top
    record = history.pop(target_idx)
    record["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history.append(record)
    save_history(history)
    return record
