from __future__ import annotations

import json
import logging
import math
import os
import threading
import uuid
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, HTTPException
from global_land_mask import globe
from pydantic import BaseModel, field_validator
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon as ShapelyPolygon
from shapely.prepared import prep

router = APIRouter(prefix="/api/v1/tracker")
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
COASTLINE_FILE = os.path.join(DATA_DIR, "india_coastline_segmented.geojson")
DB_FILE = os.path.join(DATA_DIR, "search_history_db.json")

MAX_GRID_SIDE = 40
MIN_GRID_SIDE = 12
TARGET_INTERIOR_SAMPLES = 900

db_lock = threading.Lock()


class SearchBox(BaseModel):
    coordinates: list[tuple[float, float]]

    @field_validator("coordinates")
    @classmethod
    def _validate_coordinates(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(value) < 3:
            raise ValueError("At least 3 points are required to form a polygon.")
        for lon, lat in value:
            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                raise ValueError(f"Invalid coordinate ({lon}, {lat}); lon/lat out of bounds.")
        return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iter_points(coords):
    if not isinstance(coords, (list, tuple)):
        return
    if len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        yield (float(coords[0]), float(coords[1]))
        return
    for part in coords:
        yield from _iter_points(part)


def _distance_deg(lon_a: float, lat_a: float, lon_b: float, lat_b: float, lat_ref_rad: float) -> float:
    dx = (lon_a - lon_b) * math.cos(lat_ref_rad)
    dy = lat_a - lat_b
    return math.hypot(dx, dy)


def _sampling_grid(bounds: tuple[float, float, float, float]) -> tuple[np.ndarray, np.ndarray]:
    minx, miny, maxx, maxy = bounds
    width = max(1e-6, maxx - minx)
    height = max(1e-6, maxy - miny)
    aspect = width / height

    gx = int(max(MIN_GRID_SIDE, min(MAX_GRID_SIDE, math.sqrt(TARGET_INTERIOR_SAMPLES * aspect))))
    gy = int(max(MIN_GRID_SIDE, min(MAX_GRID_SIDE, math.sqrt(TARGET_INTERIOR_SAMPLES / aspect))))
    return np.linspace(minx, maxx, gx), np.linspace(miny, maxy, gy)


def _nearest_coastline_point(center: tuple[float, float], coastline_data: dict) -> tuple[list[float] | None, float | None]:
    lon_c, lat_c = center
    lat_rad = math.radians(lat_c)
    min_dist = float("inf")
    nearest_pt: list[float] | None = None

    for feature in coastline_data.get("features", []):
        coords = feature.get("geometry", {}).get("coordinates", [])
        for lon, lat in _iter_points(coords):
            dist = _distance_deg(lon_c, lat_c, lon, lat, lat_rad)
            if dist < min_dist:
                min_dist = dist
                nearest_pt = [lon, lat]

    if nearest_pt is None:
        return None, None
    return nearest_pt, min_dist


def _deterministic_density(distance_deg: float | None) -> float:
    if distance_deg is None:
        return 0.45
    val = 0.95 - min(distance_deg, 1.5) * 0.45
    return round(max(0.30, min(0.95, val)), 3)


# Initialize DB if it doesn't exist
if not os.path.exists(DB_FILE):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)


def get_history() -> list[dict]:
    if not os.path.exists(DB_FILE):
        return []
    with db_lock:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                payload = json.load(f)
                return payload if isinstance(payload, list) else []
            except Exception as exc:
                backup = f"{DB_FILE}.bak.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
                try:
                    os.replace(DB_FILE, backup)
                    logger.warning("tracker db corrupted; moved to %s (%s)", backup, exc)
                except OSError:
                    logger.warning("tracker db corrupted and could not be moved aside (%s)", exc)
                return []


def save_history(history: list[dict]) -> None:
    with db_lock:
        tmp_file = f"{DB_FILE}.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        os.replace(tmp_file, DB_FILE)


@router.get("/coastline")
async def get_coastline():
    history = get_history()
    if not os.path.exists(COASTLINE_FILE):
        return {"type": "FeatureCollection", "features": []}

    with open(COASTLINE_FILE, "r", encoding="utf-8") as f:
        coastline_data = json.load(f)

    hit_locations: list[tuple[float, float]] = []
    for item in history:
        hit = item.get("driftVector")
        if isinstance(hit, list) and len(hit) >= 2:
            hit_locations.append((float(hit[0]), float(hit[1])))

    for feature in coastline_data.get("features", []):
        coords = feature.get("geometry", {}).get("coordinates", [])
        intensity = 0.0

        points = list(_iter_points(coords))
        if points:
            lon_avg = sum(pt[0] for pt in points) / len(points)
            lat_avg = sum(pt[1] for pt in points) / len(points)
            lat_rad = math.radians(lat_avg)
            for hit_lon, hit_lat in hit_locations:
                dist = _distance_deg(lon_avg, lat_avg, hit_lon, hit_lat, lat_rad)
                if dist < 1.0:
                    intensity += max(0.0, (1.0 - dist) * 5.0)

        props = feature.setdefault("properties", {})
        props["intensity"] = min(intensity * 0.5, 1.0)

    return coastline_data


@router.post("/search")
async def add_search(box: SearchBox):
    if not box.coordinates:
        raise HTTPException(status_code=400, detail="Coordinates array cannot be empty.")

    coordinates = [(float(lon), float(lat)) for lon, lat in box.coordinates]

    for lon, lat in coordinates:
        if globe.is_land(lat, lon):
            raise HTTPException(
                status_code=400,
                detail="Deployment Target Error: A corner point is on land. All vertices must be in ocean.",
            )

    closed_coords = coordinates + [coordinates[0]]
    try:
        poly = ShapelyPolygon(closed_coords)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid polygon geometry.")

    if not poly.is_valid:
        raise HTTPException(status_code=400, detail="Invalid polygon geometry - self-intersecting or degenerate.")

    lons, lats = _sampling_grid(poly.bounds)
    prepared = prep(poly)

    for lon in lons:
        for lat in lats:
            point = ShapelyPoint(float(lon), float(lat))
            if prepared.covers(point) and globe.is_land(float(lat), float(lon)):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Deployment Target Error: Land detected inside sector at "
                        f"({lat:.4f}N, {lon:.4f}E). The entire polygon must be over ocean."
                    ),
                )

    centroid = poly.centroid
    if globe.is_land(centroid.y, centroid.x):
        raise HTTPException(status_code=400, detail="Deployment Target Error: Center of sector is on land.")

    center = [float(centroid.x), float(centroid.y)]

    drift_vector = [center[0], center[1]]
    min_dist = None
    if os.path.exists(COASTLINE_FILE):
        with open(COASTLINE_FILE, "r", encoding="utf-8") as f:
            c_data = json.load(f)
        nearest_pt, min_dist = _nearest_coastline_point((center[0], center[1]), c_data)
        if nearest_pt is not None:
            drift_vector = nearest_pt

    density = _deterministic_density(min_dist)

    record = {
        "id": f"S-{uuid.uuid4().hex[:8]}",
        "coordinates": [[lon, lat] for lon, lat in coordinates],
        "center": center,
        "driftVector": drift_vector,
        "density": density,
        "date": _utc_now(),
    }

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

    record = history.pop(target_idx)
    record["date"] = _utc_now()
    history.append(record)
    save_history(history)
    return record
