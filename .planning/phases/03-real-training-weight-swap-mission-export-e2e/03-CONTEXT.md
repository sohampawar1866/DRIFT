# Phase 3: Real Training + Weight Swap + Mission Export + E2E — Context

**Gathered:** 2026-04-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 closes the intelligence milestone by delivering four converging deliverables against the frozen Phase 1 schema and the green Phase 2 tracker/planner:

1. **Trained-weight integration (NOT training execution).** The user supplies (a) the `backend/ml/train.py`-style training code and (b) the trained checkpoint as a pickle/state-dict artifact. Phase 3 work is **code review + wiring**, not running Kaggle epochs. We verify the training script is schema-aligned (14-band feature stack, Dice + pos-weighted BCE + MSE-on-positives, biofouling aug on plastic-masked pixels only, `_conf.tif` handled as `valid_mask = conf > 0`), commit it, and load the supplied checkpoint into `DualHeadUNetpp` via the existing `backend/ml/weights.py` `our_real` branch.
2. **Weight-swap wiring.** Flip `ml.weights_source: our_real` in `backend/config.yaml` (or `ML__WEIGHTS_SOURCE=our_real` env override) and have `load_weights()` read the user-supplied checkpoint file from a pinned local path. `physics/` and `mission/` code is byte-identical before/after the swap.
3. **Mission export (`backend/mission/export.py`)** producing three artifacts from a `MissionPlan`: GPX (Google-Earth-openable), GeoJSON (RFC-7946, `model_dump_json` < 500 KB), and a one-page PDF briefing (< 1 MB, < 3 s, matplotlib + reportlab, no headless Chrome).
4. **E2E < 15 s + 4-AOI fallbacks.** `backend/e2e_test.py` passes with `our_real` weights on a real MARIDA patch against real CMEMS+ERA5 slices; per-stage `time.perf_counter()` breakdown logged. Pre-baked fallback JSONs at `data/prebaked/{aoi}_{detections,forecast,mission}.json` by H+28. 60 s screen recording at `.planning/demo/successful_run.mp4` by H+36.

**Out of Phase 3 (not in this milestone):** FastAPI wiring, React frontend, live Kaggle training execution (user handles), marccoru baseline branch (optional bonus only if user also supplies those weights).

</domain>

<decisions>
## Implementation Decisions

### Training Code + Weights Handoff (CORRECTED SCOPE)

- **D-01:** **User supplies code + checkpoint.** The user delivers the training script and a pickle/state-dict file for the trained `DualHeadUNetpp`. Phase 3 does NOT execute a Kaggle run. This replaces the ROADMAP's "ship `backend/ml/train.py` to Kaggle + run 25 epochs + `kagglehub.model_upload`" posture — ML-05 through ML-09 collapse into **code-review + integration-smoke** rather than training execution.
- **D-02:** **Checkpoint delivery path** is `backend/ml/checkpoints/our_real.pt` (or `.pth` / `.pkl` — extension follows whatever the user provides). `backend/ml/weights.py::load_weights("our_real")` reads this local path first; `kagglehub.model_download(...)` stays as an optional secondary code path but is NOT the default for the demo. Rationale: the user's own handoff is faster and kagglehub is an unnecessary network dependency at demo time.
- **D-03:** **Training code review checklist** (Claude's verification task on the supplied script, before wiring the checkpoint in):
  1. Uses the same `DualHeadUNetpp` class signature as `backend/ml/model.py` (in_channels=14, mask_head + fraction_head outputs, SCSE decoder attention).
  2. Uses `backend/ml/features.py::feature_stack()` (single source of truth — verified by grep in Phase 1, must not be reimplemented in the training script).
  3. MARIDA `_conf.tif` handled as `valid_mask = (conf > 0)` with loss weighted by `conf/3.0 * valid_mask` (PITFALL C2).
  4. Loss = Dice + pos-weighted BCE (`pos_weight ~ 40`) on mask head, MSE on positive pixels only for fraction head (PITFALL C3, M8).
  5. Biofouling augmentation: `NIR × [0.5, 1.0]` **on plastic-masked pixels only** (PITFALL M7). Sanity check: augment a zero-mask sample → bands unchanged.
  6. fp16 autocast + GradScaler; no `torch.compile`, no `bfloat16` (PITFALL C6 addendum — P100/T4 compatibility).
  7. Train/val split respects MARIDA-provided split files; synthetic mixed-pixel val uses ONLY train scenes as source (PITFALL M11).
  8. State-dict keys match `model.state_dict()` exactly when loaded via `load_state_dict(..., strict=True)` — any mismatch flagged during the integration smoke test.
- **D-04:** **Metrics file** `.planning/metrics/phase3.json` is populated from the integration-smoke output (user's reported numbers + a sanity re-eval on one held-out MARIDA val scene). Targets from PRD §11.1: IoU ≥ 0.45, precision@0.7 ≥ 0.75, sub-pixel MAE ≤ 0.15, Sargassum FP ≤ 15%. **If the user-supplied checkpoint misses a target, we DO NOT retrain — we flag it in `phase3.json` with `{metric: ..., target: ..., actual: ..., status: "miss"}` and continue. The demo story tolerates partial metric wins as long as the chain runs end-to-end.**
- **D-05:** **Weight-swap verification.** After wiring: `run_inference` on the same MARIDA patch with `dummy` vs `our_real` must produce the SAME pydantic schema but different values. `git diff` on `backend/physics/` and `backend/mission/` between pre-swap and post-swap HEAD must be **empty** (proves the swap doesn't leak into downstream).

### Mission Export — `backend/mission/export.py`

- **D-06:** **Three-function public API.** `export_gpx(mission: MissionPlan, path: Path) -> Path`, `export_geojson(mission: MissionPlan, path: Path) -> Path`, `export_pdf(mission: MissionPlan, forecast: ForecastEnvelope | None, path: Path) -> Path`. All three are pure functions with no hidden state. PDF takes optional forecast because wind/current condition panels need it; GPX and GeoJSON don't.
- **D-07:** **GPX schema:** GPX 1.1 with a single `<trk>` for the vessel route (LineString points in order) and `<wpt>` entries for each waypoint. Waypoint `<name>` = `f"WP{order:02d}"`; `<desc>` = f-string with priority, ETA hours, and detection area_m2. No third-party library needed — hand-rolled XML via `xml.etree.ElementTree` keeps dependency surface clean (PRD §8.6 "no headless Chrome" spirit).
- **D-08:** **GeoJSON export** = `mission.model_dump_json(indent=2)` written to file. No transformation needed — the `MissionPlan` is already RFC-7946-compliant by construction. Enforcement: test asserts file size < 500 KB on a realistic 15-waypoint mission.
- **D-09:** **PDF briefing layout (one page, portrait A4):**
  - Top strip: title "DRIFT Cleanup Mission Briefing — `{aoi_id}`", timestamp, mission ID.
  - Left 60%: map panel rendered via matplotlib with (a) Indian EEZ / GSHHG coastline from an **offline shapefile** (ship a trimmed Natural Earth 10m coastline subset under `data/basemap/`), (b) vessel route LineString in red, (c) waypoints as numbered pins, (d) forecast `+72h` density contour from `ForecastEnvelope.frames[-1].density_polygons` as a translucent overlay if forecast is supplied.
  - Right 40% top: waypoint table — columns `order | lon | lat | ETA (h) | priority | conf_adj | area_m²`. reportlab `Table` with 8-point font, zebra rows.
  - Right 40% middle: wind/current summary — for the +72h frame, mean u/v magnitude and direction at each waypoint (compact 5-row table).
  - Right 40% bottom: fuel/time estimate panel — `total_distance_km`, `total_hours`, estimated fuel litres (simple linear model: `total_distance_km × fuel_l_per_km`, with `fuel_l_per_km = 2.5` hardcoded as a defensible demo value).
  - Footer: attribution strip ("DRIFT / PlastiTrack — Sankalp Bharat SKB_P5").
  - **Claude's discretion:** exact fonts, colour palette (suggest INCOIS-adjacent navy/cyan), margin tuning — iterate during build until it looks clean.
- **D-10:** **PDF implementation stack:** matplotlib renders the map panel to an in-memory PNG (via `BytesIO`); reportlab `SimpleDocTemplate` + `Image`, `Table`, `Paragraph` flowables compose the page. No headless Chrome, no weasyprint, no LaTeX. Target: < 3 s end-to-end on CPU laptop.
- **D-11:** **Basemap strategy:** ship a trimmed coastline shapefile (Natural Earth 10m `ne_10m_coastline` clipped to Indian EEZ bbox `[67, 95, 5, 25]`) under `data/basemap/`. Read with `geopandas.read_file`. No internet tile dependency at demo time. File size target < 2 MB.

### Fallback + E2E

- **D-12:** **Automatic fallback on any E2E exception.** `scripts/run_full_chain_real.py` (Phase 3 counterpart to Phase 2's dummy driver) catches exceptions at each stage boundary; on any failure after stage N, it loads `data/prebaked/{aoi}_{stage}.json` and resumes. **Fallback is silent by default** (demo-safe); a `--no-fallback` flag disables it for debugging. Each load logs `[FALLBACK] stage={stage} reason={exc_class}: {msg}` so nothing fails unobserved.
- **D-13:** **Freshness stamp** on pre-baked JSONs: a sibling `data/prebaked/MANIFEST.json` records `{aoi, stage, generated_at, git_sha, weights_source}` for each artifact. Loaded during fallback so the PDF can include a footer note when it's running from pre-bake.
- **D-14:** **Parity test definition:** byte-identical hash comparison runs on **CPU-only with a fixed seed** (`torch.manual_seed(1410)`, `numpy.random.seed(1410)`, `random.seed(1410)`, `PYTHONHASHSEED=0`). Hash is SHA-256 over the stage-N `model_dump_json(sort_keys=True)` string (after a `normalize_floats(round=6)` pass to tolerate fp rounding). Live `our_real` CPU run on a demo tile must match the pre-baked hash for that tile at each stage. GPU output is NOT required to match — parity is CPU-only.
- **D-15:** **E2E < 15 s budget allocation** (baseline assumption on CPU laptop): inference ≤ 6 s, forecast ≤ 5 s, planner ≤ 1 s, export ≤ 3 s. **Degradation knobs** (apply in order if over budget): (1) increase sliding-window stride from 128 → 192 (accepts some boundary artifact), (2) drop particles per detection from 20 → 10, (3) coarsen KDE grid from 256² → 128², (4) skip local-KDE at +24/+48 (keep only global +72 KDE for priority scoring). **Never** drop the +72 frame — that's the priority-scoring source.
- **D-16:** **Pre-baked generation script** `scripts/prebake_demo.py` runs once at H+28 against all 4 AOIs with `our_real` weights, CPU-only, fixed seed, and writes `data/prebaked/{aoi}_{detections,forecast,mission}.json` + the MANIFEST. This script is also the source of truth for the parity-test hashes.

### Demo + Freeze Discipline

- **D-17:** **Runtime freeze at H+32.** No `pip install`, no code edits beyond visual polish (PDF margins, waypoint table formatting) after H+32. Locked deps snapshot via `pip freeze > requirements.lock` at H+32.
- **D-18:** **Screen recording at H+36.** 60 s capture of a successful `our_real` E2E run against Gulf of Mannar (primary demo AOI), saved to `.planning/demo/successful_run.mp4`. Fallback-playback rehearsal also recorded as a secondary safety net.

### Claude's Discretion

- Exact PDF fonts, colour palette, and margin tuning (D-09) — iterate on visual polish during build.
- `normalize_floats` precision for parity hashing (D-14) — tune to tolerate reasonable fp drift without masking real regressions; 6 decimals is a starting point.
- Whether `export_pdf` exposes a `style: Literal["brief", "full"]` parameter for future extensibility — lean toward NOT adding it now (scope creep), but reconsider if time allows.
- Natural Earth coastline simplification tolerance for the shipped basemap (D-11) — trade file size vs visual fidelity during build.

### Folded Todos

None — no pending todos matched Phase 3 at context gathering time (`gsd-tools todo match-phase 3` returned empty).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product + Scope
- `PRD.md` §5 (dashboard/export overview, GeoJSON + GPX waypoints), §8.6 (tech stack lock — matplotlib/reportlab, no headless Chrome), §11.1 (technical metrics — IoU ≥ 0.45, P@0.7 ≥ 0.75, sub-pixel MAE ≤ 0.15, Sargassum FP ≤ 15%, full-chain latency), §12 (zero-sum scope rule), §13 (H-timeline, H+32 runtime freeze, H+36 feature freeze), §16 (risk mitigation).
- `.planning/PROJECT.md` — Core Value, Constraints, scope boundary (intelligence-only).
- `.planning/REQUIREMENTS.md` — INFRA-05, ML-02, ML-05..09, MISSION-03, E2E-01, E2E-02, Out-of-Scope table.
- `.planning/ROADMAP.md` Phase 3 section — success criteria (5 items), risk flags (PITFALLs C6, C6-addendum, C2, C3, M7, M8, M11, M12, C7 + SMP 14-channel init + hub band ordering).

### Research
- `.planning/research/STACK.md` — PyTorch + smp, matplotlib, reportlab, geopandas, Kaggle gotchas (P100 vs T4 fp16 only, no bf16, no torch.compile).
- `.planning/research/PITFALLS.md` — C2 (_conf.tif), C3 (class imbalance / Dice + pos-BCE), C6 (Kaggle GPU flag + non-deterministic P100/T4), C7 (demo laptop crash), M7 (biofouling aug direction), M8 (sub-pixel MSE collapse), M11 (synthetic val contamination), M12 (checkpoint transfer).
- `.planning/research/ARCHITECTURE.md` — module boundary conventions.
- `.planning/phases/01-schema-foundation-dummy-inference/01-RESEARCH.md` — SMP `in_channels=14` first-conv init flag; reused here when we instantiate the model to load `our_real` weights.
- `.planning/phases/02-trajectory-mission-planner/02-CONTEXT.md` — D-11 (2-opt), D-13 (`avg_speed_kmh=20`), D-18 (windage α=0.02) — export's ETA + wind/current panels reuse these.

### Existing Code (contracts not to break)
- `backend/core/schemas.py` — **FROZEN.** `DetectionProperties`, `DetectionFeatureCollection`, `ForecastEnvelope`, `ForecastFrame`, `MissionPlan`, `MissionWaypoint` all with `extra="forbid", frozen=True`. Phase 3 must NOT edit field shapes.
- `backend/ml/model.py::DualHeadUNetpp` — class signature the user's checkpoint must match (in_channels=14, dual head, SCSE).
- `backend/ml/weights.py::load_weights` — existing branch dispatcher; Phase 3 wires the `our_real` branch to read from `backend/ml/checkpoints/our_real.pt`.
- `backend/ml/features.py::feature_stack` — single source of truth for 14-band stack; training script must import this (D-03.2).
- `backend/ml/inference.py::run_inference` — Phase 1 shipped; weight-swap is transparent to it.
- `backend/physics/tracker.py::forecast_drift` — Phase 2 shipped; export's PDF wind/current panel reads its `ForecastEnvelope` output.
- `backend/mission/planner.py::plan_mission` — Phase 2 shipped; export's entire input.
- `backend/config.yaml` + `backend/core/config.py` — `ml.weights_source` flips between `dummy` and `our_real`; existing env-var override (`ML__WEIGHTS_SOURCE=our_real`) for free.
- `backend/api/routes.py` — **untouched** per milestone scope boundary.

### Codebase Maps
- `.planning/codebase/STACK.md`, `CONVENTIONS.md`, `STRUCTURE.md`, `TESTING.md`, `CONCERNS.md` — snake_case, pydantic `frozen=True`, pytest integration layout.

### External (consult via context7 during research/planning)
- `reportlab` — `SimpleDocTemplate`, `Image`, `Table`, `Paragraph`, `PageBreak` flowables.
- `matplotlib` — `Figure.savefig(buf, format="png", dpi=200)`, `cartopy`-free approach via geopandas overlay.
- `geopandas` — `read_file` for Natural Earth shapefile.
- `xml.etree.ElementTree` — stdlib GPX 1.1 writer.
- `hashlib` + `json(sort_keys=True)` — parity hash definition.

### Data Assets (must be on disk)
- `backend/ml/checkpoints/our_real.pt` (or .pth/.pkl) — **user-supplied**, committed via gitignore-exempt path OR kept local-only (state.md to reflect handoff).
- `data/env/cmems_currents_72h.nc`, `data/env/era5_winds_72h.nc` — Phase 2 deliverable (`scripts/fetch_demo_env.py`).
- `data/basemap/ne_10m_coastline_indian_eez.{shp,shx,dbf,prj}` — Phase 3 adds this (D-11).
- `data/prebaked/{gulf_of_mannar,mumbai_offshore,bay_of_bengal_mouth,arabian_sea_gyre_edge}_{detections,forecast,mission}.json` + `MANIFEST.json` — Phase 3 generates via `scripts/prebake_demo.py` at H+28.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`backend/ml/weights.py`** already has a `dummy` branch; `our_real` branch is the natural extension — the dispatcher pattern is in place, we only add a file-load path.
- **`backend/ml/model.py::DualHeadUNetpp`** is the target of `load_state_dict` — no class changes needed if the user's training script used the same definition.
- **`backend/mission/planner.py`'s `MissionPlan` output** is export's sole input — all data for GPX/GeoJSON/PDF is already in the schema (waypoints, route, totals). Export is a pure renderer, no re-computation.
- **`backend/physics/tracker.py::forecast_drift`** output has the `+72h` density polygons needed for the PDF map overlay (D-09).
- **`backend/config.yaml`** already exposes `ml.weights_source` — swap is a one-line edit, no config-schema changes.
- **Phase 2 `scripts/run_full_chain_dummy.py`** is the template for Phase 3's `scripts/run_full_chain_real.py` (same structure, swapped weights + added fallback + added export call).
- **Pytest integration layout** under `backend/tests/` and per-module test files — Phase 3 mirrors this for `test_export.py`, `test_weight_swap.py`, `test_e2e_real.py`.

### Established Patterns
- **Pydantic `frozen=True, extra="forbid"`** — export must only CONSUME schemas, never extend them.
- **Env-var override delimiter `__`** — `ML__WEIGHTS_SOURCE=our_real` works for free.
- **CLI style `python -m backend.{module} ...`** — export gets a `python -m backend.mission.export --mission path.json --format {gpx,geojson,pdf} --out path` CLI for judge-facing demo-ability.
- **No `torch.compile`, no Hydra, no Lightning, no headless Chrome** — all confirmed in Phase 2 and applied here.

### Integration Points
- `scripts/run_full_chain_real.py` chains `run_inference (our_real) → forecast_drift → plan_mission → export_all_three`, with fallback hooks at each stage boundary.
- `backend/e2e_test.py` is the pytest harness that the CI-equivalent runs (`pytest backend/e2e_test.py -v`); asserts per-stage schema validity + total wall-clock < 15 s.
- `scripts/prebake_demo.py` is called manually once at H+28; it writes the fallback artifacts + MANIFEST + the parity-hash table used by `test_prebake_parity.py`.

### Creative Options Enabled
- Because the user supplies the training code AND checkpoint, Phase 3 is a **verification + wiring phase**, not a compute phase. This frees ~12 hours of Kaggle training clock that the original ROADMAP budgeted — reallocate to PDF polish, fallback robustness, and a second screen-recording take.
- Export is a pure consumer of frozen schemas → can be built against synthetic `MissionPlan` fixtures BEFORE the real checkpoint arrives (parallel-track like Phase 2).

</code_context>

<specifics>
## Specific Ideas

- **"Demo must not crash mid-pitch"** — automatic silent fallback (D-12) is non-negotiable. Judges never see a stack trace.
- **"Code-review, not retrain"** — user will hand us the training script + trained checkpoint. We verify the script follows the pitfall-safe pattern (D-03) and wire the checkpoint into the existing `load_weights("our_real")` branch. If metrics miss, we log and continue (D-04); we do NOT re-train.
- **Gulf of Mannar is the primary demo AOI** — first on the AOI list, anchor for the 60 s screen recording. Other three AOIs are safety-net fallbacks during Q&A.
- **Offline-first demo posture** — no internet dependency at pitch time: pre-baked JSONs, bundled coastline shapefile, user-supplied checkpoint at a pinned local path, no kagglehub download in the demo code path.
- **"kagglehub model upload" is NOT on the critical path anymore** — user's handoff replaces it. Keep the code path as a commented secondary loader or remove it entirely per zero-sum scope rule (planner's call).

</specifics>

<deferred>
## Deferred Ideas

- **Actually running Kaggle training** — user handles this outside the GSD workflow; Phase 3 consumes the artifact.
- **`marccoru_baseline` weight branch** — optional bonus only; not on critical path. Activate only if the user also supplies a manual Google Drive download of those weights.
- **`export_pdf(style="full")` variant** — multi-page briefing with per-waypoint detail pages — post-milestone.
- **Interactive PDF (clickable waypoints, embedded geopackage)** — out of matplotlib+reportlab capability; post-milestone if a frontend layer is added.
- **FastAPI integration of the export endpoint** — next milestone; the existing mock at `backend/api/routes.py` stays untouched.
- **Live Mapbox/Leaflet tile base for PDF** — rejected per offline-first stance (D-11).
- **`kagglehub.model_download` as the primary weight loader** — deprioritized; user-supplied local checkpoint is faster and offline-safe. Kept as optional secondary code path OR removed entirely at planner's discretion.
- **GPU parity** in the byte-identical hash test — CPU-only parity is sufficient; GPU output variance is tolerated (D-14).
- **`--fallback` explicit CLI flag** — rejected in favour of automatic fallback with `--no-fallback` escape hatch (D-12). Demo-safe default matters more than explicit control.

### Reviewed Todos (not folded)

None — `gsd-tools todo match-phase 3` returned empty. No pending todos at context-gathering time.

</deferred>

---

*Phase: 03-real-training-weight-swap-mission-export-e2e*
*Context gathered: 2026-04-17*
</content>
</invoke>