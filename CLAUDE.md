<!-- GSD:project-start source:PROJECT.md -->
## Project

**DRIFT / PlastiTrack — Backend Intelligence**

An autonomous satellite-to-mission intelligence layer for floating marine macroplastic cleanup. DRIFT ingests Sentinel-2 multispectral imagery, detects sub-pixel plastic patches (distinguishing them from Sargassum, foam, and wakes), forecasts 72-hour Lagrangian drift using CMEMS ocean currents + ERA5 winds, and produces a deployable cleanup mission (GPX waypoints, GeoJSON, PDF briefing) targeted at Indian Coast Guard operations, INCOIS, and coastal port trusts.

**This project scope (locked after questioning 2026-04-17):** only the **backend intelligence layer** — ML detection, physics trajectory, mission planning. The FastAPI wiring and React frontend are **explicitly out of scope** for this milestone; the existing `backend/api/routes.py` mock endpoints stay untouched until a later integration milestone.

**Core Value:** **A single Python function chain `run_inference(tile) → forecast_drift(detections) → plan_mission(forecast)` must produce a valid cleanup mission plan end-to-end from a real Sentinel-2 tile — in under 15 seconds, with detection IoU ≥ 0.45 on MARIDA val.** If everything else fails, this chain must work. It is the defensible technical story that wins the Sankalp Bharat judging.

### Constraints

- **Timeline:** 24–48 hours from kickoff, feature-freeze at H36 (PRD §13). Every hour spent on out-of-scope items reduces demo polish time.
- **Tech stack (locked per PRD §8.6):** PyTorch 2.x + segmentation_models_pytorch, Rasterio, xarray, GeoPandas, Shapely — all pip-installable. No from-scratch transformers.
- **Python version:** 3.10 / 3.11 / 3.12 only (per `backend/README.md` — shapely/geopandas binary wheels are broken on 3.9 and 3.13+).
- **Training compute:** Kaggle free tier (12 GPU-hours/week, P100 or T4, ~16 GB VRAM). No AWS/GCP. Training script must be a single notebook runnable on Kaggle.
- **Pretrained weights:** Phase 1 uses the `dummy` branch (random/ImageNet-initialized SMP UnetPlusPlus) per research finding that `marccoru/marinedebrisdetector` weights live on private Google Drive (moved Aug 2024) and are not auto-fetchable by any public hub loader. The marccoru baseline is an optional Phase 2 bonus requiring a manual Drive download; the `our_real` (Kaggle-trained) weights hot-swap in Phase 3 via kagglehub. See `.planning/phases/01-schema-foundation-dummy-inference/01-RESEARCH.md`.
- **No live data ingestion:** every data source (S2 tiles, CMEMS currents, ERA5 winds) pre-staged. No auth flows in the runtime pipeline.
- **Contract freeze before Phase 1 ends:** detection GeoJSON feature schema is locked for all downstream consumers (tracker, planner, future API layer).
- **Scope rule (PRD §12, zero-sum):** any new feature proposal must be paired with a removal. Scope creep is the single highest risk.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.10, 3.11, or 3.12 - Backend API, ML model training, geospatial processing. (PRD targets 3.10–3.12 due to geopandas/shapely binary wheel availability; 3.13/3.14 not yet supported.)
- JavaScript/TypeScript (React frontend planned per PRD, not yet in codebase)
## Runtime
- Python venv (virtual environment via `python -m venv venv`)
- Fallback: Conda/Miniconda for Windows GDAL/Fiona/GeoPandas when pip fails (documented in `backend/README.md`)
- pip (with `--upgrade pip setuptools wheel` recommended before install)
- Lockfile: Missing (no `requirements.lock` or `Pipenv.lock`; only `backend/requirements.txt`)
## Frameworks
- FastAPI 0.110.0 - REST API with async support, auto-generated Swagger UI at `/docs`, CORS middleware pre-configured
- Uvicorn [standard] 0.29.0 - ASGI application server
- Pydantic 2.6.4 - Request/response validation
- Pydantic-Settings 2.2.1 - Environment-based configuration
- Shapely 2.0.3 - Geometric operations (polygon, point, intersection handling)
- GeoPandas 0.14.3 - Spatial dataframes, shapefile I/O, coordinate transformations
- PyTorch 2.x - Deep learning framework for U-Net detector
- segmentation_models_pytorch - Pre-trained encoder/decoder for semantic segmentation
- Rasterio - Sentinel-2 COG reading, band resampling, feature rasterization
- xarray - Multi-dimensional array handling for NetCDF (CMEMS/ERA5)
- NumPy - Array operations
- Scikit-learn - Optional: classical baselines (Random Forest fallback per risk mitigation §16)
- pytest - Unit testing
- pytest-cov - Coverage reporting
- React + Vite - Dashboard UI
- Mapbox GL JS - Interactive map base layer
- deck.gl - Particle animation and heatmap visualization
- Recharts - Confidence-decay chart
- togpx + jsPDF - GPX and PDF export
## Key Dependencies
- **FastAPI 0.110.0** - Core REST API server; enables `/detect`, `/forecast`, `/mission` endpoints with auto-generated OpenAPI schema
- **Uvicorn [standard] 0.29.0** - ASGI server required to run FastAPI; includes `uvicorn.run()` for live reload dev mode
- **Pydantic 2.6.4** - Runtime type validation; enforces request/response schemas
- **GeoPandas 0.14.3** - Spatial vector operations; handles shapefiles in `MARIDA/shapefiles/`; requires GDAL/GEOS/PROJ compilation (Windows fallback: conda-forge)
- **Shapely 2.0.3** - Geometric primitives (Polygon, Point, LineString); required by GeoPandas; C-compiled for performance
- **Rasterio** - Cloud-optimized GeoTIFF (COG) reading; Sentinel-2 band stacking (B2/B3/B4/B6/B8/B11 at 10m)
- **xarray** - NetCDF I/O for CMEMS currents (u/v) and ERA5 winds (10m components)
- **PyTorch 2.x + segmentation_models_pytorch** - U-Net encoder/decoder with pretrained ResNet-18 backbone
- **Scikit-image** - Polygon rasterization, morphological ops (planned for feature post-processing)
## Configuration
- Configured via FastAPI startup: CORS middleware with `allow_origins=["*"]` for local dev (set in `backend/main.py` line 15–19)
- No `.env` file currently in repo (listed in `.gitignore` line 5); environment variables would store:
- No build config files detected (no `pyproject.toml`, `setup.py`, `Makefile`)
- Execution: `uvicorn main:app --reload` from `backend/` directory
- File: `backend/requirements.txt` - Minimal (9 lines currently)
- Must be extended with ML dependencies (PyTorch, segmentation_models_pytorch, rasterio, xarray) before training phase (PRD §13, H4–H16)
## Platform Requirements
- Python 3.10, 3.11, or 3.12 (Windows/Mac/Linux)
- pip + venv (or conda for Windows geospatial issues)
- GDAL/GEOS/PROJ: Pre-compiled wheels on Linux/Mac; Windows must use conda or OSGeo4W
- Optional: GPU (CUDA 12.1+ for PyTorch) for training speedup; CPU-only fallback supported per PRD §16 risk mitigation
- Single-box Docker Compose (localhost demo per PRD §8.6 — no cloud deployment planned for hackathon)
- Requires: Docker + docker-compose
- No `Dockerfile` or `docker-compose.yml` currently committed
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Modules: lowercase with underscores (`main.py`, `mock_data.py`, `routes.py`)
- Packages: lowercase directories (`api/`, `services/`)
- lowercase with underscores: `get_mock_detection_geojson()`, `get_mock_forecast_geojson()`, `get_mock_mission_geojson()`
- Async handlers: `async def detect_plastic()`, `async def forecast_drift()`, `async def plan_mission()`
- lowercase snake_case: `aoi_id`, `hours`, `base_lon`, `base_lat`, `drift_lon_per_hour`
- Constants in capitalized patterns where needed (not yet observed in codebase)
- Not yet used in current codebase (minimal scope); will follow PascalCase when introduced (standard Python convention)
## Code Style
- No explicit formatter configured (no `.prettierrc`, `black.toml`, or `setup.cfg`)
- Follows PEP 8 conventions informally (indentation, spacing)
- 4-space indentation observed
- No linting tools configured (no `.pylintrc`, `.flake8`)
- No lint checks enforced in CI/CD
## Import Organization
- Explicit imports from modules (not `import *`)
- Blank line between stdlib and third-party groups
- Relative imports within package (e.g., `from services.mock_data import ...` in `backend/api/routes.py`)
- Example from `backend/api/routes.py` (lines 1–6):
- Not used yet; all imports are relative to package root
## Error Handling
- Inline dict-based error returns: `return {"error": "Invalid forecast step. Allowed values are [24, 48, 72]."}`
## Logging
- Default: standard library `logging` module would be idiomatic
- Current approach: silent operation (GeoJSON returned directly)
## Comments
- Docstrings on all endpoint handlers (observed pattern):
- Not applicable (Python codebase, not TypeScript)
## Function Design
- Functions are small and focused
- Example: `get_mock_detection_geojson()` (43 lines) — generates feature collection
- Example: `get_mock_forecast_geojson()` (19 lines) — applies drift transformation
- Example: `get_mock_mission_geojson()` (29 lines) — computes route
- Explicit, named parameters with defaults
- Example: `async def forecast_drift(aoi_id: str = "mumbai", hours: int = 24)`
- Type hints used (str, int)
- GeoJSON dict structure (FeatureCollection):
- Error responses: dict with "error" key (to be refactored to HTTPException)
## Module Design
- Explicit function exports from `backend/services/mock_data.py`
- Router pattern in `backend/api/routes.py`:
- Not used; codebase is minimal (no index.py or `__init__.py` exports observed)
## Architecture Patterns
- **Endpoint handlers do NO business logic** — they call service functions
- Example: `async def detect_plastic()` calls `get_mock_detection_geojson(aoi_id)` and returns result directly
- This separates concerns and makes testing easier (when tests are added)
## Middleware & Infrastructure
- Middleware pattern in `backend/main.py` (lines 14–20):
- Rationale: "Crucial to unblock the frontend React dev" (inline comment, line 13)
- Note: Permissive for local dev; should be restricted for production
- FastAPI metadata: title, description, version (lines 7–11 in `backend/main.py`)
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Current State Pattern Overview
- Thin FastAPI application with three mock endpoints
- Service layer provides synthetic GeoJSON generators
- No ML, physics, or domain logic implemented yet
- CORS enabled for frontend development
- All responses are mock data (random, not real detections)
## Current Layers
- Purpose: Accept HTTP requests, route to handlers, return GeoJSON responses
- Location: `backend/api/routes.py`
- Contains: FastAPI router with three endpoints
- Depends on: Service layer (`backend/services/mock_data.py`)
- Used by: Frontend (React dashboard, not yet implemented)
- Purpose: Generate synthetic geospatial data structures
- Location: `backend/services/mock_data.py`
- Contains: Three generator functions returning FeatureCollections
- Depends on: Python standard library (random, no external geo libraries)
- Used by: API route handlers
- Purpose: Initialize FastAPI app, mount router, configure CORS
- Location: `backend/main.py`
- Contains: FastAPI instance, CORS middleware, root health check
- Depends on: FastAPI, Uvicorn, routes module
- Used by: Uvicorn server at startup
## Current Data Flow
```
```
```
```
```
```
- No persistent state; all data is generated on-the-fly
- Each request produces independent mock output
- No database, cache, or file-based state
- Frontend will eventually manage zoom/layer visibility state
## Intended Architecture (from PRD §5)
## Key Abstractions (Current vs. Intended)
```json
```
- Channels 0-2: RGB (B2, B3, B4)
- Channels 3-4: RedEdge + NIR (B6, B8)
- Channel 5: SWIR (B11)
- Channel 6: FDI (computed: B8 - interpolated NIR from B6/B11)
- Channel 7: NDVI (computed: (B8 - B4) / (B8 + B4))
- Channel 8: PI / Plastic Index (computed: ratio-based spectral signature)
- Shape: (256, 256, 9) or 10m resolution patches
- Head 1: Binary plastic probability mask (Dice + weighted BCE loss)
- Head 2: Sub-pixel fractional cover regression (MSE loss on synthetic mixed-pixel labels)
## Entry Points
- Location: `backend/main.py` (FastAPI app initialization)
- Triggers: `uvicorn main:app --reload` or import as module
- Responsibilities: CORS setup, router mounting, health check endpoint
- POST `/api/v1/detect` — Tile ingestion + model inference
- GET `/api/v1/forecast` — Trajectory computation
- POST `/api/v1/mission` — Mission planning with parameters
- Location: `backend/ml/train.py` (not yet created)
- Triggers: Manual execution during development
- Responsibilities: MARIDA dataset loading, model training loop, checkpoint saving
## Error Handling
- No error handling in `mock_data.py`; assumes valid `aoi_id` parameter
- `routes.py` has basic input validation for `hours` parameter (24|48|72)
- Validation on raster tile paths (pre-staged locally)
- Model inference error (GPU OOM, corrupted checkpoint) → graceful fallback to cached results
- Physics integrator bounds checks (particles must stay within valid lat/lon bounds)
- Mission planner robustness for edge cases (no hotspots detected, unreachable waypoints)
## Cross-Cutting Concerns
- Current: None
- Intended: Structured logging (JSON format) for:
- Current: AOI ID and forecast hours parameters only
- Intended:
- Current: Not implemented (development mode, all origins allowed)
- Intended (P2 - Nice-to-Have per PRD §6): OAuth/SSO for INCOIS/NCCR integration; not in MVP
- Current: Not implemented; age is random
- Intended: Applied at inference time
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
