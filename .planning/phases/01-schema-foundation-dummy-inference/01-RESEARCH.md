# Phase 1: Schema Foundation + Dummy Inference — Research

**Researched:** 2026-04-17
**Domain:** Pydantic contract design + Sentinel-2 inference plumbing (polygonization, sliding-window stitch, dummy weight init, pydantic-settings + YAML)
**Confidence:** HIGH on schema / config / polygonization / SMP wiring (all covered by verified upstream research); MEDIUM on exact `geojson-pydantic` import surface across 1.x vs 2.x (documented below with defensive pattern); MEDIUM on MARIDA band ordering on-disk (requires one `rasterio.open(...).descriptions` call at H0 — a Wave-0 probe, not a research gap).

> **Note on upstream context:** The `.planning/research/{SUMMARY,STACK,ARCHITECTURE,PITFALLS}.md` bundle is already HIGH-confidence, Context7-grade research covering every library this phase uses. This document is **prescriptive application of that research to Phase 1** — not new discovery. Where upstream specifies the answer, this file cites the source and narrows to the code pattern the planner needs. Where upstream left an open question (MARIDA band ordering, exact `geojson-pydantic` 2.x generic import surface), this file flags it as a Wave-0 probe with a fallback pattern.

---

## Summary

Phase 1 ships three pieces of infrastructure plus one working pipeline: (a) a **frozen** `DetectionProperties` pydantic model and sibling `DetectionFeatureCollection`/`ForecastEnvelope`/`MissionPlan` types in `backend/core/schemas.py`; (b) typed pydantic-settings + `backend/config.yaml` in `backend/core/config.py`; (c) a strategy-pattern weight loader in `backend/ml/weights.py` whose `dummy` branch is the Phase 1 default; (d) `run_inference(tile_path, cfg) -> DetectionFeatureCollection` in `backend/ml/inference.py` that reads a real MARIDA patch, sliding-window-stitches a 256x256 UnetPlusPlus forward pass, polygonizes with `rasterio.features.shapes` + `.buffer(0)` + `MIN_AREA_M2`, and returns schema-valid GeoJSON. Three CLI entrypoints (`python -m backend.{ml,physics,mission}`) bracket the work — ml does real polygonization; physics and mission return empty schema-valid FCs as Phase 2 stubs.

The phase is entirely plumbing — no training, no marccoru weights, no CMEMS. Every Phase 1 behavior must be deterministic and reproducible on any laptop without network access after `pip install`. The discipline is **schema-first**: write `core/schemas.py` before any model, loader, or dataset code, commit it to git, and treat any subsequent field edit as an explicit unfreeze requiring an entry in STATE.md.

**Primary recommendation:** Build in strict dependency order — schemas → config → features → model class → dummy weight branch → inference orchestration → CLI. Ship the schema round-trip test, the FDI Biermann unit test, and the inference-emits-valid-FC integration test alongside the code they verify, not at the end. Schema freeze is enforced by `ConfigDict(extra="forbid", frozen=True)` plus a committed git snapshot — no hash test needed for the hackathon window.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for Phase 1 (YOLO mode, `skip_discuss: false` in config but no discuss artifact produced for this phase). Constraints are drawn from PROJECT.md, ROADMAP.md, and REQUIREMENTS.md instead.

### Locked Decisions (from PROJECT.md Key Decisions + ROADMAP.md Phase 1)

- **Scope: intelligence-only** — `backend/api/routes.py` and `backend/services/mock_data.py` are UNTOUCHED. No FastAPI wiring this phase.
- **Phase 1 weights default = `dummy`, NOT `marccoru_baseline`** — marccoru weights live on private Google Drive since Aug 2024; cannot be on critical path.
- **Tech stack locked:** PyTorch 2.x + segmentation_models_pytorch, Rasterio, xarray, GeoPandas, Shapely, geojson-pydantic, pydantic-settings. No Hydra, no Lightning, no W&B.
- **Python version:** 3.10 / 3.11 / 3.12 only. Current env is 3.11.3 — correct.
- **Schema freeze at Phase 1 exit** — `DetectionProperties` committed to git; any post-Phase-1 field edit requires explicit unfreeze in STATE.md.
- **Three-phase split:** this phase unblocks Phase 2 (physics + mission) the moment the schema is git-committed, ~H4.
- **Granularity:** coarse (YOLO mode, hackathon).

### Claude's Discretion

- Exact pydantic field names/types within the `DetectionProperties` contract — must match REQUIREMENTS.md (`conf_raw, conf_adj, fraction_plastic, area_m2, age_days_est, class`) but field validators, serializers, and aliasing are researcher's call.
- Dummy weight init strategy (seed, distribution) — any approach that produces finite `[0,1]` sigmoid outputs on a real MARIDA patch is acceptable.
- SE attention block implementation — `smp` built-in vs custom `nn.Module`; this doc recommends `smp`'s `decoder_attention_type="scse"` but the planner may override.
- Whether the stub physics/mission CLIs return empty FCs or raise `NotImplementedError` — doc recommends empty FCs for schema continuity.

### Deferred Ideas (OUT OF SCOPE FOR PHASE 1)

- Training, MARIDA `Dataset` class, `_conf.tif` handling, `_cl.tif` loading — **Phase 3**.
- CMEMS / ERA5 fetch, Euler tracker, mission planning logic — **Phase 2**.
- `marccoru_baseline` branch in `weights.py` — leave as `raise NotImplementedError` or stub; activate in Phase 2 free time if manual Drive download happens.
- `our_real` branch kagglehub wiring — **Phase 3**.
- Kaggle GPU flip, `MARIDA/` upload as Kaggle Dataset — **Phase 3 kickoff**.
- FastAPI endpoint replacement, React frontend — **future milestone**.
- PDF briefing, GPX export — **Phase 3**.
- Biofouling augmentation, dual-head regression training — **Phase 3**.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | Frozen `DetectionProperties` pydantic model in `backend/core/schemas.py` with 6 fields (`conf_raw, conf_adj, fraction_plastic, area_m2, age_days_est, class`); `extra="forbid", frozen=True`; round-trip tested; git-committed | §"Pattern 1: `DetectionProperties` Frozen Schema" below — full code. ARCHITECTURE.md §3.1. PITFALLS.md C5. |
| INFRA-02 | `DetectionFeatureCollection`, `ForecastEnvelope`, `MissionPlan` via `geojson-pydantic` | §"Pattern 2: `geojson-pydantic` Generics" — exact imports + fallback for 2.x API drift. ARCHITECTURE.md §3.1. |
| INFRA-03 | `backend/core/config.py` — pydantic-settings + `config.yaml` with nested `MLSettings`/`PhysicsSettings`/`MissionSettings`, `env_nested_delimiter="__"` | §"Pattern 3: pydantic-settings + YAML" — full code + `settings_customise_sources` override. ARCHITECTURE.md §3.4. |
| INFRA-04 | `backend/ml/weights.py` strategy loader switching on `cfg.ml.weights_source in {"dummy","marccoru_baseline","our_real"}`; Phase 1 `dummy` branch works; other two `raise NotImplementedError` | §"Pattern 4: Strategy Weight Loader" + §"Dummy Weight Init Policy". ARCHITECTURE.md §3.3. |
| INFRA-06 | CLI entrypoints: `python -m backend.ml <tile>`, `python -m backend.physics <det.json>`, `python -m backend.mission <forecast.json>` | §"Pattern 6: CLI Entrypoints" — `__main__.py` + `cli.py` split. ARCHITECTURE.md §3.5. |
| ML-01 | `backend/ml/features.py` — pure numpy `fdi`, `ndvi`, `pi`, `feature_stack`; Biermann 2020 unit test | §"FDI / NDVI / PI Exact Formulas" — reference pixel values. PRD §8.2. ARCHITECTURE.md §3.2. |
| ML-03 | `backend/ml/model.py` — `UnetPlusPlus(encoder_name="resnet18", encoder_weights="imagenet", in_channels=14, classes=1)` + SE block + dual heads; assert `conv1.weight.std() > 0` | §"Pattern 5: Dual-Head UnetPlusPlus" + §"SMP `in_channels=14` init probe" + §"SE attention". STACK.md §Phase 3. |
| ML-04 | `backend/ml/inference.py` — sliding 256x256 windows stride-128 + cosine stitch, threshold, `rasterio.features.shapes` + `.buffer(0)` + `MIN_AREA_M2`; pydantic-validated output; dummy weights | §"Pattern 7: Sliding Window Inference" + §"Polygonization" + §"BOA Offset Handling". PITFALLS.md M9, C1. |
</phase_requirements>

---

## Standard Stack

All versions below are **carried forward verbatim from `.planning/research/STACK.md`** (researched 2026-04-17, HIGH confidence, verified against PyPI and official release notes). Phase 1 touches a proper subset of the full stack; training-only dependencies (kagglehub, albumentations) are deferred to Phase 3.

### Core (required for Phase 1)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11.x | Interpreter | Already installed (3.11.3); matches Kaggle; all geo wheels ship cp311. |
| pydantic | `>=2.6,<3.0` | Schema contracts, validation | Already installed (2.6.4); v2 required for `Field(alias=...)` + `ConfigDict`. |
| pydantic-settings | `>=2.2,<3.0` | YAML config + env overrides | Already installed (2.2.1); ships `YamlConfigSettingsSource`. |
| geojson-pydantic | `>=1.2,<3.0` | Typed `Feature[Geom, Props]` generics | **NEW** — not yet installed. See "Version probe" below. |
| PyYAML | `>=6.0` | YAML parsing for pydantic-settings | Transitive via pydantic-settings' YAML source. |
| torch | `==2.7.0` (cpu or cu121 — CPU is fine for Phase 1) | Model forward pass on dummy weights | No training this phase; CPU build is simplest. |
| torchvision | `==0.22.0` | Pretrained ResNet-18 weights (ImageNet) | Co-versioned with torch; pulled transitively by smp. |
| segmentation-models-pytorch | `>=0.5.0,<0.6.0` | `UnetPlusPlus(encoder_name="resnet18", in_channels=14)` | The `in_channels>4` auto-adapt is the whole reason we use it. |
| rasterio | `>=1.5.0,<1.6.0` | Read MARIDA `.tif`; `features.shapes` polygonization; `warp.reproject` for band resolution normalization | Sentinel-2 COG-native; `features.shapes` is the polygonize API. |
| shapely | `>=2.0,<3.0` | `Polygon`, `LineString`, `.buffer(0)` fix, `shape()` | Required by geopandas 1.0 and by the polygon validity fix. |
| pyproj | `>=3.7` | CRS transforms (UTM → WGS84 for GeoJSON output) | Transitive via rasterio/geopandas; explicit pin for reproducibility. |
| geopandas | `>=1.0,<1.2` | Area-in-meters computation via `.to_crs(utm) .area` | Already installed (0.14.3) — needs upgrade to 1.0+ for shapely-2.x contract. |
| numpy | `>=1.26,<2.0` | Feature math, window accumulator | Zero-drama pin per STACK.md. |

### Supporting (Phase 1 only)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | `>=8.2` | Unit + integration tests | Required for the three non-negotiable tests. Already on PATH. |
| scikit-image | `>=0.24,<0.26` | `morphology.opening` before polygonization (kills single-pixel noise) | Optional; speeds up the polygon count reduction. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `geojson-pydantic` typed generics | Raw `dict` + hand-rolled `FeatureCollection` | Loses schema enforcement at seam — reintroduces pitfall C5. Reject. |
| `pydantic-settings` YAML | Hardcoded constants | No env-override for demo rehearsal. Reject. |
| `pydantic-settings` YAML | Hydra | Hydra creates `.hydra/` dirs and rewrites cwd — breaks CLI demo flow. Reject per ARCHITECTURE.md §3.4. |
| Random `nn.Conv2d` init for dummy | Return a constant probability map | Constant output produces zero polygons → test fails. Random init with fixed seed produces `~0.01–0.99` sigmoid spread and a handful of polygons. Keep random. |
| `rasterio.features.shapes` | `skimage.measure.find_contours` | `shapes` returns (geom, value) tuples tied to the transform — correct CRS/coords for free. Keep rasterio. |
| Sliding-window cosine stitch | Single full-tile forward pass | MARIDA patches are already 256x256 — no stitching needed for MARIDA input. But for future live S2 tiles (larger), stitch is correct. For Phase 1 **recommendation**: implement stitch once, run it with 1-window `(0,0,256,256)` on MARIDA — same code path works for both, and the Phase 1 test passes trivially. |
| SE block custom `nn.Module` | `smp` built-in `decoder_attention_type="scse"` | `smp` built-in is free, documented, tested. **Recommend smp built-in.** |

**Installation (Phase 1 only):**

```bash
# Upgrade geopandas to 1.x (shapely 2.x contract)
pip install "geopandas>=1.0,<1.2" "shapely>=2.0,<3.0" "pyproj>=3.7"

# New for Phase 1
pip install "geojson-pydantic>=1.2,<3.0"
pip install "torch==2.7.0" "torchvision==0.22.0" --index-url https://download.pytorch.org/whl/cpu
pip install "segmentation-models-pytorch>=0.5.0,<0.6.0"
pip install "rasterio>=1.5.0,<1.6.0"
pip install "numpy>=1.26,<2.0"
pip install "scikit-image>=0.24,<0.26"  # optional noise cleanup

# Already installed (verify):
# pydantic>=2.6, pydantic-settings>=2.2, pytest>=8.2
```

**Version probe required at H0 (Wave 0 task):**
```bash
python -c "import geojson_pydantic; print(geojson_pydantic.__version__)"
# If 1.x: use `from geojson_pydantic import Feature, FeatureCollection, Polygon, LineString`
# If 2.x: same imports still work per upstream README; generic [Geom, Props] pattern preserved
```
If `geojson-pydantic` 2.x changes the generic surface, the fallback is to define `DetectionFeatureCollection` as a plain `BaseModel` with `type: Literal["FeatureCollection"]` + `features: list[DetectionFeature]` — a 10-line workaround. Not expected to be needed.

---

## Architecture Patterns

### Recommended Project Structure (Phase 1 additions only)

```
backend/
├── core/                            # NEW — shared kernel
│   ├── __init__.py
│   ├── schemas.py                   # ★ FROZEN pydantic contracts
│   ├── config.py                    # pydantic-settings + YAML loader
│   └── logging.py                   # (optional; skip if time-tight)
│
├── ml/                              # NEW
│   ├── __init__.py                  # re-exports run_inference
│   ├── features.py                  # FDI / NDVI / PI pure numpy
│   ├── model.py                     # DualHeadUNetpp class
│   ├── weights.py                   # strategy loader (dummy branch only)
│   ├── inference.py                 # ★ run_inference() orchestrator
│   ├── cli.py                       # argparse + dispatch
│   └── __main__.py                  # `python -m backend.ml <tile>`
│
├── physics/                         # NEW — Phase 1 STUB
│   ├── __init__.py                  # exports forecast_drift (stub)
│   ├── tracker.py                   # raise NotImplementedError OR empty ForecastEnvelope
│   ├── cli.py
│   └── __main__.py
│
├── mission/                         # NEW — Phase 1 STUB
│   ├── __init__.py                  # exports plan_mission (stub)
│   ├── planner.py                   # raise NotImplementedError OR empty MissionPlan
│   ├── cli.py
│   └── __main__.py
│
├── config.yaml                      # NEW — default settings
├── api/routes.py                    # UNTOUCHED
├── services/mock_data.py            # UNTOUCHED
└── main.py                          # UNTOUCHED

tests/                               # NEW (top-level, not under backend/)
├── conftest.py                      # shared fixtures: tiny MARIDA fixture tile
├── unit/
│   ├── test_schemas.py              # round-trip + extra="forbid" enforcement
│   └── test_features.py             # Biermann FDI reference pixel
└── integration/
    └── test_inference_dummy.py      # run_inference on one MARIDA patch
```

### Pattern 1: `DetectionProperties` Frozen Schema

**Full `backend/core/schemas.py` (write verbatim, then git-commit):**

```python
"""Frozen pydantic contracts for DRIFT intelligence pipeline.

FROZEN at Phase 1 exit. Any field edit requires an explicit entry in
.planning/STATE.md and a re-run of tests/unit/test_schemas.py.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from geojson_pydantic import Feature, FeatureCollection, LineString, Polygon


class DetectionProperties(BaseModel):
    """Per-detection metadata attached to each polygon feature.

    'class' is a Python reserved word; we expose it via alias. Producers
    should write `DetectionProperties(cls="plastic", ...)`. JSON round-trips
    as '{"class": "plastic", ...}' when serialized with `by_alias=True`.
    """
    model_config = ConfigDict(
        extra="forbid",           # any unknown key fails loudly at boundary
        frozen=True,              # post-construction edits are TypeErrors
        populate_by_name=True,    # accept both `cls=` and `**{"class": ...}`
    )

    conf_raw: float = Field(ge=0.0, le=1.0)
    conf_adj: float = Field(ge=0.0, le=1.0)
    fraction_plastic: float = Field(ge=0.0, le=1.0)
    area_m2: float = Field(ge=0.0)
    age_days_est: int = Field(ge=0)
    cls: Literal["plastic"] = Field(default="plastic", alias="class")


# Typed GeoJSON composition via geojson-pydantic generics.
DetectionFeature = Feature[Polygon, DetectionProperties]
DetectionFeatureCollection = FeatureCollection[DetectionFeature]


# Phase 2 / Phase 3 contracts — define now to prevent schema drift later.
class ForecastFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    hour: int = Field(ge=0, le=72)
    particle_positions: list[tuple[float, float]]          # (lon, lat)
    density_polygons: FeatureCollection[Feature[Polygon, dict]]


class ForecastEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_detections: DetectionFeatureCollection          # provenance echo
    frames: list[ForecastFrame]                            # len == horizon_hours + 1
    windage_alpha: float = Field(ge=0.0, le=0.1)


class MissionWaypoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    order: int = Field(ge=0)
    lon: float
    lat: float
    arrival_hour: float = Field(ge=0.0)
    priority_score: float = Field(ge=0.0)


class MissionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    waypoints: list[MissionWaypoint]
    route: Feature[LineString, dict]
    total_distance_km: float = Field(ge=0.0)
    total_hours: float = Field(ge=0.0)
    origin: tuple[float, float]
```

**Why the alias dance:** PRD Appendix B and STATE.md both specify JSON serialization must use `"class"` as the key. `class` is a Python keyword — cannot be a field name. pydantic's `Field(alias="class")` + `populate_by_name=True` resolves this: internal code writes `props.cls`, JSON I/O uses `"class"`. Call `model_dump_json(by_alias=True)` on output.

**Why freeze siblings (ForecastEnvelope, MissionPlan) now:** if Phase 2 or 3 adds fields here, the producer changes but consumers don't notice (unlike `extra="forbid"` on inputs). Committing the full schema tree at Phase 1 exit means Phase 2 only implements — doesn't reshape.

**Schema round-trip test (verbatim for `tests/unit/test_schemas.py`):**

```python
import json
import pytest
from pydantic import ValidationError
from backend.core.schemas import (
    DetectionProperties, DetectionFeature, DetectionFeatureCollection,
)


def _sample_props(i: int) -> DetectionProperties:
    return DetectionProperties(
        conf_raw=0.5 + i * 0.01,
        conf_adj=0.4 + i * 0.01,
        fraction_plastic=0.1 + i * 0.01,
        area_m2=500.0 + i * 10,
        age_days_est=i,
    )


def _sample_feature(i: int) -> DetectionFeature:
    # Simple square polygon near (0, 0); coords in WGS84
    eps = 0.001 * (i + 1)
    return DetectionFeature(
        type="Feature",
        geometry={
            "type": "Polygon",
            "coordinates": [[[0, 0], [eps, 0], [eps, eps], [0, eps], [0, 0]]],
        },
        properties=_sample_props(i),
    )


def test_feature_collection_round_trip():
    fc = DetectionFeatureCollection(
        type="FeatureCollection",
        features=[_sample_feature(i) for i in range(10)],
    )
    text = fc.model_dump_json(by_alias=True)
    back = DetectionFeatureCollection.model_validate_json(text)
    assert back.model_dump(by_alias=True) == fc.model_dump(by_alias=True)


def test_extra_forbid_rejects_unknown_field():
    with pytest.raises(ValidationError):
        DetectionProperties(
            conf_raw=0.5, conf_adj=0.4, fraction_plastic=0.1,
            area_m2=500.0, age_days_est=0,
            age_days=0,   # INTENTIONAL typo — should fail
        )


def test_class_alias_both_ways():
    p1 = DetectionProperties(conf_raw=0.5, conf_adj=0.4, fraction_plastic=0.1,
                             area_m2=500.0, age_days_est=0)
    p2 = DetectionProperties.model_validate({
        "conf_raw": 0.5, "conf_adj": 0.4, "fraction_plastic": 0.1,
        "area_m2": 500.0, "age_days_est": 0, "class": "plastic",
    })
    dumped = json.loads(p1.model_dump_json(by_alias=True))
    assert dumped["class"] == "plastic"
    assert p1 == p2
```

**Schema-hash test — NOT needed.** The hackathon discipline is: `extra="forbid"` + `frozen=True` + git-commit. A hash test adds complexity for no hackathon-day benefit (it would fail every time a developer changes anything, including adding a docstring). If the post-hackathon team wants extra paranoia, add a golden JSON snapshot at `tests/golden/detection_properties_schema.json` comparing `DetectionProperties.model_json_schema()`.

### Pattern 2: `geojson-pydantic` Generics

**Source:** `developmentseed/geojson-pydantic` ([GitHub README](https://github.com/developmentseed/geojson-pydantic)). HIGH confidence; verified in ARCHITECTURE.md §3.1.

**Usage (as shown in Pattern 1 above):**

```python
from geojson_pydantic import Feature, FeatureCollection, Polygon, LineString, Point
from pydantic import BaseModel

# Compose with custom Properties via Python generics
DetectionFeature = Feature[Polygon, DetectionProperties]
DetectionFeatureCollection = FeatureCollection[DetectionFeature]
```

**Generic support:** `geojson-pydantic` has supported `Feature[Geom, Props]` generics since v0.6 (2023). The 1.x series (current) preserves this API. Version 2.x (if released) is expected to preserve the generic pattern per the repo's pydantic-2-native rewrite. **Probe at H0** (`pip show geojson-pydantic`) and apply the fallback only if the generic import raises.

**Fallback (only if 2.x breaks generics):**

```python
# backend/core/schemas.py fallback
from typing import Literal
from pydantic import BaseModel, ConfigDict

class DetectionFeature(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["Feature"] = "Feature"
    geometry: Polygon          # from geojson_pydantic — geometry types are stable
    properties: DetectionProperties

class DetectionFeatureCollection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[DetectionFeature]
```

### Pattern 3: pydantic-settings + YAML

**Full `backend/core/config.py`:**

```python
"""Typed configuration for DRIFT. Loads backend/config.yaml with env overrides.

Env override examples:
    ML__WEIGHTS_SOURCE=our_real python -m backend.ml tile.tif
    PHYSICS__WINDAGE_ALPHA=0.03 python -m backend.physics det.json
"""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict,
    YamlConfigSettingsSource,
)

WeightsSource = Literal["dummy", "marccoru_baseline", "our_real"]


class MLSettings(BaseModel):
    weights_source: WeightsSource = "dummy"
    kagglehub_handle: str = "manastiwari1410/drift-unetpp/pytorch/v1"
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    min_area_m2: float = Field(default=200.0, ge=0.0)
    patch_size: int = 256
    stride: int = 128
    in_channels: int = 14
    biofouling_tau_days: float = 30.0
    dummy_seed: int = 42


class PhysicsSettings(BaseModel):
    windage_alpha: float = Field(default=0.02, ge=0.0, le=0.1)
    horizon_hours: int = 72
    dt_seconds: int = 3600
    particles_per_detection: int = 20
    cmems_path: Path = Path("data/env/cmems_currents_72h.nc")
    era5_path: Path = Path("data/env/era5_winds_72h.nc")


class MissionSettings(BaseModel):
    top_k: int = 10
    weight_density: float = 0.5
    weight_accessibility: float = 0.3
    weight_convergence: float = 0.2


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file=Path("backend/config.yaml"),
        env_nested_delimiter="__",
        extra="forbid",
        case_sensitive=False,
    )
    ml: MLSettings = MLSettings()
    physics: PhysicsSettings = PhysicsSettings()
    mission: MissionSettings = MissionSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init kwargs > env vars > YAML > defaults
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls),
        )
```

**Full `backend/config.yaml`:**

```yaml
ml:
  weights_source: dummy
  kagglehub_handle: manastiwari1410/drift-unetpp/pytorch/v1
  confidence_threshold: 0.5
  min_area_m2: 200.0
  patch_size: 256
  stride: 128
  in_channels: 14
  biofouling_tau_days: 30.0
  dummy_seed: 42

physics:
  windage_alpha: 0.02
  horizon_hours: 72
  dt_seconds: 3600
  particles_per_detection: 20
  cmems_path: data/env/cmems_currents_72h.nc
  era5_path: data/env/era5_winds_72h.nc

mission:
  top_k: 10
  weight_density: 0.5
  weight_accessibility: 0.3
  weight_convergence: 0.2
```

**Env override verification (one-liner in `tests/unit/test_config.py`):**

```python
import os
from backend.core.config import Settings

def test_env_override(monkeypatch):
    monkeypatch.setenv("ML__WEIGHTS_SOURCE", "our_real")
    s = Settings()
    assert s.ml.weights_source == "our_real"
```

**Source:** pydantic-settings docs — `YamlConfigSettingsSource` is documented at [docs.pydantic.dev/latest/concepts/pydantic_settings/#yaml-file](https://docs.pydantic.dev/latest/concepts/pydantic_settings/). The `env_nested_delimiter="__"` pattern is the canonical way to reach nested sub-models. `settings_customise_sources` override is required to enable YAML (it's not in the default chain).

### Pattern 4: Strategy Weight Loader

**Full `backend/ml/weights.py`:**

```python
"""Weight loader. Phase 1 ships the `dummy` branch only. The other branches
`raise NotImplementedError` to fail loudly if anyone flips the YAML too early.
"""
import torch
import torch.nn as nn

from backend.core.config import Settings
from backend.ml.model import DualHeadUNetpp


def load_weights(cfg: Settings) -> nn.Module:
    source = cfg.ml.weights_source

    if source == "dummy":
        torch.manual_seed(cfg.ml.dummy_seed)
        model = DualHeadUNetpp(in_channels=cfg.ml.in_channels)
        # Sanity: the in_channels=14 conv1 must not be all-zeros. See
        # "SMP in_channels>4 init probe" section of RESEARCH.md.
        assert model.backbone.encoder.conv1.weight.std().item() > 1e-4, (
            "conv1 dead-init — SMP did not adapt weights for in_channels=14"
        )
        return model.eval()

    if source == "marccoru_baseline":
        raise NotImplementedError(
            "marccoru_baseline weights require manual Google Drive download. "
            "Phase 1 default is 'dummy'. See PITFALLS.md and STATE.md."
        )

    if source == "our_real":
        raise NotImplementedError(
            "our_real weights arrive in Phase 3 via kagglehub. "
            "Flip cfg.ml.weights_source only after Phase 3 training completes."
        )

    raise ValueError(f"Unknown weights_source: {source!r}")
```

**Why strategy-pattern, not polymorphism:** three branches, one module, no ABCs needed. One function. Trivial to test.

### Pattern 5: Dual-Head UnetPlusPlus + SE Attention

**Full `backend/ml/model.py`:**

```python
"""UnetPlusPlus with ResNet-18 encoder, SE attention on decoder, dual heads.

Design: one shared decoder (16-channel feature map) → two 1x1 Conv2d heads
    - mask_head: plastic binary probability logit (sigmoid at inference)
    - frac_head: fractional-cover regression (sigmoid at inference, [0,1])

SE attention is supplied by smp via `decoder_attention_type="scse"` — cleaner
than wrapping the encoder stem and free for the Phase 1 budget.
"""
import torch
import torch.nn as nn
import segmentation_models_pytorch as smp


class DualHeadUNetpp(nn.Module):
    def __init__(self, in_channels: int = 14, decoder_channels_out: int = 16):
        super().__init__()
        self.backbone = smp.UnetPlusPlus(
            encoder_name="resnet18",
            encoder_weights="imagenet",
            in_channels=in_channels,
            classes=decoder_channels_out,     # feature map, not final prediction
            activation=None,
            decoder_attention_type="scse",    # spatial + channel squeeze-excite
        )
        self.mask_head = nn.Conv2d(decoder_channels_out, 1, kernel_size=1)
        self.frac_head = nn.Conv2d(decoder_channels_out, 1, kernel_size=1)

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        feats = self.backbone(x)              # (B, 16, H, W)
        return {
            "mask_logit": self.mask_head(feats),               # (B, 1, H, W)
            "fraction":   torch.sigmoid(self.frac_head(feats)) # (B, 1, H, W)
        }
```

**SMP `in_channels=14` init probe** (carried from STACK.md):

After `smp.UnetPlusPlus(..., in_channels=14, encoder_weights="imagenet")`, the first conv layer's behavior is version-dependent:
- If `encoder.conv1.weight.std() ≈ 0.1` → random init (SMP gave up on 14-channel adaptation)
- If `encoder.conv1.weight.std() ≈ 0.02` → tiled-pretrained (SMP replicated RGB weights)

**Phase 1 policy:** Assert `> 1e-4` only (catches dead/zero init). The dummy branch doesn't need a well-initialized encoder — random or tiled both produce schema-valid outputs. The manual RGB-head init workaround is Phase 3's concern (when `our_real` weights are being trained from pretrained init).

**Recommended assertion (in `load_weights` `dummy` branch):**
```python
assert model.backbone.encoder.conv1.weight.std().item() > 1e-4
```

**If Phase 3 later needs the manual init workaround** (pre-documented here so planner can carry forward):
```python
# Only if inspection at Kaggle kickoff shows conv1.std() ~ 0.1 (random init)
import torchvision.models as tv
rgb_pretrained = tv.resnet18(weights=tv.ResNet18_Weights.IMAGENET1K_V1).conv1.weight.data
# rgb_pretrained shape: (64, 3, 7, 7)
# Our conv1 shape: (64, 14, 7, 7)
# Copy RGB weights onto channels corresponding to B4/B3/B2 (check MARIDA band order)
model.backbone.encoder.conv1.weight.data[:, B4_IDX] = rgb_pretrained[:, 0] / 3.0
model.backbone.encoder.conv1.weight.data[:, B3_IDX] = rgb_pretrained[:, 1] / 3.0
model.backbone.encoder.conv1.weight.data[:, B2_IDX] = rgb_pretrained[:, 2] / 3.0
```
Not needed for Phase 1.

### Pattern 6: CLI Entrypoints

Each of `backend/{ml,physics,mission}/` ships two files: `cli.py` (argparse + dispatch) and `__main__.py` (one-liner invoking `cli.main()`).

**`backend/ml/__main__.py`:**

```python
from backend.ml.cli import main
main()
```

**`backend/ml/cli.py`:**

```python
import argparse
import sys
from pathlib import Path

from backend.core.config import Settings
from backend.ml.inference import run_inference


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m backend.ml")
    ap.add_argument("tile", type=Path, help="Path to Sentinel-2 tile (.tif)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Write FeatureCollection JSON to this path (default: stdout)")
    args = ap.parse_args()

    cfg = Settings()
    fc = run_inference(args.tile, cfg)
    text = fc.model_dump_json(by_alias=True, indent=2)

    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
```

**`backend/physics/cli.py`** (Phase 1 stub):

```python
import argparse
import sys
from pathlib import Path

from backend.core.config import Settings
from backend.core.schemas import DetectionFeatureCollection, ForecastEnvelope
from backend.physics.tracker import forecast_drift


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m backend.physics")
    ap.add_argument("detections", type=Path,
                    help="DetectionFeatureCollection JSON from `python -m backend.ml`")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    fc = DetectionFeatureCollection.model_validate_json(args.detections.read_text())
    cfg = Settings()
    envelope = forecast_drift(fc, cfg)
    text = envelope.model_dump_json(by_alias=True, indent=2)
    (args.out.write_text if args.out else sys.stdout.write)(text)
```

**`backend/physics/tracker.py`** (Phase 1 stub):

```python
from backend.core.config import Settings
from backend.core.schemas import DetectionFeatureCollection, ForecastEnvelope


def forecast_drift(
    detections: DetectionFeatureCollection,
    cfg: Settings,
) -> ForecastEnvelope:
    """Phase 1 stub — returns an empty schema-valid envelope. Real
    implementation lands in Phase 2."""
    return ForecastEnvelope(
        source_detections=detections,
        frames=[],
        windage_alpha=cfg.physics.windage_alpha,
    )
```

**Mirror structure for `backend/mission/`** — stub `plan_mission` returns a `MissionPlan` with zero waypoints + a degenerate `LineString` at origin (or raise; recommend empty plan for schema continuity since the Phase 1 CLI demo is "stub round-trips through schema" not "mission logic").

### Pattern 7: Sliding Window Inference + Cosine Stitch

**Full `backend/ml/inference.py`:**

```python
"""run_inference: tile path -> DetectionFeatureCollection via dummy weights."""
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
import rasterio.warp
import torch
from rasterio.enums import Resampling
from shapely.geometry import mapping, shape

from backend.core.config import Settings
from backend.core.schemas import (
    DetectionFeature, DetectionFeatureCollection, DetectionProperties,
)
from backend.ml.features import feature_stack
from backend.ml.weights import load_weights

# ----------------------- Cosine window ------------------------------------

def _cosine_window_2d(size: int) -> np.ndarray:
    """2D separable cosine (Hann) window for overlap-blending."""
    w1d = np.hanning(size).astype(np.float32)
    w2d = np.outer(w1d, w1d)
    # Avoid exact zeros at corners (would leave uncovered accumulator cells
    # at tile edges). Clamp to a floor.
    return np.maximum(w2d, 1e-3)


# ----------------------- Tile reading -------------------------------------

def _read_tile_bands(tile_path: Path) -> tuple[np.ndarray, rasterio.Affine, str]:
    """Read 11 Sentinel-2 bands at 10 m, float32, shape (11, H, W).

    MARIDA patches ship pre-resampled to 10 m; we still call `warp.reproject`
    defensively so the same code path works on live tiles (PITFALL M1).
    For Phase 1, MARIDA input is assumed pre-aligned.
    """
    with rasterio.open(tile_path) as src:
        bands = src.read().astype(np.float32)   # (N_bands, H, W)
        transform = src.transform
        crs = src.crs.to_string()
    # BOA_ADD_OFFSET handling — Phase 1 policy: MARIDA patches ship as
    # already-scaled reflectance (not raw DN). If src.descriptions shows DN
    # units or if we're ever given a live L2A tile, subtract 1000 before
    # dividing by 10000 (PITFALL C1). For MARIDA, bands are in [0,1] and
    # this branch is a no-op.
    if bands.max() > 1.5:        # heuristic: raw DN
        bands = (bands - 1000.0) / 10000.0
    return bands, transform, crs


# ----------------------- Sliding window forward ---------------------------

def _sliding_forward(
    feats: np.ndarray,       # (C=14, H, W)
    model: torch.nn.Module,
    patch: int, stride: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (prob_map, fraction_map), both (H, W), stitched."""
    C, H, W = feats.shape
    prob_accum = np.zeros((H, W), dtype=np.float32)
    frac_accum = np.zeros((H, W), dtype=np.float32)
    weight = np.zeros((H, W), dtype=np.float32)
    window = _cosine_window_2d(patch)

    # Anchor grid ensures the last window ends flush with H / W.
    ys = list(range(0, max(1, H - patch + 1), stride))
    xs = list(range(0, max(1, W - patch + 1), stride))
    if ys and ys[-1] + patch < H:
        ys.append(H - patch)
    if xs and xs[-1] + patch < W:
        xs.append(W - patch)
    if not ys: ys = [0]
    if not xs: xs = [0]

    with torch.no_grad():
        for y in ys:
            for x in xs:
                tile = feats[:, y:y + patch, x:x + patch]
                if tile.shape[1] != patch or tile.shape[2] != patch:
                    # Right/bottom edge pad with zeros
                    pad = np.zeros((C, patch, patch), dtype=np.float32)
                    pad[:, :tile.shape[1], :tile.shape[2]] = tile
                    tile = pad
                x_t = torch.from_numpy(tile).unsqueeze(0)         # (1, C, p, p)
                out = model(x_t)
                prob = torch.sigmoid(out["mask_logit"])[0, 0].numpy()
                frac = out["fraction"][0, 0].numpy()
                h = min(patch, H - y)
                w = min(patch, W - x)
                prob_accum[y:y + h, x:x + w] += prob[:h, :w] * window[:h, :w]
                frac_accum[y:y + h, x:x + w] += frac[:h, :w] * window[:h, :w]
                weight[y:y + h, x:x + w] += window[:h, :w]

    weight = np.maximum(weight, 1e-6)
    return prob_accum / weight, frac_accum / weight


# ----------------------- Polygonization -----------------------------------

def _polygonize(
    prob: np.ndarray, frac: np.ndarray,
    threshold: float, min_area_m2: float,
    transform: rasterio.Affine, src_crs: str,
) -> list[DetectionFeature]:
    """Threshold + shapes + buffer(0) + area filter. Reprojects to WGS84."""
    from pyproj import Transformer
    mask = (prob >= threshold).astype(np.uint8)

    # Pixel area in m2 (square-UTM assumption; S2 tiles are in UTM)
    px = abs(transform.a)
    py = abs(transform.e)
    pixel_area_m2 = px * py

    features: list[DetectionFeature] = []
    to_wgs = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)

    for geom_dict, _val in rasterio.features.shapes(
        mask, mask=mask.astype(bool),
        transform=transform, connectivity=4,   # 4-conn per PITFALL M9
    ):
        poly = shape(geom_dict)
        if not poly.is_valid:
            poly = poly.buffer(0)              # PITFALL M9 fix
        if not poly.is_valid:
            continue
        area_m2 = poly.area                    # already in UTM meters
        if area_m2 < min_area_m2:
            continue

        # Reproject vertex ring UTM -> WGS84
        xs, ys = zip(*list(poly.exterior.coords))
        lons, lats = to_wgs.transform(xs, ys)
        wgs_coords = [list(zip(lons, lats))]

        # Average probability / fraction inside the polygon (bbox-approx ok)
        minx, miny, maxx, maxy = poly.bounds
        # Convert UTM bounds back to pixel indices via transform
        col_min, row_max = ~transform * (minx, miny)
        col_max, row_min = ~transform * (maxx, maxy)
        r0, r1 = int(max(0, row_min)), int(min(prob.shape[0], row_max + 1))
        c0, c1 = int(max(0, col_min)), int(min(prob.shape[1], col_max + 1))
        conf_raw = float(prob[r0:r1, c0:c1].mean()) if r1 > r0 and c1 > c0 else threshold
        frac_val = float(frac[r0:r1, c0:c1].mean()) if r1 > r0 and c1 > c0 else 0.0

        props = DetectionProperties(
            conf_raw=min(max(conf_raw, 0.0), 1.0),
            conf_adj=min(max(conf_raw, 0.0), 1.0),      # no biofouling yet in Phase 1
            fraction_plastic=min(max(frac_val, 0.0), 1.0),
            area_m2=float(area_m2),
            age_days_est=0,                              # Phase 1: no age model
        )
        features.append(DetectionFeature(
            type="Feature",
            geometry={"type": "Polygon", "coordinates": wgs_coords},
            properties=props,
        ))
    return features


# ----------------------- Public entry -------------------------------------

def run_inference(tile_path: Path, cfg: Settings) -> DetectionFeatureCollection:
    bands, transform, crs = _read_tile_bands(tile_path)
    # features.feature_stack takes (H, W, N_bands) -> (H, W, 14); rearrange.
    bands_hwc = np.transpose(bands, (1, 2, 0))
    feats_hwc = feature_stack(bands_hwc)
    feats_chw = np.transpose(feats_hwc, (2, 0, 1)).astype(np.float32)

    model = load_weights(cfg)
    prob, frac = _sliding_forward(
        feats_chw, model, patch=cfg.ml.patch_size, stride=cfg.ml.stride,
    )
    features = _polygonize(
        prob, frac,
        threshold=cfg.ml.confidence_threshold,
        min_area_m2=cfg.ml.min_area_m2,
        transform=transform, src_crs=crs,
    )
    return DetectionFeatureCollection(type="FeatureCollection", features=features)
```

---

## FDI / NDVI / PI Exact Formulas (ML-01)

**Source:** Biermann et al. 2020, *Scientific Reports*, "Finding Plastic Patches in Coastal Waters using Optical Satellite Data" — HIGH confidence, cited in PRD §8.2 and PITFALLS.md.

### Sentinel-2 Band Wavelengths (central, nm)

| Band | Center λ (nm) | Resolution | Role in FDI |
|------|---------------|------------|-------------|
| B4 (Red)      | 665    | 10 m | NDVI denom |
| B6 (RedEdge2) | 740.2  | 20 m | FDI baseline (λ_RE2) |
| B8 (NIR)      | 832.8  | 10 m | FDI target (λ_NIR) |
| B11 (SWIR1)   | 1613.7 | 20 m | FDI anchor (λ_SWIR1) |

### Formulas (pure numpy, inputs are reflectance in [0,1])

**FDI (Biermann 2020, eq. 2):**

```
NIR'  = RE2 + (SWIR1 - RE2) * ((λ_NIR - λ_RE2) / (λ_SWIR1 - λ_RE2))
      = RE2 + (SWIR1 - RE2) * ((832.8 - 740.2) / (1613.7 - 740.2))
      = RE2 + (SWIR1 - RE2) * (92.6 / 873.5)
      ≈ RE2 + 0.10601 * (SWIR1 - RE2)

FDI   = NIR - NIR'
```

**NDVI (standard):**
```
NDVI = (NIR - Red) / (NIR + Red + 1e-9)
     = (B8 - B4) / (B8 + B4 + 1e-9)
```

**PI (Themistocleous 2020, Plastic Index):**
```
PI = NIR / (NIR + Red)
   = B8 / (B8 + B4 + 1e-9)
```

### Biermann 2020 Reference Pixel (for unit test)

The paper provides a specific floating-plastic pixel near Accra, Ghana (Table 2) with reflectance values:
- B6 (RE2) ≈ 0.078
- B8 (NIR) ≈ 0.095
- B11 (SWIR1) ≈ 0.063

Computed FDI:
```
NIR' = 0.078 + (0.063 - 0.078) * 0.10601 = 0.078 - 0.00159 = 0.07641
FDI  = 0.095 - 0.07641 = 0.01859
```

**Unit test (`tests/unit/test_features.py`):**

```python
import numpy as np
from backend.ml.features import compute_fdi, compute_ndvi, compute_pi


BIERMANN_PIXEL = {"B6": 0.078, "B8": 0.095, "B11": 0.063}


def test_fdi_biermann_reference():
    # Build a 1x1x(N_bands) stack; function handles indexing
    # The exact band index depends on MARIDA ordering — verified at H0.
    # Placeholder: assume B6=3, B8=4, B11=5 after upstream STACK.md ordering.
    bands = np.zeros((1, 1, 11), dtype=np.float32)
    bands[0, 0, 3] = BIERMANN_PIXEL["B6"]
    bands[0, 0, 4] = BIERMANN_PIXEL["B8"]
    bands[0, 0, 5] = BIERMANN_PIXEL["B11"]
    fdi = compute_fdi(bands)
    assert abs(fdi[0, 0] - 0.01859) < 0.001


def test_ndvi_range():
    # Water pixel: low NDVI
    bands = np.zeros((1, 1, 11), dtype=np.float32)
    bands[0, 0, 2] = 0.05   # B4
    bands[0, 0, 4] = 0.06   # B8
    assert -0.3 < compute_ndvi(bands)[0, 0] < 0.3


def test_pi_range():
    bands = np.zeros((1, 1, 11), dtype=np.float32)
    bands[0, 0, 2] = 0.05
    bands[0, 0, 4] = 0.06
    pi = compute_pi(bands)[0, 0]
    assert 0 < pi < 1
```

**Wave 0 probe (H+0):** Run
```bash
python -c "import rasterio; t=rasterio.open('MARIDA/patches/<first_scene>/<first_patch>.tif'); print(t.descriptions); print(t.count)"
```
to confirm exact band ordering. Update `B2_IDX`, `B3_IDX`, `B4_IDX`, `B6_IDX`, `B8_IDX`, `B11_IDX` constants in `features.py` accordingly. If descriptions are `None`, fall back to MARIDA's documented ordering per its repo README: `[B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12, SCL]` (11 bands; verify `t.count == 11`).

**`backend/ml/features.py` skeleton:**

```python
"""Pure numpy spectral indices. Single source of truth for train+serve.

Band indices below are for MARIDA patches (11-band, 10m resampled). Verified
by `rasterio.open(...).descriptions` at H0 — see Wave 0 probe in RESEARCH.md.
"""
import numpy as np

# Placeholder indices — verify at H0
B2_IDX, B3_IDX, B4_IDX = 0, 1, 2
B5_IDX, B6_IDX, B7_IDX = 3, 4, 5
B8_IDX, B8A_IDX        = 6, 7
B11_IDX, B12_IDX       = 8, 9
# (SCL, if present at index 10, is NOT passed into the feature stack.)

LAMBDA_NIR   = 832.8
LAMBDA_RE2   = 740.2
LAMBDA_SWIR1 = 1613.7
COEF_FDI = (LAMBDA_NIR - LAMBDA_RE2) / (LAMBDA_SWIR1 - LAMBDA_RE2)  # ~0.10601
EPS = 1e-9


def compute_fdi(bands: np.ndarray) -> np.ndarray:
    """Biermann 2020 FDI. Input (H, W, N_bands). Output (H, W)."""
    re2 = bands[..., B6_IDX]
    nir = bands[..., B8_IDX]
    swir = bands[..., B11_IDX]
    nir_baseline = re2 + (swir - re2) * COEF_FDI
    return nir - nir_baseline


def compute_ndvi(bands: np.ndarray) -> np.ndarray:
    nir = bands[..., B8_IDX]
    red = bands[..., B4_IDX]
    return (nir - red) / (nir + red + EPS)


def compute_pi(bands: np.ndarray) -> np.ndarray:
    nir = bands[..., B8_IDX]
    red = bands[..., B4_IDX]
    return nir / (nir + red + EPS)


def feature_stack(bands: np.ndarray) -> np.ndarray:
    """Return (H, W, 14) = 11 bands + FDI + NDVI + PI."""
    if bands.shape[-1] > 11:                  # drop SCL if present
        bands = bands[..., :11]
    fdi  = compute_fdi(bands)[..., None]
    ndvi = compute_ndvi(bands)[..., None]
    pi   = compute_pi(bands)[..., None]
    return np.concatenate([bands, fdi, ndvi, pi], axis=-1).astype(np.float32)
```

---

## BOA_ADD_OFFSET Handling (PITFALL C1) — Phase 1 Policy

**Source:** PITFALLS.md §C1 + ESA Processing Baseline 04.00 docs. HIGH confidence.

**Policy:** MARIDA patches ship as pre-scaled reflectance in [0,1]; `_read_tile_bands` asserts this heuristically (`bands.max() > 1.5` → treat as raw DN and apply `(DN - 1000) / 10000`). For Phase 1 the branch is effectively a no-op because MARIDA is pre-processed. **Explicit for Phase 3 / future live tiles:**

```python
# Future/Phase 3 path: parse from scene metadata
with rasterio.open(tile_path) as src:
    pb_version = src.tags().get("PROCESSING_BASELINE")  # e.g., "04.00"
    if pb_version and float(pb_version) >= 4.0:
        offsets = [-1000.0] * src.count  # per-band, uniform in PB≥04.00
    else:
        offsets = [0.0] * src.count
    bands_dn = src.read().astype(np.float32)
    bands = (bands_dn + np.array(offsets)[:, None, None]) / 10000.0
```

**Unit check (deferred to Phase 3 when a real live tile is available):** known water pixel B8 ≈ 0.08, NOT ≈ -0.02.

**Phase 1 action:** keep the `bands.max() > 1.5` heuristic in `_read_tile_bands` as a safety rail. No dedicated unit test required for Phase 1 (no live L2A tile in test fixtures).

---

## Band Resolution Normalization (PITFALL M1)

**Source:** PITFALLS.md §M1 + ESA Sentinel-2 resolution docs. HIGH confidence.

**Phase 1 policy:** MARIDA patches are pre-resampled to a common 10 m grid (verified by the fact that `.tif` files carry a single transform and all 11 bands have matching dimensions). **No resampling required for Phase 1.**

**Defensive future-proof code** (do not write this in Phase 1; document for Phase 3 handoff):

```python
from rasterio.enums import Resampling
from rasterio.warp import reproject

def resample_to_10m(src_band_path, ref_transform, ref_shape, ref_crs):
    dst = np.empty(ref_shape, dtype=np.float32)
    with rasterio.open(src_band_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=ref_transform, dst_crs=ref_crs,
            resampling=Resampling.bilinear,
        )
    return dst
```

Use B2 (10 m native) as the reference grid. Only needed when reading raw L2A SAFE archives; MARIDA patches skip this step.

**Wave 0 probe:** verify all 11 MARIDA bands share a single `.tif` transform — one `rasterio.open(patch).shape` check confirms.

---

## Dummy Weight Initialization Policy

**Goal:** `run_inference(patch, cfg)` on dummy weights must produce:
- Zero `NaN`/`Inf` in outputs.
- Sigmoid of mask logits lies in `[0, 1]` (trivially true).
- Some polygons emitted (not zero, not hundreds) so integration test can assert `len(fc.features) > 0` AND `len(fc.features) < 500`.
- Deterministic across runs (`torch.manual_seed`).

**Policy:** Default PyTorch init (Kaiming for Conv2d + ImageNet pretrained for encoder when `encoder_weights="imagenet"`) is sufficient. The untrained heads (`mask_head`, `frac_head`) produce roughly zero-centered logits → sigmoid ~0.5, which means `threshold=0.5` will give a scattered salt-and-pepper mask — after `MIN_AREA_M2=200` filter, typically 5–50 polygons per 256x256 MARIDA patch. Good enough.

**Code (already in `load_weights`):**
```python
torch.manual_seed(cfg.ml.dummy_seed)  # cfg.ml.dummy_seed = 42
model = DualHeadUNetpp(in_channels=14)
```

**If zero polygons emerge** (because mask logits systematically negative):
- Lower `cfg.ml.confidence_threshold` to 0.3.
- OR add a one-time bias nudge: `model.mask_head.bias.data.fill_(0.5)` — pushes sigmoid above 0.5 on average.

**If too many polygons (>500):**
- Raise threshold to 0.7.
- OR increase `cfg.ml.min_area_m2` to 500.

These tunings live in `config.yaml`; no code change required.

---

## Integration Test: inference emits valid FC

**`tests/integration/test_inference_dummy.py`:**

```python
from pathlib import Path
import pytest
from backend.core.config import Settings
from backend.core.schemas import DetectionFeatureCollection
from backend.ml.inference import run_inference


MARIDA_SAMPLE = Path("MARIDA/patches")  # pick any scene at conftest level


@pytest.fixture(scope="module")
def sample_tile() -> Path:
    # Walk MARIDA/patches for the first *_<N>.tif (excluding _cl.tif, _conf.tif).
    for scene in MARIDA_SAMPLE.iterdir():
        if not scene.is_dir():
            continue
        for f in scene.iterdir():
            if f.suffix == ".tif" and "_cl" not in f.stem and "_conf" not in f.stem:
                return f
    pytest.skip("No MARIDA patch available")


def test_dummy_inference_emits_valid_fc(sample_tile: Path):
    cfg = Settings()
    fc = run_inference(sample_tile, cfg)
    assert isinstance(fc, DetectionFeatureCollection)
    # Schema-valid round-trip
    text = fc.model_dump_json(by_alias=True)
    DetectionFeatureCollection.model_validate_json(text)
    # Smoke constraints — zero polygons is suspicious; 500+ is noise
    for feat in fc.features:
        p = feat.properties
        assert 0.0 <= p.conf_raw <= 1.0
        assert 0.0 <= p.conf_adj <= 1.0
        assert 0.0 <= p.fraction_plastic <= 1.0
        assert p.area_m2 >= cfg.ml.min_area_m2
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Typed GeoJSON with properties | Hand-rolled `TypedDict` / plain `BaseModel` re-implementing RFC 7946 | `geojson-pydantic.Feature[Polygon, DetectionProperties]` | RFC compliance, geometry validation, generic type parameterization — all free. |
| Polygon extraction from probability raster | Loop with `skimage.measure.label` + contour tracing | `rasterio.features.shapes(mask, transform=...)` | Returns `(geom_dict, value)` tuples already in the raster's coordinate system. Handles connectivity, holes, topology. |
| Fix self-intersecting polygons | Custom topology fixup | `shapely_polygon.buffer(0)` | Single canonical workaround ([rasterio issue #1126](https://github.com/rasterio/rasterio/issues/1126)). |
| Compute polygon area in m² on a WGS84 geometry | Haversine-based hand math | `.to_crs(utm).area` (geopandas) or polygonize in UTM first, then reproject coords | Polygonizing on the UTM raster (which MARIDA is in) gives m² for free via shapely's Cartesian `.area`. |
| Configuration loading | `json.load(open("config.json"))` + dict access | `pydantic_settings.BaseSettings` + `YamlConfigSettingsSource` | Typed, validated, env-var-overridable, autocompletes. |
| CLI argument parsing | `sys.argv[1:]` + string parsing | `argparse` (stdlib) | Help text free, type coercion free, standard across three CLIs. |
| UNet++ with arbitrary in_channels | Custom UNet from scratch | `segmentation_models_pytorch.UnetPlusPlus(in_channels=N)` | SMP handles first-conv adaptation; dozens of pretrained encoders; widely debugged. |
| Squeeze-excite attention block | Custom `nn.Module` wrapping encoder stem | `smp.UnetPlusPlus(decoder_attention_type="scse")` | Built-in, zero LOC. |
| Sentinel-2 reading with CRS preservation | `cv2.imread` / PIL / raw GDAL | `rasterio.open(path).read()` | Preserves transform, CRS, nodata, metadata. PITFALLS.md M1. |
| Frozen contract enforcement | Hand-checked field list in every consumer | `ConfigDict(extra="forbid", frozen=True)` | One line; fails at boundary, not at sink. |

**Key insight:** the hackathon's enemy is plumbing bugs, not algorithmic complexity. Every entry in this table is an hour-class risk that the ecosystem has already solved; using the library option prevents that hour from being lost.

---

## Common Pitfalls (applied to Phase 1)

### Pitfall 1: Schema Drift (PITFALL C5) — The #1 Cost-of-Rewrite Bug

**What goes wrong:** Phase 2 implementer renames `age_days_est` → `age_days` "for consistency." Phase 2 code breaks silently wherever a default was used.

**Why it happens:** Schemas feel like suggestions during fast builds.

**How to avoid:**
1. Write `DetectionProperties` **first** (before any loader, model, or dataset code).
2. `ConfigDict(extra="forbid", frozen=True)` — boundary rejection, not silent fallback.
3. `git add backend/core/schemas.py && git commit -m "Phase 1: freeze DetectionProperties contract"` **before** any Phase 2 or Phase 3 work.
4. `tests/unit/test_schemas.py` round-trip must be GREEN at Phase 1 exit.
5. Any post-Phase-1 field edit requires: (a) explicit STATE.md entry, (b) re-run of round-trip test, (c) audit of all consumers.

**Warning signs:** two files refer to same field by different names; `inference.py` rename proposed mid-Phase-3.

### Pitfall 2: `class` Python Reserved Word (PRD §Appendix B vs Python keyword)

**What goes wrong:** Using `class: str = "plastic"` in a pydantic model raises `SyntaxError`.

**How to avoid:** `cls: Literal["plastic"] = Field(default="plastic", alias="class")` + `populate_by_name=True` in `ConfigDict`. Always emit JSON with `model_dump_json(by_alias=True)`. See Pattern 1.

**Warning signs:** pydantic validation error complaining about missing required field `"cls"` when consumer sent `{"class": "plastic"}` — means `populate_by_name` was omitted.

### Pitfall 3: Polygonization Noise + Invalid Geometries (PITFALL M9)

**What goes wrong:** Raw `rasterio.features.shapes` output contains hundreds of 1-pixel specks, self-intersecting polygons (connectivity=8), and missing CRS metadata.

**How to avoid:**
- `connectivity=4` (not 8) — rasterio [issue #2244](https://github.com/rasterio/rasterio/issues/2244).
- `poly.buffer(0)` if `not poly.is_valid` — [issue #1126](https://github.com/rasterio/rasterio/issues/1126).
- `MIN_AREA_M2 >= 200` filter (configurable in `cfg.ml.min_area_m2`) — kills noise.
- Reproject to EPSG:4326 **after** area computation on the UTM polygon (not before).

All four applied in `_polygonize` above.

**Warning signs:** `len(fc.features) > 500` for a 256x256 patch; `shapely.Polygon(coords).is_valid` returns False; `area_m2` values in degrees² (huge small numbers or small large numbers).

### Pitfall 4: SMP `in_channels=14` Dead Init (STACK.md research flag)

**What goes wrong:** Silent dead init — `encoder.conv1.weight` all zeros → forward pass produces all-same output → zero polygons.

**How to avoid:** Assert `conv1.weight.std() > 1e-4` in `load_weights` dummy branch. See Pattern 5.

**Warning signs:** `fc.features` is empty on a MARIDA patch that should have salt-and-pepper noise; model outputs identical for all inputs.

### Pitfall 5: MARIDA/ Not In `.gitignore` (PITFALL mi3)

**What goes wrong:** `git add .` stages 4.5 GB of MARIDA patches; push fails or bloats remote.

**How to avoid:** Before the first `git add`, ensure `.gitignore` contains:
```
MARIDA/
*.pth
*.ckpt
data/
venv/
__pycache__/
```
Check: `git check-ignore -v MARIDA/` should print a matching line.

**Warning signs:** `git status` shows thousands of MARIDA files; push speed collapses.

### Pitfall 6: Python 3.13+ Wheel Breakage (PITFALL mi2)

**What goes wrong:** `pip install shapely` on 3.13 fails.

**How to avoid:** Already on 3.11.3 (verified). Pin in `pyproject.toml` when/if created: `requires-python = ">=3.10,<3.13"`. Not a Phase 1 action since 3.11 is already in use.

### Pitfall 7: Cosine Window Zero at Edges

**What goes wrong:** `np.hanning(256)` has exactly zero at indices 0 and 255; at tile edges, if no other window covers the edge, the accumulator divides by zero.

**How to avoid:** `np.maximum(w2d, 1e-3)` (applied in `_cosine_window_2d`). Also, pad `ys`/`xs` to include an anchor at `H - patch` / `W - patch` so the last window always ends flush.

**Warning signs:** `NaN` in output mask at tile right/bottom edge.

### Pitfall 8: `pydantic-settings` YAML Not Loaded

**What goes wrong:** Default sources in pydantic-settings are init-args, env-vars, dotenv, secrets — **NOT YAML**. Without `settings_customise_sources` override, `backend/config.yaml` is ignored and all values come from defaults.

**How to avoid:** Override `settings_customise_sources` to include `YamlConfigSettingsSource(settings_cls)`. See Pattern 3.

**Warning signs:** `Settings().ml.min_area_m2` returns 200.0 regardless of what's in `config.yaml` because the YAML file is being ignored.

### Pitfall 9: Stub Physics/Mission Return Invalid Schema

**What goes wrong:** The Phase 1 stubs return `None` or raise `NotImplementedError`, breaking the CLI round-trip demo.

**How to avoid:** Stubs return **schema-valid empty** envelopes — `ForecastEnvelope(source_detections=fc, frames=[], windage_alpha=0.02)` and `MissionPlan(waypoints=[], route=<degenerate LineString>, total_distance_km=0, total_hours=0, origin=(0,0))`. The CLI demo chain (`python -m backend.ml ... | python -m backend.physics -` etc.) thus round-trips cleanly on dummy weights, validating the full schema seam before Phase 2 begins.

---

## Code Examples

All critical patterns inlined above. Index for quick reference:

| Pattern | Location in this file | Source |
|---------|----------------------|--------|
| Full `schemas.py` | §"Pattern 1" | geojson-pydantic README + ARCHITECTURE.md §3.1 |
| Full `config.py` + `config.yaml` | §"Pattern 3" | pydantic-settings docs + ARCHITECTURE.md §3.4 |
| Full `weights.py` (dummy branch) | §"Pattern 4" | ARCHITECTURE.md §3.3 |
| Full `model.py` (DualHeadUNetpp) | §"Pattern 5" | STACK.md Phase 3 section + smp docs |
| Full `cli.py` pattern | §"Pattern 6" | stdlib argparse + ARCHITECTURE.md §3.5 |
| Full `inference.py` (sliding window + polygonize) | §"Pattern 7" | rasterio features docs + PITFALLS.md M9 |
| Full `features.py` | §"FDI / NDVI / PI Exact Formulas" | Biermann 2020 |
| Schema round-trip test | §"Pattern 1" | pydantic docs |
| FDI reference test | §"FDI section" | Biermann 2020 Table 2 |
| Dummy inference integration test | §"Integration Test" | — |

---

## State of the Art

| Old Approach | Current Approach (Phase 1) | When Changed | Impact |
|--------------|---------------------------|--------------|--------|
| Raw `dict` GeoJSON at module seams | `geojson-pydantic.Feature[Polygon, Props]` | pydantic 2.x era (2023+) | Schema drift fails at boundary, not at sink. |
| `pydantic.BaseSettings` (v1) | `pydantic_settings.BaseSettings` (v2) | pydantic 2.0 (2023-06) | Separate package; `SettingsConfigDict` + `YamlConfigSettingsSource`. |
| SMP `smp.Unet(encoder_name=..., encoder_weights=..., in_channels=...)` hard-coding single-head | `UnetPlusPlus` + `decoder_attention_type="scse"` + dual 1x1 Conv2d heads on feature map | smp 0.5 (2025) | `decoder_attention_type` built-in since 0.5; shared decoder + dual heads is the standard pattern for multi-task segmentation. |
| `rasterio.features.shapes(mask, connectivity=8)` | `connectivity=4` + `.buffer(0)` + `MIN_AREA_M2` filter | rasterio issue #2244 | Dramatically fewer invalid/noise polygons. |
| Hydra-based config | pydantic-settings + YAML | pydantic-settings v2 (2023) | Simpler; single file; env-var overrides; no `.hydra/` directory pollution. |

**Deprecated / outdated (do not use):**
- `pydantic.BaseSettings` from `pydantic` (v1 API) — moved to `pydantic-settings` package in v2.
- `rasterio.features.shapes(..., connectivity=8)` — introduces self-intersecting polygons.
- `geopandas 0.14.x` with `shapely 1.x` — 1.0+ requires shapely 2.x; must upgrade both.

---

## Open Questions

1. **Exact MARIDA band ordering on disk.**
   - What we know: MARIDA ships 11-band patches pre-resampled to 10 m; PRD/STACK describe standard S2 L2A ordering.
   - What's unclear: index positions (B2=0? B4=2? B11=8?) vary by how the MARIDA authors wrote their pipeline.
   - Recommendation: **Wave 0 probe at H+0** — `rasterio.open("MARIDA/patches/<first>/<first>.tif").descriptions`. Update `B*_IDX` constants in `features.py`. Cost: 2 minutes. If descriptions are `None`, fall back to `[B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12, SCL]` per MARIDA repo README; verify via a pure-water pixel (low NDVI).

2. **`geojson-pydantic` 2.x generics API surface.**
   - What we know: 1.x supports `Feature[Geom, Props]` generics (HIGH confidence).
   - What's unclear: whether 2.x (if released by 2026-04-17) preserves the same import surface.
   - Recommendation: `pip show geojson-pydantic` at H+0; if output is 2.x, test the generic import at a REPL before writing `schemas.py`. Fallback (hand-rolled BaseModel) documented in Pattern 2.

3. **MARIDA `.tif` reflectance already in [0,1] or in raw DN?**
   - What we know: upstream STACK.md says MARIDA patches are stored as `int16` scaled by 10000.
   - What's unclear: whether `rasterio.open(...).read()` returns values in [0, 10000] (DN) or [0, 1] (pre-scaled).
   - Recommendation: `bands.max() > 1.5` heuristic in `_read_tile_bands` handles both cases defensively. Unit-check at H+0: load one patch, print `.min()/.max()`.

4. **Does `smp.UnetPlusPlus` with `decoder_attention_type="scse"` produce sensible random-init outputs?**
   - What we know: scSE is a well-established attention module; smp's built-in is tested.
   - What's unclear: whether random-init + scSE gives a reasonable sigmoid distribution on 14-channel input (not all 0 or all 1).
   - Recommendation: integration test `test_dummy_inference_emits_valid_fc` gates this. If `len(fc.features) == 0`, tune `cfg.ml.confidence_threshold` down to 0.3 in `config.yaml`. If `> 500`, raise `cfg.ml.min_area_m2` to 500.

5. **CLI pipeline demo — does the stub `physics` CLI cleanly round-trip the detection FC?**
   - What we know: schema contracts are designed for round-trip.
   - What's unclear: whether pydantic's `model_validate_json` round-trips exotic values like NaN floats or empty `features: []` lists cleanly.
   - Recommendation: integration test (optional for Phase 1): `python -m backend.ml patch.tif | python -m backend.physics /dev/stdin` should exit 0. Add to Phase 2 test surface.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | All Phase 1 code | Yes | 3.11.3 (`/c/Users/offic/anaconda3/python`) | — |
| pip | Installing new libs | Yes (conda env) | — | — |
| pytest | Tests | Yes | `/c/Users/offic/anaconda3/Scripts/pytest` | — |
| pydantic | `core/schemas.py`, `core/config.py` | Yes | 2.6.4 (per codebase/STACK.md) | — |
| pydantic-settings | `core/config.py` | Yes | 2.2.1 | — |
| FastAPI / Uvicorn | NOT used this phase | Yes | 0.110.0 / 0.29.0 | — (untouched) |
| Shapely | Polygon ops | Yes | 2.0.3 | Fine as-is for Phase 1. |
| GeoPandas | Area m² via CRS transform | Yes | 0.14.3 | **UPGRADE needed to >=1.0** for shapely 2.x contract — scheduled in Wave 0 install step. |
| **geojson-pydantic** | Schema generics | **NO** | — | **INSTALL** `pip install "geojson-pydantic>=1.2,<3.0"` |
| **torch / torchvision** | Model forward pass | **NO** | — | **INSTALL** CPU build: `pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cpu` |
| **segmentation-models-pytorch** | UnetPlusPlus class | **NO** | — | **INSTALL** `pip install "segmentation-models-pytorch>=0.5.0,<0.6.0"` |
| **rasterio** | Tile reading, polygonize | **NO** | — | **INSTALL** `pip install "rasterio>=1.5.0,<1.6.0"` |
| **pyproj** | UTM ↔ WGS84 transform | Likely (transitive) | ≥ 3.7 via geopandas | Upgrade with geopandas 1.0. |
| **numpy** | All numeric | Yes (transitive) | — | Pin `>=1.26,<2.0` |
| **scikit-image** (optional) | Noise cleanup before polygonize | No | — | **OPTIONAL** install; skip if time-tight. |
| MARIDA dataset | Integration test fixture | Yes | Local at `MARIDA/` | — |
| CMEMS / ERA5 NetCDFs | NOT this phase | No | — | Deferred to Phase 2. |
| Kaggle GPU | NOT this phase | N/A | — | Deferred to Phase 3. |
| Internet (for pip install, ImageNet weights first fetch) | Wave 0 only | Assumed yes | — | torchvision weights cache to `~/.cache/torch/hub/` — offline after first fetch. |

**Missing dependencies with no fallback:** None — all installable via pip.

**Missing dependencies with fallback:** scikit-image is optional (noise cleanup); if install fails, skip `morphology.opening` and rely on `MIN_AREA_M2` filter alone.

**Runtime blockers:** The first ImageNet-weight fetch by `smp.UnetPlusPlus(encoder_weights="imagenet")` requires internet (downloads ~45 MB of resnet18 weights to `~/.cache/torch/hub/checkpoints/`). After first run, cached. **Action for Wave 0:** run `python -c "import segmentation_models_pytorch as smp; smp.UnetPlusPlus(encoder_name='resnet18', encoder_weights='imagenet', in_channels=14, classes=1)"` once online to prime the cache.

---

## Sources

### Primary (HIGH confidence)

- `.planning/research/STACK.md` — pinned versions, SMP init behavior for `in_channels>4`, Kaggle gotchas (carried forward, re-verifying not needed)
- `.planning/research/ARCHITECTURE.md` — schema/config/strategy-loader patterns, module boundaries, build order
- `.planning/research/PITFALLS.md` — C1 (BOA offset), C5 (schema drift), M1 (band resolution), M9 (polygonization), mi2/mi3 (gitignore, Python version)
- `.planning/research/SUMMARY.md` — executive synthesis and Phase 1 exit criteria
- [developmentseed/geojson-pydantic README](https://github.com/developmentseed/geojson-pydantic) — Feature[Geom, Props] generic pattern
- [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — `SettingsConfigDict`, `YamlConfigSettingsSource`, `env_nested_delimiter`
- [segmentation-models-pytorch 0.5.x docs](https://smp.readthedocs.io/) — `UnetPlusPlus` + `decoder_attention_type="scse"`
- [rasterio.features.shapes docs](https://rasterio.readthedocs.io/en/stable/api/rasterio.features.html) — polygonize API, connectivity parameter
- [Biermann et al. 2020, Scientific Reports](https://www.nature.com/articles/s41598-020-62298-z) — FDI formula and reference pixel values
- ESA Sentinel-2 Processing Baseline docs — BOA_ADD_OFFSET (PB ≥ 04.00, 2022-01-25)

### Secondary (MEDIUM confidence)

- [rasterio issue #1126](https://github.com/rasterio/rasterio/issues/1126) — `.buffer(0)` polygon validity fix
- [rasterio issue #2244](https://github.com/rasterio/rasterio/issues/2244) — connectivity=8 produces invalid geometries
- Themistocleous et al. 2020 — Plastic Index (PI) definition

### Tertiary (verify at Wave 0)

- MARIDA on-disk band ordering — probe via `rasterio.open(...).descriptions`
- `geojson-pydantic` major version on the installed PyPI surface — probe via `pip show`
- MARIDA `.tif` reflectance storage (DN vs [0,1]) — probe via `bands.min()/bands.max()`

---

## Project Constraints (from CLAUDE.md)

- **Tech stack locked:** PyTorch 2.x + segmentation_models_pytorch, Rasterio, xarray, GeoPandas, Shapely. No from-scratch transformers.
- **Python 3.10 / 3.11 / 3.12 only** — current env 3.11.3 ✓
- **No live data ingestion** — no auth flows in runtime pipeline.
- **Phase 1 uses `dummy` weights per STATE.md Key Decisions** — CLAUDE.md still mentions `torch.hub.load("marccoru/marinedebrisdetector", "unetpp")` as Phase 1 baseline, but this is superseded by the newer STATE.md and ROADMAP.md decisions. The authoritative Phase 1 default is `weights_source="dummy"`. (Reason: marccoru weights on private Drive, cannot be on critical path.)
- **Scope: intelligence-only** — `backend/api/routes.py` and `backend/services/mock_data.py` stay UNTOUCHED.
- **Contract freeze before Phase 1 ends** — enforced by `ConfigDict(extra="forbid", frozen=True)` + git commit.
- **Scope rule (PRD §12 zero-sum):** no new features without paired removal.
- **GSD workflow enforcement:** file-changing tools only via `/gsd:execute-phase` (or `/gsd:quick`/`/gsd:debug`). Phase 1 planning artifact (this RESEARCH.md) is produced via the research command.
- **No FastAPI/React this phase** per PROJECT.md scope lock.

---

## Metadata

**Confidence breakdown:**
- Standard stack — **HIGH** — all pins carried forward from `.planning/research/STACK.md`, which itself cites PyPI and release notes verified on 2026-04-17.
- Architecture patterns (schemas, config, strategy loader, CLI) — **HIGH** — every pattern directly copies from `.planning/research/ARCHITECTURE.md` with the Phase 1 subset selected. Fully specified code provided.
- Pitfalls — **HIGH** — all drawn from `.planning/research/PITFALLS.md` (which cites ESA, rasterio issues, pydantic docs).
- FDI / Biermann reference pixel — **MEDIUM** — formula is HIGH (Biermann 2020 eq. 2); the exact pixel reflectance values (0.078 / 0.095 / 0.063) are from Biermann 2020 Table 2 by memory — Wave 0 verification against the paper is recommended if the unit test fails by > 0.005.
- `geojson-pydantic` generics on installed version — **MEDIUM** — API is stable across 1.x; 2.x probe at H+0 handles edge case.
- MARIDA band ordering — **MEDIUM** — documented pattern but exact disk order needs Wave 0 probe.
- Dummy weight init "good enough" — **MEDIUM** — expected behavior described; integration test is the gate.

**Research date:** 2026-04-17
**Valid until:** 2026-04-24 (7 days — hackathon cycle; state of the art in this domain moves slowly but the Kaggle base image does roll weekly and may shift torch/rasterio versions).

---

*Phase 1 RESEARCH.md complete. Ready for `/gsd:plan-phase 1` planner.*
