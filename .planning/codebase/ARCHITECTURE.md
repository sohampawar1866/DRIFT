# Architecture

**Analysis Date:** 2026-04-17

## Current State Pattern Overview

**Overall:** Minimal layered REST API (HTTP → Route → Service)

**Key Characteristics:**
- Thin FastAPI application with three mock endpoints
- Service layer provides synthetic GeoJSON generators
- No ML, physics, or domain logic implemented yet
- CORS enabled for frontend development
- All responses are mock data (random, not real detections)

## Current Layers

**Presentation (HTTP Layer):**
- Purpose: Accept HTTP requests, route to handlers, return GeoJSON responses
- Location: `backend/api/routes.py`
- Contains: FastAPI router with three endpoints
- Depends on: Service layer (`backend/services/mock_data.py`)
- Used by: Frontend (React dashboard, not yet implemented)

**Service Layer:**
- Purpose: Generate synthetic geospatial data structures
- Location: `backend/services/mock_data.py`
- Contains: Three generator functions returning FeatureCollections
- Depends on: Python standard library (random, no external geo libraries)
- Used by: API route handlers

**Main Application:**
- Purpose: Initialize FastAPI app, mount router, configure CORS
- Location: `backend/main.py`
- Contains: FastAPI instance, CORS middleware, root health check
- Depends on: FastAPI, Uvicorn, routes module
- Used by: Uvicorn server at startup

## Current Data Flow

**Detection Request:**
```
GET /api/v1/detect?aoi_id=mumbai
  ↓
routes.detect_plastic(aoi_id)
  ↓
get_mock_detection_geojson(aoi_id)
  ↓
Random polygon generator (5 patches per request)
  ↓
Return FeatureCollection with random confidence, area, age
```

**Forecast Request:**
```
GET /api/v1/forecast?aoi_id=mumbai&hours=24
  ↓
routes.forecast_drift(aoi_id, hours)
  ↓
get_mock_forecast_geojson(aoi_id, hours)
  ↓
Retrieve base detections, apply simple linear drift
  ↓
Return FeatureCollection with drifted coordinates
```

**Mission Request:**
```
GET /api/v1/mission?aoi_id=mumbai
  ↓
routes.plan_mission(aoi_id)
  ↓
get_mock_mission_geojson(aoi_id)
  ↓
Extract first 4 detection centroids, create LineString
  ↓
Return FeatureCollection with waypoint route
```

**State Management:**
- No persistent state; all data is generated on-the-fly
- Each request produces independent mock output
- No database, cache, or file-based state
- Frontend will eventually manage zoom/layer visibility state

## Intended Architecture (from PRD §5)

The design must support a **five-stage pipeline** that is NOT yet implemented:

1. **Ingest:** Read pre-staged Sentinel-2 L2A tiles from local storage
   - Input: 4 demo AOI `.SAFE` or COG files
   - Output: 6-band raster (B2, B3, B4, B6, B8, B11)
   - Location (to build): `backend/ml/ingest.py`

2. **Detect:** Run U-Net model on feature stack, produce probability mask
   - Input: 9-channel stack (RGB + RedEdge + NIR + SWIR + FDI + NDVI + PI)
   - Output: Per-pixel plastic probability, sub-pixel fraction estimate
   - Location (to build): `backend/ml/model.py`, `backend/ml/features.py`, `backend/ml/inference.py`
   - Model: U-Net with SE attention bottleneck (5M parameters)

3. **Forecast:** Integrate Lagrangian particle tracker with wind/current fields
   - Input: Detected polygons + CMEMS currents + ERA5 winds (pre-downloaded NetCDF)
   - Output: Particle positions at t+0h, t+24h, t+48h, t+72h
   - Location (to build): `backend/physics/tracker.py`, `backend/physics/env_data.py`
   - Physics: Euler-step integrator with windage coefficient α=0.02

4. **Visualize:** Serve all layers (detection, forecast, hotspots) as GeoJSON/PNG tiles
   - Input: Model outputs + physics results
   - Output: REST endpoints returning GeoJSON + optional tile PNGs
   - Location (to build): `backend/api/v2/` with expanded endpoints
   - Extends: Current `backend/api/routes.py`

5. **Act:** Cleanup mission planner (greedy TSP solver)
   - Input: Top-K hotspots weighted by density × accessibility × forecast convergence
   - Output: Ordered waypoints + GPX + PDF briefing
   - Location (to build): `backend/mission/planner.py`, `backend/mission/export.py`
   - Solves: Traveling Salesman Problem over detected patches

## Key Abstractions (Current vs. Intended)

**GeoJSON Feature Contract (Current & Intended):**
```json
{
  "type": "Feature",
  "geometry": {
    "type": "Polygon | LineString",
    "coordinates": [...]
  },
  "properties": {
    "id": "patch_N | route_N",
    "confidence": 0.0-1.0,
    "area_sq_meters": float,
    "age_days": integer (mock now, estimated from age regressor later),
    "type": "macroplastic | route",
    "forecast_hour": integer (optional),
    "fraction_plastic": float (to add),
    "conf_adj": float (to add, biofouling-adjusted)
  }
}
```

**Feature Stack (Intended, not built):**
- Channels 0-2: RGB (B2, B3, B4)
- Channels 3-4: RedEdge + NIR (B6, B8)
- Channel 5: SWIR (B11)
- Channel 6: FDI (computed: B8 - interpolated NIR from B6/B11)
- Channel 7: NDVI (computed: (B8 - B4) / (B8 + B4))
- Channel 8: PI / Plastic Index (computed: ratio-based spectral signature)
- Shape: (256, 256, 9) or 10m resolution patches

**Detection Model Output Heads (Intended):**
- Head 1: Binary plastic probability mask (Dice + weighted BCE loss)
- Head 2: Sub-pixel fractional cover regression (MSE loss on synthetic mixed-pixel labels)

## Entry Points

**Current:**
- Location: `backend/main.py` (FastAPI app initialization)
- Triggers: `uvicorn main:app --reload` or import as module
- Responsibilities: CORS setup, router mounting, health check endpoint

**Intended (API v2):**
- POST `/api/v1/detect` — Tile ingestion + model inference
- GET `/api/v1/forecast` — Trajectory computation
- POST `/api/v1/mission` — Mission planning with parameters

**Intended (Training):**
- Location: `backend/ml/train.py` (not yet created)
- Triggers: Manual execution during development
- Responsibilities: MARIDA dataset loading, model training loop, checkpoint saving

## Error Handling

**Current Strategy:** Pass-through; mock functions return valid FeatureCollections always

**Patterns Observed:**
- No error handling in `mock_data.py`; assumes valid `aoi_id` parameter
- `routes.py` has basic input validation for `hours` parameter (24|48|72)

**Intended:**
- Validation on raster tile paths (pre-staged locally)
- Model inference error (GPU OOM, corrupted checkpoint) → graceful fallback to cached results
- Physics integrator bounds checks (particles must stay within valid lat/lon bounds)
- Mission planner robustness for edge cases (no hotspots detected, unreachable waypoints)

## Cross-Cutting Concerns

**Logging:**
- Current: None
- Intended: Structured logging (JSON format) for:
  - Model inference latency
  - API response times
  - Physics solver convergence/divergence
  - Dataset loading progress

**Validation:**
- Current: AOI ID and forecast hours parameters only
- Intended:
  - Geospatial bounds validation (detections must be within AOI)
  - Raster data integrity checks (non-null bands, valid georeferencing)
  - Confidence threshold filtering (conf > 0.7 for public dashboards)

**Authentication:**
- Current: Not implemented (development mode, all origins allowed)
- Intended (P2 - Nice-to-Have per PRD §6): OAuth/SSO for INCOIS/NCCR integration; not in MVP

**Biofouling Confidence Decay:**
- Current: Not implemented; age is random
- Intended: Applied at inference time
  - Formula: `conf_adj = conf_raw · exp(−age_days / τ)` where τ=30 days
  - Requires: Age estimator head on model (trained on synthetic augmented data)
  - Display: Dashboard chart showing confidence vs. estimated debris age

---

*Architecture analysis: 2026-04-17*
