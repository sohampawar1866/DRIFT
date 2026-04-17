# Roadmap: DRIFT / PlastiTrack — Backend Intelligence

**Created:** 2026-04-17
**Granularity:** coarse (3 phases, Sankalp Bharat 24-48 h hackathon)
**Core Value:** `run_inference(tile) -> forecast_drift(detections) -> plan_mission(forecast)` produces a schema-valid cleanup mission from a real Sentinel-2 tile in < 15 s on a CPU laptop, with MARIDA IoU >= 0.45.

**Feature freeze:** H36 from kickoff (H0 = 2026-04-17 kickoff moment). No code touches beyond H36; only demo polish, precomputed fallbacks, and screen-recording after that.

**Scope guardrail:** intelligence-only. No FastAPI wiring, no frontend in this milestone. The existing `backend/api/routes.py` mock stays untouched. Any scope-creep proposal must pair with a deletion (PRD Section 12 zero-sum rule).

---

## Phases

- [ ] **Phase 1: Schema Foundation + Dummy Inference** - Freeze the pydantic `DetectionProperties` contract and ship `run_inference(tile) -> DetectionFeatureCollection` on random `dummy` weights so all downstream modules can start immediately.
- [ ] **Phase 2: Trajectory + Mission Planner** - Build `forecast_drift` (Euler Lagrangian in UTM meters, CMEMS+ERA5, windage alpha=0.02) and `plan_mission` (priority-scored greedy+2-opt TSP with vessel-range and time-budget constraints) in parallel against the frozen Phase 1 schema.
- [ ] **Phase 3: Real Training + Weight Swap + Mission Export + E2E** - Train the dual-head UNet++ on Kaggle GPU to hit PRD Section 11.1 metrics, hot-swap weights via `cfg.ml.weights_source=our_real`, ship GPX+GeoJSON+PDF mission export, and drive the full chain to < 15 s end-to-end with precomputed 4-AOI fallbacks.

## Phase Details

### Phase 1: Schema Foundation + Dummy Inference

**Goal**: Freeze the `DetectionProperties` pydantic contract in git and ship a `run_inference(tile) -> DetectionFeatureCollection` that returns schema-valid GeoJSON on random-initialized weights. This unblocks both Phase 2 modules (physics, mission) the moment the schema is frozen — roughly H4.

**Depends on**: Nothing (first phase). Requires .gitignore updated for `MARIDA/`, `*.pth`, `*.ckpt` at H0 before any git add.

**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-06, ML-01, ML-03, ML-04

**Success Criteria** (what must be TRUE):
  1. `backend/core/schemas.py` defines `DetectionProperties` with `extra="forbid"`, six required fields (`conf_raw`, `conf_adj`, `fraction_plastic`, `area_m2`, `age_days_est`, `class` aliased via pydantic `Field(alias="class")`), and is git-committed. `tests/unit/test_schemas.py` passes: schema round-trip on 10 sample detections (`FeatureCollection.model_validate_json(fc.model_dump_json()) == fc`).
  2. `python -m backend.ml MARIDA/patches/.../S2_..._0.tif` on a real MARIDA patch emits a pydantic-valid `DetectionFeatureCollection` to stdout with random-weight `dummy` inference — every polygon has six properties, every `conf_raw` is finite and in `[0,1]`, every `area_m2 >= MIN_AREA_M2` (no sub-10 m^2 specks).
  3. `backend/ml/features.py` FDI unit test passes: a known Biermann 2020 water pixel returns FDI within 0.001 of the published reference value; the same `feature_stack()` function is invoked from both `dataset.py` and `inference.py` (single source of truth verified by grep).
  4. `backend/core/config.py` loads `config.yaml` via pydantic-settings with nested `MLSettings` / `PhysicsSettings` / `MissionSettings`; env-var override works (`ML__WEIGHTS_SOURCE=our_real python -m backend.ml ...` switches branches without YAML edit).
  5. CLI entrypoints exist and run: `python -m backend.ml <tile>`, `python -m backend.physics <detections.json>`, `python -m backend.mission <forecast.json>` all parse args, load `Settings()`, and call their module's public function (physics+mission can be stubs returning empty FC at this point; ML must do real polygonization).

**Plans**: 5 plans

Plans:
- [x] 01-01-PLAN.md � Wave 0: env setup (.gitignore hardening, pyproject.toml + Python 3.11 pin, pip installs, Wave-0 probes for MARIDA band order / geojson-pydantic / reflectance scale / SMP init)
- [x] 01-02-PLAN.md � Wave 1: frozen schemas (DetectionProperties + FC + Forecast + Mission) + pydantic-settings + YAML + env override
- [x] 01-03-PLAN.md � Wave 1: backend/ml/features.py (FDI/NDVI/PI + feature_stack) with Biermann 2020 unit test
- [x] 01-04-PLAN.md � Wave 2: DualHeadUNetpp model, strategy weight loader (dummy branch only), 3 CLI entrypoints, physics/mission stubs
- [x] 01-05-PLAN.md � Wave 3: backend/ml/inference.py (sliding window + cosine stitch + polygonization) + MARIDA integration test

**Risk flags**:
  - **Schema drift into Phase 2** (PITFALL C5): if `DetectionProperties` changes after Phase 2 consumers import it, their code breaks silently. **Mitigation**: schema is committed to git at Phase 1 exit; any Phase 2/3 field edit requires an explicit "schema unfreeze" decision entry in STATE.md and a re-run of `tests/unit/test_schemas.py`.
  - **S2 L2A BOA_ADD_OFFSET bug** (PITFALL C1): tiles with Processing Baseline >= 04.00 (post-2022-01-25) need `(DN + -1000) / 10000` not `DN / 10000`. Unit test at Phase 1 exit: known water pixel produces B8 ~ 0.08, not ~ -0.02.
  - **Band resolution mismatch** (PITFALL M1): B1/B9 are 60 m, B5-B7/B8A/B11/B12 are 20 m. MARIDA ships pre-resampled to 10 m but live-staged tiles may not — resample everything to B2's 10 m grid before `feature_stack()`.
  - **MARIDA/ not in .gitignore** (PITFALL mi3): 4.5 GB accidental commit. Fix at H0 before any `git add`.
  - **Python 3.13+ shapely/geopandas wheel breakage** (PITFALL mi2): pin `requires-python = ">=3.10,<3.13"` in `pyproject.toml`.

---

### Phase 2: Trajectory + Mission Planner

**Goal**: Deliver `forecast_drift(detections, cfg) -> ForecastEnvelope` and `plan_mission(forecast, ...) -> MissionPlan` both callable against synthetic fixture FCs AND the Phase 1 dummy-inference output. Physics and mission are built in parallel because neither depends on the other — both depend only on the Phase 1 frozen schema.

**Depends on**: Phase 1 (schema freeze only). The schema needs to be committed; after that, Phase 2 can start immediately even if Phase 1's full `run_inference` is still being polished. Neither physics nor mission need real trained weights.

**Requirements**: INFRA-05 (deferred-but-started: checkpoint dir and .gitignore prep), PHYS-01, PHYS-02, PHYS-03, PHYS-04, PHYS-05, MISSION-01, MISSION-02

Note on INFRA-05: the original traceability mapping places INFRA-05 in Phase 3. Keeping it there — `kagglehub.model_upload` only fires at Phase 3 end. Phase 2 only prepares the `backend/ml/checkpoints/` directory + gitignore.

**Success Criteria** (what must be TRUE):
  1. `tests/integration/test_tracker_synth.py` passes: a constant 0.5 m/s eastward current over 24 h moves a seed particle **43.2 km +/- 1%**. Zero-field test: particle stays put within 100 m over 72 h. This test **gates Phase 2 exit** — no Phase 3 work starts until green.
  2. Real-data smoke test (`backend/physics/test_tracker_real.py`): seed 10 particles at Gulf of Mannar (78.9 E, 9.2 N) using the fetched CMEMS+ERA5 slice; all 10 remain within the Indian Ocean basin bbox over 72 h; none land in the Deccan Plateau on a GSHHG coastline visual check; no position goes NaN (beach-on-NaN logic catches land-crossing particles).
  3. `plan_mission(fake_forecast, 200 km, 8 h, origin=(72.8, 18.9))` on a 15-detection synthetic forecast returns a pydantic-valid `MissionPlan` with: at least 3 waypoints, `total_distance_km <= 200`, `total_hours <= 8`, `waypoints[0].order == 0`, strict ordering, and `route.type == "Feature"` with `LineString` geometry connecting origin -> waypoints -> origin. All 5 edge cases pass unit tests: 0 detections, 1 detection, all-out-of-range, budget-exhausted-mid-route, singleton.
  4. `scripts/fetch_demo_env.py` runs to completion against real credentials from env vars, writes `data/env/cmems_currents_72h.nc` and `data/env/era5_winds_72h.nc` clipped to the union of 4 AOI bboxes (< 500 MB each), and **documents** the credential flow in the script's docstring. Success check: `xarray.open_dataset` loads both files and `ds.longitude.min() >= -180, ds.longitude.max() <= 180` (M4 normalization applied if needed).
  5. Full dummy-weight E2E chain (invoked via a scratch `scripts/run_full_chain_dummy.py`) completes `run_inference -> forecast_drift -> plan_mission` without exceptions on one MARIDA patch; each stage produces schema-valid pydantic output; total wall-clock < 20 s on CPU laptop (15 s target is Phase 3's job; Phase 2 only proves the chain works).

**Plans**: 5 plans

Plans:
- [ ] 02-01-env-data-config-PLAN.md — Wave 1: backend/physics/env_data.py EnvStack (CMEMS+ERA5 loader, lon norm, time-axis assert, wind standard_name check) + mission.avg_speed_kmh config + INFRA-05 checkpoints dir prep
- [x] 02-02-mission-scoring-PLAN.md — Wave 1: backend/mission/scoring.py priority scoring primitives (haversine, density_at, convergence_ratio, priority_score per D-12)
- [ ] 02-03-tracker-PLAN.md — Wave 2: backend/physics/tracker.py real Euler Lagrangian tracker (UTM-meter integration, beach-on-NaN, 90%/75% KDE at hours {24,48,72}) + PHYS-04 synthetic 43.2 km gate test
- [ ] 02-04-mission-planner-PLAN.md — Wave 2: backend/mission/planner.py + tsp.py greedy+2-opt TSP with dual (range+time) budget enforcement, never-raise contract, 5 edge-case tests (MISSION-02 gate)
- [ ] 02-05-fetch-real-e2e-PLAN.md — Wave 3: scripts/fetch_demo_env.py (CMEMS+ERA5 pre-stage, fail-loud creds) + scripts/run_full_chain_dummy.py E2E driver + PHYS-05 real-data smoke test

**Risk flags**:
  - **CRS unit confusion** (PITFALL C4, CRITICAL): integrating in lon/lat degrees instead of UTM meters moves particles ~55 km per second. **Mitigation**: integrate in UTM meters via `pyproj.Transformer(EPSG:4326 -> EPSG:326XX)`; convert back to WGS84 only for output. The synthetic 43.2 km / 24 h test gates this.
  - **CMEMS+ERA5 not yet downloaded** (CRITICAL BLOCKER): user has accounts but data is not on disk. Phase 2 is gated on `scripts/fetch_demo_env.py` succeeding. If network flakes at demo venue, pre-bake slices to disk early (H+10 at latest). Document fallback: Phase 2 smoke tests can run against synthetic xarray Datasets defined inline in pytest fixtures if the real fetch fails — Phase 3 precomputed fallbacks take over.
  - **Particles crossing land** (PITFALL M2): CMEMS NaN at coastal fills causes positions to go NaN. **Mitigation**: "beach on NaN" — if `interp_currents` returns NaN for any particle, freeze it in place (status=beached) and exclude from KDE.
  - **Time-axis misalignment** (PITFALL M3): CMEMS and ERA5 may cover different `[tmin, tmax]`. Assert coverage >= 72 h at load; clip horizon to `min(t_end_cmems, t_end_era5) - detection_time`.
  - **CMEMS longitude convention** (PITFALL M4): check `ds.longitude.min()/max()`; normalize 0-360 to -180-180 via `((lon + 180) % 360) - 180`.
  - **Windage to wrong vector component** (PITFALL M5): verify `ds.uo.attrs["standard_name"] == "eastward_sea_water_velocity"`; use CMEMS Global Physics Analysis and Forecast (GLOBAL_ANALYSISFORECAST_PHY_001_024) — regular lat-lon grid, u=east v=north m/s.
  - **TSP edge cases** (PITFALL M10): zero detections, singleton, all-out-of-range, range overflow — each needs a unit test. Without these, `plan_mission` will crash on an empty AOI at demo time.
  - **Rasterio polygonization artifacts** (PITFALL M9): carried from Phase 1 into Phase 2 because tracker consumes polygons — `.buffer(0)` + `MIN_AREA_M2 >= 200 m^2` + `connectivity=4` not 8. (Already enforced in Phase 1 but re-tested when real detections feed the tracker.)

---

### Phase 3: Real Training + Weight Swap + Mission Export + E2E

**Goal**: Train the dual-head UNet++ on Kaggle GPU (25 epochs, biofouling augmentation, Dice + pos-weighted BCE + MSE-on-positives, MARIDA `_conf.tif` handled correctly), hit all PRD Section 11.1 metric targets, hot-swap weights via YAML one-liner, ship GPX + GeoJSON + PDF mission briefing, drive the full chain to < 15 s end-to-end, and bake fallbacks for all 4 demo AOIs.

**Depends on**: Phase 1 (schema still frozen), Phase 2 (tracker + planner green). Kaggle GPU must be enabled (`enable_gpu: true` in `kaggle.yml`) **before this phase starts**; MARIDA must already be uploaded as a Kaggle Dataset.

**Requirements**: INFRA-05, ML-02, ML-05, ML-06, ML-07, ML-08, ML-09, MISSION-03, E2E-01, E2E-02

**Success Criteria** (what must be TRUE):
  1. `backend/ml/train.py` completes on Kaggle in one session (25 epochs, ~60-90 min on P100 or ~45 min on T4x2) and `.planning/metrics/phase3.json` records **all PRD Section 11.1 targets met**: IoU >= 0.45 on MARIDA val, precision@0.7 >= 0.75, sub-pixel MAE <= 0.15 on synthetic held-out mixed-pixel val, Sargassum (classes 2/3) false-positive rate <= 15% on the 15-class confusion matrix. `best_iou_model.pt` uploaded to `kagglehub.model_upload(handle="manastiwari1410/drift-unetpp/pytorch/v1", ...)`.
  2. Weight-swap is a one-line YAML change: flipping `ml.weights_source: our_real` in `backend/config.yaml` (or `ML__WEIGHTS_SOURCE=our_real` env override) routes `load_weights()` through `kagglehub.model_download(...)` -> `~/.cache/kagglehub/...` -> `state_dict` loaded into the same `DualHeadUNetpp` class. `physics/` and `mission/` code is byte-identical before and after the swap (verified by `git diff`). `run_inference` on the same MARIDA patch with `dummy` vs `our_real` produces the **same pydantic schema** but different values — no downstream consumer notices the difference.
  3. `backend/e2e_test.py` passes: real MARIDA patch -> `run_inference` (our_real weights) -> `forecast_drift` (real CMEMS+ERA5 slice) -> `plan_mission` (vessel_range=200 km, hours=8, origin=one of 4 AOIs). Every stage boundary validates against pydantic schema. **Total wall-clock < 15 s on CPU-only laptop** (PRD Core Value hard requirement). `time.perf_counter()` breakdown logged per stage.
  4. `backend/mission/export.py` produces three artifacts from a `MissionPlan`: (a) **GPX** — opens cleanly in Google Earth, shows vessel route as a track with waypoints as pins; (b) **GeoJSON** — `pydantic.model_dump_json(indent=2)` < 500 KB, RFC-7946 compliant; (c) **PDF briefing** — one page, < 1 MB, generated in < 3 s via matplotlib + reportlab (no headless Chrome), contains: vessel route over Indian EEZ map, waypoint table with (order, lon, lat, ETA, priority), wind/current conditions at each stop, fuel estimate summary.
  5. **Pre-baked 4-AOI fallback JSONs** land at `data/prebaked/{gulf_of_mannar,mumbai_offshore,bay_of_bengal_mouth,arabian_sea_gyre_edge}_{detections,forecast,mission}.json` by **H+28** (before feature freeze at H+36). Fallback parity test: live output hash on the 4 demo tiles === pre-baked hash for each stage (asserts determinism: same inputs + same seed -> byte-identical output per D11). Screen recording of a successful end-to-end run saved at `.planning/demo/successful_run.mp4` by H+36.

**Plans**: 6 plans

Plans:
- [x] 03-01-PLAN.md — Wave 1: Deps + offline basemap (reportlab, Natural Earth coastline clip, .gitignore hardening for checkpoints dir)
- [x] 03-02-PLAN.md — Wave 2: backend/mission/export.py (GPX + GeoJSON + PDF briefing) against synthetic fixtures — MISSION-03
- [x] 03-03-PLAN.md — Wave 2: Fallback infrastructure (scripts/run_full_chain_real.py + scripts/parity_hash.py + tests/test_fallback.py) — partial E2E-02
- [ ] 03-04-PLAN.md — Wave 3: weights.py our_real branch + train.py D-03 review + weight-swap smoke + metrics re-eval — INFRA-05, ML-02/05/06/07/08/09 (scope-corrected per D-01: code-review, not training execution)
- [ ] 03-05-PLAN.md — Wave 3: backend/e2e_test.py with warm-up + per-stage timing + < 15 s total gate — E2E-01
- [ ] 03-06-PLAN.md — Wave 4: scripts/prebake_demo.py + tests/test_prebake_parity.py + requirements.lock H+32 freeze + H+36 recording protocol — E2E-02 close

**Risk flags**:
  - **Kaggle GPU currently DISABLED** (PITFALL C6, CRITICAL BLOCKER): `kaggle.yml` has `enable_gpu: false`. **Flip this BEFORE Phase 3 kicks off**, not after training starts. First cell of notebook must `assert torch.cuda.is_available()` or abort. If it runs on CPU, a 25-epoch run blows past the 9-hour session timeout — full Phase 3 compute budget destroyed.
  - **Non-deterministic P100 vs T4 assignment** (PITFALL C6 addendum): do NOT use `torch.compile` (Triton requires compute capability >= 7.0, P100 is 6.0) and do NOT use `bfloat16` (T4 has no bf16 hardware). Use `fp16 autocast` + `GradScaler` only — works on both.
  - **MARIDA `_conf.tif` misuse** (PITFALL C2): `conf==0` means unlabeled, NOT "confident no-plastic". Mask out with `valid_mask = (conf > 0)`; weight loss by `conf/3.0 * valid_mask`. Smoke test after epoch 1: `(pred > 0.5).sum() / total_pixels` must be > 0.1% or loss is collapsed.
  - **Plastic class imbalance (~2% positives)** (PITFALL C3): unweighted BCE collapses to "predict zero everywhere". Use **Dice + pos-weighted BCE** with `pos_weight ~ 40` (N_negative/N_positive, computed on train set). MSE on fraction head with weight 0.1-0.3 keeps mask learning dominant.
  - **Biofouling augmentation teaching wrong direction** (PITFALL M7): must apply NIR x [0.5, 1.0] **only on plastic-masked pixels**, not the whole patch. Unit test: augment a sample with all-zero mask -> bands unchanged.
  - **Sub-pixel MSE collapse to near-zero** (PITFALL M8): regression loss only on positive pixels (`mask==1`); verify Pearson(pred_frac, true_frac) >= 0.5 on val, not just low MSE.
  - **Val/test contamination from synthetic mixing** (PITFALL M11): enforce `assert source_scene in train_scenes` when synthesising mixed pixels; never blend from val scenes.
  - **Checkpoint transfer Kaggle -> laptop** (PITFALL M12): use **kagglehub model upload/download** (primary), not `git add model.pt` (blows GitHub 100 MB limit). Pre-run `kagglehub.model_download(...)` on the demo laptop **before demo day** so `~/.cache/kagglehub/` is primed — offline-safe during judging.
  - **Demo laptop crashes / Docker / CUDA issues** (PITFALL C7, CRITICAL): freeze runtime at H+32 — no `pip install` after H+32. Precompute 4-AOI fallback JSONs by H+28. 60 s screen recording by H+36. Fallback code path loads `data/prebaked/*.json` if live inference fails mid-pitch.
  - **marccoru weights on private Google Drive** (PITFALL reference): `marccoru_baseline` branch is optional bonus only — NOT default. `dummy` is Phase 1 default; `our_real` is the Phase 3 swap target. If Phase 3 training fails outright (GPU budget destroyed), final demo falls back to `marccoru_baseline` ONLY if weights were manually downloaded during Phase 2 free time.
  - **SMP `in_channels=14` first-conv init** (STACK.md Phase 3 research flag): at Kaggle kickoff, check `model.encoder.conv1.weight.std()` after instantiation. If ~0.1 (random init), apply manual RGB-head pretrained initialization for B4/B3/B2 channels. If ~0.02 (tiled-pretrained), leave as-is.
  - **Hub band ordering** (STACK.md Phase 3 research flag): if falling back to marccoru, read `hubconf.py` to confirm 12-band order and determine zero-pad/duplicate strategy for MARIDA's 11 bands.

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Schema Foundation + Dummy Inference | 0/? | Not started | - |
| 2. Trajectory + Mission Planner | 0/? | Not started | - |
| 3. Real Training + Weight Swap + Mission Export + E2E | 0/6 | Not started | - |

## Critical-Path Timing (24-48 h hackathon)

Rough estimates; H0 = kickoff moment.

| Window | Activity |
|--------|----------|
| **H0-H1** | `.gitignore` (MARIDA, *.pth), Python 3.11 venv setup, dependency install per `research/STACK.md`, flip `kaggle.yml` `enable_gpu: true`, upload MARIDA as Kaggle Dataset (background), start `scripts/fetch_demo_env.py` (background, may take 20-40 min for CMEMS slices) |
| **H1-H4** | Phase 1 core: `core/schemas.py` (frozen), `core/config.py`, `ml/features.py` + Biermann test, `ml/model.py` + `ml/weights.py` dummy branch, `ml/inference.py` + sliding-window polygonization, CLI entrypoints. **Exit:** schema committed to git + `python -m backend.ml <tile>` produces valid FC |
| **H4-H16** | Phase 2 in parallel streams: (stream A) physics — `env_data.py`, `tracker.py` with UTM integration, 43.2 km synthetic test, real CMEMS+ERA5 smoke test; (stream B) mission — `scoring.py`, `planner.py` greedy+2-opt with edge-case tests. **Exit:** both streams green + full dummy-weight chain runs end-to-end. This is where the parallelizable work lives — physics and mission share zero critical-path dependencies on each other. |
| **H16-H28** | Phase 3 training: upload training script to Kaggle notebook, start 25-epoch run (~60-90 min clock time on P100), iterate if metrics miss on first run (second run is the "for keeps" attempt). In parallel on laptop: build `mission/export.py` (GPX + GeoJSON + PDF briefing). **Exit:** `kagglehub.model_upload` done + `mission/export.py` produces valid GPX/PDF on synthetic inputs |
| **H28-H32** | Weight swap: flip `cfg.ml.weights_source=our_real` in YAML -> `kagglehub.model_download` on laptop -> re-run full E2E chain -> validate < 15 s. Precompute 4-AOI fallback JSONs at `data/prebaked/*.json`. |
| **H32-H36** | Runtime freeze (no `pip install` or code changes), final E2E validation, 60 s screen recording of successful run, PDF briefing visual polish |
| **H36+** | Demo polish only: slide alignment, Q&A prep, fallback playback rehearsal. **No code edits.** |

## Requirements Coverage

**Total v1 requirements:** 25
**Mapped to phases:** 25
**Unmapped:** 0

| Phase | Requirement Count | Requirements |
|-------|-------------------|--------------|
| Phase 1 | 8 | INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-06, ML-01, ML-03, ML-04 |
| Phase 2 | 7 | PHYS-01, PHYS-02, PHYS-03, PHYS-04, PHYS-05, MISSION-01, MISSION-02 |
| Phase 3 | 10 | INFRA-05, ML-02, ML-05, ML-06, ML-07, ML-08, ML-09, MISSION-03, E2E-01, E2E-02 |

Every v1 requirement maps to exactly one phase. Traceability in `.planning/REQUIREMENTS.md` reflects this mapping.

---

*Roadmap created: 2026-04-17*
*Granularity: coarse (3 phases, hackathon scope)*
*Parallelization: Phase 2 streams (physics, mission) can run simultaneously after Phase 1 schema freeze*
