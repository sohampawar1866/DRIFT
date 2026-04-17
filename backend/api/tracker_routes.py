from fastapi import APIRouter
from pydantic import BaseModel
import json
import os
import random
from datetime import datetime

router = APIRouter(prefix="/api/v1/tracker")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
COASTLINE_FILE = os.path.join(DATA_DIR, "india_coastline_segmented.geojson")
DB_FILE = os.path.join(DATA_DIR, "search_history_db.json")

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
    with open(DB_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return []

def save_history(history):
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
            for hit in hit_locations:
                # Euclidean distance proxy
                dx = seg_center[0] - hit[0]
                dy = seg_center[1] - hit[1]
                dist = (dx*dx)**0.5 + (dy*dy)**0.5
                if dist < 1.0: # Roughly ~100km radius 
                    intensity += max(0, 1.0 - dist)
                
        # Cap at 1.0
        feature["properties"]["intensity"] = min(intensity * 0.5, 1.0)
        
    return coastline_data

@router.post("/search")
async def add_search(box: SearchBox):
    # Calculate center of box
    lon_sum = sum([pt[0] for pt in box.coordinates])
    lat_sum = sum([pt[1] for pt in box.coordinates])
    center = [lon_sum / len(box.coordinates), lat_sum / len(box.coordinates)]
    
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
                    dist = ((center[0]-pt[0])**2 + (center[1]-pt[1])**2)**0.5
                    if dist < min_dist:
                        min_dist = dist
                        nearest_pt = pt
            if nearest_pt:
                drift_vector = nearest_pt
    
    density = random.uniform(0.3, 0.95)
    
    record = {
        "id": f"S{int(datetime.now().timestamp())}",
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
