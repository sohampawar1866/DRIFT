# PRD — PlastiTrack: Autonomous Sub-Pixel Detection & Trajectory Mapping of Floating Marine Macroplastics

**Hackathon:** Sankalp Bharat — Problem SKB_P5
**Team Target:** Top 3 / Winning submission
**Timeframe:** 24–48 hours
**Date:** 2026-04-17

---

## Context

Marine plastic pollution enters the ocean at ~11 Mt/year. The Sankalp Bharat P5 challenge asks teams to build an **autonomous, satellite-driven system** that (a) detects floating macroplastic patches at sub-pixel scale from Sentinel-2 imagery, (b) disambiguates plastic from spectrally-similar natural matter (Sargassum, foam), (c) compensates for biofouling-induced signal decay, (d) forecasts drift using wind + ocean currents, and (e) delivers it all through a government-facing dashboard that drives cleanup mission planning.

**Why this matters now:** India's 7,500 km coastline makes this strategically aligned with Sankalp Bharat's theme. A working prototype could plug into INCOIS/NCCR workflows. The judges will reward teams who (1) actually execute the sub-pixel ML story with proper data, (2) close the loop from pixels → cleanup mission, and (3) show a visually striking, working demo — not slides.

---

## 1. Deep Problem Understanding

### 1.1 The Four Core Technical Challenges

| # | Challenge | Technical Crux | Feasibility (48h) |
|---|-----------|----------------|--------------------|
| A | **Sub-pixel detection** | Sentinel-2 MSI = 10 m GSD (100 m²/pixel). Macroplastic windrows often cover <20 m² → SNR-limited. Linear mixing model: `ρ_pixel = f_plastic · ρ_plastic + (1−f_plastic) · ρ_water`. | **HIGH** — MARIDA dataset has labeled sub-pixel patches; proven with U-Net/RF baselines (Biermann 2020, Mifdal 2021). |
| B | **Spectral confusion** | Weathered plastic, *Sargassum*, sea foam, wood, pumice share reflectance peaks in NIR (~705, 740 nm). FDI alone gives ~65% precision; need multi-feature disambiguation. | **HIGH** — solved by multi-band attention (ViT) + contextual features (texture, shape, proximity to coast). |
| C | **Biofouling** | Algal biofilm (chlorophyll-a) accumulates on floating plastic over weeks, suppressing NIR reflectance by 30–60%. Signal → indistinguishable from algae. Needs temporal modeling. | **MEDIUM** — full spatiotemporal model is hard; we simulate via **augmentation + confidence-decay heuristic** (see §4). |
| D | **Trajectory prediction** | Lagrangian drift: `dx/dt = v_current + α·v_wind + v_stokes`, where α (windage) ≈ 1–3% for partially submerged plastic. Needs CMEMS currents + ERA5 winds. | **HIGH** — OpenDrift or ~100 LOC custom Euler integrator; physics is textbook. |

### 1.2 Criticality vs. Feasibility Matrix (MVP Selection)

```
                   HIGH IMPACT
                        │
       Sub-pixel DL ────┼──── Trajectory Forecast
       (A)              │     (D)
                        │
    ─────────────── FEASIBILITY ───────────────
                        │
       Biofouling       │     Real-time Sat
       (C - simplified) │     Ingestion (skip)
                        │
                   LOW IMPACT
```

**MVP priorities:** A + D are table-stakes for winning. B is solved implicitly by A's multi-band model. C gets a lightweight treatment. Real-time satellite streaming is explicitly out of scope.

---

## 2. Target Users

Specific, not generic:

1. **Primary — INCOIS (Indian National Centre for Ocean Information Services, Hyderabad)**
   Already publishes ocean state forecasts; needs a plastic monitoring layer for their existing dashboards. Our output format (GeoJSON + NetCDF) will align with their stack.

2. **Primary — NCCR (National Centre for Coastal Research, Chennai)**
   Runs India's beach litter monitoring. Currently samples <50 sites. Needs open-ocean visibility.

3. **Primary — Indian Coast Guard (Operations cells)**
   Tasked with coordinating cleanup and marine pollution response. Consumes mission waypoints, not raw imagery.

4. **Secondary — Municipal coastal authorities** (Mumbai, Kochi, Chennai, Kolkata port trusts) — need 72hr warnings of debris making landfall.

5. **Secondary — International** — NOAA Marine Debris Program, UNEP, The Ocean Cleanup (System 03 deployment planning).

6. **Tertiary — Maritime insurers & shipping operators** — debris patches threaten intakes/props.

**User persona for demo:** "Commander Priya Rao, Coast Guard Ops, Mumbai. Needs to know: *where* is plastic right now, *where* will it be in 3 days, and *where* should I send my 2 available vessels?"

---

## 3. Key Pain Points (Why Current Solutions Fail)

| Pain Point | Current State | Evidence from Problem Statement |
|-----------|---------------|-------------------------------|
| **Localized site surveys miss 99% of open-ocean debris** | Beach transects, net trawls | "tedious, localized site surveys... fundamentally incapable of tracking chaotic trajectories" |
| **Single-index detectors produce unusable false-positive rates** | FDI thresholding alone | "distinguishing weathered plastics from natural marine materials... nearly identical reflectance spectra" |
| **Sub-pixel blindness in mid-res satellites** | Thresholds on 10m pixels | "plastic debris may cover less than 20% of a single pixel's area" |
| **Signal degrades over time, tracking fails** | Static detection models | "biofouling...dampens its RGB signal over time" |
| **No link from detection to action** | Raw imagery handed to analysts | (Implied by "coordinate efficient maritime cleanup initiatives") |
| **Static snapshots without forecast** | Past-tense maps | (Implied by "dynamic trajectory modeling") |

---

## 4. Smart Scope Definition ⭐ (The Winning Discipline)

This is where most hackathon teams fail. We are ruthless.

### BUILD ✅ (the 6 things that win)

1. **Detection model** — fine-tuned U-Net (with lightweight attention bottleneck) on **MARIDA dataset** + FloatingObjects supplement. Multi-band input: Sentinel-2 B2/B3/B4/B6/B8/B11 + computed FDI + NDVI + PI (Plastic Index). Output: per-pixel plastic probability + sub-pixel fraction estimate.
2. **Pre-staged demo tiles** — 4–6 Sentinel-2 L2A tiles over known/synthetic hotspots (Gulf of Mannar, Bay of Bengal mouth, Mumbai offshore, Arabian Sea gyre edge). Downloaded in advance; served locally.
3. **Trajectory engine** — Euler-step Lagrangian particle tracker. Inputs: CMEMS surface currents (u/v), ERA5 10-m winds, windage coeff α=0.02. 72-hour horizon, 1-hour steps.
4. **Biofouling-aware confidence** — age-decay function applied to predicted detections: `conf_adj = conf_raw · exp(−λ·days_since_last_clean_detection)`. Training-time augmentation simulates dampened NIR for robustness.
5. **Dashboard** — React + Mapbox/Leaflet. Four views: (i) live detection overlay, (ii) hotspot heatmap, (iii) 72-hr trajectory animation with time slider, (iv) cleanup mission export (GeoJSON + GPX waypoints).
6. **Cleanup mission planner** — simple greedy TSP over top-K hotspots weighted by (debris density × accessibility × forecast convergence). One-click export.

### SIMPLIFY 🟡 (good enough for demo, deep enough to defend)

- **Biofouling** → no full spatiotemporal CNN-LSTM. We ship: (a) synthetic NIR-dampening augmentation at train time, (b) a decay heuristic at inference time, (c) a chart on the dashboard showing "confidence vs. estimated debris age" to tell the story. Defensible to judges; does not consume 20 hours.
- **Trajectory physics** → Euler not RK4; no Stokes drift term unless time permits; use pre-downloaded 7-day NetCDF slice instead of live API. Accuracy lost is marginal for 72h horizons.
- **Training** → fine-tune pre-trained Segformer-B0 or small U-Net encoder from ImageNet. Don't train from scratch. 2 hours of training, not 20.
- **Area coverage** → 4 demo AOIs, not global. Judges don't reward coverage they can't verify.

### IGNORE ❌ (these will kill you)

- Real-time Sentinel-2 ingestion pipeline (STAC cron, async fetching)
- Full 3D hydrodynamic modeling / coupled ocean-atmosphere
- Multi-satellite fusion (Sentinel-3 OLCI, PlanetScope, drone imagery)
- Mobile apps, role-based access, OAuth/SSO
- Automated UAV/USV dispatch
- Historical reanalysis beyond demo window
- SAR (Sentinel-1) integration — huge rabbit hole
- On-device/edge inference

**Justification philosophy:** Every hour spent on "ignore" items = an hour not spent on a polished demo. Judges score what they see, not what's in your README.

---

## 5. Proposed Solution — System Overview

### 5.1 End-to-End Pipeline

```
┌───────────────────────┐
│ Sentinel-2 L2A Tiles  │  (pre-staged .SAFE / COG, 4 AOIs)
│ (B2,B3,B4,B6,B8,B11)  │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ Preprocessing         │  cloud mask (SCL), land mask (OSM coastline),
│ (Rasterio, NumPy)     │  resample B6/B11 → 10m, scale 0–1
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ Feature Stack (9ch)   │  RGB + RedEdge + NIR + SWIR +
│ FDI, NDVI, PI         │  spectral indices
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│ Detection Model       │  U-Net w/ spectral attention; outputs
│ (PyTorch, ~5M params) │  plastic-probability + sub-pixel fraction
└──────────┬────────────┘
           │  GeoJSON polygons w/ confidence, area, age-hint
           ▼
┌───────────────────────┐
│ Biofouling Adjuster   │  conf_adj = conf · decay(age_days)
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐      ┌──────────────────────┐
│ Trajectory Engine     │◀─────│ CMEMS currents +     │
│ (Euler, 72h, 1hr dt)  │      │ ERA5 winds (NetCDF)  │
└──────────┬────────────┘      └──────────────────────┘
           │  particle paths + forecast hotspot polygons
           ▼
┌───────────────────────┐
│ FastAPI Backend       │  /detect /forecast /mission
└──────────┬────────────┘
           │  REST + GeoJSON
           ▼
┌───────────────────────┐
│ React + Mapbox        │  map, heatmap, timeslider, mission export
│ Dashboard             │
└───────────────────────┘
```

### 5.2 Data Flow Summary

1. Ingest pre-staged S2 tile → clip to AOI.
2. Stack features → pass to detector.
3. Post-process probability map → polygonize (rasterio.features) → apply biofouling decay.
4. Seed detected polygons as Lagrangian particles → integrate with wind/current fields.
5. Rasterize particle density at t+24h, t+48h, t+72h → forecast heatmaps.
6. Serve all layers as GeoJSON/PNG tiles from FastAPI.
7. Frontend composes layers on Mapbox; user scrubs time, clicks hotspot, exports mission.

---

## 6. Core Features (MVP — Realistic in 24–48h)

### Must-Have (P0 — ship or die)

1. **F1: Sub-pixel plastic detector** — U-Net ingesting 9-ch feature stack, outputting probability mask + fractional cover. IoU ≥ 0.45 on MARIDA val.
2. **F2: Interactive map dashboard** — pan/zoom, base layer (satellite), detection overlay with opacity slider, confidence legend.
3. **F3: 72-hour drift forecast** — time-slider animation showing particle positions / density heatmap at +0h, +24h, +48h, +72h.

### Standout (P1 — what wins)

4. **F4: Biofouling confidence-decay visualization** — side panel charting detection confidence vs. estimated age; auto-flagging "aging" patches.
5. **F5: Cleanup mission planner + export** — "Plan Mission" button: ranks top-K hotspots by priority score, computes vessel-friendly waypoint order, exports GPX + GeoJSON + printable PDF briefing.

### Nice-to-Have (P2 — only if ahead of schedule)

6. **F6: What-if wind scenario slider** — adjust windage α to see trajectory sensitivity.
7. **F7: Before/after time travel** — load a second date, show debris movement observed vs. predicted (validation).

---

## 7. User Flow (Dashboard Interaction)

**Primary flow — "From satellite to mission in 3 clicks":**

1. **Landing** — user opens dashboard; map centers on India's EEZ. Sidebar shows 4 demo AOIs as cards with "last updated" timestamps.
2. **Select AOI** — user clicks "Gulf of Mannar — 2026-04-15." Map zooms; detection overlay loads within 2 seconds. Legend shows confidence bins (low/med/high) and area coverage summary ("~42 detected patches, 3.8 hectares estimated plastic").
3. **Inspect hotspot** — user clicks a red cluster. Popup shows: confidence, estimated area, age, biofouling adjustment, 72hr forecast path preview.
4. **Forecast mode** — user toggles "Forecast" → time-slider appears. Scrubs from +0h to +72h; heatmap animates drift. Vector field overlay optional.
5. **Plan mission** — user clicks "Plan Cleanup Mission." Modal: select vessel range (km), available hours, origin port. Click "Generate." Output: ordered waypoint list + map route + export buttons (GPX/GeoJSON/PDF).
6. **Export** — one click. User is done in under 90 seconds.

**Secondary flow — analyst exploration:**
AOI → switch bands (show raw FDI vs. DL output) → overlay Sargassum-likelihood layer → export report.

---

## 8. Technical Approach (High-Level but Smart)

### 8.1 Detection Model

**Choice: U-Net with spectral attention bottleneck (hybrid CNN + lightweight Transformer).**

- **Why not pure ViT/Segformer?** Data is limited (MARIDA has ~1300 labeled scenes); ViTs underperform on small datasets and are slow to train. U-Net with pretrained ResNet-18 encoder hits the sweet spot.
- **Why add attention?** A single squeeze-and-excitation (SE) block on channel dimension gives the model explicit spectral importance weighting — critical for discriminating plastic vs. Sargassum.
- **Output heads (multi-task):**
  1. Binary plastic mask (primary loss: Dice + BCE, weighted).
  2. Sub-pixel fraction regression (aux loss: MSE on fraction-labeled pixels where available).
- **Input:** 9-channel stack at 10m, 256×256 patches, batch size 16.
- **Training:** 20–30 epochs, Adam 1e-4, cosine schedule, ~1.5 hours on a single T4/3090.

### 8.2 FDI Computation (Explicit)

Biermann et al. 2020 formulation:
```
FDI = R_NIR − R'_NIR
where R'_NIR = R_RedEdge2 + (R_SWIR1 − R_RedEdge2) · (λ_NIR − λ_RE2) / (λ_SWIR1 − λ_RE2)
Sentinel-2: λ_NIR=B8 (832nm), λ_RE2=B6 (740nm), λ_SWIR1=B11 (1613nm)
```
FDI + NDVI together discriminate plastic from Sargassum because Sargassum has high NDVI while plastic is ambiguous in NDVI but high in FDI. Both indices feed the network as explicit channels.

### 8.3 Sub-Pixel Handling (the honest bit)

We do **not** claim true spectral unmixing in an MVP. We approximate:
- **Training-time:** synthesize sub-pixel training examples by alpha-blending pure plastic pixel spectra with water spectra at ratios {0.05, 0.1, 0.2, 0.4}. Labels carry the fractional cover.
- **Inference-time:** model's regression head predicts fractional cover. Calibrate against MARIDA held-out set.
- **Judge-facing story:** "We treat sub-pixel detection as a joint classification + fractional regression task, training with synthetic mixed pixels — this mirrors Linear Spectral Mixture Analysis but leverages learned features for non-linear cases." This is defensible and real.

### 8.4 Biofouling Model

- **Training-time augmentation:** for 40% of positive samples, multiply NIR and RedEdge bands by sampled factor ∈ [0.5, 1.0] simulating 0–60 day biofouling age. Add corresponding "age" label (synthetic).
- **Inference-time decay:** each detection carries an "estimated age" (from a small regressor head or persistence tracking across dates). Confidence shown on dashboard: `conf_display = conf_raw · exp(−age_days / τ)` with τ=30 days.
- **Judge story:** We don't hide that full temporal modeling needs months-long S2 time series; we instrument the problem so the dashboard and model *handle* the effect even if we don't fully solve it.

### 8.5 Trajectory Engine

Minimal viable physics, correctly implemented:
```python
# For each detected particle at (x0, y0, t0):
for t in range(0, 72):  # hourly steps
    u_c, v_c = interp_currents(x, y, t)    # CMEMS, 0.083° grid
    u_w, v_w = interp_winds(x, y, t)        # ERA5, 0.25° grid
    u_total = u_c + 0.02 * u_w              # 2% windage
    v_total = v_c + 0.02 * v_w
    x += u_total * 3600                      # dt=1hr in seconds
    y += v_total * 3600
    path.append((x, y, t))
```
Wrap ~20 particles per detected patch for ensemble spread → kernel-density-estimate heatmap at each forecast hour. Lightweight, physically grounded, looks great animated.

### 8.6 Stack Summary

| Layer | Choice | Rationale |
|-------|--------|-----------|
| DL framework | PyTorch 2.x + segmentation_models_pytorch | Fastest path to U-Net w/ pretrained encoder |
| Geo | Rasterio, GDAL, Shapely, GeoPandas | Standard; handles S2 COGs painlessly |
| Env data | Pre-downloaded CMEMS + ERA5 NetCDFs | Avoids API auth in demo |
| Backend | FastAPI + Uvicorn | Async, GeoJSON-friendly, 30-min setup |
| Frontend | React + Vite + Mapbox GL JS + deck.gl | Mapbox for base + heatmap; deck.gl for animated particle layer |
| Charts | Recharts (confidence decay) | Lightweight |
| Export | togpx, jsPDF | Waypoint + briefing export |
| Deployment | Single-box Docker Compose, localhost demo | No cloud deploy risk during judging |

---

## 9. Innovation & Differentiation (Why Judges Pick Us)

1. **Dual-head detector (classification + sub-pixel fraction regression)** — most teams ship binary masks; we quantify "how much plastic" per pixel. Judges who read the problem statement know sub-pixel is *the* hard part — we address it head-on.
2. **Closed-loop: detection → forecast → mission waypoints.** Most teams stop at detection. We go all the way to a one-click deployable cleanup plan. This is the "oh, they actually built the whole thing" moment.
3. **Biofouling instrumented, not hand-waved.** Augmentation + decay heuristic + dashboard visualization = we show judges we understood the temporal problem even if we didn't solve it fully.
4. **FDI + learned spectral attention (best of both worlds)** — physics-informed features feeding an ML model with explicit channel weighting. Interpretable *and* accurate.
5. **Regional relevance (Sankalp Bharat framing).** Demo AOIs over Indian EEZ, integration hook for INCOIS format, cleanup planner aware of Indian port origins.
6. **Honest scope.** We will tell judges exactly what is real vs. simulated. Credibility compounds; teams who over-claim lose in Q&A.

**"Our standout line":** *"PlastiTrack is the only system that takes a Sentinel-2 scene and returns a cleanup mission — waypoints, vessel plan, and briefing — in under 90 seconds."*

---

## 10. Demo Strategy ⭐ (Where Hackathons Are Won)

### 10.1 Demo Narrative (5-minute pitch)

- **0:00 – 0:30** — Hook: "Every minute, a garbage truck's worth of plastic enters the ocean. India's Coast Guard manages 2.3M sq km. How do you know where to look?"
- **0:30 – 1:30** — Problem tech depth: show a raw Sentinel-2 tile. Point to pixel size. "Plastic is often <20% of a 100m² pixel. FDI alone is 65% precise. Sargassum looks the same."
- **1:30 – 3:30** — Live demo: select Gulf of Mannar AOI → detections appear → click hotspot → forecast animation plays over map → click "Plan Mission" → waypoints + GPX export.
- **3:30 – 4:15** — Technical highlights: dual-head model, biofouling decay chart, confidence-over-age visualization.
- **4:15 – 5:00** — Impact: "Plug into INCOIS. One command center. 7,500 km coast. Real cleanup." Q&A.

### 10.2 Visual "Wow" Moments

1. **Satellite layer → heatmap reveal** — toggle animation, detections "light up" over blue ocean.
2. **Particle animation** — thousands of dots flowing along current vectors like a fluid simulation. (deck.gl ParticleLayer or IconLayer with frame interpolation.)
3. **Time-slider scrub** — user drags 0 → 72h, sees debris swept toward a beach. Dramatic.
4. **Mission export** — map draws vessel route line; PDF briefing slides out with coordinates, ETA, fuel estimate.
5. **Split-screen "before/after" biofouling** — same patch with NIR signal simulated over 30 days.

### 10.3 Fallback Plan (if something breaks mid-demo)

- **Pre-recorded 60s screen capture** of the full flow, ready to play if live demo fails.
- **Static precomputed results** for all 4 AOIs — dashboard still works even if model server is down.
- **Plan B narrative:** "Let me show you the core flow from cache while the inference warms up…"

---

## 11. Success Metrics

### 11.1 Technical Metrics

| Metric | Target | How We Measure |
|--------|--------|----------------|
| Detection IoU (MARIDA val) | ≥ 0.45 | Held-out split during training |
| Precision @ conf > 0.7 | ≥ 0.75 | Reduces false positives on Sargassum |
| Sub-pixel fraction MAE | ≤ 0.15 | Against synthetic mixed labels |
| Inference latency (1024×1024) | ≤ 5 sec | Single-tile dashboard response |
| Trajectory endpoint error (72h) | < 25 km | Compare against known NOAA drifter buoy tracks (1 validation case) |

### 11.2 Product/UX Metrics

| Metric | Target |
|--------|--------|
| Time: landing → mission export | < 90 seconds |
| Dashboard FCP | < 2s |
| Time-slider animation FPS | ≥ 30 fps |

### 11.3 Judging Metrics (what we optimize for)

- **Technical depth:** sub-pixel + biofouling + physics all addressed in code.
- **Completeness of pipeline:** satellite → mission export end-to-end, demoable live.
- **Visual polish:** map, animation, export artifacts.
- **Defensibility in Q&A:** every design choice justified with evidence/paper.
- **Alignment with Sankalp Bharat theme:** Indian waters focus, INCOIS-friendly output.

---

## 12. Scope Control — What We WILL NOT Build

Codified to resist mid-hackathon temptation:

1. ❌ Live Sentinel-2 ingestion (STAC API, Sentinel Hub auth).
2. ❌ Historical reanalysis beyond the 4 demo tiles.
3. ❌ Full transformer-from-scratch training.
4. ❌ Multi-satellite fusion (S1 SAR, S3 OLCI, PlanetScope).
5. ❌ Real-time websocket updates.
6. ❌ User accounts, RBAC, OAuth.
7. ❌ Mobile app.
8. ❌ Automated UAV/USV dispatch integration.
9. ❌ 3D globe visualization (Cesium) — Mapbox 2D is enough and faster.
10. ❌ On-device inference / model optimization (ONNX, TensorRT).
11. ❌ Full Stokes-drift / wave-radiation physics beyond windage.
12. ❌ Cloud deployment (AWS/GCP). Demo on laptop. One less thing to break.
13. ❌ Custom dataset labeling UI. Use MARIDA as-is.
14. ❌ Multi-language support.
15. ❌ Dark-mode / theme toggle / user settings.

**Guardrail rule:** if a teammate proposes a feature not in §6, they must first delete something from §6 to make room. Zero-sum scope.

---

## 13. 48-Hour Execution Timeline

### H0–H4 (Hours 0–4): Foundation
- [ ] Team split: 1 ML, 1 backend/physics, 1 frontend, 1 demo/deck (rotate if fewer people)
- [ ] Download MARIDA + 4 Sentinel-2 L2A demo tiles
- [ ] Download CMEMS + ERA5 NetCDFs for demo window
- [ ] Scaffold FastAPI skeleton + React/Vite frontend + shared GeoJSON contract
- [ ] Git repo, shared drive for large data

### H4–H16: Core ML + Physics
- [ ] Preprocess MARIDA → feature stack dataloader
- [ ] Train U-Net (iterate 2–3 times); log IoU, pick best
- [ ] Implement FDI/NDVI/PI computation module (reusable)
- [ ] Implement Lagrangian particle tracker; unit test on synthetic field

### H16–H28: Integration
- [ ] Inference pipeline: tile in → GeoJSON out
- [ ] Biofouling decay heuristic + sub-pixel fraction head
- [ ] Trajectory API endpoint
- [ ] Mapbox base + detection layer in frontend
- [ ] Time-slider skeleton

### H28–H40: Polish + Demo Features
- [ ] Particle animation (deck.gl)
- [ ] Mission planner (greedy TSP) + GPX/PDF export
- [ ] Confidence-decay chart
- [ ] Populate dashboard for all 4 AOIs (pre-bake responses)
- [ ] Fallback screen-recording

### H40–H48: Rehearsal + Buffer
- [ ] End-to-end dry run x3 (catch bugs, time the pitch)
- [ ] Final README with architecture diagram
- [ ] Submission package: repo link, demo video, slides

**Hard rule:** At H36, feature-freeze. Only polish/bugs after that.

---

## 14. Critical Files & Reused Utilities (for execution phase)

These are the **only** heavy files needed. Everything else is thin glue.

| Path | Purpose |
|------|---------|
| `backend/ml/model.py` | U-Net w/ SE attention, multi-head outputs |
| `backend/ml/features.py` | FDI, NDVI, PI computation (reusable; single source of truth) |
| `backend/ml/dataset.py` | MARIDA loader with biofouling augmentation |
| `backend/ml/train.py` | Training loop, ~150 LOC |
| `backend/ml/inference.py` | Tile → GeoJSON pipeline |
| `backend/physics/tracker.py` | Lagrangian Euler integrator |
| `backend/physics/env_data.py` | CMEMS/ERA5 NetCDF interp |
| `backend/api/main.py` | FastAPI `/detect` `/forecast` `/mission` |
| `backend/mission/planner.py` | Greedy TSP over hotspots |
| `frontend/src/components/Map.tsx` | Mapbox + deck.gl layers |
| `frontend/src/components/TimeSlider.tsx` | 72h scrubbing |
| `frontend/src/components/MissionModal.tsx` | Planner UI + export buttons |
| `frontend/src/api.ts` | Typed client for backend |
| `data/aois/*.json` | 4 demo AOI bounding boxes |
| `data/staged/*.tif` | Pre-downloaded S2 tiles |
| `data/env/*.nc` | Pre-downloaded CMEMS + ERA5 slices |

---

## 15. Verification Plan

How we prove it works end-to-end before demo:

1. **Unit-level**
   - `features.py`: known pixel → known FDI value (assert against Biermann paper example).
   - `tracker.py`: synthetic eastward 0.5 m/s current field → particle displaces 43.2 km in 24h (±1%).

2. **Model-level**
   - Held-out MARIDA split: IoU ≥ 0.45, precision ≥ 0.75 at conf>0.7.
   - Confusion matrix shows Sargassum FPR < 15%.

3. **Pipeline-level**
   - `curl /detect?aoi=gulf_of_mannar` → GeoJSON with ≥1 feature, schema-valid.
   - `curl /forecast?...` → 72 hourly frames, particles bounded within basin.
   - `curl /mission?...` → GPX with ≥3 waypoints in TSP order.

4. **Frontend-level**
   - All 4 AOIs load < 3s.
   - Time slider scrubs smoothly at 30fps.
   - Mission export downloads a valid GPX that opens in Google Earth.

5. **Dress rehearsal**
   - Full 5-min demo executed 3 times without touching code between.
   - Record the final successful run as fallback.

---

## 16. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| MARIDA download slow / corrupted | Med | High | Mirror on Drive; fetch at H0 |
| U-Net IoU < 0.3 after training | Med | High | Fall back to pretrained Segformer-B0; keep RF baseline ready |
| Env NetCDFs too large | Med | Med | Clip to AOI spatial extent at download time |
| deck.gl performance lags | Low | Med | Downsample to 500 particles; pre-render frames as PNG tiles |
| Demo laptop crashes mid-pitch | Low | Critical | Fallback recorded video + static tile cache |
| Overambitious scope creep | **HIGH** | **Critical** | §12 scope-control list enforced by PM role |

---

## 17. Open Questions for User (Before Execution)

These are ambiguity checks I should confirm before any code is written:

1. **Team size & skills** — how many developers, and what's the strongest stack (PyTorch comfort? React comfort?)?
2. **Submission format** — is this a code repo + deck, or live demo + deck? Judging rubric link?
3. **Hardware available** — any GPU for training (a 30/40-series or T4)? If CPU-only, we must pre-train and ship weights only.
4. **Team preference for AOI focus** — stick with Indian EEZ (aligns with Sankalp Bharat) or include an international Sargassum hotspot for dataset availability?
5. **Willingness to use Mapbox** — requires free-tier token. OK, or prefer OSM/Leaflet?

---

## Appendix A — Key Datasets & Papers (Defensibility Bank)

- **MARIDA** — Kikaki et al. 2022, Marine Debris Archive (Sentinel-2 labeled)
- **FloatingObjects** — Mifdal et al. 2021
- **FDI definition** — Biermann et al. 2020 "Finding Plastic Patches in Coastal Waters using Optical Satellite Data"
- **Plastic Index (PI)** — Themistocleous et al. 2020
- **CMEMS Global Ocean Physics Analysis and Forecast** — 1/12° surface currents
- **ERA5** — ECMWF reanalysis 10m winds, 0.25°
- **OpenDrift** — Lagrangian framework, reference for our simplified integrator
- **Biofouling rates** — Amaral-Zettler et al., Fazey & Ryan 2016 (plastic age vs. biofilm)

---

## Appendix B — Example API Contract

```
GET /aois                              → list of 4 demo AOIs
GET /detect?aoi=<id>&date=<YYYY-MM-DD> → FeatureCollection of detections
GET /forecast?aoi=<id>&horizon=72      → {frames: [{t, features}]}
POST /mission
     body: {aoi, vessel_range_km, hours, origin: [lon,lat]}
     → {waypoints:[...], gpx_url, pdf_url, summary}
```

Detection feature schema:
```json
{
  "type": "Feature",
  "geometry": {"type": "Polygon", "coordinates": [...]},
  "properties": {
    "conf_raw": 0.82,
    "conf_adj": 0.61,
    "fraction_plastic": 0.18,
    "area_m2": 1240,
    "age_days_est": 22,
    "class": "plastic"
  }
}
```

---

**Bottom line:** This PRD ships a defensible, visually striking, end-to-end pipeline. We handle sub-pixel detection with a dual-head model, acknowledge biofouling with both augmentation and a runtime heuristic, integrate physics for 72-hour drift forecasts, and close the loop with a one-click mission planner. We strictly avoid feature creep. We optimize the last 8 hours for polish and rehearsal. We win on clarity, completeness, and credibility.
