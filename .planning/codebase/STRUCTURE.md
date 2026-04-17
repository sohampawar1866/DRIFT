# Codebase Structure

**Analysis Date:** 2026-04-17

## Directory Layout

```
DRIFT/
├── .git/                         # Git repository metadata
├── .gitignore                    # Excludes venv, *.pyc, data/, *.geojson, *.shp, *.gpkg
├── .planning/
│   └── codebase/                 # GSD documentation (ARCHITECTURE.md, STRUCTURE.md, etc.)
├── .claude/                      # Claude IDE settings
├── PRD.md                         # Full product requirements document (§14 specifies architecture)
├── PPT_CONTENT.md                # Presentation content for demo pitch
├── problem_statement.pdf         # Original hackathon problem statement
│
├── backend/                       # Python FastAPI backend
│   ├── main.py                   # FastAPI app initialization, CORS config, uvicorn entry
│   ├── requirements.txt          # pip dependencies (fastapi, uvicorn, pydantic, geopandas)
│   ├── README.md                 # Setup guide (Python 3.10/3.11/3.12 requirement, venv instructions)
│   │
│   ├── api/
│   │   └── routes.py             # APIRouter with /detect, /forecast, /mission endpoints
│   │
│   └── services/
│       └── mock_data.py          # Synthetic GeoJSON generators (no real data yet)
│
│       *(To build per PRD §14)*
│       ├── ml/
│       │   ├── model.py          # U-Net w/ SE attention bottleneck (dual-head: class + fraction)
│       │   ├── features.py       # FDI, NDVI, PI computation (reusable feature engineering)
│       │   ├── dataset.py        # MARIDA PyTorch DataLoader w/ biofouling augmentation
│       │   ├── train.py          # Training loop (~150 LOC), 1.5h on T4/3090
│       │   └── inference.py      # Tile → GeoJSON pipeline (model inference + post-processing)
│       │
│       ├── physics/
│       │   ├── tracker.py        # Lagrangian Euler integrator (72h, 1hr steps, windage α=0.02)
│       │   └── env_data.py       # CMEMS/ERA5 NetCDF interpolation
│       │
│       └── mission/
│           ├── planner.py        # Greedy TSP solver over hotspots (density × accessibility × convergence)
│           └── export.py         # GPX + PDF briefing export
│
├── MARIDA/                        # MARIDA dataset (Sentinel-2 labeled plastic patches)
│   ├── patches/                   # 63 scene directories
│   │   ├── S2_1-12-19_48MYU/     # Scene: Sentinel-2 date + tile ID
│   │   │   ├── S2_1-12-19_48MYU_0.tif      # 6 bands: B2,B3,B4,B6,B8,B11 (10m)
│   │   │   ├── S2_1-12-19_48MYU_0_cl.tif   # Class label (0=non-plastic, 1=plastic)
│   │   │   ├── S2_1-12-19_48MYU_0_conf.tif # Confidence map (0-1 float)
│   │   │   ├── S2_1-12-19_48MYU_1.tif
│   │   │   ├── S2_1-12-19_48MYU_1_cl.tif
│   │   │   ├── S2_1-12-19_48MYU_1_conf.tif
│   │   │   ├── ... (multiple 256×256 patches per scene)
│   │   │   └── (repeat for 62 other scenes)
│   │   │
│   │   ├── S2_11-1-19_19QDA/
│   │   ├── S2_11-6-18_16PCC/
│   │   ├── ... (63 total scene directories)
│   │
│   ├── shapefiles/                # 63 corresponding vector boundaries (*.shp, *.shx, *.dbf, *.prj)
│   │   ├── S2_1-12-19_48MYU.shp
│   │   ├── ... (61 other shapefiles)
│   │
│   ├── splits/                    # Train/val/test split indices
│   │   ├── train_X.txt           # List of training scene IDs
│   │   ├── val_X.txt             # List of validation scene IDs
│   │   └── test_X.txt            # List of test scene IDs
│   │
│   └── labels_mapping.txt         # Class labels (pixel value → meaning)
│
└── data/                          # (Gitignored; to be populated during execution)
    ├── staged/                    # Pre-downloaded Sentinel-2 L2A tiles (4 demo AOIs)
    │   ├── gulf_of_mannar.tif
    │   ├── bay_of_bengal.tif
    │   ├── mumbai_offshore.tif
    │   └── arabian_sea_gyre.tif
    │
    ├── env/                       # CMEMS currents + ERA5 winds (NetCDF slices, 7-day)
    │   ├── cmems_currents_2026-04-17.nc
    │   └── era5_winds_2026-04-17.nc
    │
    ├── aois/                      # AOI bounding box definitions
    │   └── demo_aois.json         # 4 AOIs with lat/lon bounds, metadata
    │
    └── results/                   # Model outputs (generated during demo)
        ├── detections/
        ├── forecasts/
        └── missions/
```

## Directory Purposes

**DRIFT/ (Root):**
- Purpose: Project root; orchestrates backend, dataset, documentation
- Contains: PRD, problem statement, pitch content, backend code, MARIDA dataset
- Key files: `PRD.md` (§14 defines architecture), `backend/main.py` (entry point)

**backend/:**
- Purpose: All Python API and ML code
- Contains: FastAPI app, routes, services, (future) ML pipeline, physics engine, mission planner
- Key files: `main.py` (start here), `requirements.txt` (dependencies)

**backend/api/:**
- Purpose: HTTP route handlers
- Contains: APIRouter definition, endpoint docstrings
- Key files: `routes.py` (3 mock endpoints: /detect, /forecast, /mission)

**backend/services/:**
- Purpose: Business logic layer (currently: mock data generators)
- Contains: Functions that return data structures
- Key files: `mock_data.py` (random GeoJSON generators)

**MARIDA/:**
- Purpose: Training dataset for plastic detection model
- Contains: 63 labeled Sentinel-2 scenes with pixel-level ground truth
- Key files:
  - `patches/`: Raster imagery (TIF format, 3 variants per patch: raw bands, class label, confidence)
  - `shapefiles/`: Vector scene boundaries
  - `splits/`: Train (majority), val, test indices
  - `labels_mapping.txt`: Class value definitions

**data/ (Gitignored):**
- Purpose: Runtime data (staged satellite tiles, environment NetCDFs, results)
- Contains: Pre-downloaded S2, currents/winds, AOI definitions, model outputs
- Generated: During execution phase (not committed to git)

## Key File Locations

**Entry Points:**
- `backend/main.py`: FastAPI app start (run: `uvicorn main:app --reload`)
- (Intended) `backend/ml/train.py`: Model training script
- (Intended) `backend/ml/inference.py`: Single-tile inference pipeline

**Configuration:**
- `backend/requirements.txt`: Python dependencies (pip install -r)
- `backend/README.md`: Environment setup (Python version, venv, Conda fallback)
- (Intended) `data/aois/demo_aois.json`: AOI definitions (lat/lon bounds, names)

**Core Logic:**
- `backend/api/routes.py`: HTTP endpoint definitions (GET /detect, /forecast, /mission)
- `backend/services/mock_data.py`: Mock response generators (TEMPORARY; replaced by ml/inference.py)
- (Intended) `backend/ml/model.py`: U-Net architecture definition
- (Intended) `backend/ml/features.py`: FDI/NDVI/PI feature engineering (source of truth)
- (Intended) `backend/physics/tracker.py`: Lagrangian particle integrator

**Testing:**
- Not yet present; will add `backend/tests/` with pytest fixtures

**Data:**
- `MARIDA/patches/`: Training data (63 scenes, ~1300 labeled patches)
- `MARIDA/splits/`: Data split indices (train/val/test)
- (Intended) `data/staged/*.tif`: Pre-downloaded demo tiles
- (Intended) `data/env/*.nc`: CMEMS currents, ERA5 winds

## Naming Conventions

**Python Files:**
- snake_case: `mock_data.py`, `model.py`, `tracker.py`, `env_data.py`
- Suffixes indicate purpose: `_dataset.py`, `_inference.py`, `_test.py`

**Python Functions/Classes:**
- snake_case for functions: `get_mock_detection_geojson()`, `interp_currents()`
- PascalCase for classes: `UNetSegmentation`, `LagrangianTracker`, `MissionPlanner`

**Python Variables:**
- snake_case: `aoi_id`, `forecast_hours`, `base_lon`, `drifted_coords`

**Raster Files (MARIDA Patches):**
- Pattern: `S2_<date>_<tile>_<N>.tif`
  - `<date>`: DD-MM-YY (e.g., 1-12-19 = December 1, 2019)
  - `<tile>`: Sentinel-2 MGRS grid ID (e.g., 48MYU)
  - `<N>`: Patch index within scene (0, 1, 2, ...)
  - Suffix: `_cl` = class label, `_conf` = confidence map
- Example: `S2_1-12-19_48MYU_0.tif`, `S2_1-12-19_48MYU_0_cl.tif`

**Vector Files (Shapefiles):**
- Pattern: `S2_<date>_<tile>.shp` (+ .shx, .dbf, .prj companions)
- Example: `S2_1-12-19_48MYU.shp`

**GeoJSON Files (API Responses):**
- snake_case: `detections.geojson`, `forecast_frames.geojson`, `mission_route.geojson`
- Gitignored (*.geojson rule in .gitignore)

**Feature Collection Property Keys:**
- snake_case: `confidence`, `area_sq_meters`, `age_days`, `forecast_hour`, `fraction_plastic`

**Directories:**
- snake_case: `backend`, `services`, `patches`, `shapefiles`, `splits`, `staged`, `aois`
- Special: MARIDA (dataset name, uppercase as published)

## Where to Add New Code

**New ML Model Component (e.g., better U-Net variant):**
- Primary code: `backend/ml/model.py` (architecture definition)
- Dataset handling: `backend/ml/dataset.py` (extend DataLoader if needed)
- Tests: `backend/tests/test_model.py`
- Entry point: Import in `backend/ml/train.py` and `backend/ml/inference.py`

**New Physics Feature (e.g., add Stokes drift term):**
- Primary code: `backend/physics/tracker.py` (extend `LagrangianTracker` class)
- Environment data: `backend/physics/env_data.py` (add wave-height interpolation)
- Tests: `backend/tests/test_tracker.py`
- Entry point: API call via `backend/api/routes.py` → `/forecast` endpoint

**New API Endpoint (e.g., /api/v1/band-comparison):**
- Route definition: `backend/api/routes.py` (add route handler)
- Logic: New service module or extend `backend/ml/inference.py`
- Tests: `backend/tests/test_routes.py`
- Entry point: Direct HTTP GET/POST to `/api/v1/band-comparison`

**New Utility Function (reusable across modules):**
- Shared helpers: `backend/utils/` (create if doesn't exist)
- Example: Coordinate transformation, file I/O, logging setup
- Import from: Any module via `from backend.utils.xxx import yyy`

**New Frontend Component (React, not in Python scope but critical integration):**
- Location (not yet created): `frontend/src/components/` (e.g., `TimeSlider.tsx`)
- API integration: Via `frontend/src/api.ts` (typed client calling backend endpoints)
- Depends on: Backend JSON schema (GeoJSON structure defined in ARCHITECTURE.md)

## Special Directories

**MARIDA/:**
- Purpose: Labeled training dataset from Kikaki et al. 2022
- Generated: No (pre-published open dataset)
- Committed: Yes, included in repo for reproducibility
- Size: ~63 MB for patches (compressed TIFFs)
- Structure: Organized by S2 scenes; use `splits/` to create train/val/test

**data/ (Gitignored):**
- Purpose: Runtime data (too large or sensitive to commit)
- Generated: Yes (during execution: S2 tiles downloaded/staged, model outputs created)
- Committed: No (rule: `data/` in .gitignore)
- Expected subdirs:
  - `staged/`: Pre-downloaded Sentinel-2 L2A tiles (4 demo AOIs, ~2 GB)
  - `env/`: CMEMS/ERA5 NetCDF slices (7-day window, ~500 MB)
  - `aois/`: JSON metadata for demo areas
  - `results/`: Model outputs (detections, forecasts, missions)

**.planning/codebase/ (GSD Generated):**
- Purpose: Architecture documentation for future GSD commands
- Generated: Yes (by `/gsd:map-codebase`)
- Committed: Yes (documents are small, aid navigation)
- Contains: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md (etc., as requested)

**.git/ & .gitignore:**
- Purpose: Version control metadata and exclusion rules
- Committed: Yes (.git/ is internal, .gitignore defines rules)
- Key exclusions: venv/, __pycache__/, data/, *.pyc, *.geojson, *.shp, *.gpkg

---

*Structure analysis: 2026-04-17*
