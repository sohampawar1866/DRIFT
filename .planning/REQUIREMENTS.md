# Requirements: DRIFT / PlastiTrack — Backend Intelligence

**Defined:** 2026-04-17
**Core Value:** A single Python function chain `run_inference(tile) → forecast_drift(detections) → plan_mission(forecast)` must produce a valid cleanup mission plan end-to-end from a real Sentinel-2 tile — in under 15 seconds, with detection IoU ≥ 0.45 on MARIDA val.

Source docs: `.planning/PROJECT.md` · `.planning/research/SUMMARY.md` · `.planning/research/{STACK,FEATURES,ARCHITECTURE,PITFALLS}.md` · `PRD.md`

## v1 Requirements

Requirements for this milestone. Each maps to exactly one roadmap phase via Traceability below.

### Infrastructure (INFRA)

Core scaffolding that every downstream module consumes. Cannot be deferred.

- [ ] **INFRA-01**: Frozen `DetectionProperties` pydantic model (`extra="forbid", frozen=True`) with fields `conf_raw: float`, `conf_adj: float`, `fraction_plastic: float`, `area_m2: float`, `age_days_est: int`, `class: str = "plastic"` (aliased via pydantic `Field(alias="class")`). Defined in `backend/core/schemas.py`. Schema round-trip test passes. Schema is git-committed and frozen at Phase 1 exit.
- [ ] **INFRA-02**: Typed `DetectionFeatureCollection = FeatureCollection[Feature[Polygon, DetectionProperties]]` and `ForecastEnvelope`, `MissionPlan` companion schemas (using `geojson-pydantic`). All three public entry points consume/return these types exclusively.
- [ ] **INFRA-03**: `backend/core/config.py` — pydantic-settings + single `config.yaml` driving nested `MLSettings`, `PhysicsSettings`, `MissionSettings`. Env-var overrides via `env_nested_delimiter="__"` (e.g., `ML__WEIGHTS_SOURCE=our_real`). No Hydra.
- [ ] **INFRA-04**: Strategy-pattern weight loader `backend/ml/weights.py` — `load_weights(cfg) -> nn.Module` switching on `cfg.ml.weights_source ∈ {"dummy", "marccoru_baseline", "our_real"}`. Phase 3 weight swap is a single YAML-line change; physics/mission modules cannot observe the difference.
- [ ] **INFRA-05**: `backend/ml/checkpoints/` ignored by git; checkpoint transfer via `kagglehub` (Kaggle → laptop cache at `~/.cache/kagglehub/`). Offline-safe: once downloaded, demo runs with no network.
- [ ] **INFRA-06**: CLI entrypoints `python -m backend.ml <tile>`, `python -m backend.physics <detections.json>`, `python -m backend.mission <forecast.json>` for standalone module invocation (no API dependency).

### Machine Learning / Detection (ML)

- [ ] **ML-01**: `backend/ml/features.py` — pure NumPy FDI (Biermann 2020), NDVI, PI (Themistocleous 2020). Single source of truth for train+serve. Unit test: known water pixel → FDI within 0.001 of Biermann published value.
- [ ] **ML-02**: `backend/ml/dataset.py` — MARIDA loader reading `MARIDA/splits/{train,val,test}_X.txt` → tuples of (11-band `.tif`, `_cl.tif` mask, `_conf.tif` weight). Normalizes reflectance with S2 L2A BOA_ADD_OFFSET (−1000 DN then /10000); excludes `_conf.tif == 0` pixels from loss; handles B6/B11 resample to 10 m reference.
- [ ] **ML-03**: `backend/ml/model.py` — `segmentation_models_pytorch.UnetPlusPlus(encoder_name="resnet18", encoder_weights="imagenet", in_channels=14, classes=1)` with SE spectral-attention block at encoder stem; **dual output heads**: binary plastic mask + fractional-cover regression. Assert `model.encoder.conv1.weight.std() > 0` to catch dead-init on `in_channels=14`.
- [ ] **ML-04**: `backend/ml/inference.py` — `run_inference(tile_path, cfg) -> DetectionFeatureCollection`. Sliding 256×256 windows with stride-128 overlap and cosine-blended stitching; threshold + `rasterio.features.shapes` polygonization with `.buffer(0)` fix and `area_m2 >= MIN_AREA_M2` filter; pydantic-validated output. **Phase 1 runs on `dummy` weights** (lightweight random init) so the pipeline is schema-complete before real weights exist.
- [ ] **ML-05**: `backend/ml/train.py` — Kaggle-ready 25-epoch training loop: Adam 1e-4, cosine schedule, Dice + pos-weighted BCE on binary head (pos_weight ≈ 40 to counter ~2% plastic pixels), MSE ×0.3 on fraction head. Uses `_conf.tif` as per-pixel weight. No `torch.compile`, no `bfloat16`. Saves best-IoU checkpoint via `kagglehub.model_upload`.
- [ ] **ML-06**: Sub-pixel fraction regression head — training data augmented with alpha-blended plastic×water at α ∈ {0.05, 0.1, 0.2, 0.4}. Target: **MAE ≤ 0.15** on synthetic held-out val. Populates `fraction_plastic` at inference.
- [ ] **ML-07**: Biofouling instrumentation — (a) training-time augmentation: multiply NIR (B8) and RedEdge (B6/B7) by `uniform(0.5, 1.0)` on 40% of positive samples with synthetic age label; (b) inference-time decay: `conf_adj = conf_raw · exp(−age_days_est / 30)` applied in post-processing.
- [ ] **ML-08**: Phase 3 metric targets met on MARIDA val: **IoU ≥ 0.45**, **precision @ conf > 0.7 ≥ 0.75**, **Sargassum false-positive rate ≤ 15%** (class 2/3 confusion). Metrics logged from final epoch and saved to `.planning/metrics/phase3.json`.
- [ ] **ML-09**: Optional 15-class multi-class auxiliary head (weight 0.1) for regularization — helps disambiguate plastic (class 1) from dense/sparse Sargassum (classes 2, 3), ships, foam, wakes. Defer if training budget tight.

### Physics / Trajectory (PHYS)

- [ ] **PHYS-01**: `backend/physics/env_data.py` — loads pre-staged CMEMS surface currents (u/v, 1/12°, hourly) + ERA5 10 m winds (u10/v10, 0.25°, hourly) NetCDFs via `xarray`. Bilinear interp at `(lon, lat, t)`. Normalizes lon to -180..180; correctly handles scalar vs. time-dim coordinate. Loaded via `copernicusmarine.open_dataset()` at fetch time (not runtime) — **NOT the deprecated motuclient/OPeNDAP**.
- [ ] **PHYS-02**: `scripts/fetch_demo_env.py` — one-shot fetch script pulling 7-day CMEMS + ERA5 slices clipped to the union of 4 AOI bounding boxes. Saves to `data/env/*.nc`. Reads credentials from env vars; documented in README.
- [ ] **PHYS-03**: `backend/physics/tracker.py` — Euler Lagrangian integrator. `forecast_drift(detections, cfg) -> ForecastEnvelope`. **Integrates in UTM meters, not lon/lat degrees** (prevents the 55-km-per-second CRS bug); converts back to WGS84 for output. Per detection: seed 20 particles at polygon centroid with ±50 m jitter; hourly dt for 72 h horizon; `v_total = v_current + 0.02 * v_wind` (windage α=0.02). Returns 73 frames (0..72) + density polygons at +24/+48/+72 h via `sklearn.neighbors.KernelDensity`.
- [ ] **PHYS-04**: Synthetic-field unit test (`backend/physics/test_tracker.py`): constant 0.5 m/s eastward current → 43.2 km displacement over 24 h ±1%. Zero-field test: particle stays put. **This test gates Phase 2 exit.**
- [ ] **PHYS-05**: Real-data smoke test: seed 10 particles at Gulf of Mannar (78.9 E, 9.2 N) using real CMEMS+ERA5 slice; all particles remain within Indian Ocean basin; none cross land (visual check against GSHHG coastline).

### Mission Planning (MISSION)

- [ ] **MISSION-01**: `backend/mission/scoring.py` — priority score per detection = `conf_adj × area_m2 × fraction_plastic × forecast_convergence_bonus`. Forecast-convergence bonus favors hotspots where the +72 h KDE density is *higher* than +0 h (debris concentrating, not dispersing).
- [ ] **MISSION-02**: `backend/mission/planner.py` — `plan_mission(forecast, vessel_range_km, hours, origin_lonlat, cfg) -> MissionPlan`. Greedy nearest-neighbor TSP with 2-opt improvement; enforces vessel range AND time budget (prune tour when cumulative distance × avg speed exceeds `hours`). Returns ordered waypoints + `LineString` route + summary.
- [ ] **MISSION-03**: `backend/mission/export.py` — exports GPX (`togpx`), GeoJSON (pydantic `.model_dump_json()`), and **printable PDF briefing** (`matplotlib` + `reportlab`: vessel route over EEZ map, waypoint table, ETA, fuel estimate, wind/current conditions at each stop). PDF is the differentiator for judging.

### End-to-End (E2E)

- [ ] **E2E-01**: `backend/e2e_test.py` — full chain on one MARIDA val patch → `run_inference` → `forecast_drift` (with synthetic or real env slice) → `plan_mission`. Asserts schema validation passes at every boundary; total wall-clock < 15 s on CPU laptop.
- [ ] **E2E-02**: Pre-baked 4-AOI fallback JSONs at `data/prebaked/{aoi}_{stage}.json` computed at H+28. Dashboard / demo can load these directly if live inference fails mid-pitch. Fallback parity test: live output hash === pre-baked hash on the 4 demo tiles.

## v2 Requirements

Deferred — tracked but NOT in this 24–48 h milestone.

### FastAPI integration

- **API-01**: Replace `backend/services/mock_data.py` calls in `backend/api/routes.py` with real `run_inference / forecast_drift / plan_mission` invocations behind the existing `/api/v1/*` surface.
- **API-02**: Add `GET /api/v1/aois` endpoint listing the 4 demo AOIs per PRD §Appendix B.
- **API-03**: Reconcile query-param contract drift (`aoi_id` → `aoi` + `date` per PRD) and replace `{"error": ...}` dict returns with `HTTPException`.

### Frontend

- **FE-01..**: Full React + Vite + Mapbox + deck.gl + Recharts dashboard per PRD §6 (F2-F7). Not this milestone.

### Performance / deployment

- **OPS-01**: Docker Compose single-laptop bundle.
- **OPS-02**: ONNX/TensorRT inference path.
- **OPS-03**: Model quantization.

## Out of Scope

Explicitly excluded for this milestone. Do NOT re-litigate.

| Feature | Reason |
|---|---|
| Live Sentinel-2 ingestion (STAC API, Sentinel Hub auth) | PRD §12 scope guardrail; runtime auth is a rabbit hole; pre-staged tiles only |
| Multi-satellite fusion (Sentinel-1 SAR, Sentinel-3 OLCI, PlanetScope) | PRD §12; blows the 24–48 h budget |
| OpenDrift / Parcels / full 3D hydrodynamics / Stokes drift beyond 2% windage | Euler + windage α=0.02 is defensible for 72 h (PRD §4, published tracker errors 13–16 km) |
| ViT / Segformer from scratch | MARIDA's 1,381 patches too small (PRD §8.1); UNet++ w/ ImageNet encoder is the sweet spot |
| User accounts, OAuth, RBAC | PRD §12; intelligence-only milestone |
| Mobile app / UAV dispatch / automated USV coordination | PRD §12 |
| 3D globe (Cesium) | PRD §12; Mapbox 2D (future milestone) is enough |
| Cloud deployment (AWS/GCP) | PRD §12; single-laptop demo reduces judging-day risk |
| ONNX / TensorRT / on-device inference | Premature optimization for a 24-h build |
| Custom dataset labeling UI | MARIDA + FloatingObjects are sufficient labels |
| Real-time websocket updates / dashboards | Not in intelligence-only scope |
| Dark mode / i18n / theming / user settings | PRD §12 |
| FastAPI endpoint wiring, React/Mapbox frontend | Scoped OUT by user on 2026-04-17 — this milestone is intelligence-only |
| PyTorch Lightning / W&B / Hydra / AlbumentationsX | Adds auth/config friction with zero demo value (SUMMARY.md) |
| Live CMEMS API fetch at inference time | Pre-stage 7-day NetCDF slice; runtime has no network dependency |
| marccoru pretrained weights as default Phase 1 baseline | Weights on private Google Drive since Aug 2024 (PITFALLS.md) — not auto-fetchable, cannot be on critical path. `dummy` branch is Phase 1 default. |

## Traceability

Confirmed during roadmap creation 2026-04-17. All 25 v1 requirements map to exactly one phase. See `.planning/ROADMAP.md` for phase success criteria and risk flags.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Pending |
| INFRA-04 | Phase 1 | Pending |
| INFRA-05 | Phase 3 | Pending |
| INFRA-06 | Phase 1 | Pending |
| ML-01 | Phase 1 | Pending |
| ML-02 | Phase 3 | Pending |
| ML-03 | Phase 1 | Pending |
| ML-04 | Phase 1 | Pending |
| ML-05 | Phase 3 | Pending |
| ML-06 | Phase 3 | Pending |
| ML-07 | Phase 3 | Pending |
| ML-08 | Phase 3 | Pending |
| ML-09 | Phase 3 | Pending |
| PHYS-01 | Phase 2 | Pending |
| PHYS-02 | Phase 2 | Pending |
| PHYS-03 | Phase 2 | Pending |
| PHYS-04 | Phase 2 | Pending |
| PHYS-05 | Phase 2 | Pending |
| MISSION-01 | Phase 2 | Pending |
| MISSION-02 | Phase 2 | Pending |
| MISSION-03 | Phase 3 | Pending |
| E2E-01 | Phase 3 | Pending |
| E2E-02 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0 ✓

**Per-phase counts:**
- Phase 1 (Schema Foundation + Dummy Inference): 8 requirements
- Phase 2 (Trajectory + Mission Planner): 7 requirements
- Phase 3 (Real Training + Weight Swap + Mission Export + E2E): 10 requirements

---
*Requirements defined: 2026-04-17*
*Last updated: 2026-04-17 after roadmap creation (traceability confirmed)*
