# Project Research Summary

**Project:** DRIFT / PlastiTrack — Backend Intelligence Layer
**Domain:** Satellite marine-plastic ML detection + Lagrangian ocean-drift forecasting + cleanup mission planning (Python-only backend, hackathon scope)
**Researched:** 2026-04-17
**Confidence:** HIGH (stack and pitfalls verified against official sources); MEDIUM (marccoru weight-hosting specifics, SMP first-conv init behavior)

---

## Executive Summary

DRIFT is a three-function Python intelligence pipeline that must run end-to-end in under 15 seconds on a CPU laptop and produce schema-valid GeoJSON at every stage. The domain is well-studied (MARIDA benchmark, Sentinel-2 L2A preprocessing, CMEMS Lagrangian drift) but carries several silent-failure traps: a reflectance-offset bug introduced in Sentinel-2 Processing Baseline 04.00 (post-2022-01-25), a pretrained-weights hosting problem that makes the marccoru baseline non-auto-fetchable, and class-imbalance collapse if the training loss is not carefully designed. The recommended approach is a strict three-phase split: Phase 1 ships a dummy-weight inference path to freeze the schema and unblock downstream modules; Phase 2 builds the Lagrangian tracker and mission planner against that frozen schema; Phase 3 trains on Kaggle GPU and hot-swaps weights via a one-YAML-line config change.

The highest-leverage architectural discipline is a frozen Pydantic schema at every module seam, enforced from the first hour of Phase 1. All three modules (ml/, physics/, mission/) communicate exclusively through typed pydantic models backed by geojson-pydantic; raw dicts and GeoDataFrames never cross a module boundary. The strategy-pattern weight loader load_weights(cfg)->nn.Module with three branches (dummy, marccoru_baseline, our_real) is the single seam between Phase 1 and Phase 3; flipping cfg.ml.weights_source in config.yaml performs the swap without touching any other module. Physics and mission code can therefore be built and tested in parallel against dummy outputs, which is the only way to fit the 36-hour feature-freeze constraint.

The primary risks are: (1) marccoru pretrained weights require a manual Google Drive download and must not be placed on the critical path; (2) Sentinel-2 L2A tiles acquired after 2022-01-25 require a BOA_ADD_OFFSET correction of -1000 DN before dividing by 10000 or model confidence collapses silently; (3) Kaggle GPU assignment is non-deterministic (P100 or T4x2), forbidding torch.compile and bfloat16 - use fp16 autocast only; (4) schema drift between Phase 1 dummy stubs and Phase 3 real outputs is the single highest-cost bug class and must be prevented by Pydantic validation at every stage boundary from hour one.

---

## Key Findings

### Recommended Stack

The stack is fully pip-installable and centered on Python 3.11. PyTorch 2.7 is the last version with validated support for both P100 (compute capability 6.0) and T4 (7.5). segmentation-models-pytorch>=0.5,<0.6 provides the UNet++ dual-head with arbitrary in_channels. xarray 2026.2.0 requires Python 3.11+ and handles CMEMS/ERA5 bilinear interpolation. On Kaggle, only segmentation-models-pytorch and albumentations==2.0.14 need explicit pip install. Skip W&B, PyTorch Lightning, and OpenDrift entirely.

**Core technologies:**
- **Python 3.11** - sweet spot for all geospatial wheels; matches Kaggle kernel
- **PyTorch 2.7 + torchvision 0.22** - last version with P100+T4 dual support; avoid torch.compile and bfloat16
- **segmentation-models-pytorch 0.5.x** - UNet++ with ResNet-18 encoder, arbitrary in_channels; handles channel adaptation internally
- **rasterio 1.5.x** - Sentinel-2 COG reading, polygonization via shapes(); never use cv2.imread or GDAL bindings directly
- **xarray 2026.2.0 + netCDF4 1.7.2** - CMEMS and ERA5 lazy loading and bilinear interp(lon=, lat=, time=)
- **shapely 2.x + geopandas 1.x + pyproj 3.7+** - geometry, CRS transforms, GeoJSON serialization; install shapely before geopandas on Windows
- **geojson-pydantic** - typed GeoJSON contract layer at every module seam; the preferred mechanism to prevent Phase 1 to Phase 3 schema drift
- **pydantic-settings + YAML** - single config.yaml with env-var overrides; skip Hydra
- **kagglehub** - weight upload/download between Kaggle training and laptop demo; primary checkpoint transfer mechanism
- **scikit-image 0.24+** - morphological opening before polygonization to eliminate single-pixel noise
- **scikit-learn 1.5+** - KernelDensity for KDE forecast polygons at +24/+48/+72 h

**What NOT to use:** torch.compile (fails on P100), bfloat16 (not supported on T4), motuclient/OPeNDAP (dead since April 2024 - use copernicusmarine.open_dataset()), albumentationsx (AGPL), PyTorch Lightning, W&B, Python 3.9 or 3.13+.

### Expected Features

The milestone delivers three Python-callable functions only. No FastAPI wiring, no frontend.

**Must have (table stakes):**
- T1: Binary plastic segmentation (UNet++ + ResNet-18) - IoU >= 0.45 on MARIDA val
- T2: Per-pixel confidence score conf_raw as sigmoid output
- T3: Polygonization to GeoJSON FeatureCollection with frozen schema {conf_raw, conf_adj, fraction_plastic, area_m2, age_days_est, class}
- T4: Water/land/cloud masking (SCL band + GSHHG coastline)
- T5: FDI + NDVI + PI spectral indices (Biermann 2020 / Themistocleous 2020)
- T6: Lagrangian Euler tracker: 20 particles/detection, windage alpha=0.02, 72 h, CMEMS + ERA5
- T7: Per-hour trajectory frames (73 frames, 0..72)
- T8: Greedy + 2-opt nearest-neighbor TSP mission planner
- T9: Priority scoring: conf_adj x area_m2 x fraction_plastic
- T10: Vessel range and time budget constraint enforcement
- T11: Full chain < 15 s on CPU laptop
- T12: Frozen schema validated at every stage boundary
- T13: CLI entrypoint (python -m drift.demo)

**Should have (P1 differentiators):**
- D1: Sub-pixel fractional-cover regression head (directly answers SKB_P5 challenge A; MAE <= 0.15)
- D2+D3+D4: Biofouling trio: NIR x [0.5,1.0] augmentation on 40% positives (D4), age regression head (D3), confidence decay conf_adj = conf_raw x exp(-age/30) (D2)
- D7: Multi-class disambiguation (plastic vs. Sargassum FPR <= 15%)

**Should have (P2, add at H28-H36):**
- D5: Ensemble spread (N=20 perturbed particles)
- D6: KDE density polygons at +24/+48/+72 h
- D10: PDF mission briefing (matplotlib + reportlab) - very high judge value
- D8: Forecast-convergence bonus in priority score
- D9: Per-waypoint forecast summary on mission output
- D11: Deterministic seeding
- D12: End-to-end pytest smoke test

**Defer (anti-features - non-negotiable per PRD Section 12):**
- Live Sentinel-2 ingestion, OpenDrift/full 3D hydrodynamics, multi-satellite fusion, FastAPI endpoint wiring, React/Mapbox frontend, ViT/Segformer from scratch, ONNX/TensorRT, cloud deployment, RBAC, OAuth

### Architecture Approach

The architecture is a strict unidirectional pipeline with three sibling modules (backend/ml/, backend/physics/, backend/mission/) that depend only on backend/core/ (shared schemas, config, logging). Modules communicate exclusively via frozen pydantic models; no raw dicts, no GeoDataFrames cross a module boundary. Each module exposes one public entry point (run_inference, forecast_drift, plan_mission) and a thin cli.py for standalone invocation. The strategy-pattern weight loader in ml/weights.py branches on cfg.ml.weights_source in {dummy, marccoru_baseline, our_real}, making the Phase 1 to Phase 3 weight swap a single YAML line change invisible to physics/ and mission/.

**Major components:**
1. core/schemas.py - FROZEN pydantic contracts (DetectionProperties, DetectionFeatureCollection, ForecastEnvelope, MissionPlan) with extra=forbid; geojson-pydantic Feature[Polygon, DetectionProperties] generics.
2. core/config.py - pydantic-settings + YAML; nested MLSettings, PhysicsSettings, MissionSettings; env-var overrides (ML__WEIGHTS_SOURCE=our_real) for demo-day tweaks.
3. ml/features.py - Pure numpy FDI/NDVI/PI; single source of truth called from both dataset.py (training) and inference.py (serving) to prevent training-serving skew.
4. ml/weights.py - Strategy-pattern loader with dummy (default Phase 1), marccoru_baseline (optional Phase 2 bonus), our_real (Phase 3 Kaggle checkpoint via kagglehub).
5. ml/inference.py - Entry: run_inference(tile_path, cfg) -> DetectionFeatureCollection. Orchestrates: rasterio read, features.feature_stack, model forward, threshold, rasterio.features.shapes, pydantic validation.
6. physics/env_data.py + tracker.py - Entry: forecast_drift(detections, cfg) -> ForecastEnvelope. Euler integrator, UTM-meter positions converted back to WGS84; xarray bilinear interp for CMEMS/ERA5.
7. mission/scoring.py + planner.py + export.py - Entry: plan_mission(forecast, range_km, hours, origin, cfg) -> MissionPlan. Greedy nearest-neighbor TSP with budget-aware pruning; GPX + GeoJSON + optional PDF output.
8. tests/ - Three mandatory: FDI formula vs. Biermann 2020 pixel, synthetic-field tracker (0.5 m/s x 24h = 43.2 km +/- 1%), schema round-trip.

### Critical Pitfalls

1. **Sentinel-2 L2A BOA_ADD_OFFSET (C1, CRITICAL)** - Tiles acquired after 2022-01-25 (Processing Baseline >= 04.00) require reflectance = (DN + (-1000)) / 10000.0. Skipping shifts inputs by -0.1 relative to MARIDA training distribution; model confidence collapses silently to near-zero. Fix: parse BOA_ADD_OFFSET_VALUES_LIST from scene metadata; unit-test a known water pixel gives B8 ~= 0.08, not -0.02.

2. **Schema drift Phase 1 to Phase 3 (C5, CRITICAL)** - A field rename during Phase 3 (age_days vs age_days_est) silently breaks the tracker and planner. Prevention: Pydantic DetectionProperties with extra=forbid validated at every stage boundary from Phase 1 hour one. Schema freeze is the Phase 1 exit criterion.

3. **marccoru weights NOT auto-fetchable (CRITICAL)** - Repo owner moved weights to private Google Drive in August 2024. torch.hub.load() fetches code but not weights. The dummy branch must be the real Phase 1 default; marccoru_baseline is an optional Phase 2 bonus requiring one-time manual download. Do not place this on the critical path.

4. **Kaggle GPU disabled by default + non-deterministic assignment (C6, CRITICAL)** - enable_gpu is currently false in kaggle.yml. Flip before Phase 3. Kaggle may assign P100 (sm_60) or T4x2 non-deterministically; code must avoid torch.compile and bfloat16. Use fp16 autocast only. Assert torch.cuda.is_available() as cell 1.

5. **CRS unit confusion in Lagrangian tracker (C4, CRITICAL)** - lon += u * dt with u in m/s and lon in degrees moves a particle ~55 km per second at the equator. Integrate in UTM meters, convert to WGS84 for output only. Enforce with synthetic 43.2 km / 24h unit test before any real CMEMS data.

6. **Plastic class imbalance to loss collapse (C3)** - ~1-3% plastic pixels; unweighted BCE predicts all-zero at epoch 1. Use Dice + weighted BCE with positive-class weight = N_negative/N_positive (typically 30-60x).

7. **MARIDA _conf.tif misuse (C2)** - conf==0 means unlabeled, not confident no-plastic. Weight the loss by conf/3.0 and zero out nodata before summing. Val IoU plateauing below 0.3 after 10 epochs is the warning sign.

---

## Implications for Roadmap

Suggested phase structure (3 phases, matching PROJECT.md Key Decisions):

### Phase 1: Schema Foundation + Dummy Inference
**Rationale:** Nothing downstream can be built without a frozen schema. The dummy branch makes this the fastest possible unblocking move - schema-valid GeoJSON with untrained weights in ~4 hours, unblocking Phase 2 work immediately. marccoru weights must NOT be the Phase 1 default because they require manual Google Drive download (ARCHITECTURE.md Section 5). Dummy-first de-risks the weight-swap seam before committing Kaggle GPU budget.
**Delivers:** run_inference(tile_path, cfg) -> DetectionFeatureCollection on dummy weights; frozen DetectionProperties pydantic schema in core/schemas.py; FDI/NDVI/PI features with Biermann 2020 unit test; SCL cloud mask and band-resolution normalization to 10 m reference grid; polygonization with .buffer(0) and MIN_AREA_M2; schema round-trip test passing.
**Addresses features:** T1 (dummy), T2, T3, T4, T5, T12, T13 stub.
**Avoids pitfalls:** C5 (schema drift), C1 (S2 L2A offset), M1 (band resolution), M6 (cloud mask), M9 (polygonization artifacts).
**Exit criterion:** Schema frozen in git. python -m backend.ml data/staged/gulf_of_mannar.tif emits schema-valid GeoJSON. FDI formula and schema round-trip tests pass.
**Research flag:** SKIP - patterns are well-documented and fully specified in ARCHITECTURE.md and PITFALLS.md.

### Phase 2: Lagrangian Tracker + Mission Planner
**Rationale:** Physics and mission modules can be built in parallel against Phase 1 frozen schema using synthetic fixture FCs, without waiting for real trained weights. CMEMS + ERA5 NetCDFs must be pre-staged; scripts/fetch_demo_env.py is a prerequisite. The synthetic 43.2 km / 24h unit test must be written FIRST and pass BEFORE plugging in real environment data.
**Delivers:** forecast_drift(detections, cfg) -> ForecastEnvelope (20 particles/detection, 73 hourly frames, KDE polygons at +24/+48/+72 h); plan_mission(forecast, ...) -> MissionPlan (greedy TSP with budget constraint, edge-case handling for 0/1/N-out-of-range detections); GPX + GeoJSON export; E2E smoke test on dummy weights < 15 s.
**Addresses features:** T6, T7, T8, T9, T10, T11, D5, D6 (if time), D8 (if time), D9 (if time).
**Avoids pitfalls:** C4 (CRS/UTM units), M2 (beaching NaN), M3 (time-axis misalignment), M4 (lon 0-360 vs -180-180), M5 (windage vector direction), M10 (TSP edge cases).
**Exit criterion:** Synthetic 43.2 km test passes. Full chain on dummy weights completes < 15 s and produces schema-valid outputs at each stage.
**Research flag:** SKIP - standard Euler integration and greedy TSP are textbook; CMEMS/ERA5 xarray patterns fully documented; lon-convention normalization fully specified in PITFALLS.md M4.

### Phase 3: Real Training on Kaggle + Weight Swap + Mission Polish
**Rationale:** Training is the longest clock-wall task (~60-90 min on Kaggle GPU). It must be queued as soon as Phases 1 and 2 are functional. All training decisions must be pre-committed before the Kaggle run starts, because mid-run corrections waste the weekly GPU quota. The weight swap itself is a 30-minute task: flip weights_source: our_real in YAML, call kagglehub.model_download, re-run E2E test.
**Delivers:** DualHeadUNetpp trained 25 epochs on MARIDA (Dice + weighted BCE + MSE on positives only); IoU >= 0.45, precision@0.7 >= 0.75, sub-pixel MAE <= 0.15; biofouling NIR augmentation (40% of positives, mask-only); age regression head; multi-class disambiguation with Sargassum FPR <= 15%; weights uploaded via kagglehub.model_upload and hot-swapped via YAML; optional PDF briefing (D10); precomputed 4-AOI fallback JSONs at H+28; screen recording at H+36.
**Addresses features:** REQ-ML-03, REQ-ML-05, REQ-ML-06, D1, D2, D3, D4, D7, D10, D11, D12.
**Avoids pitfalls:** C2 (conf mask), C3 (imbalance loss), C6 (GPU disabled), C7 (demo crashes), M7 (biofouling augmentation direction), M8 (fraction MSE collapse), M11 (val contamination from synthetic mixing), M12 (checkpoint transfer).
**Exit criterion:** E2E test re-runs with our_real weights; IoU >= 0.45 on MARIDA val; chain < 15 s; precomputed fallback JSONs in place; screen recording done.
**Research flag:** NEEDS attention at Phase 3 kickoff - read marccoru/marinedebrisdetector/hubconf.py to confirm exact 12-band ordering and determine zero-pad/duplicate strategy for MARIDA 11-band patches. Inspect SMP first-conv init for in_channels=14 empirically (check model.encoder.conv1.weight.std(); if ~0.1, apply manual RGB-head init for B4/B3/B2 channels).

### Phase Ordering Rationale

- Schema before anything: Freeze core/schemas.py before writing any loader or model. Work the other direction: schema first, then build backward.
- Dummy before marccoru: marccoru weights are not auto-fetchable (private Google Drive). Using dummy as the real Phase 1 default proves the full pipeline chain before exercising any external dependency.
- Physics and mission in parallel with Phase 1 frozen output: Because modules communicate only via pydantic types, Phase 2 can start the moment Phase 1 schema is frozen, using hand-crafted fixture FCs.
- Training as late as possible but not last-minute: The Kaggle GPU run is the highest-variance single task. Starting at Phase 3 kickoff gives a 16-hour buffer before H+36 feature freeze.
- PDF briefing as Phase 3 stretch, not core: D10 is high judge value but medium cost; attempt only after E2E chain is green with real weights.

### Research Flags

Phases needing deeper research during planning:
- Phase 3 kickoff (immediate action): Read marccoru/marinedebrisdetector/hubconf.py to confirm exact 12-band ordering and determine which band to zero-pad/duplicate for MARIDA 11-band patches.
- Phase 3 kickoff (immediate action): Inspect model.encoder.conv1.weight.std() after smp.UnetPlusPlus(in_channels=14) instantiation. If random init (~0.1), apply manual RGB-head initialization for B4/B3/B2 channels.

Phases with standard patterns (skip research):
- Phase 1: Sentinel-2 COG reading with rasterio, pydantic schema patterns, geojson-pydantic generics - all HIGH confidence, fully specified.
- Phase 2: Euler Lagrangian integration, xarray bilinear interp, greedy TSP - textbook; fully specified in ARCHITECTURE.md and PITFALLS.md.
- Phase 3 training loop: Dice + weighted BCE, MARIDA data loader with _conf.tif weighting, custom augmentation - fully specified in STACK.md Phase 3 section.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyTorch 2.7, SMP 0.5.x, rasterio 1.5, xarray 2026.2 all verified against PyPI/release notes. MEDIUM for marccoru input spec (band ordering must be read from hubconf.py at kickoff) and SMP first-conv init for in_channels>4 (version-dependent, needs empirical check on Kaggle). |
| Features | HIGH | MARIDA benchmarks, OpenDrift validation, Ocean Cleanup references all corroborate table-stakes features. Sub-pixel regression targets are MEDIUM (few peer-reviewed MARIDA regression benchmarks exist). |
| Architecture | HIGH | Module boundary patterns, pydantic schema discipline, kagglehub weight handoff all verified against official docs. MEDIUM for marccoru weight hosting (confirmed moved to private Google Drive - workaround fully specified). |
| Pitfalls | HIGH | S2 L2A offset, CMEMS lon convention, CRS integration error, Kaggle GPU flags all confirmed against official ESA/Copernicus/Kaggle docs. MEDIUM for biofouling augmentation direction (derived from PRD + augmentation best practice). |

**Overall confidence:** HIGH for core decisions; MEDIUM for marccoru-specific integration details that must be resolved at Phase 3 kickoff.

### Gaps to Address

- marccoru 12-band vs. MARIDA 11-band ordering: Resolve by reading hubconf.py at Phase 3 kickoff. Zero-pad B10 or duplicate B8A; exact band position must match repo preprocessing code.
- SMP in_channels=14 first-conv initialization: Resolve empirically at Phase 3 kickoff by checking model.encoder.conv1.weight.std(). If random (~0.1), apply manual RGB-head pretrained-weight initialization for channels B4/B3/B2.
- CMEMS + ERA5 NetCDF pre-staging: Data not yet downloaded. Phase 2 is blocked until scripts/fetch_demo_env.py runs and files land in data/env/. Pre-clip to AOI extent to stay under 500 MB.
- Kaggle GPU quota timing: Budget allows at most two full training runs on the 12 GPU-hours/week free tier. The first run must use pre-committed hyperparameters; no exploratory runs.
- MARIDA and model weights not in .gitignore: Confirmed in CONCERNS.md. Add MARIDA/, *.pth, *.ckpt to .gitignore at Phase 1 hour zero before any git add.

---

## Sources

### Primary (HIGH confidence)
- ESA Sentinel-2 Processing Baseline docs - BOA_ADD_OFFSET documentation, PB 04.00 change date (2022-01-25)
- PyPI: rasterio 1.5.0, xarray 2026.2.0, segmentation-models-pytorch 0.5.x - version compatibility matrix, wheel availability
- PyTorch 2.7 release blog - P100 (sm_60) + T4 (sm_75) support, torch.compile Triton requirement (needs compute capability >= 7.0)
- Copernicus Marine Toolbox docs - copernicusmarine.open_dataset() as sole supported live CMEMS access; motuclient dead since April 2024
- geojson-pydantic (developmentseed/geojson-pydantic) - Feature[Geom, Props] generic pattern verified
- pydantic-settings + YAML - YamlConfigSettingsSource, env-nested-delimiter pattern
- kagglehub README - model upload/download handle format, cache path ~/.cache/kagglehub/
- Kaggle kernel-metadata schema - enable_gpu, enable_internet, dataset_sources fields; 9-hour runtime limit
- MARIDA: Kikaki 2022 (PLoS ONE) - benchmark IoU 0.65-0.82, class imbalance structure, _conf.tif semantics
- Biermann 2020 (Sci Rep) - FDI formula, lambda values for B6/B8/B11
- OpenDrift validation study (JOET 2024) - 72 h endpoint error 13-16 km; basis for < 25 km target
- pyproj Transformer docs - UTM integration pattern for Lagrangian tracker
- CMEMS Global PUM (GLOBAL_ANALYSISFORECAST_PHY_001_024) - regular lat-lon grid, standard_name eastward_sea_water_velocity

### Secondary (MEDIUM confidence)
- MarcCoru/marinedebrisdetector GitHub - torch.hub.load confirmed; 12-channel input confirmed; weights moved to private Google Drive confirmed; exact band ordering requires hubconf.py inspection
- SMP docs Insights page - first-conv init for in_channels>4 behavior is version-dependent between 0.3.x and 0.5.x; empirical check required
- Hyperspectral biofouling data (ESSD 2024) - 30-60% NIR suppression at depth; basis for NIR x [0.5,1.0] augmentation range
- Performance diagnostics for probabilistic Lagrangian drift (Taylor & Francis 2025) - ensemble 1-sigma coverage target

### Tertiary (LOW confidence - validate during implementation)
- Confidence decay tau=30 days calibration - reasonable default but may require tuning once real age estimates are available from the regression head

---
*Research completed: 2026-04-17*
*Ready for roadmap: yes*