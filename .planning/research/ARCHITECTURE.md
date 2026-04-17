# Architecture Research

**Domain:** Python multi-module geospatial ML+physics+mission pipeline (satellite → detect → forecast → plan)
**Researched:** 2026-04-17
**Confidence:** HIGH for data-contract and module-boundary patterns (Context7 + official docs); MEDIUM for the Phase 1 weight-loader path (marccoru hosting has shifted to Google Drive — verified); MEDIUM for checkpoint transfer Kaggle → laptop (multiple viable paths).

---

## 0. The One Question This Document Answers

> *How do we wire three independently-testable Python modules (`backend/ml/`, `backend/physics/`, `backend/mission/`) so that Phase 1 ships with dummy weights, Phase 3 swaps in real weights without any downstream touching, and the whole chain executes `run_inference(tile) → forecast_drift(detections) → plan_mission(forecast)` in under 15 seconds on a judging laptop?*

The answer has five pillars: **frozen GeoJSON schema**, **unidirectional imports**, **YAML + pydantic-settings config**, **kagglehub for weight handoff**, and **pytest with synthetic fixtures** — each justified below.

---

## 1. Standard Architecture

### 1.1 System Overview (components, boundaries, direction)

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         backend/core/  (shared kernel)                      │
│  ┌────────────────────┐   ┌──────────────────┐   ┌──────────────────────┐ │
│  │ schemas.py         │   │ config.py        │   │ logging.py           │ │
│  │ (pydantic models:  │   │ (pydantic-       │   │ (structured logger,  │ │
│  │  DetectionProps,   │   │  settings +      │   │  perf timers)        │ │
│  │  Feature, FC;      │   │  config.yaml)    │   │                      │ │
│  │  FROZEN contract)  │   │                  │   │                      │ │
│  └────────┬───────────┘   └────────┬─────────┘   └──────────┬───────────┘ │
└───────────┼────────────────────────┼────────────────────────┼─────────────┘
            │                        │                        │
            │  (import-only, never reverse)                   │
            ▼                        ▼                        ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌──────────────────────┐
│  backend/ml/        │   │  backend/physics/   │   │  backend/mission/    │
│  ─────────────      │   │  ───────────────    │   │  ──────────────      │
│  features.py        │   │  env_data.py        │   │  planner.py          │
│    └ FDI/NDVI/PI    │   │    └ CMEMS+ERA5     │   │    └ greedy TSP      │
│  dataset.py         │   │      xarray interp  │   │  scoring.py          │
│    └ MARIDA loader  │   │  tracker.py         │   │    └ priority score  │
│  model.py           │   │    └ Euler Lagr.    │   │  export.py           │
│    └ UNet++ dual    │   │      72h, 20 parts  │   │    └ GPX/GeoJSON/PDF │
│  weights.py         │   │                     │   │                      │
│    └ loader:        │   │  Entry:             │   │  Entry:              │
│      Phase1 dummy → │   │    forecast_drift(  │   │    plan_mission(     │
│      Phase3 real    │   │      FeatureColl    │   │      forecast_obj    │
│  inference.py       │   │    ) -> Forecast    │   │      ) -> Mission    │
│                     │   │                     │   │                      │
│  Entry:             │   │                     │   │                      │
│    run_inference(   │   │                     │   │                      │
│      tile_path      │   │                     │   │                      │
│    ) -> FeatureColl │   │                     │   │                      │
└─────────┬───────────┘   └──────────┬──────────┘   └──────────┬───────────┘
          │                          │                         │
          │  FeatureCollection       │  ForecastEnvelope       │  MissionPlan
          │  (frozen schema)         │  (detections+frames)    │  (waypoints+route)
          └──────────────────────────┴─────────────────────────┘
                                     │
                                     ▼
                          ┌─────────────────────────┐
                          │  tests/  (pytest)       │
                          │  synthetic fixtures     │
                          │  + fakes + goldens      │
                          └─────────────────────────┘
                                     │
                         (next milestone, NOT this one)
                                     ▼
                          ┌─────────────────────────┐
                          │  backend/api/routes.py  │
                          │  (FastAPI — untouched)  │
                          └─────────────────────────┘
```

**Import direction is strict and unidirectional:**
```
ml/, physics/, mission/  ──import──►  core/   (ALLOWED)
core/                    ──import──►  ml/     (FORBIDDEN)
ml/                      ──import──►  physics/ (FORBIDDEN)
physics/                 ──import──►  mission/ (FORBIDDEN)
```

Each pipeline module depends **only** on `core/` and its own internals. They communicate **only** via the frozen pydantic types in `core/schemas.py`. This is the single discipline that keeps the three modules from drifting.

### 1.2 Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `core/schemas.py` | FROZEN contracts: `DetectionProperties`, `DetectionFeature`, `DetectionFeatureCollection`, `ForecastFrame`, `ForecastEnvelope`, `MissionWaypoint`, `MissionPlan` | `geojson-pydantic` + custom `BaseModel` properties; `model_config = ConfigDict(frozen=True, extra="forbid")` |
| `core/config.py` | Typed settings; merges `config.yaml` defaults + env overrides | `pydantic-settings` with `YamlConfigSettingsSource` |
| `core/logging.py` | Structured logs, phase timing, IoU/latency metrics | stdlib `logging` + JSON formatter |
| `ml/features.py` | FDI (Biermann 2020), NDVI, PI as pure numpy functions on `(bands, H, W)` arrays | Single source of truth; also called during **training** and **inference** (avoids training-serving skew) |
| `ml/dataset.py` | MARIDA `Dataset` + biofouling NIR augmentation | `torch.utils.data.Dataset`; reads `splits/*.txt` + per-patch triplet `{*.tif, *_cl.tif, *_conf.tif}` |
| `ml/model.py` | UNet++ (resnet18 encoder) + SE attention block + dual head | `segmentation_models_pytorch.UnetPlusPlus` wrapped; two heads: mask logits + fraction regression |
| `ml/weights.py` | Single function `load_weights(config) -> nn.Module` with three branches: "dummy", "marccoru_baseline", "our_real" | `kagglehub.model_download()` + `torch.hub.load()` + local `.pt` fallback |
| `ml/inference.py` | **Public entry:** `run_inference(tile_path: Path, cfg: Settings) -> DetectionFeatureCollection` | Orchestrates: read tile (rasterio) → `features.compute()` → model.forward → threshold → polygonize (`rasterio.features.shapes`) → attach props → return |
| `physics/env_data.py` | Load + interpolate CMEMS currents, ERA5 winds | `xarray.open_dataset`, bilinear `interp(lon=, lat=, time=)` |
| `physics/tracker.py` | **Public entry:** `forecast_drift(det_fc: DetectionFeatureCollection, cfg) -> ForecastEnvelope` | Euler loop, 20 particles/det, α=0.02, 72 h; emits per-hour positions + KDE density polygons at +24/+48/+72 h |
| `mission/scoring.py` | `priority(det, fc, forecast_env) -> float` — density × accessibility × convergence | Pure numpy; no side effects |
| `mission/planner.py` | **Public entry:** `plan_mission(forecast_env, vessel_range_km, hours, origin) -> MissionPlan` | Greedy TSP (nearest-neighbor) over top-K scored detections, respecting range budget |
| `mission/export.py` | GPX / GeoJSON / PDF from `MissionPlan` | `gpxpy` + `json` + `reportlab` |

### 1.3 The Three Public Function Signatures (lock before Phase 1 ends)

```python
# backend/ml/inference.py
def run_inference(
    tile_path: pathlib.Path,
    cfg: Settings,
) -> DetectionFeatureCollection: ...

# backend/physics/tracker.py
def forecast_drift(
    detections: DetectionFeatureCollection,
    cfg: Settings,
    env_override: EnvironmentData | None = None,
) -> ForecastEnvelope: ...

# backend/mission/planner.py
def plan_mission(
    forecast: ForecastEnvelope,
    vessel_range_km: float,
    hours: float,
    origin_lonlat: tuple[float, float],
    cfg: Settings,
) -> MissionPlan: ...
```

**These three signatures are the contract.** Everything else in `ml/`, `physics/`, `mission/` is an implementation detail. They are the seam the future FastAPI milestone will wrap.

---

## 2. Recommended Project Structure

```
DRIFT/
├── backend/
│   ├── __init__.py
│   ├── main.py                     # FastAPI — UNTOUCHED this milestone
│   │
│   ├── core/                       # shared kernel (NEW)
│   │   ├── __init__.py
│   │   ├── schemas.py              # ★ FROZEN contracts (pydantic)
│   │   ├── config.py               # pydantic-settings loader
│   │   └── logging.py              # structured logger
│   │
│   ├── ml/                         # (NEW)
│   │   ├── __init__.py             # re-exports run_inference
│   │   ├── features.py             # FDI/NDVI/PI (shared train+serve)
│   │   ├── dataset.py              # MARIDA Dataset
│   │   ├── model.py                # UNet++ + SE + dual head
│   │   ├── weights.py              # dummy | marccoru | our_real loader
│   │   ├── inference.py            # ★ run_inference() entry point
│   │   └── cli.py                  # python -m backend.ml <tile> → stdout
│   │
│   ├── physics/                    # (NEW)
│   │   ├── __init__.py             # re-exports forecast_drift
│   │   ├── env_data.py             # CMEMS + ERA5 xarray loaders
│   │   ├── tracker.py              # ★ forecast_drift() entry point
│   │   └── cli.py                  # python -m backend.physics <det.json>
│   │
│   ├── mission/                    # (NEW)
│   │   ├── __init__.py             # re-exports plan_mission
│   │   ├── scoring.py              # priority scoring
│   │   ├── planner.py              # ★ plan_mission() entry point
│   │   ├── export.py               # GPX / GeoJSON / PDF
│   │   └── cli.py                  # python -m backend.mission <forecast.json>
│   │
│   ├── api/
│   │   └── routes.py               # UNTOUCHED this milestone
│   │
│   ├── services/
│   │   └── mock_data.py            # UNTOUCHED this milestone
│   │
│   ├── config.yaml                 # (NEW) defaults for Settings
│   ├── requirements.txt
│   └── README.md
│
├── tests/                          # (NEW, top-level so modules import cleanly)
│   ├── conftest.py                 # synthetic fixtures (fake tile, fake env)
│   ├── unit/
│   │   ├── test_features.py        # FDI value vs Biermann 2020 example
│   │   ├── test_schemas.py         # FeatureCollection round-trip
│   │   └── test_scoring.py         # priority score monotonic in density
│   ├── integration/
│   │   ├── test_tracker_synth.py   # 0.5 m/s east → 43.2 km/24h ±1%
│   │   └── test_planner_tsp.py     # greedy TSP on 5 known points
│   └── e2e/
│       └── test_chain.py           # MARIDA patch → FC → forecast → mission
│
├── scripts/
│   ├── train_kaggle.py             # single notebook-runnable training
│   ├── export_weights.py           # checkpoint → kagglehub model upload
│   └── fetch_demo_env.py           # CMEMS+ERA5 slice download
│
├── MARIDA/                         # existing dataset (unchanged)
├── data/                           # existing (gitignored)
│   ├── staged/                     # pre-downloaded S2 tiles
│   ├── env/                        # CMEMS+ERA5 NetCDFs
│   └── weights/                    # ★ local checkpoint cache
│       ├── .gitkeep
│       └── (downloaded at runtime — NOT committed)
│
├── kaggle.yml                      # existing
├── kernel-metadata.json            # existing
└── .planning/                      # existing GSD docs
```

### 2.1 Structure Rationale

- **`core/`** is the new dependency root. It is the only module every other module depends on. This prevents cycles and keeps schemas/config in exactly one place.
- **`ml/`, `physics/`, `mission/`** are siblings, never parents/children of each other. Their exchange currency is the pydantic types in `core/schemas.py`. A Phase-3 refactor to real weights touches `ml/weights.py` only; `physics/` and `mission/` are unaware.
- **Each pipeline module exposes one public entry** re-exported via `__init__.py` and mirrored by a thin `cli.py` that reads/writes GeoJSON on stdin/stdout. This is the "standalone-callable" requirement the milestone demands — each module can be dev-tested with a single `python -m backend.ml data/staged/gulf_of_mannar.tif > out.geojson`.
- **`tests/` is top-level** (not nested in `backend/`) so `from backend.ml.inference import run_inference` works without `sys.path` hacks. This matches modern pytest conventions and avoids the `src/` vs. `backend/` packaging ambiguity.
- **`data/weights/` is gitignored** — checkpoints never commit; they're downloaded from `kagglehub` on first use and cached.
- **`scripts/`** holds anything that is explicitly *not* part of the runtime pipeline (training, bulk fetching, weight export). Keeping them separate from `backend/` prevents accidental imports of training code in inference.

---

## 3. Architectural Patterns

### 3.1 Pattern 1: Frozen Pydantic Schemas at the Module Seam

**What:** Every module exchange (`ml → physics`, `physics → mission`) uses a pydantic `BaseModel` with `frozen=True, extra="forbid"`. Raw dicts and raw `GeoDataFrame`s never cross a module boundary.

**Why it wins for a 24–48 h build:**
- Schema drift is the #1 cause of inter-module bugs under time pressure; `extra="forbid"` fails loudly at the boundary, not silently at the sink.
- `geojson-pydantic` ([developmentseed/geojson-pydantic](https://github.com/developmentseed/geojson-pydantic)) already ships RFC-7946 compliant `Feature`, `FeatureCollection`, `Point`, `Polygon`, `LineString` types; compose them with a custom `Properties` model using Python generics: `Feature[Polygon, DetectionProperties]`.
- Instantiating is a one-liner; validation happens in the constructor.

**Minimal freeze (put in `core/schemas.py`):**
```python
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from geojson_pydantic import Feature, FeatureCollection, Polygon, LineString, Point

class DetectionProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")  # any drift fails loudly
    conf_raw: float = Field(ge=0.0, le=1.0)
    conf_adj: float = Field(ge=0.0, le=1.0)
    fraction_plastic: float = Field(ge=0.0, le=1.0)
    area_m2: float = Field(ge=0.0)
    age_days_est: int = Field(ge=0)
    cls: Literal["plastic"] = "plastic"   # renamed from `class` (reserved)

DetectionFeature = Feature[Polygon, DetectionProperties]
DetectionFeatureCollection = FeatureCollection[DetectionFeature]

class ForecastFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hour: int                              # 0..72
    particle_positions: list[tuple[float, float]]   # (lon, lat) pairs
    density_polygons: FeatureCollection[Feature[Polygon, dict]]  # KDE contours

class ForecastEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_detections: DetectionFeatureCollection   # echo input for provenance
    frames: list[ForecastFrame]            # length == horizon_hours + 1
    windage_alpha: float

class MissionWaypoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: int
    lon: float
    lat: float
    arrival_hour: float
    priority_score: float

class MissionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    waypoints: list[MissionWaypoint]
    route: Feature[LineString, dict]       # ordered LineString
    total_distance_km: float
    total_hours: float
    origin: tuple[float, float]
```

**Trade-offs:**
- (+) Every downstream consumer gets autocomplete + validation free.
- (+) JSON dump/load is `fc.model_dump_json()` / `DetectionFeatureCollection.model_validate_json(text)`. Round-trips through the CLI are trivial.
- (–) Adds `geojson-pydantic` (~0 MB, pure Python) and `pydantic>=2` (already present via FastAPI).
- (–) ~40 LOC of schema code. Cheapest insurance in the project.

**Rename `class` → `cls`:** PRD Appendix B writes `"class": "plastic"`, but `class` is a Python reserved word and will break pydantic. Alias it in the model if the demo JSON must read `class`:
```python
cls: Literal["plastic"] = Field(default="plastic", alias="class")
model_config = ConfigDict(populate_by_name=True, extra="forbid")
```

### 3.2 Pattern 2: Feature Engineering as a Pure Function (Training-Serving Parity)

**What:** `ml/features.py` exports pure numpy functions that take `(H, W, 11)` reflectance arrays and return `(H, W, K)` feature stacks. **The same function is called from `dataset.py` (training) and `inference.py` (serving).** Never duplicate.

**Why:** Training-serving skew is the classic ML pipeline bug. If training computes FDI one way and inference another, the model is silently degraded. Making `features.py` the single source of truth is cheap insurance.

**Example:**
```python
# backend/ml/features.py
import numpy as np

# Sentinel-2 band indices within MARIDA's 11-band stack (validated)
B6_IDX, B8_IDX, B11_IDX = 3, 4, 5    # pseudo — set to real indices for the stack
LAMBDA = {"B6": 740.0, "B8": 832.0, "B11": 1613.0}

def compute_fdi(bands: np.ndarray) -> np.ndarray:
    """Biermann 2020 FDI. Input: (H, W, 11). Output: (H, W)."""
    re2_prime = bands[..., B6_IDX] + (bands[..., B11_IDX] - bands[..., B6_IDX]) * (
        (LAMBDA["B8"] - LAMBDA["B6"]) / (LAMBDA["B11"] - LAMBDA["B6"])
    )
    return bands[..., B8_IDX] - re2_prime

def compute_ndvi(bands: np.ndarray) -> np.ndarray: ...
def compute_pi(bands: np.ndarray) -> np.ndarray: ...

def feature_stack(bands: np.ndarray) -> np.ndarray:
    """Return 14-channel stack: 11 bands + FDI + NDVI + PI."""
    return np.concatenate([
        bands,
        compute_fdi(bands)[..., None],
        compute_ndvi(bands)[..., None],
        compute_pi(bands)[..., None],
    ], axis=-1)
```

Dataset and inference both call `feature_stack(...)`. Phase 3 training uses the exact same function.

**Trade-off:** Forces a test on `compute_fdi` against a known Biermann 2020 pixel example. Do this in `tests/unit/test_features.py` — 10 minutes, catches 80% of future skew bugs.

### 3.3 Pattern 3: Strategy-Pattern Weight Loader (Phase 1 ↔ Phase 3 Seam)

**What:** `ml/weights.py` has a single function `load_weights(cfg) -> nn.Module`. It branches on `cfg.ml.weights_source ∈ {"dummy", "marccoru_baseline", "our_real"}`. Downstream (`inference.py`) never knows which branch ran.

```python
# backend/ml/weights.py
import torch
import torch.nn as nn
from pathlib import Path
from backend.core.config import Settings
from backend.ml.model import UNetPlusPlusDualHead

def load_weights(cfg: Settings) -> nn.Module:
    source = cfg.ml.weights_source
    if source == "dummy":
        # Phase 1: untrained net with correct I/O shape. Outputs random-ish
        # probabilities but yields *schema-valid* GeoJSON every time.
        return UNetPlusPlusDualHead(in_channels=14, num_classes=1)

    if source == "marccoru_baseline":
        # Phase 1.5 / Phase 2: pretrained single-head UNet++ via torch.hub.
        # NOTE: repo weights moved to Google Drive (Aug 2024). torch.hub.load
        # pulls *code* but user must manually place the .pt in the expected
        # cache dir — or use our copy vendored under data/weights/.
        return torch.hub.load("marccoru/marinedebrisdetector", "unetpp")

    if source == "our_real":
        # Phase 3: our trained weights from Kaggle. Downloaded via kagglehub
        # model_download on first call; cached under ~/.cache/kagglehub/.
        import kagglehub
        path = kagglehub.model_download(cfg.ml.kagglehub_handle)  # e.g. "manastiwari1410/drift-unetpp/pytorch/v1"
        model = UNetPlusPlusDualHead(in_channels=14, num_classes=1)
        state = torch.load(Path(path) / "model.pt", map_location="cpu")
        model.load_state_dict(state, strict=True)
        return model

    raise ValueError(f"Unknown weights_source: {source}")
```

**Why this is the *only* Phase-1 ↔ Phase-3 switch:** `run_inference` never mentions checkpoints. Flipping `cfg.ml.weights_source = "our_real"` in `config.yaml` is the full swap. `physics/` and `mission/` cannot tell the difference.

**Trade-offs:**
- (+) Swapping dummy → real is one YAML line or one env var override (`ML__WEIGHTS_SOURCE=our_real`).
- (+) `dummy` branch unblocks `physics/` and `mission/` from hour one; they don't wait for training.
- (–) You *must* write `UNetPlusPlusDualHead` in `ml/model.py` early so the dummy branch has a real class to instantiate. ~50 LOC.

### 3.4 Pattern 4: Config as Typed Settings (pydantic-settings + YAML)

**What:** One `config.yaml` at `backend/config.yaml`; one `Settings` class in `core/config.py`. Nested sub-models for `ml`, `physics`, `mission`. Env-var overrides for demo-day tweaks.

```python
# backend/core/config.py
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

class MLSettings(BaseModel):
    weights_source: str = "dummy"               # "dummy" | "marccoru_baseline" | "our_real"
    kagglehub_handle: str = "manastiwari1410/drift-unetpp/pytorch/v1"
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)
    biofouling_tau_days: float = 30.0
    patch_size: int = 256

class PhysicsSettings(BaseModel):
    windage_alpha: float = 0.02
    horizon_hours: int = 72
    dt_seconds: int = 3600
    particles_per_detection: int = 20
    cmems_path: Path = Path("data/env/cmems_currents.nc")
    era5_path: Path = Path("data/env/era5_winds.nc")

class MissionSettings(BaseModel):
    top_k: int = 10
    weight_density: float = 0.5
    weight_accessibility: float = 0.3
    weight_convergence: float = 0.2

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file=Path("backend/config.yaml"),
        env_nested_delimiter="__",              # e.g. ML__WEIGHTS_SOURCE
        extra="forbid",
    )
    ml: MLSettings = MLSettings()
    physics: PhysicsSettings = PhysicsSettings()
    mission: MissionSettings = MissionSettings()

    @classmethod
    def settings_customise_sources(cls, *args, **kwargs):
        return (YamlConfigSettingsSource(kwargs["settings_cls"]),)
```

**Why not just hardcode constants?**
- Hardcoded: OK for Phase 0 spike. Becomes "hunt-the-threshold" by hour 20 when a judge asks "what if α is 0.03?"
- YAML alone: no validation, typos pass silently (`windage_aplha: 0.02` — silent zero).
- `pydantic-settings`: 15 minutes to set up, then env-var overrides (`PHYSICS__WINDAGE_ALPHA=0.03 python -m backend.physics ...`) work for free. Essential for demo rehearsal.
- **Hydra:** overkill. Hydra shines for multi-experiment ML sweeps; our pipeline has one config. Hydra would add `.hydra/` dirs and working-directory reassignments that confuse demo scripts.

**Verdict for 24–48 h:** `pydantic-settings + YAML`, single file, 60 LOC. Skip Hydra.

### 3.5 Pattern 5: Standalone-Callable Modules via `python -m`

**What:** Each pipeline module ships a `cli.py` with an `if __name__ == "__main__"` guard registered as `python -m backend.ml`, `python -m backend.physics`, `python -m backend.mission`. Input/output is GeoJSON on file paths (or stdin/stdout).

```python
# backend/ml/cli.py
import argparse, sys
from pathlib import Path
from backend.core.config import Settings
from backend.ml.inference import run_inference

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tile", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    fc = run_inference(args.tile, Settings())
    text = fc.model_dump_json(indent=2)
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)

if __name__ == "__main__":
    main()
```

**Why:** The milestone explicitly says each module must be "standalone-callable." Shipping a `cli.py` also makes demo debugging trivial: `python -m backend.ml data/staged/mumbai_offshore.tif | head` proves the module works without any API layer.

---

## 4. Data Flow

### 4.1 Happy Path (the ≤15 s chain)

```
run_pipeline.py
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│ (0) Settings.model_validate(config.yaml)                         │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ (1) ml.run_inference(tile_path, cfg)                             │
│     rasterio.open → bands (H,W,11) → features.feature_stack →   │
│     (H,W,14) tensor → model.forward → (mask, frac) → threshold  │
│     → rasterio.features.shapes → polygons → DetectionProperties │
│     → DetectionFeatureCollection                                 │
└──────────────────────┬───────────────────────────────────────────┘
                       │  DetectionFeatureCollection
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ (2) physics.forecast_drift(detections, cfg)                      │
│     env_data.load(cmems, era5) → xarray.Dataset                 │
│     for each detection centroid, seed 20 particles              │
│     for hour in 0..72: Euler(u_c + α·u_w) → positions[hour]     │
│     KDE density at +24/+48/+72 h → polygons                      │
│     → ForecastEnvelope                                           │
└──────────────────────┬───────────────────────────────────────────┘
                       │  ForecastEnvelope
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ (3) mission.plan_mission(forecast, range, hours, origin, cfg)    │
│     scoring.priority(det, forecast) for each detection           │
│     top-K → greedy TSP from origin → waypoints                   │
│     Shapely LineString route                                     │
│     → MissionPlan                                                │
└──────────────────────┬───────────────────────────────────────────┘
                       │  MissionPlan
                       ▼
                (optional) mission.export → GPX / PDF / GeoJSON
```

**State management:** None. Every call is a pure function; no global state, no singletons, no caches inside the pipeline. The only "state" is `Settings` (configuration), which is immutable. This is what makes each module testable in isolation.

### 4.2 Raw dict vs. GeoDataFrame vs. Shapely — The Honest Answer

Three idiomatic ways to pass geospatial data between Python modules exist. The judging-winning choice is pydantic-typed GeoJSON + Shapely internally, never GeoPandas on the seam.

| Transport | When to use | Trade-offs |
|---|---|---|
| **Raw `dict` (GeoJSON)** | Cross-language boundaries (API, file). | No validation, silent drift, awkward field access (`d["properties"]["conf_raw"]`). **Bad choice** for Python-to-Python module seams. |
| **`pydantic` model wrapping GeoJSON** (recommended) | Python-to-Python module seams where schema correctness matters more than bulk ops. | Adds import (`geojson-pydantic`), adds ~40 LOC schema, but *eliminates* the schema-drift class of bugs. Serializable (`model_dump_json`), JSON-round-trippable, typed, IDE-autocompletable. |
| **`geopandas.GeoDataFrame`** | Bulk vector analytics (spatial join, groupby, CRS conversions). | Heavy import (~200 MB), CRS gotchas, `__geo_interface__` forces dict-reconstruction on every access ([shapely deepwiki](https://deepwiki.com/shapely/shapely/8.3-geojson-and-__geo_interface__)), and it encourages leaking pandas index/column semantics across module boundaries. **Use internally inside `physics/` or `ml/` if needed, but do not put a `GeoDataFrame` on a public function signature.** |
| **`shapely` geometries** | Pure geometric ops (intersection, buffer, convex hull). | Lightweight, no CRS (operate in projected meters), perfect for TSP distances and LineString construction. **Use inside `mission/` freely; convert to `Polygon`/`LineString` pydantic model at the boundary.** |

**Recommendation (HIGH confidence):** Contract layer = `geojson-pydantic` types. Implementation layer inside each module = Shapely (for geometry) + numpy / xarray / rasterio (for raster). `GeoDataFrame` allowed inside a single module only, never exported.

### 4.3 Key Data Flows

1. **Forward chain:** tile → `DetectionFeatureCollection` → `ForecastEnvelope` → `MissionPlan`. Each step reads the previous typed object.
2. **Config flow:** `config.yaml` → `Settings()` → passed explicitly to every entry point. No hidden globals.
3. **Weights flow (Phase 3):** Kaggle training → `model.pt` → `kagglehub.model_upload` → on laptop: `kagglehub.model_download` → `~/.cache/kagglehub/` → `load_weights` → instantiated model in memory.
4. **Env data flow:** `scripts/fetch_demo_env.py` → `data/env/*.nc` (~500 MB pre-clipped slice) → `env_data.load_currents`, `load_winds` → in-memory `xarray.Dataset` reused across detections.

---

## 5. Build Order — Phase-Mapped

The milestone scopes three phases: **Phase 1 = dummy inference**, **Phase 2 = physics + mission**, **Phase 3 = real training + polish**. The sequencing below front-loads the contract and de-risks the weight swap.

| Order | Task | Phase | Hours | Rationale |
|---:|---|---:|---:|---|
| 1 | Write `core/schemas.py` (FROZEN). Ship round-trip test `tests/unit/test_schemas.py`. | 1 | 1–2 | **Nothing else starts until this is done.** Schema is the seam. |
| 2 | Write `core/config.py` + `backend/config.yaml` with sane defaults. | 1 | 0.5 | Settings is passed everywhere; defer = refactor pain. |
| 3 | Write `ml/features.py` (FDI/NDVI/PI) + unit test vs. Biermann 2020 pixel. | 1 | 1 | Pure numpy; single source of truth for train+serve. |
| 4 | Write `ml/model.py` (UNet++ dual-head stub, 14→1+1 output) — even with random init. | 1 | 1 | Needed for dummy weights. |
| 5 | Write `ml/weights.py` with **only** the `"dummy"` branch working. | 1 | 0.5 | Unblocks the rest. |
| 6 | Write `ml/inference.py` and `ml/cli.py`. Run on one MARIDA patch; get schema-valid `DetectionFeatureCollection` out. | 1 | 2–3 | **Phase 1 exit gate.** Schema is now proven end-to-end on dummy weights. |
| 7 | Write `physics/env_data.py`. Unit test bilinear interp on synthetic constant field. | 2 | 1.5 | |
| 8 | Write `physics/tracker.py` + synthetic-field test (0.5 m/s east → 43.2 km / 24h ±1%). | 2 | 2–3 | **Physics validated before real environment data arrives.** |
| 9 | Wire `forecast_drift(DetectionFeatureCollection)` using synthetic detections (hand-crafted FC from test fixtures), then using dummy-model FC. | 2 | 1 | Proves `ml → physics` seam works. |
| 10 | Write `mission/scoring.py` + `mission/planner.py` + `mission/cli.py`. | 2 | 2 | Greedy NN-TSP is ~40 LOC; don't over-engineer. |
| 11 | Write `mission/export.py` (GPX + GeoJSON; PDF optional). | 2 | 1 | |
| 12 | Write `tests/e2e/test_chain.py` — **full chain on dummy weights**, assert timing <15 s. | 2 | 1 | **Phase 2 exit gate.** |
| 13 | Flip `ml/weights.py` `"marccoru_baseline"` branch on. Re-run chain. | 2→3 | 0.5 | First reality-check with pretrained net. |
| 14 | Run `scripts/train_kaggle.py` on Kaggle (GPU-enabled kernel). Hit IoU ≥ 0.45 on val. | 3 | 2–3 (clock time; 60–90 min training) | |
| 15 | `kagglehub.model_upload(...)` the trained `.pt`. | 3 | 0.2 | |
| 16 | On laptop: `kagglehub.model_download(...)` → flip `weights_source: our_real` in YAML. Re-run chain. | 3 | 0.3 | **The swap.** |
| 17 | E2E test re-runs; IoU + latency checked automatically. Polish demo. | 3 | 1+ | |

**Build-order insight (the sequencing refinement):** The user's proposed order is correct in spirit but has one subtle risk — *writing the dataset loader before the feature schema* is common and dangerous. Dataset output shape determines model output shape, which determines the GeoJSON polygon shape, which determines `DetectionProperties`. Work the *other* direction: **freeze `DetectionProperties` first, then build backward from there**. That's why steps 1–3 above are "schema, config, features" before any loader or model.

**Why Phase 1 uses dummy weights, not marccoru_baseline:** the baseline requires `torch.hub.load(...)` which requires `git` + Google Drive manual download (the marccoru repo owner [moved weights private](https://github.com/MarcCoru/marinedebrisdetector) due to hosting costs). A `dummy` branch is deterministic, works offline, and yields schema-valid outputs *immediately*, unblocking all of Phase 2. Marccoru baseline is step 13 — a 30-minute task once the chain is proven.

---

## 6. Checkpoint Strategy (Kaggle ↔ Laptop)

The milestone demands weights trained on Kaggle be usable on the judging laptop without code changes. Four options exist; one wins.

| Approach | Setup cost | Size limit | Offline demo? | Recommendation |
|---|---|---|---|---|
| **Git LFS** | High (installing LFS, repo bloat) | ~2 GB free tier | ✓ once cloned | ✗ Avoid — LFS quotas are frequently hit mid-hackathon, and every clone pulls the `.pt`. |
| **Hugging Face Hub** | Low | 50 MB auto-LFS, practically unlimited | ✓ once `huggingface-cli download` cached | ✓ Solid alt if already logged in. Needs `huggingface_hub` token. |
| **`torch.hub`** (custom repo with `hubconf.py`) | Medium (must host weights somewhere reachable) | Unlimited if you self-host | ✓ once cached | ✗ Overkill for one model; weights still need hosting. |
| **`kagglehub` model upload/download** | **Low** (already have Kaggle account; already logged in for training) | Generous (20 GB/dataset) | ✓ once `kagglehub.model_download` has cached to `~/.cache/kagglehub/` | **✓ RECOMMENDED.** Same credentials used for training; same CLI. |

**Recommended flow (verified via [kagglehub README](https://github.com/Kaggle/kagglehub)):**

```python
# On Kaggle (end of scripts/train_kaggle.py)
import kagglehub
kagglehub.model_upload(
    handle="manastiwari1410/drift-unetpp/pytorch/v1",
    local_model_dir="./checkpoint/",   # contains model.pt + config.json + README.md
    license_name="MIT",
)

# On laptop (first call inside ml/weights.py — happens automatically)
import kagglehub
local_path = kagglehub.model_download("manastiwari1410/drift-unetpp/pytorch/v1")
# → ~/.cache/kagglehub/models/manastiwari1410/drift-unetpp/pytorch/v1/1/
state = torch.load(Path(local_path) / "model.pt", map_location="cpu")
```

**Offline-demo safety:** Pre-run `kagglehub.model_download(...)` once on the judging laptop before the demo. The file is cached; network goes away, model still loads. Add a sanity check at startup:
```python
if not (Path.home() / ".cache/kagglehub").exists():
    raise RuntimeError("Run kagglehub.model_download pre-demo for offline safety.")
```

**Backup plan:** Also commit a ~5 MB compressed `.pt` under `data/weights/backup_v1.pt.gz` via Git (not LFS — under 100 MB GitHub limit at default). Fallback branch in `weights.py`:
```python
if source == "local_backup":
    state = torch.load("data/weights/backup_v1.pt", map_location="cpu")
    ...
```
Two ways to load the same weights. Paranoia is appropriate here.

---

## 7. Testing Strategy — Minimal Viable for 24–48 h

The temptation in a hackathon is to skip tests. Don't; the three tests below cost <90 minutes and prevent the three most-likely demo-killers.

### 7.1 The Minimum Three Tests (non-negotiable)

| Test | Location | What it catches | Time |
|---|---|---|---|
| **FDI formula test** | `tests/unit/test_features.py` | Training-serving skew on the feature most judges will quiz you about. Pin a known input → known Biermann 2020 output. | 15 min |
| **Synthetic-field tracker test** | `tests/integration/test_tracker_synth.py` | Physics regressions. Constant 0.5 m/s east field → particle at (0,0,t=0) ends up at (~0.386°, 0) after 24 h ± 1%, i.e., 43.2 km. | 20 min |
| **Schema round-trip test** | `tests/unit/test_schemas.py` | Contract drift between modules. `DetectionFeatureCollection.model_validate(fc.model_dump()) == fc` for every type. | 10 min |

### 7.2 Recommended Additions (if time allows)

| Test | Catches | Time |
|---|---|---|
| `tests/integration/test_inference_dummy.py` | Model → polygonize → schema path works on any tile without NaN. | 30 min |
| `tests/integration/test_planner_tsp.py` | Greedy TSP ordering given 5 known points matches a hand-computed ordering. | 20 min |
| `tests/e2e/test_chain.py` | **The money test.** Real MARIDA patch → `run_inference` → `forecast_drift` → `plan_mission` produces schema-valid outputs at each stage; full chain <15 s. | 30 min |

### 7.3 Testing Patterns

- **Synthetic fixtures over fake mocks.** For `physics/`, a 5-line xarray constant-velocity dataset in a pytest fixture beats a `Mock(return_value=...)` every time: the synthetic field *is* the physics; you test the real code path.
- **Schema tests as golden files.** Commit `tests/golden/minimal_fc.json`; assert `DetectionFeatureCollection.model_validate_json(file.read_text()).model_dump() == expected`.
- **No mocking inside pure functions.** `features.py`, `scoring.py`, `tracker.py` inner loop — none should ever see a `Mock`.
- **Skip tests you can't afford but not these three.** You will get asked "did you unit-test your FDI?" in Q&A. Say yes.

### 7.4 What NOT to test

- Don't write tests for `dataset.py` (MARIDA loader) — rely on a quick visual sanity check in the Kaggle notebook.
- Don't write tests for `export.py` (GPX/PDF) — open the output in Google Earth once. Sufficient.
- Don't write API tests — **this milestone excludes the API**; testing mocked endpoints is wasted time.

---

## 8. Scaling Considerations

The milestone is a single-laptop demo, but the architecture should survive later growth.

| Scale | Architecture Adjustments |
|---|---|
| **1 tile, 1 laptop (demo)** | Everything in-process. `run_inference` takes ~5 s on CPU, ~1 s on GPU. No queue, no cache. Current design. |
| **1–10 tiles/hour (pilot)** | Add Redis-backed `functools.lru_cache` on `env_data.load_*` (NetCDFs are 500 MB; don't reload). Wrap `run_inference` with a simple FIFO queue in the API layer. |
| **100+ tiles/hour (production)** | Split into services: inference worker (GPU), physics worker (CPU-bound), mission worker (CPU-bound). Redis queue. Shared schema package. **The pydantic schema trivially becomes the cross-service protocol.** |

### Scaling Priorities

1. **First bottleneck (inference latency):** GPU > CPU. If >2 s on laptop, reduce patch size 256→128 or batch tiles.
2. **Second bottleneck (env NetCDF I/O):** xarray's lazy loading is great, but repeated `interp()` calls on same fields thrash the cache. Pre-slice the NetCDF to AOI extent at download time (scripts/fetch_demo_env.py does this).
3. **Third bottleneck (TSP scale):** Greedy TSP is O(K²) over top-K; K=10 is instant. If K grows past 50, swap to OR-Tools.

---

## 9. Anti-Patterns

### 9.1 Anti-Pattern 1: Passing Raw GeoJSON Dicts Between Modules

**What people do:** `det_dict = run_inference(...); forecast = forecast_drift(det_dict)`. Feels "lightweight."
**Why it's wrong:** `det_dict["properties"]["conf_raw"]` fails silently if a typo renames it `confraw`. By the time the bug surfaces in `plan_mission`, you've burned 2 hours of debugging at hour 38.
**Do this instead:** Always pydantic-typed (`DetectionFeatureCollection`). Wrap once at the edge; strongly type through the middle.

### 9.2 Anti-Pattern 2: Scattered Hyperparameters

**What people do:** `conf_threshold = 0.5` in `inference.py`, `windage_alpha = 0.02` hardcoded in `tracker.py`, `TOP_K = 10` as a module-level constant in `planner.py`.
**Why it's wrong:** Demo-day "what if we tweak α?" requires editing three files, risking a syntax error on the live laptop.
**Do this instead:** Everything tunable lives in `Settings`. Env-var overrides let you answer the judge's question with `PHYSICS__WINDAGE_ALPHA=0.03 python ...` without touching code.

### 9.3 Anti-Pattern 3: Cyclic Imports (ml ↔ physics)

**What people do:** `physics/tracker.py` imports `ml/inference.py` because "it's convenient to re-run inference from inside the tracker."
**Why it's wrong:** The cycle forbids testing either module in isolation; worse, it makes the dependency order undefined.
**Do this instead:** Compose at the call site. `main.py` (or `tests/e2e/test_chain.py`) is the *only* place that imports all three. Pipeline modules import `core/` only.

### 9.4 Anti-Pattern 4: Feature Engineering Living Inside the Dataset

**What people do:** Compute FDI inline in `dataset.__getitem__` but compute it again from scratch in `inference.py`.
**Why it's wrong:** Training-serving skew. Inference-time FDI drifts 1e-6 from training-time FDI due to a dtype difference; model accuracy collapses inexplicably.
**Do this instead:** `ml/features.py` holds FDI/NDVI/PI as pure numpy functions. `dataset.py` calls them. `inference.py` calls the same functions. Covered by a single unit test. (See Pattern 2 above.)

### 9.5 Anti-Pattern 5: Serializing Shapely Geometries Ad-Hoc

**What people do:** `json.dumps({"geom": str(shapely_polygon)})` — quick but produces WKT strings, not GeoJSON.
**Why it's wrong:** Every downstream consumer (mission planner, export, tests) must re-parse WKT. Leaks an internal representation.
**Do this instead:** `shapely.geometry.mapping(polygon)` → plain dict → pydantic `Polygon.model_validate(...)` → typed geometry.

### 9.6 Anti-Pattern 6: Committing Large Weights to Git

**What people do:** `git add model.pt` with a 50 MB checkpoint.
**Why it's wrong:** Every clone is slow; GitHub push may fail at 100 MB; collaboration becomes painful.
**Do this instead:** `kagglehub.model_upload/download` (primary), Git-ignored `data/weights/` (cache), plus a compressed <5 MB fallback in the repo (belt-and-suspenders).

---

## 10. Integration Points

### 10.1 External Services

| Service | Integration Pattern | Notes |
|---|---|---|
| **MARIDA dataset** | Local filesystem reads; patch-level triplet `{*.tif, *_cl.tif, *_conf.tif}` per scene. | Already staged. On Kaggle: upload as Kaggle Dataset; `/kaggle/input/marida/` path in the notebook. |
| **CMEMS currents** | `xarray.open_dataset(Path)` on pre-downloaded NetCDF. Bilinear `interp()` at `(lon, lat, time)`. | No live API. Pre-clipped to AOI extent at download-time to stay under 500 MB. |
| **ERA5 winds** | Same as CMEMS; `xarray.open_dataset(Path)`. | u10, v10 only. |
| **Kaggle training kernel** | `kagglehub` library + `kernel-metadata.json` already scaffolded. GPU flag must flip before Phase 3. | `enable_gpu: true` in `kernel-metadata.json`. |
| **torch.hub (marccoru)** | `torch.hub.load("marccoru/marinedebrisdetector", "unetpp")`. | Code pulls fine; weights private (Google Drive since Aug 2024). Plan: vendor `.pt` under `data/weights/marccoru_unetpp.pt` after manual one-time download. |
| **Hugging Face Hub** | Backup checkpoint host if kagglehub fails. | Optional; only if time permits. |

### 10.2 Internal Boundaries

| Boundary | Communication | Notes |
|---|---|---|
| `ml` ↔ `physics` | `DetectionFeatureCollection` (pydantic). One-way: ml → physics. | The frozen schema. Any drift here costs hours downstream. |
| `physics` ↔ `mission` | `ForecastEnvelope` (pydantic). One-way. | Mission reads `frames` for convergence score + `source_detections` for base coords. |
| `core/config` → all modules | `Settings` passed explicitly to each entry point. Never imported globally at module scope. | Enables per-test overrides (`Settings(physics=PhysicsSettings(horizon_hours=12))`). |
| `core/schemas` → all modules | Imported freely. `core/` is the dependency root. | Zero runtime cost — pure types. |
| `backend/api/routes.py` ↔ pipeline modules | **No integration this milestone.** API stays mocked. | Future milestone only. Pipeline functions are already shaped as the seam the API will wrap. |

---

## 11. Key Open Risks (for Roadmap Author)

1. **marccoru weights are not auto-fetchable.** Verified: the repo owner moved weights to a private Google Drive folder due to hosting costs ([source](https://github.com/MarcCoru/marinedebrisdetector)). *Mitigation:* plan the "dummy" branch as the real Phase 1 default; treat `marccoru_baseline` as an optional Phase 2 bonus requiring manual Drive download. **Do not put this on the critical path.**
2. **MARIDA band ordering on disk.** PRD says 11 bands; existing codebase `ARCHITECTURE.md` mentions 6 (B2,B3,B4,B6,B8,B11). Must verify at Phase 1 hour 0 (read one `.tif` header) before coding `features.py`. One `rasterio.open("MARIDA/patches/.../*_0.tif").descriptions` call resolves this.
3. **Kaggle GPU-flag currently disabled.** Step 14 cannot start until this flips. Queue it early — Kaggle quota resets are weekly.
4. **CMEMS + ERA5 not yet downloaded.** Fetch script is a Phase 2 prereq; if network is flaky at demo venue, pre-bake the `.nc` files at H0.
5. **The `"class"` reserved-word conflict** between PRD Appendix B and Python. Resolve via pydantic `alias` — noted in Pattern 1.

---

## 12. Sources

### Authoritative (HIGH confidence)
- **geojson-pydantic (data contract):** [developmentseed/geojson-pydantic GitHub](https://github.com/developmentseed/geojson-pydantic), [intro docs](https://developmentseed.org/geojson-pydantic/intro/) — verified Feature[Geom, Props] generic pattern.
- **pydantic-settings + YAML:** [Pydantic Settings Management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/), [pydantic-yaml config guide](https://medium.com/@jonathan_b/a-simple-guide-to-configure-your-python-project-with-pydantic-and-a-yaml-file-bef76888f366), [ML pipeline YAML validation](https://www.sarahglasmacher.com/how-to-validate-config-yaml-pydantic/).
- **segmentation_models_pytorch:** [smp on PyPI](https://pypi.org/project/segmentation-models-pytorch/), [releases](https://github.com/qubvel-org/segmentation_models.pytorch/releases) — `UnetPlusPlus` + `from_pretrained` pattern.
- **kagglehub model workflow:** [Kaggle/kagglehub GitHub](https://github.com/Kaggle/kagglehub), [README model upload/download](https://github.com/Kaggle/kagglehub/blob/main/README.md) — model handle format `<user>/<model>/<framework>/<variation>`.
- **GeoPandas ↔ Shapely ↔ GeoJSON:** [GeoPandas docs](https://geopandas.org/), [Shapely __geo_interface__ deepwiki](https://deepwiki.com/shapely/shapely/8.3-geojson-and-__geo_interface__).

### Verified (MEDIUM confidence — used as pattern references)
- **MarcCoru/marinedebrisdetector:** [GitHub repo](https://github.com/MarcCoru/marinedebrisdetector) — confirmed `torch.hub.load("marccoru/marinedebrisdetector", "unetpp")` exists; confirmed weights moved to Google Drive.
- **ML pipeline testing patterns:** [Effective Testing for ML Pt 1](https://ploomber.io/blog/ml-testing-i/), [Writing Robust Tests for Data Pipelines (eugeneyan)](https://eugeneyan.com/writing/testing-pipelines/).
- **Particle tracker validation patterns:** [OceanParcels](https://oceanparcels.org/), [Parcels test suite](https://github.com/OceanParcels/parcels/blob/master/tests/test_particle_file.py).

### Contextual (LOW confidence — secondary reading)
- [Configuration Management for ML Experiments (Pydantic + Hydra)](https://towardsdatascience.com/configuration-management-for-model-training-experiments-using-pydantic-and-hydra-d14a6ae84c13/) — Hydra deemed overkill, but article informed the comparison.
- [Satellite Imagery Analysis End-to-End (2025)](https://labelyourdata.com/articles/satellite-imagery-analysis) — ecosystem context.

---

*Architecture research for: Python intelligence-layer pipeline (satellite → ML detection → physics forecast → mission planning)*
*Researched: 2026-04-17*
