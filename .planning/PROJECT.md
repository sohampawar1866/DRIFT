# DRIFT / PlastiTrack — Backend Intelligence

## What This Is

An autonomous satellite-to-mission intelligence layer for floating marine macroplastic cleanup. DRIFT ingests Sentinel-2 multispectral imagery, detects sub-pixel plastic patches (distinguishing them from Sargassum, foam, and wakes), forecasts 72-hour Lagrangian drift using CMEMS ocean currents + ERA5 winds, and produces a deployable cleanup mission (GPX waypoints, GeoJSON, PDF briefing) targeted at Indian Coast Guard operations, INCOIS, and coastal port trusts.

**This project scope (locked after questioning 2026-04-17):** only the **backend intelligence layer** — ML detection, physics trajectory, mission planning. The FastAPI wiring and React frontend are **explicitly out of scope** for this milestone; the existing `backend/api/routes.py` mock endpoints stay untouched until a later integration milestone.

## Core Value

**A single Python function chain `run_inference(tile) → forecast_drift(detections) → plan_mission(forecast)` must produce a valid cleanup mission plan end-to-end from a real Sentinel-2 tile — in under 15 seconds, with detection IoU ≥ 0.45 on MARIDA val.** If everything else fails, this chain must work. It is the defensible technical story that wins the Sankalp Bharat judging.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. Inferred from existing codebase. -->

- ✓ FastAPI skeleton with CORS wide-open and `/api/v1` prefix — existing (`backend/main.py`)
- ✓ Mock GeoJSON endpoints for `/detect`, `/forecast`, `/mission` — existing (`backend/services/mock_data.py`) — preserved as fallback during demo
- ✓ MARIDA dataset staged locally — 1,381 patches across 63 Sentinel-2 scenes, 15 classes (plastic at index 1), pre-split train/val/test (`MARIDA/splits/*.txt`)
- ✓ **REQ-ML-01** — FDI (Biermann 2020) / NDVI / PI (Themistocleous 2020) features via `backend/ml/features.py::feature_stack` (14-channel tensor). Validated in Phase 1.
- ✓ **REQ-ML-04** (partial, dummy branch) — `run_inference(tile_path) → DetectionFeatureCollection` returns schema-valid GeoJSON on real MARIDA patches. Real pretrained weights (our_real branch) deferred to Phase 3. Validated in Phase 1.
- ✓ **Frozen detection schema** — `backend/core/schemas.py` committed with `extra="forbid", frozen=True`. All Phase 2/3 consumers can depend on it.

### Active

<!-- Current scope for this milestone. Building toward these. -->

- [ ] **REQ-ML-02** — MARIDA dataset loader: reads `splits/*.txt` → 256×256 torch tensors, loads 11-band `.tif` + `_cl.tif` mask + `_conf.tif` confidence weight, normalizes reflectance
- [ ] **REQ-ML-03** — Dual-head detection model: UNet++ (ResNet-18 encoder) with SE spectral-attention block; outputs binary plastic mask + fractional-cover regression; 14-channel input (11 bands + FDI + NDVI + PI) *(model class shipped in Phase 1; SE attention + trained weights land in Phase 3)*
- [ ] **REQ-ML-05** — Phase 3 real training on Kaggle T4/P100 (25 epochs, Dice+BCE + MSE losses, biofouling augmentation, synthetic sub-pixel mixing); achieves IoU ≥ 0.45, precision@0.7 ≥ 0.75, sub-pixel MAE ≤ 0.15 on MARIDA val
- [ ] **REQ-ML-06** — Biofouling instrumentation: training-time NIR×[0.5,1.0] augmentation on 40% of positive samples; inference-time confidence decay `conf_adj = conf_raw · exp(-age/30)`
- [ ] **REQ-PHYS-01** — Environment data loader: CMEMS surface currents (u/v, 1/12°, hourly) + ERA5 10 m winds (u10/v10, 0.25°, hourly) via xarray; bilinear interpolation at (lon, lat, t)
- [ ] **REQ-PHYS-02** — Lagrangian Euler particle tracker: 20 particles per detection, hourly dt for 72 h horizon, windage α=0.02; returns per-hour positions + KDE density polygons at +24/+48/+72 h; unit-tested against synthetic constant-velocity fields (43.2 km / 24 h ±1%)
- [ ] **REQ-MISSION-01** — Greedy TSP cleanup planner: `plan_mission(detections, vessel_range_km, hours, origin_lonlat)` → ordered waypoints + route LineString; priority score = density × accessibility × forecast-convergence
- [ ] **REQ-E2E-01** — End-to-end smoke test: real MARIDA patch → `run_inference` → `forecast_drift` → `plan_mission` produces schema-valid outputs at each stage; full chain < 15 s

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- **FastAPI endpoint wiring** — The existing mock `backend/api/routes.py` stays untouched. Integration with real inference/forecast/mission moves to a separate milestone after intelligence modules are standalone-callable. *Why:* the user explicitly scoped this milestone to "only the intelligence part."
- **React/Mapbox/deck.gl frontend** — Not started; not this milestone. *Why:* same as above.
- **Live Sentinel-2 ingestion (STAC, Sentinel Hub auth)** — Pre-staged tiles only. *Why:* PRD §12 scope guardrail; live auth is a rabbit hole.
- **Multi-satellite fusion (Sentinel-1 SAR, Sentinel-3 OLCI, PlanetScope)** — *Why:* PRD §12.
- **OpenDrift / full 3D hydrodynamics / Stokes drift beyond 2% windage** — *Why:* Euler + windage is defensible for 72 h horizons; full physics doesn't fit 24–48 h.
- **User accounts, OAuth, RBAC, mobile app, UAV dispatch** — *Why:* PRD §12.
- **Cloud deployment (AWS/GCP), ONNX/TensorRT on-device inference** — *Why:* single-laptop demo is less risky during judging.
- **Custom dataset labeling UI** — *Why:* MARIDA + FloatingObjects are sufficient.

## Context

**Hackathon:** Sankalp Bharat — Problem SKB_P5 (*Autonomous Sub-Pixel Detection & Trajectory Mapping of Floating Marine Macroplastics*). Today: **2026-04-17**. Hard deadline: 24–48 h from start. Target: top-3 finish.

**Key documents already in repo:**
- `PRD.md` (540 lines) — full product requirements doc, authoritative for the product vision
- `PPT_CONTENT.md` — 8-slide ideation deck content
- `problem_statement.pdf` (207 KB) — official Sankalp Bharat brief
- `.planning/codebase/*.md` — freshly mapped: STACK, INTEGRATIONS, ARCHITECTURE, STRUCTURE, CONVENTIONS, TESTING, CONCERNS (commit 75de467)

**Datasets staged:**
- **MARIDA** (Kikaki 2022): 63 S2 scenes, 1,381 patches, 15-class labels, 11-band 10 m reflectance. At `MARIDA/` (project root, NOT under `data/` — may be re-moved later).
- **CMEMS** + **ERA5** NetCDFs: user has accounts but data not yet downloaded. Phase 2 will include a fetch script + credentials documentation.

**Four demo AOIs (Indian EEZ, per PRD §4):** Gulf of Mannar, Mumbai offshore, Bay of Bengal mouth, Arabian Sea gyre edge.

**Training compute:** Kaggle notebook kernel `ManasTiwari1410/drift-model` (slug present in `kaggle.yml`, `kernel-metadata.json`). GPU currently DISABLED; must be enabled before Phase 3 training (see Key Decisions).

**Existing code baseline:** thin FastAPI skeleton with mock endpoints. 3 Python files, ~150 LOC total. No tests. No ML. No physics. No frontend. This is a greenfield build for the intelligence layer *on top of* a minimal API shell.

## Constraints

- **Timeline:** 24–48 hours from kickoff, feature-freeze at H36 (PRD §13). Every hour spent on out-of-scope items reduces demo polish time.
- **Tech stack (locked per PRD §8.6):** PyTorch 2.x + segmentation_models_pytorch, Rasterio, xarray, GeoPandas, Shapely — all pip-installable. No from-scratch transformers.
- **Python version:** 3.10 / 3.11 / 3.12 only (per `backend/README.md` — shapely/geopandas binary wheels are broken on 3.9 and 3.13+).
- **Training compute:** Kaggle free tier (12 GPU-hours/week, P100 or T4, ~16 GB VRAM). No AWS/GCP. Training script must be a single notebook runnable on Kaggle.
- **Pretrained weights:** Phase 1 uses `torch.hub.load("marccoru/marinedebrisdetector", "unetpp")` as-is (already validated on MARIDA) — not building from scratch.
- **No live data ingestion:** every data source (S2 tiles, CMEMS currents, ERA5 winds) pre-staged. No auth flows in the runtime pipeline.
- **Contract freeze before Phase 1 ends:** detection GeoJSON feature schema is locked for all downstream consumers (tracker, planner, future API layer).
- **Scope rule (PRD §12, zero-sum):** any new feature proposal must be paired with a removal. Scope creep is the single highest risk.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| **Scope milestone to intelligence-only** (no FastAPI wiring, no frontend) | User confirmed 2026-04-17: "plan about only the intelligence part. Leave the API and frontend" | — Pending |
| **Three-phase split: (1) dummy inference → (2) trajectory → (3) real training + mission + opt** | Dummy-first de-risks schema/plumbing before committing to a 60-90 min training run | — Pending |
| **Kaggle as training target (not Colab or local)** | User chose 2026-04-17. Free P100/T4; notebook already scaffolded (`kaggle.yml`, `kernel-metadata.json`) | — Pending (requires `enable_gpu: true` flip + MARIDA upload as Kaggle dataset) |
| **Phase 1 baseline = `marccoru/marinedebrisdetector` pretrained** | Already trained on MARIDA; gives realistic outputs for downstream Phase 2/3 integration without waiting on training | — Pending |
| **UNet++ (resnet18 encoder) with SE attention + dual head over ViT/Segformer** | MARIDA's 1,381 patches too small for ViT; UNet++ with pretrained encoder is the defensible sweet spot (PRD §8.1) | — Pending |
| **Euler Lagrangian tracker, α=0.02 windage, no Stokes drift** | Textbook physics, 72 h horizons tolerate it (PRD §4 simplify); OpenDrift is overkill for the demo | — Pending |
| **Biofouling: synthetic NIR×[0.5,1.0] augmentation + `exp(-age/30)` decay at inference** | Full spatiotemporal CNN-LSTM is months of work; this is defensible without over-claiming (PRD §8.4) | — Pending |
| **Freeze detection feature schema at end of Phase 1** | All downstream (tracker, planner, future API) must consume the same `{conf_raw, conf_adj, fraction_plastic, area_m2, age_days_est, class}` — any drift here costs hours | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-17 after Phase 01 completion (schema-foundation-dummy-inference)*
