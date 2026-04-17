# Technology Stack

**Analysis Date:** 2026-04-17

## Languages

**Primary:**
- Python 3.10, 3.11, or 3.12 - Backend API, ML model training, geospatial processing. (PRD targets 3.10–3.12 due to geopandas/shapely binary wheel availability; 3.13/3.14 not yet supported.)

**Not Yet Implemented:**
- JavaScript/TypeScript (React frontend planned per PRD, not yet in codebase)

## Runtime

**Environment:**
- Python venv (virtual environment via `python -m venv venv`)
- Fallback: Conda/Miniconda for Windows GDAL/Fiona/GeoPandas when pip fails (documented in `backend/README.md`)

**Package Manager:**
- pip (with `--upgrade pip setuptools wheel` recommended before install)
- Lockfile: Missing (no `requirements.lock` or `Pipenv.lock`; only `backend/requirements.txt`)

## Frameworks

**Core:**
- FastAPI 0.110.0 - REST API with async support, auto-generated Swagger UI at `/docs`, CORS middleware pre-configured
- Uvicorn [standard] 0.29.0 - ASGI application server

**Data & Geospatial (Current):**
- Pydantic 2.6.4 - Request/response validation
- Pydantic-Settings 2.2.1 - Environment-based configuration
- Shapely 2.0.3 - Geometric operations (polygon, point, intersection handling)
- GeoPandas 0.14.3 - Spatial dataframes, shapefile I/O, coordinate transformations

**Planned but Not Installed (from PRD §8.6):**
- PyTorch 2.x - Deep learning framework for U-Net detector
- segmentation_models_pytorch - Pre-trained encoder/decoder for semantic segmentation
- Rasterio - Sentinel-2 COG reading, band resampling, feature rasterization
- xarray - Multi-dimensional array handling for NetCDF (CMEMS/ERA5)
- NumPy - Array operations
- Scikit-learn - Optional: classical baselines (Random Forest fallback per risk mitigation §16)

**Testing (Planned, not configured yet):**
- pytest - Unit testing
- pytest-cov - Coverage reporting

**Frontend (Planned, not yet scaffolded):**
- React + Vite - Dashboard UI
- Mapbox GL JS - Interactive map base layer
- deck.gl - Particle animation and heatmap visualization
- Recharts - Confidence-decay chart
- togpx + jsPDF - GPX and PDF export

## Key Dependencies

**Critical (Currently Installed):**
- **FastAPI 0.110.0** - Core REST API server; enables `/detect`, `/forecast`, `/mission` endpoints with auto-generated OpenAPI schema
- **Uvicorn [standard] 0.29.0** - ASGI server required to run FastAPI; includes `uvicorn.run()` for live reload dev mode
- **Pydantic 2.6.4** - Runtime type validation; enforces request/response schemas
- **GeoPandas 0.14.3** - Spatial vector operations; handles shapefiles in `MARIDA/shapefiles/`; requires GDAL/GEOS/PROJ compilation (Windows fallback: conda-forge)
- **Shapely 2.0.3** - Geometric primitives (Polygon, Point, LineString); required by GeoPandas; C-compiled for performance

**Infrastructure (Planned per PRD):**
- **Rasterio** - Cloud-optimized GeoTIFF (COG) reading; Sentinel-2 band stacking (B2/B3/B4/B6/B8/B11 at 10m)
- **xarray** - NetCDF I/O for CMEMS currents (u/v) and ERA5 winds (10m components)
- **PyTorch 2.x + segmentation_models_pytorch** - U-Net encoder/decoder with pretrained ResNet-18 backbone
- **Scikit-image** - Polygon rasterization, morphological ops (planned for feature post-processing)

## Configuration

**Environment:**
- Configured via FastAPI startup: CORS middleware with `allow_origins=["*"]` for local dev (set in `backend/main.py` line 15–19)
- No `.env` file currently in repo (listed in `.gitignore` line 5); environment variables would store:
  - `DATABASE_URL` (if persistence added)
  - `SENTINEL_HUB_TOKEN` (future: if live S2 ingestion enabled)
  - `COPERNICUS_USER` / `COPERNICUS_PASS` (future: if Copernicus Data Space auth needed)
  - `CMEMS_USER` / `CMEMS_PASS` (future: if live CMEMS API needed)

**Build:**
- No build config files detected (no `pyproject.toml`, `setup.py`, `Makefile`)
- Execution: `uvicorn main:app --reload` from `backend/` directory

**Package Requirements:**
- File: `backend/requirements.txt` - Minimal (9 lines currently)
- Must be extended with ML dependencies (PyTorch, segmentation_models_pytorch, rasterio, xarray) before training phase (PRD §13, H4–H16)

## Platform Requirements

**Development:**
- Python 3.10, 3.11, or 3.12 (Windows/Mac/Linux)
- pip + venv (or conda for Windows geospatial issues)
- GDAL/GEOS/PROJ: Pre-compiled wheels on Linux/Mac; Windows must use conda or OSGeo4W
- Optional: GPU (CUDA 12.1+ for PyTorch) for training speedup; CPU-only fallback supported per PRD §16 risk mitigation

**Production (Future):**
- Single-box Docker Compose (localhost demo per PRD §8.6 — no cloud deployment planned for hackathon)
- Requires: Docker + docker-compose
- No `Dockerfile` or `docker-compose.yml` currently committed

---

*Stack analysis: 2026-04-17*
