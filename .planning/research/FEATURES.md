# Feature Research — DRIFT Intelligence Layer

**Domain:** Satellite marine-plastic detection + 72 h Lagrangian drift forecasting + cleanup mission planning (Python-callable backend intelligence).
**Researched:** 2026-04-17
**Confidence:** HIGH (MARIDA benchmarks + OpenDrift validation + Ocean Cleanup references all corroborate; sub-pixel regression is MEDIUM since few peer-reviewed MARIDA regression benchmarks exist).

**Scope reminder.** This milestone ships three Python functions only:
```
run_inference(tile)    -> GeoJSON FeatureCollection
forecast_drift(dets, 72h) -> {frames:[...], kde_polys:[...]}
plan_mission(dets, ...) -> {waypoints, route, summary}
```
No FastAPI wiring, no React frontend, no live S2 ingestion. Features below are evaluated against this constraint.

---

## Feature Landscape

### Table Stakes (Users Expect These — credibility lost without them)

These are the capabilities that ocean-remote-sensing / Lagrangian-drift / maritime-ops judges and operators assume exist. Shipping without any one of them means the system looks like a toy.

| # | Feature | Why Expected | Metric Target | Complexity (hrs) | Notes |
|---|---------|--------------|---------------|------------------|-------|
| T1 | **Binary plastic/water semantic segmentation** on 11-band Sentinel-2 patches | Every MARIDA/MADOS/FloatingObjects baseline ships this; it is the minimum viable detection output. | IoU **>= 0.45** on MARIDA val (PRD §11.1); published baselines sit at 0.65-0.82 IoU so 0.45 is a conservative floor. | 4 | UNet++ + ResNet-18 encoder via `segmentation_models_pytorch`. Phase 1 uses `marccoru/marinedebrisdetector` pretrained weights to de-risk the Phase 2/3 integration. |
| T2 | **Per-pixel confidence score** (softmax probability, not just hard mask) | Downstream tracker & planner need to weight particles and prioritise waypoints. Without probabilities the whole "priority-weighted TSP" story collapses. | `conf_raw in [0,1]` emitted as `properties.conf_raw` per GeoJSON Feature. | 1 | Sigmoid output of detection head; no extra module needed. |
| T3 | **Polygonisation of mask -> GeoJSON** | The deliverable schema is GeoJSON; raw rasters are not a deliverable. Judges & INCOIS-alike consumers need vector features. | Schema-valid FeatureCollection: `{geometry:Polygon, properties:{conf_raw, conf_adj, fraction_plastic, area_m2, age_days_est, class}}` per PRD Appendix B. | 2 | `rasterio.features.shapes` + `shapely` simplification + `pyproj` CRS transform to EPSG:4326. |
| T4 | **Water-only / land-mask rejection** (don't predict plastic over land or clouds) | A detector that fires on land or cloud shadows is immediately disqualified in Q&A. MARIDA's 15-class scheme explicitly trains for this; the Mifdal 2021 + FloatingObjects baseline hard-masks non-water. | Water-pixel false-positive rate **<= 1 per 10^6 pixels** on a mixed land+water patch; SCL cloud mask applied pre-inference. | 3 | Two layers: (a) Sentinel-2 SCL band cloud mask, (b) OSM / GSHHG coastline shape for land mask. No ML needed. |
| T5 | **FDI + NDVI + PI spectral index computation** (Biermann 2020, Themistocleous 2020) | Every published marine-plastic paper reports FDI. If we don't compute it, judges will ask why and we look unserious. | Single-pixel sanity test: `features.compute_fdi(pixel) == paper_reference_value +/- 1e-3`. | 2 | Pure NumPy on bands B6/B8/B11 (FDI), B4/B8 (NDVI), B2/B4/B8 (PI). `backend/ml/features.py`. |
| T6 | **Lagrangian particle tracker** with **windage + surface currents** | OpenDrift, Parcels, and CMS all ship this as their minimum. Without windage, 72 h trajectories drift the wrong way on wind-dominated coastal scenarios. | Synthetic constant-velocity test: 0.5 m/s eastward -> 43.2 km / 24 h **+/- 1%** (PRD §15.1). | 4 | Euler integrator, hourly dt, windage alpha=0.02; CMEMS 1/12 deg currents + ERA5 0.25 deg 10m winds, bilinear spatiotemporal interpolation via xarray. |
| T7 | **Per-hour trajectory frames** (0, 1, ..., 72 h) | The downstream `plan_mission` consumer and any future frontend animation expect frame-indexed outputs. A single endpoint position is not a forecast. | `len(frames) == 73` (0..72 inclusive), each frame is a schema-valid FeatureCollection of particles. | 2 | Just a list of serialisations. Depends on T6. |
| T8 | **Greedy nearest-neighbour TSP mission planner** | Coast Guard / INCOIS operators need ordered waypoints, not an unordered pin list. Every planning competitor (NOAA MDP, OceanCleanup navigation system) ships ordered routes. | For N=50 detections: produces ordered list with `total_distance_km` monotone-decreasing vs. random ordering on 3+ synthetic seeds. | 3 | Greedy + 2-opt swap is sufficient for N<=100; exact TSP is unnecessary and wastes hours. |
| T9 | **Priority score on detections** (density x confidence x area) | Without prioritisation the TSP visits low-value waypoints first and the "mission plan" is operationally useless. | `priority = conf_adj * area_m2 * fraction_plastic`; top-K selection before TSP. | 1 | Pandas/GeoDataFrame scoring; K <= 20 for vessel feasibility. |
| T10 | **Vessel range / time budget constraint** | An unconstrained mission plan is just a sorted list; operators want "what can my 200 km / 12 h vessel actually do?" | Route total distance <= `vessel_range_km`; total time (distance / vessel_speed + on-station hours) <= `max_hours`. | 2 | Post-TSP pruning: drop tail waypoints until constraint satisfied. |
| T11 | **End-to-end function chain runs in < 15 s on a laptop** | PRD §2 and Core Value explicitly make this the defensible technical story. A 60 s pipeline is a dealbreaker in live demo. | `run_inference + forecast_drift + plan_mission` on one MARIDA 256x256 patch < 15 s wall clock on a CPU-only laptop. | 2 | Mostly a perf-hygiene task: batch inference, avoid geopandas round-trips, cache env NetCDFs. |
| T12 | **Contract-stable GeoJSON schema** (frozen after Phase 1) | Downstream consumers (tracker, planner, future API) cannot re-code when fields rename mid-hackathon. | JSON schema validator passes on outputs of all three functions; schema checked-in at `backend/schemas/`. | 2 | `jsonschema` library + a one-page schema doc. PRD §14 / Key Decisions lock this. |
| T13 | **Reproducible Python CLI entrypoint** (no API, no UI) | The whole scope statement says "three Python-callable functions". Judges will ask "can you run it?" and we need a one-liner. | `python -m drift.demo --tile X --origin lon,lat,range_km,hours -> writes detect.geojson, forecast.geojson, mission.geojson`. | 2 | Argparse + pathlib + the three function calls. |

**Table-stakes total: ~30 hrs.** (Everything below stacks on top of these.)

---

### Differentiators (What Wins the Hackathon)

These are the capabilities that let us say "no other team did this" during Q&A. Each is scoped to be defensible without over-claiming.

| # | Feature | Value Proposition | Metric Target | Complexity (hrs) | Notes |
|---|---------|-------------------|---------------|------------------|-------|
| D1 | **Sub-pixel fractional-cover regression head** (dual head: classification + fraction in [0,1]) | The problem statement (SKB_P5) explicitly names sub-pixel detection as "the hard part". Most MARIDA implementations ship binary masks only; a fraction head addresses the stated problem head-on. Closes the "are you really doing sub-pixel?" Q&A vulnerability. | MAE **<= 0.15** on synthetic mixed-pixel val set (alpha-blended plastic x water at ratios {0.05, 0.1, 0.2, 0.4}). PRD §11.1. | 5 | Second decoder head with MSE loss on fraction-labeled pixels. Training data synthesised by alpha-blending pure plastic x water MARIDA pixels. PRD §8.3 locks the narrative. |
| D2 | **Biofouling-aware confidence decay at inference** (`conf_adj = conf_raw * exp(-age/30)`) | Biofouling is the *second* explicitly-named challenge in SKB_P5. Competitors either ignore it (losing points) or over-claim spatiotemporal modelling (losing credibility). Our instrumented approach threads the needle. | Unit test: `conf_adj(age=30, conf_raw=0.9) ~ 0.33` (exp(-1)*0.9). Dashboard-ready numeric output. | 2 | Pure closed-form function applied post-detection. Age estimation comes from D3. |
| D3 | **Age regression head** (auxiliary output `age_days_est` from NIR suppression signature) | Without an age estimate the `conf_adj` decay is hand-waved. Training with simulated NIR x [0.5,1.0] augmentation teaches the head to recognise biofouling severity. PRD §8.4. | Ordinal agreement: predicted age rank-correlates with synthetic augmentation factor at Spearman rho **>= 0.5** on held-out val. | 4 | Small regression head on the same UNet++ bottleneck. Synthetic labels: days_since_clean = f(aug_factor). **Depends on D1 dual-head plumbing**. |
| D4 | **Biofouling augmentation during training** (40% of positives get NIR/RedEdge x [0.5, 1.0]) | Makes D3 trainable and makes the detector robust to aged plastic in production. Without this augmentation, the detector silently fails on >30-day-old patches. | On a biofouling-simulated val split (all positives dimmed to 0.5x NIR), IoU **>= 0.35** (vs. ~0.10 for a non-augmented baseline). | 3 | Torch transform, stochastic per-sample. Must be deterministic under `seed` for reproducibility. |
| D5 | **Ensemble drift spread** (N=20 particles per detection with perturbed wind/current + windage jitter) | Deterministic single-trajectory forecasts are not defensible; operators need "where is it likely, with uncertainty." OpenDrift/Parcels both ship ensemble spread; we match table-stakes and add KDE on top. | At +72 h: 68% of synthetic-buoy validation endpoints fall within predicted 1-sigma ellipse on >= 8/10 seeds. | 4 | N particles x 73 hours = 1460 positions per detection; still fast (pure NumPy). Perturbations: windage ~ N(0.02, 0.005), current ~ N(0, 0.1 m/s). |
| D6 | **Kernel-density-estimate (KDE) forecast polygons at +24/+48/+72 h** | A ring of dots is hard to read; a density contour is a one-glance decision tool. The Ocean Cleanup's own internal "plastic navigation" system uses exactly this representation. | At each horizon: 68%/95% contour polygons emitted as GeoJSON MultiPolygon with `properties.horizon_h` and `properties.percentile`. | 3 | `scipy.stats.gaussian_kde` on (lon, lat) -> evaluate on lat/lon grid -> `matplotlib.contour` -> shapely polygonise. Cached per forecast run. |
| D7 | **Multi-class disambiguation** (plastic vs. Sargassum vs. foam vs. wake) via MARIDA 15-class labels | FDI alone gives ~17% precision on plastic-vs-Sargassum; ML disambiguation is the reason to use MARIDA over FloatingObjects. This is the explicit answer to SKB_P5 challenge B. | Sargassum -> plastic **FPR <= 15%** (PRD §15.2); confusion matrix reported per MARIDA test class. | 3 | Train on 15-class softmax, then collapse non-plastic classes to "not plastic" for the binary deliverable but keep the class head for reporting. |
| D8 | **Forecast-convergence bonus in priority score** | Debris heading *toward* a coast in 72 h is higher-priority for cleanup than debris heading out to sea. This is the planner's intelligence moment — not just "where is it now" but "where is it going." | `priority *= convergence(forecast_track, coast)` where convergence = (1 - dist_to_coast_t72h / dist_to_coast_t0). | 2 | Requires T6+T8 + a coastline shapefile. **Depends on forecast_drift output**. |
| D9 | **Per-detection forecast attached to the mission briefing** (each waypoint carries a mini-forecast summary) | Operators don't want two disconnected reports; they want one briefing. Joint output = differentiator. | `plan_mission` output includes per-waypoint `forecast_summary = {t24h:[lon,lat], t48h:[lon,lat], t72h:[lon,lat]}`. | 2 | Pure glue: planner accepts the already-computed forecast and indexes it. |
| D10 | **Printable PDF mission briefing** (map thumbnail + waypoint table + vessel summary) | Coast Guard Ops cells do not read GeoJSON; they brief from PDFs. This is the "oh you actually thought about the user" moment. | One-page PDF, < 1 MB, generated in < 3 s, produced from a pure-Python toolchain (no headless Chrome). | 4 | `matplotlib` map thumbnail + `reportlab` or `fpdf2`. No browser dep. |
| D11 | **Deterministic seeded runs** (every function accepts `seed=...`) | Judges ask "run it again"; flakiness = death. Torch + NumPy + KDE all seeded. | Same inputs + same seed -> byte-identical GeoJSON outputs. | 1 | One line at top of each function. |
| D12 | **End-to-end smoke test in CI** (`pytest tests/test_e2e.py`) | Proves the whole chain works; answers the "can you reproduce" question without a live demo. | One test: real MARIDA patch in -> schema-valid detect + forecast + mission out, chain time < 15 s. | 2 | Depends on T1, T6, T8. Uses a tiny cached 256x256 patch checked into `tests/fixtures/`. |

**Differentiator total: ~35 hrs.** Stacked on table stakes: ~65 hrs.

**The three "oh, they actually did it" moments** (rank-ordered by judge impact per hour):
1. **D1 sub-pixel fractional head** — directly answers SKB_P5 challenge A. Highest ROI.
2. **D2 + D3 + D4 biofouling instrumentation** — answers SKB_P5 challenge C without over-claiming. Tells judges "we understood this, here's how we handled it, and here's what we'd need for the full solution."
3. **D5 + D6 ensemble + KDE forecast** — lifts the drift module from "physics lite" to "operationally credible." Ocean Cleanup uses exactly this representation.

---

### Anti-Features (Things Competitors Ship That We Deliberately Do NOT Build)

Codified to resist mid-hackathon scope creep. Every one of these has a plausible-sounding "but wouldn't it be cool if..." framing; every one would cost us demo polish time.

| Anti-Feature | Why Often Requested / Shipped | Why Problematic for THIS Milestone | Alternative / What We Ship Instead |
|--------------|-------------------------------|------------------------------------|-------------------------------------|
| **Live Sentinel-2 ingestion** (STAC crawler, Sentinel Hub auth, automated fetching) | "Real-time" is an easy slide. Competitors showcase cron jobs. | Auth flows fail in demo environments; cloud masking over wrong scene wastes hours; PRD §12 explicit guardrail. | Pre-stage 4-6 AOIs on disk. Judges only see the inference, not the ingestion, and the scope guardrail prevents a rabbit hole. |
| **OpenDrift / Parcels / full Lagrangian framework** | "Use the real tool" is a reviewer-flattering choice. | OpenDrift adds GDAL/proj dep hell, 20+ min cold-start, and Windows wheel breakage; OpenDrift 72 h RMSE (13-16 km) is not meaningfully better than a seeded Euler for 72 h horizons. | ~100 LOC Euler integrator with windage alpha=0.02. Validated against synthetic constant field (43.2 km / 24 h +/- 1%) and the published 72 h drifter-error range (PRD §11.1 target: < 25 km). |
| **Full 3D hydrodynamics / coupled ocean-atmosphere / Stokes drift beyond 2% windage** | Reviewers love "we added Stokes drift." | Stokes reduces separation distance by 34-40% over *long* runs; on a 72 h horizon the marginal gain is < 5 km, below our target error. Adds days of physics validation. | Document in README that Stokes = future work; justify windage-only for 72 h. |
| **Multi-satellite fusion** (Sentinel-1 SAR, Sentinel-3 OLCI, PlanetScope, drone imagery) | "Fusion" is a buzzword. | Each sensor has its own preprocessing pipeline; SAR needs speckle filtering + radiometric cal; OLCI resolution is 300 m (useless for windrows < 100 m); zero time budget. | Sentinel-2 L2A only. Tell judges the fusion story is architecturally possible but out-of-scope. |
| **Live re-training / online learning / active-learning loop** | "Self-improving" sounds good on a slide. | We barely have time for ONE training run on Kaggle. Concept drift in 48 h is nonsensical. | Frozen Phase-3 weights. Document retraining protocol in README. |
| **Transformer from scratch (Segformer, ViT, DINOv2)** | "We used a transformer" is perceived as state-of-the-art. | MARIDA's 1,381 patches is ~100x too small for ViT; published results show UNet++ matches or beats ViT on this dataset (ResAttUNet F1=0.95 with a CNN backbone). | UNet++ (ResNet-18 encoder) + SE spectral attention block. Defensible in Q&A with paper citations. |
| **ONNX / TensorRT on-device inference** | "Edge deployment" is a marketing bullet. | Build-system pain; on a laptop demo we gain nothing; ONNX conversion of multi-head UNet++ is a known footgun. | Plain PyTorch `.eval()` + `torch.no_grad()`. < 5 s per tile is already a PRD target. |
| **Cloud deployment (AWS/GCP, Docker swarm, K8s)** | "Production-ready" buzzword. | Demo laptop + localhost is less risky; zero gain for judging. | Document that containerisation is trivial; ship a `pyproject.toml` + one README line. |
| **FastAPI endpoints / REST API / websockets** | The existing `backend/api/routes.py` tempts re-wiring. | Explicit scope carve-out per PRD §12 and user instruction 2026-04-17: "only the intelligence part." Any API hook = scope creep. | `run_inference / forecast_drift / plan_mission` are **pure Python functions** callable from a script. A future milestone wires them into the existing mock endpoints. |
| **React / Mapbox / deck.gl frontend** | "Visual polish" is a huge hackathon edge. | Explicit scope carve-out. Intelligence milestone only. Downstream milestone handles UI. | `plan_mission` returns GeoJSON consumable by *any* frontend. Judges can see the raw GeoJSON in the demo. |
| **User accounts / RBAC / OAuth / multi-tenant** | "Production feature" expected in enterprise demos. | Zero value for hackathon judging; hours burned. | Single-user, single-process, no auth. |
| **UAV / USV / autonomous dispatch integration** | "Closed the loop from space to action" sounds incredible. | Regulatory, hardware, safety — not shippable in 48 h; demo would just be fake. | `plan_mission` outputs GPX; operators dispatch vessels manually. |
| **3D globe visualisation (Cesium)** | "Looks cool." | 2D Mapbox already looks great; Cesium adds 100MB of bundle and no judging value. | N/A — no frontend in this milestone. |
| **Mobile app / native iOS-Android** | "Cross-platform." | Multiplies build complexity; not shippable. | N/A. |
| **Dark mode / theme toggle / i18n / user settings** | "Polish." | 0% judging value vs. scope cost. | N/A. |
| **Automatic label refinement / semi-supervised pseudo-labeling** | "Recent SOTA technique." | Requires an unlabeled pool and several extra training cycles; Kaggle GPU budget does not allow. | Train on MARIDA as-is; document pseudo-labeling as future work. |
| **PDF briefing via headless Chrome / Puppeteer** | "Web-like PDFs look great." | Chromium dep fails on Kaggle-style environments; flaky in demo. | `matplotlib` + `reportlab` pure-Python pipeline (D10). |
| **Cost-aware routing / fuel optimisation / multi-vessel dispatch** | Optimisation papers make it sound essential. | Single-vessel greedy TSP is already non-trivial under time constraint; multi-vessel is a PhD thesis. | Single vessel, distance + time budget. Document multi-vessel as future milestone. |
| **Custom MARIDA labeling UI / annotation tool** | "Labeled our own data." | MARIDA + FloatingObjects + MADOS are already sufficient; labeling is weeks of work. | Use published datasets as-is. |

**Rule enforced by PRD §12 and §17 guardrails:** *If a teammate proposes adding any item from this list, they must first delete something from the BUILD column. Zero-sum scope.*

---

## Feature Dependencies

```
                    T5 (FDI/NDVI/PI indices)
                            |
                            v
        +-------+    T1 (binary segmentation, UNet++ + ResNet-18)
        |       |       |     ^
        |       |       |     |
        T4 (masks)      T2 (per-pixel conf)
        |               |
        +------+--------+
               v
           T3 (polygonise -> GeoJSON)
               |
               +-----> D7 (multi-class disambiguation; Sargassum vs plastic)
               |
               +-----> D1 (sub-pixel fraction regression head)
               |               \
               |                v
               |          D3 (age regression head)  <-- D4 (biofouling aug)
               |                |
               |                v
               |          D2 (confidence decay conf_adj)
               v
           T6 (Lagrangian Euler tracker) <-- needs CMEMS + ERA5 (data gate, out-of-scope for fetch)
               |
               +-----> T7 (per-hour frames 0..72)
               |
               +-----> D5 (ensemble spread, N=20 particles)
                          |
                          v
                      D6 (KDE polygons +24/+48/+72 h)
               |
               v
           T9 (priority score) <-- D8 (forecast-convergence bonus)
               |
               v
           T8 (greedy + 2-opt TSP)
               |
               v
           T10 (vessel range/time budget)
               |
               +-----> D9 (per-waypoint forecast attached)
               |
               +-----> D10 (PDF briefing)
               |
               v
        T11 (end-to-end < 15 s) <-- T12 (schema freeze) <-- T13 (CLI entrypoint)
               |
               v
           D12 (E2E pytest) <-- D11 (deterministic seeding)
```

### Dependency Notes (critical ones)

- **D1 (sub-pixel fraction) requires T1 (binary segmentation):** the regression head shares the UNet++ bottleneck. If T1 is a pretrained-only baseline (Phase 1), D1 must wait for Phase 3 training.
- **D3 (age regression) requires D1 (dual-head plumbing):** adding a third head is cheap *if* the dual-head infra exists; bolting it onto a single-head model doubles the effort.
- **D2 (confidence decay) requires D3 (age estimate):** without an age signal, `conf_adj = conf_raw * exp(-age/30)` reduces to `conf_adj = conf_raw` and the differentiator collapses.
- **D4 (biofouling aug) must be in the Phase-3 training script or D3 cannot learn age:** training-data decision, not inference-time.
- **T6 (tracker) requires data outside this milestone:** CMEMS + ERA5 NetCDFs. Phase 2 fetch script is a prerequisite. If data fetch fails, T6 can run on cached/synthetic fields for the E2E demo (fallback).
- **D6 (KDE polygons) requires D5 (ensemble spread):** KDE on a single trajectory is a zero-width PDF; you need N particles.
- **D8 (convergence bonus) requires T6 + a coastline shapefile:** adds one external asset (GSHHG or OSM coastline clipped to Indian EEZ).
- **D10 (PDF briefing) requires T8 + D9:** the PDF renders the route + per-waypoint forecast; with no planner output, the PDF is empty.
- **T11 (< 15 s) constrains D5's particle count:** 20 particles x 73 hours x (# detections) must fit in the time budget. If detections > 50, particles per detection drops to 10. Enforced by T11 acceptance test.
- **T12 (schema freeze) gates EVERYTHING downstream:** any field rename after Phase 1 costs hours across tracker + planner + PDF. Lock at end of Phase 1 per PRD Key Decisions.

### Conflicts

- **D1 (dual-head) conflicts with Phase-1 pretrained-only baseline:** `marccoru/marinedebrisdetector` is single-head. D1 requires Phase 3 custom training. Sequencing issue, not a permanent conflict.
- **D5 (20-particle ensemble) conflicts with T11 (< 15 s) at high detection counts:** mitigated by `top_k=50` cap on detections fed to the tracker. Under that cap the math works (50 x 20 x 73 = 73k positions, ~0.5 s of NumPy).
- **None of the anti-features conflict with the build list — they *replace* it.** That's the whole point of the zero-sum scope rule.

---

## MVP Definition (this milestone only — intelligence layer)

### Launch With (Phase 1 + 2 + 3 = H0..H36)

Minimum viable intelligence — what must ship for the demo to be runnable end-to-end.

- [ ] **T1** Binary plastic segmentation (Phase 1: pretrained; Phase 3: custom-trained)
- [ ] **T2** Per-pixel confidence
- [ ] **T3** Polygonisation -> GeoJSON
- [ ] **T4** Water/land/cloud masking
- [ ] **T5** FDI + NDVI + PI features
- [ ] **T6** Lagrangian Euler tracker with windage
- [ ] **T7** Per-hour frames (0..72)
- [ ] **T8** Greedy + 2-opt TSP
- [ ] **T9** Priority scoring
- [ ] **T10** Vessel range/time budget
- [ ] **T11** < 15 s end-to-end
- [ ] **T12** Frozen GeoJSON schema
- [ ] **T13** CLI entrypoint (`python -m drift.demo ...`)

Plus the three top-ROI differentiators:

- [ ] **D1** Sub-pixel fractional-cover head (directly answers SKB_P5 challenge A)
- [ ] **D2 + D3 + D4** Biofouling trio (answers SKB_P5 challenge C honestly)
- [ ] **D7** Multi-class disambiguation with Sargassum-FPR reporting (answers challenge B)

### Add After If Time (H36 buffer)

- [ ] **D5** Ensemble spread
- [ ] **D6** KDE polygons
- [ ] **D8** Forecast-convergence bonus
- [ ] **D9** Per-waypoint forecast on the mission output
- [ ] **D10** PDF briefing (very high judge value, medium cost — push hard for this)
- [ ] **D11** Deterministic seeding
- [ ] **D12** E2E smoke test

### Deliberately Out (see Anti-Features table)

Everything in the Anti-Features table. Non-negotiable per PRD §12.

---

## Feature Prioritisation Matrix

| Feature | User Value | Impl. Cost | Priority | Rationale |
|---------|------------|------------|----------|-----------|
| T1 Binary segmentation | HIGH | LOW (pretrained) / HIGH (trained) | P1 | Core deliverable. Starts with baseline. |
| T2 Per-pixel confidence | HIGH | LOW | P1 | Enables everything downstream. |
| T3 GeoJSON polygonisation | HIGH | LOW | P1 | Deliverable schema. |
| T4 Land/cloud mask | HIGH | LOW | P1 | Credibility killer if omitted. |
| T5 FDI/NDVI/PI | HIGH | LOW | P1 | Paper-defensible. |
| T6 Lagrangian tracker | HIGH | MEDIUM | P1 | Core deliverable. |
| T7 Per-hour frames | HIGH | LOW | P1 | Schema requirement. |
| T8 Greedy TSP | HIGH | LOW | P1 | Core deliverable. |
| T9 Priority scoring | HIGH | LOW | P1 | TSP is useless without it. |
| T10 Vessel constraint | HIGH | LOW | P1 | Operational credibility. |
| T11 < 15 s chain | HIGH | MEDIUM | P1 | PRD Core Value. |
| T12 Schema freeze | HIGH | LOW | P1 | De-risks downstream. |
| T13 CLI entrypoint | HIGH | LOW | P1 | Milestone deliverable. |
| **D1 Sub-pixel fraction** | **HIGH** | **MEDIUM** | **P1** | **Answers challenge A; highest judge ROI.** |
| **D2 Conf decay** | HIGH | LOW | P1 | Cheap win for challenge C. |
| **D3 Age head** | HIGH | MEDIUM | P1 | Required for D2 to be defensible. |
| **D4 Biofouling aug** | HIGH | LOW | P1 | Training-time; almost free. |
| **D7 Multi-class disambig** | HIGH | LOW-MEDIUM | P1 | Answers challenge B with FPR numbers. |
| D5 Ensemble spread | MEDIUM | MEDIUM | P2 | Lifts forecast credibility. |
| D6 KDE polygons | HIGH | MEDIUM | P2 | Visual-ready but requires D5. |
| D8 Convergence bonus | MEDIUM | LOW | P2 | Planner intelligence moment. |
| D9 Per-waypoint forecast | MEDIUM | LOW | P2 | Tight coupling between modules. |
| **D10 PDF briefing** | **HIGH** | **MEDIUM** | **P2 (push to P1 if time)** | **"Oh, they thought about the user" moment.** |
| D11 Deterministic seeds | MEDIUM | LOW | P2 | Q&A insurance. |
| D12 E2E test | HIGH | LOW | P2 | Proves it works. |

**Priority key:**
- P1: Must have for the milestone demo. ~30-35 hrs table stakes + ~15 hrs high-ROI differentiators = **~45-50 hrs**, fits within 36 h feature-freeze if team is 2-3 devs in parallel.
- P2: Should have, add at H28-H36. ~15 hrs, mostly glue.
- P3: Future milestone (none in this list; everything P3 went to anti-features).

---

## Competitor Feature Analysis

| Feature | MARIDA reference (Kikaki 2022) | `marccoru/marinedebrisdetector` | OpenDrift / Parcels | The Ocean Cleanup (ADOPT / AWS nav system) | Our Approach |
|---------|-------------------------------|----------------------------------|----------------------|---------------------------------------------|---------------|
| Detection architecture | RF baselines + simple CNNs; multi-class 15-way | UNet++ (ResNet-18); combined MARIDA + FloatingObjects + S2Ships + PLP datasets | N/A | Internal YOLO-class + proprietary ADIS for ship-mounted cameras | UNet++ (ResNet-18) + SE spectral attention; 14-channel input (11 bands + FDI + NDVI + PI) |
| Sub-pixel regression | NOT in original MARIDA paper (classification only) | No (binary output) | N/A | Not published | **D1: dual head, MSE on synthetic mixed pixels** |
| Biofouling | Not addressed | Not addressed | N/A | Acknowledged, not implemented | **D2+D3+D4: aug + age head + decay** |
| Multi-class disambiguation | Full 15-class | Collapses to binary | N/A | Proprietary | D7: train 15-class, report Sargassum FPR, ship binary |
| Drift model | N/A | N/A | Full Runge-Kutta, Stokes drift, wave radiation | Proprietary + HYCOM | **T6: Euler + windage alpha=0.02 + CMEMS + ERA5** |
| Ensemble spread | N/A | N/A | Yes (Parcels ensembles) | Yes (internal) | **D5: N=20 perturbed particles** |
| KDE forecast polygons | N/A | N/A | Available via post-proc | Yes (internal) | **D6: scipy.stats.gaussian_kde + shapely contours** |
| Mission planning / routing | N/A | N/A | N/A | Yes (AWS navigation system) | **T8+T9+T10: greedy + 2-opt + priority + vessel budget** |
| PDF briefing | N/A | N/A | N/A | Internal only | **D10: matplotlib + reportlab** |
| Live S2 ingestion | N/A (dataset only) | No | N/A | Yes (ADOPT via Sentinel) | Deliberately NOT (see anti-features) |
| Output format | Geotiff + CSV labels | GeoTIFF mask | NetCDF trajectories | Not public | GeoJSON everywhere + GPX mission |

**Where we win:** D1 + D2/3/4 + D10 are uncommon in any single system. The Ocean Cleanup has detection-and-forecast; few combine biofouling instrumentation, sub-pixel regression, AND one-click mission planning in the same pipeline. That is our defensible novelty.

**Where we choose not to compete:** full multi-satellite fusion, live ingestion, 3D hydro, real-time websockets. All anti-features. We concede these deliberately.

---

## Numeric Metric Targets (with sources)

Consolidated for the downstream requirements doc.

### Detection

| Metric | Target | Source | Notes |
|--------|--------|--------|-------|
| IoU (MARIDA val, binary plastic) | **>= 0.45** | PRD §11.1; published baselines 0.67-0.82 | Conservative floor; actual target 0.55+ |
| Precision @ conf > 0.7 | **>= 0.75** | PRD §11.1 | Reduces Sargassum FPs |
| Recall @ conf > 0.5 | **>= 0.60** | Derived from MARIDA baselines | Complement to precision target |
| Macro-F1 (15-class) | >= 0.65 | MARIDA Kikaki 2022 RFSS+SI+GLCM baseline at 0.79 F1 | Multi-class quality floor |
| Sub-pixel fraction MAE | **<= 0.15** | PRD §11.1 (synthetic val) | Direct evidence for challenge A |
| Sargassum -> plastic FPR | **<= 15%** | PRD §15.2 | Direct evidence for challenge B |
| Water-pixel FPR | <= 10^-6 (1 per 10^6 pixels) | Standard for remote-sensing production detectors | Depends on T4 masking |
| Water-pixel rejection rate | >= 90% (equivalently, TNR >= 0.90 on clear water) | Standard; MARIDA negatives explicit | Required by §4 problem statement |
| Inference latency (1024x1024) | **<= 5 s** CPU | PRD §11.1 | Enables T11 |

### Forecast

| Metric | Target | Source | Notes |
|--------|--------|--------|-------|
| Synthetic field test (eastward 0.5 m/s, 24 h) | 43.2 km +/- **1%** | PRD §15.1 unit test | Sanity check for integrator |
| 72 h endpoint error vs. drifter | < **25 km** | PRD §11.1; published OpenDrift 72h is 13-16 km | Realistic target given Euler + no Stokes |
| Ensemble spread 1-sigma coverage | **>= 68%** of synthetic buoy endpoints | Standard ensemble-forecast quality metric | Evidence for D5 |
| Frame count | len == 73 (hours 0..72) | Schema | Hard requirement |

### Mission

| Metric | Target | Source | Notes |
|--------|--------|--------|-------|
| Greedy TSP vs random ordering | total_distance_km **strictly less** on 3/3 random seeds | Sanity check | Proves planner does something |
| Route total distance | <= `vessel_range_km` | PRD §6 F5 | Hard constraint |
| Route total time | <= `max_hours` | PRD §6 F5 | Hard constraint |
| Top-K selection | K <= 20 default, configurable | Operational realism | 20 waypoints ~ 1 day mission |
| PDF size | < 1 MB | Practical for email to ops cell | D10 |
| PDF generation latency | < 3 s | Demo polish | D10 |

### Integration

| Metric | Target | Source |
|--------|--------|--------|
| Full chain wall-clock (CPU laptop) | **< 15 s** | PRD Core Value |
| Schema validity | 100% of outputs pass `jsonschema` check | T12 |
| Determinism | byte-identical outputs for same inputs + same seed | D11 |

---

## Sources

- [MARIDA: A benchmark for Marine Debris detection from Sentinel-2 remote sensing data (Kikaki 2022)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0262247) — PLOS One. Primary benchmark + 15-class schema.
- [MARIDA dataset + docs](https://marine-debris.github.io/) — data access, splits, confidence weights.
- [MARIDA GitHub + baseline code](https://github.com/marine-debris/marine-debris.github.io) — RF + CNN baselines.
- [Binary reformulation for marine debris detection in Sentinel-2 imagery (Frontiers 2026)](https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2026.1765021/full) — combined MARIDA+MADOS benchmarks; IoU=0.82, F1=0.90 on modern UNet.
- [MarcCoru/marinedebrisdetector](https://github.com/MarcCoru/marinedebrisdetector) — pretrained UNet++ weights for Phase 1 baseline.
- [Large-scale detection of marine debris in coastal areas with Sentinel-2 (iScience 2023)](https://www.cell.com/iscience/fulltext/S2589-0042(23)02479-3) — combined-dataset + UNet++ arch paper behind `marinedebrisdetector`.
- [Finding Plastic Patches in Coastal Waters using Optical Satellite Data (Biermann 2020, Sci Rep)](https://www.nature.com/articles/s41598-020-62298-z) — FDI definition; Naive Bayes baseline on FDI+NDVI.
- [Towards Detecting Floating Objects on a Global Scale (Mifdal 2021)](https://ui.adsabs.harvard.edu/abs/2021ISPAn..53..285M/abstract) — FloatingObjects dataset; CNN-vs-spectral-index study.
- [FloatingObjects dataset (ESA-PhiLab)](https://github.com/ESA-PhiLab/floatingobjects) — 26 globally distributed S2 scenes, 3,297 annotations.
- [ResAttUNet: Detecting Marine Debris using an Attention activated Residual UNet](https://arxiv.org/pdf/2210.08506) — F1=0.95 but IoU=0.67 on MARIDA; CBAM attention reference.
- [Emerging Technologies for Remote Sensing of Floating and Submerged Plastic Litter (MDPI 2024)](https://www.mdpi.com/2072-4292/16/10/1770) — biofouling effect on NIR reflectance (30-60% suppression at depth).
- [Hyperspectral reflectance of pristine / ocean-weathered / biofouled plastics (ESSD 2024)](https://essd.copernicus.org/preprints/essd-2023-209/essd-2023-209-manuscript-version4.pdf) — spectral basis for biofouling age simulation.
- [Validation of OpenDrift-Based Drifter Trajectory Prediction (JOET 2024)](https://www.joet.org/journal/view.php?viewtype=pubreader&number=3110) — 72 h NCLS errors: 13.68 km (leeway) / 15.80 km (oceandrift). Our < 25 km target is realistic.
- [OpenDrift documentation / CMEMS example](https://opendrift.github.io/gallery/example_long_cmems.html) — reference for Euler integrator design.
- [Performance diagnostics for probabilistic Lagrangian drift prediction (Taylor & Francis 2025)](https://www.tandfonline.com/doi/full/10.1080/1755876X.2025.2538383) — ensemble skill scores; basis for D5 1-sigma coverage target.
- [Assessing ocean ensemble drift predictions vs. oil slicks (Frontiers 2023)](https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2023.1122192/full) — ensemble drift spread and KDE visualisation reference.
- [Surface drifters in the German Bight: validation considering windage and Stokes drift](https://www.researchgate.net/publication/317151414_Surface_drifters_in_the_German_Bight_model_validation_considering_windage_and_Stokes_drift) — windage 0.5-3% range; justifies our 2% choice.
- [The Ocean Cleanup + AWS navigation system](https://theoceancleanup.com/press/press-releases/the-ocean-cleanup-and-aws-join-forces/) — competitor reference for mission-planning intelligence.
- [The Ocean Cleanup AI technology overview](https://sustainability.aboutamazon.com/stories/how-aws--the-ocean-cleanup--and-artificial-intelligence-are-find) — ADIS + predictive modelling details.
- [A Competition-Based Large Neighborhood Search for Vessel Routing — Sustainable Marine Debris Cleanup (Springer 2024)](https://link.springer.com/chapter/10.1007/978-981-95-4960-3_11) — MILP + GNOME reference for vessel routing; justifies why we keep it simple (greedy + 2-opt). 
- [Green marine waste collector routing (Cluster Computing 2024)](https://link.springer.com/article/10.1007/s10586-024-04812-w) — alternative optimisation; also notes simple greedy is competitive at small N.
- [Review of automatic plastic detection in water (PMC 2024)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11359068/) — comprehensive survey of index-method FPR; index-only precision < 17%, justifying our ML-over-index approach.
- [Detection of Sargassum from Sentinel using Deep Learning (MDPI 2023)](https://www.mdpi.com/2072-4292/15/4/1104) — basis for Sargassum-FPR target; F1 88% on MSI.

---

*Feature research for: satellite marine-plastic detection + Lagrangian drift + cleanup mission planning (Python intelligence layer)*
*Researched: 2026-04-17*
*Next consumer: `.planning/research/SUMMARY.md` + roadmap Phase 1/2/3 scoping*
