# External Integrations

**Analysis Date:** 2026-04-17

## APIs & External Services

**Satellite Imagery (Planned):**
- **Sentinel-2 L2A** (Copernicus Open Access Hub / Copernicus Data Space Ecosystem)
  - What it's used for: Pre-processed multispectral imagery (10 bands at 10–60m resolution); primary data source for plastic detection
  - SDK/Client: Rasterio (COG reading), sentinelsat or Copernicus Data Space API client (to be added)
  - Auth: Copernicus Data Space Ecosystem credentials (username/password or API token)
  - Current implementation: Pre-staged tiles only (4 demo AOIs downloaded in advance, served locally per PRD §4 "simplify")
  - Files: Will live in `data/staged/*.tif` once fetched

**Ocean State Data (Planned):**
- **CMEMS (Copernicus Marine Environment Monitoring Service) — Global Ocean Physics**
  - What it's used for: Surface currents (u/v components, 0.083° grid) for Lagrangian trajectory modeling
  - SDK/Client: xarray + netCDF4 (read pre-downloaded NetCDF files)
  - Auth: CMEMS credentials (to be stored as env vars if live API; currently skipped per PRD §4)
  - Current implementation: Pre-downloaded 7-day NetCDF slice for demo window (no live API calls)
  - Files: Will live in `data/env/*.nc`

- **ERA5 (ECMWF Reanalysis)** — 10-meter Wind Components
  - What it's used for: Surface wind field (u/v, 0.25° grid) for drift windage term (α=0.02)
  - SDK/Client: xarray + netCDF4 (CDS API client optional, but not used in MVP per PRD scope)
  - Auth: Copernicus Climate Data Store API key (stored as env var if live; skipped for demo)
  - Current implementation: Pre-downloaded NetCDF for demo window
  - Files: Will live in `data/env/*.nc`

**Training Data (Current):**
- **MARIDA Dataset (Marine Debris Archive) — Kikaki et al. 2022**
  - What it's used for: 1,381 labeled Sentinel-2 patches (10 × 10 tiles) in 15 debris classes + water/cloud
  - Location: `MARIDA/patches/`, `MARIDA/shapefiles/`, `MARIDA/splits/`
  - Files: Train/val/test splits in `MARIDA/splits/train_X.txt`, `MARIDA/splits/val_X.txt`, `MARIDA/splits/test_X.txt`
  - Auth: None (open-source dataset; downloaded via kaggle CLI or direct link)

- **FloatingObjects Dataset (Mifdal et al. 2021)** — Planned supplement
  - What it's used for: Additional labeled floating debris examples (not yet integrated)
  - Auth: Kaggle (kaggle CLI credentials in `~/.kaggle/kaggle.json`)

## Data Storage

**Databases:**
- None currently configured
- Planned: Could add PostgreSQL/PostGIS if persistence needed (future work; out of scope for hackathon per PRD §12)

**File Storage:**
- Local filesystem only
  - `MARIDA/` — Training dataset (1.4 GB +)
  - `data/staged/` — Pre-staged Sentinel-2 tiles (COG format, ~1–2 GB per tile)
  - `data/env/` — Pre-downloaded CMEMS + ERA5 NetCDFs (~500 MB total)
  - `backend/` — FastAPI skeleton + services

**Caching:**
- None configured
- Planned: Optional in-memory caching for model weights + interpolated env data (future optimization)

## Authentication & Identity

**Auth Provider:**
- Custom authentication not yet implemented
- CORS middleware allows all origins (`allow_origins=["*"]`) for local dev (set in `backend/main.py`)
- Planned auth (future, out of MVP scope per PRD §12):
  - Copernicus Data Space OAuth/API token for live S2 ingestion
  - CMEMS credentials for live current API
  - Copernicus Climate Data Store API key for live ERA5 winds

**External Service Credentials (To Be Added):**
- Environment variables (to be defined in `.env` or deployment config):
  - `COPERNICUS_USER` / `COPERNICUS_PASS` — Copernicus Data Space Ecosystem (Sentinel-2)
  - `CMEMS_USER` / `CMEMS_PASS` — CMEMS marine.copernicus.eu API
  - `CDS_API_KEY` — Copernicus Climate Data Store (ERA5 winds)
  - `KAGGLE_USERNAME` / `KAGGLE_KEY` — Kaggle API (MARIDA + FloatingObjects dataset download)

## Monitoring & Observability

**Error Tracking:**
- None configured (not applicable to hackathon 48-hour scope)

**Logs:**
- FastAPI/Uvicorn stdout logging (standard Python logging)
- Planned: Request/response logging in `/api/v1/detect`, `/api/v1/forecast`, `/api/v1/mission` endpoints (basic now; enhanced in production)

## CI/CD & Deployment

**Hosting:**
- Localhost development only (demo laptop, no cloud per PRD §8.6 and §12)
- Future: Single-box Docker Compose (not yet implemented)

**CI Pipeline:**
- None (git repo exists but no GitHub Actions, Jenkins, etc.)
- Pre-commit hooks: Not configured

## Environment Configuration

**Required env vars (planned, not yet implemented):**
```
COPERNICUS_USER=<data-space-username>
COPERNICUS_PASS=<data-space-password>
CMEMS_USER=<marine.copernicus.eu-username>
CMEMS_PASS=<marine.copernicus.eu-password>
CDS_API_KEY=<copernicus-climate-datastore-key>
KAGGLE_USERNAME=<kaggle-api-username>
KAGGLE_KEY=<kaggle-api-key>
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
```

**Secrets location:**
- Current: None (.env listed in `.gitignore` line 5 but not created)
- Planned: `.env` file (local) or environment variables (deployment)
- Never commit secrets; use Copernicus/CMEMS/CDS/Kaggle official credential storage

## Webhooks & Callbacks

**Incoming:**
- None (API is query-driven, no webhook listeners)

**Outgoing:**
- None (no downstream service integrations in MVP per PRD scope)

## Satellite Imagery Access Workflow (Per PRD §8.5)

**Current (Hackathon MVP):**
1. Pre-download 4 Sentinel-2 L2A tiles (Gulf of Mannar, Bay of Bengal, Mumbai, Arabian Sea) as COG
2. Store in `data/staged/*.tif`
3. Rasterio reads bands at request time; no live API calls

**Future (if needed):**
1. sentinelsat or Copernicus Data Space client queries available tiles
2. Auth with `COPERNICUS_USER`/`COPERNICUS_PASS`
3. Download L2A product; Rasterio processes COG bands
4. Cache to disk to reduce repeated fetches

## Environmental Data Ingestion (Per PRD §4 & §8.5)

**Current (Hackathon MVP):**
1. Pre-download 7-day CMEMS + ERA5 NetCDFs for demo window
2. Store in `data/env/*.nc`
3. xarray reads and interpolates at particle positions during trajectory forecast

**Future (if time permits):**
1. CMEMS API + CDS API client fetch latest slices on-demand
2. Auth with `CMEMS_USER`/`CMEMS_PASS` and `CDS_API_KEY`
3. Cache interpolated fields in memory for 1-hour windows
4. Fall back to pre-downloaded data if API unavailable

## Data Flow Summary

```
┌─────────────────────────┐
│ Sentinel-2 COG Tiles    │  (pre-staged in data/staged/)
│ (B2,B3,B4,B6,B8,B11)    │
└────────┬────────────────┘
         │ Rasterio reads
         ▼
┌─────────────────────────┐
│ Feature Stack (9ch)     │  (compute FDI, NDVI, PI in memory)
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ FastAPI /detect         │  → FeatureCollection GeoJSON
│ (U-Net inference)       │  (plastic patches + confidence)
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ CMEMS/ERA5 NetCDFs      │  (pre-staged in data/env/)
│ (currents + winds)      │  xarray interpolates at particle x,y,t
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ FastAPI /forecast       │  → {frames: [t0, t+24h, t+48h, t+72h]}
│ (Euler integrator)      │  (particle positions + density heatmap)
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│ FastAPI /mission        │  → LineString waypoints (greedy TSP)
│ (mission planner)       │  (cleanup route + GeoJSON + GPX export)
└─────────────────────────┘
```

---

*Integration audit: 2026-04-17*
