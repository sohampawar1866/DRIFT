# Phase 3: Real Training + Weight Swap + Mission Export + E2E — Research

**Researched:** 2026-04-17
**Domain:** Checkpoint integration (not training execution) + mission artifact export + E2E latency + offline fallback architecture
**Confidence:** HIGH for checkpoint loading, PDF stack, GPX schema, Natural Earth redistribution; MEDIUM for end-to-end CPU latency numbers (hardware-dependent); MEDIUM for training-code static-verification patterns (user's exact script shape not yet seen).

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Training Code + Weights Handoff (CORRECTED SCOPE)**
- **D-01:** User supplies training code + checkpoint pickle/state-dict. Phase 3 does NOT execute Kaggle training. ML-05..ML-09 collapse to code-review + integration-smoke.
- **D-02:** Checkpoint delivery path = `backend/ml/checkpoints/our_real.pt` (or `.pth`/`.pkl`). `load_weights("our_real")` reads local path first; `kagglehub.model_download` is an optional secondary code path (demoted, not default).
- **D-03:** 8-point training-code review checklist (DualHeadUNetpp match, feature_stack reuse, `_conf.tif` as `conf>0` mask, Dice + pos-BCE + MSE-on-positives, biofouling aug on plastic pixels only, fp16 autocast + GradScaler, split-aware synthetic mixing, `strict=True` state-dict match).
- **D-04:** `.planning/metrics/phase3.json` logs reported + sanity-re-eval numbers. If targets miss, log and continue — do NOT retrain.
- **D-05:** Post-swap `git diff` on `backend/physics/` and `backend/mission/` must be empty. `dummy` vs `our_real` on the same patch → same schema, different values.

**Mission Export**
- **D-06:** Three pure functions: `export_gpx(mission, path)`, `export_geojson(mission, path)`, `export_pdf(mission, forecast|None, path)`.
- **D-07:** GPX 1.1, hand-rolled via `xml.etree.ElementTree` (no third-party dep). Single `<trk>` for route, `<wpt>` per waypoint. `<name>=f"WP{order:02d}"`, `<desc>` with priority/ETA/area_m2.
- **D-08:** GeoJSON export = `mission.model_dump_json(indent=2)`. < 500 KB assertion.
- **D-09:** PDF layout — one-page portrait A4, title strip, left 60% map (matplotlib + offline Natural Earth coastline + route + waypoints + +72h density overlay), right 40% with waypoint table / wind-current summary / fuel panel / footer. `fuel_l_per_km=2.5`.
- **D-10:** Stack = matplotlib → PNG via `BytesIO` → reportlab `SimpleDocTemplate` + `Image`/`Table`/`Paragraph`. No headless Chrome, no weasyprint.
- **D-11:** Offline basemap = Natural Earth `ne_10m_coastline` clipped to `[67, 95, 5, 25]` under `data/basemap/`. < 2 MB target.

**Fallback + E2E**
- **D-12:** Silent automatic fallback on any E2E exception at stage boundaries. `--no-fallback` escape hatch. Log `[FALLBACK] stage=... reason=...`.
- **D-13:** `data/prebaked/MANIFEST.json` tracks `{aoi, stage, generated_at, git_sha, weights_source}`.
- **D-14:** Parity test = SHA-256 over `model_dump_json(sort_keys=True)` after `normalize_floats(round=6)`. CPU-only + fixed seeds (`torch 1410`, `numpy 1410`, `random 1410`, `PYTHONHASHSEED=0`). GPU parity NOT required.
- **D-15:** E2E budget: inference ≤ 6 s, forecast ≤ 5 s, planner ≤ 1 s, export ≤ 3 s. Degradation knobs: stride 128→192 → particles 20→10 → KDE 256²→128² → drop local-KDE at +24/+48 (NEVER drop +72).
- **D-16:** `scripts/prebake_demo.py` runs once at H+28 with `our_real` + CPU + fixed seed, writes all fallbacks + MANIFEST + parity hashes.

**Demo + Freeze**
- **D-17:** Runtime freeze H+32. `pip freeze > requirements.lock` snapshot.
- **D-18:** 60 s screen recording at H+36 to `.planning/demo/successful_run.mp4`. Fallback-playback rehearsal recorded as secondary.

### Claude's Discretion
- Exact PDF fonts, colour palette (suggest INCOIS-adjacent navy/cyan), margin tuning.
- `normalize_floats` precision for parity hashing (start at 6 decimals).
- Whether to expose `export_pdf(style=...)` (lean NO — scope creep).
- Natural Earth simplification tolerance (file size vs. visual fidelity).

### Deferred Ideas (OUT OF SCOPE)
- **Actually running Kaggle training** — user handles outside GSD.
- **`marccoru_baseline`** branch — bonus only.
- **`export_pdf(style="full")`** multi-page variant — post-milestone.
- **Interactive PDF** (clickable waypoints) — post-milestone.
- **FastAPI integration** of export — next milestone.
- **Live Mapbox/Leaflet tile base** — rejected.
- **`kagglehub.model_download` as primary loader** — demoted to optional secondary or delete at planner's discretion.
- **GPU parity** in hash test — CPU-only is sufficient.
- **`--fallback` explicit CLI flag** — replaced by auto-on + `--no-fallback` escape.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **INFRA-05** | Checkpoint transfer; offline-safe once local | §1 Safe Checkpoint Loading, §D-02; `backend/ml/checkpoints/` ignore rule carries forward |
| **ML-02** | `dataset.py` — MARIDA loader with `_conf.tif` masking + BOA_ADD_OFFSET + B6/B11 resample | §2 Training-Script Review Checklist (code-review mechanical), §9 One-Epoch Dry-Run Smoke |
| **ML-05** | 25-epoch training loop, Dice+pos-BCE+MSE, no `torch.compile`, `kagglehub.model_upload` | **REDUCED TO CODE-REVIEW** per D-01; §2 provides grep/AST patterns |
| **ML-06** | Sub-pixel fraction regression, MAE ≤ 0.15 | §10 Metric Re-eval on laptop — confirms number, not retrains |
| **ML-07** | Biofouling instrumentation | §2 D-03.5 static-inspection pattern — mask-gated NIR scaling |
| **ML-08** | IoU ≥ 0.45, P@0.7 ≥ 0.75, Sargassum FP ≤ 15% | §10 Metric re-eval. D-04 says log-and-continue on miss |
| **ML-09** | Optional 15-class aux head | Deferred if training code doesn't include it; not critical |
| **MISSION-03** | GPX + GeoJSON + PDF export | §3 PDF stack, §4 GPX schema, §5 Coastline |
| **E2E-01** | `e2e_test.py` — full chain < 15 s + schema valid at every boundary | §7 Latency budget, §6 Determinism |
| **E2E-02** | Pre-baked 4-AOI fallbacks + parity test | §8 Fallback architecture, §6 Determinism |

</phase_requirements>

## Summary

Phase 3 is a **verification + wiring + packaging** phase. Training execution moved off the critical path (user handles externally); we receive artifacts and must: (a) mechanically review the training script for 8 known-pitfall classes; (b) safely load an untrusted local pickle into `DualHeadUNetpp` with informative error reporting; (c) ship three deterministic export artifacts; (d) guarantee a demo-safe silent fallback path; (e) prove CPU-only byte-parity for the pre-baked demo set.

**Primary recommendation:** Build export + fallback + prebake scaffolding against synthetic `MissionPlan` fixtures starting H+16 *in parallel with* waiting for the user's checkpoint. The weight-swap wiring itself is ~30 LOC once a checkpoint lands; the rest of Phase 3 is independent of that delivery and should not block on it.

---

## Project Constraints (from CLAUDE.md)

- **Python 3.10 / 3.11 / 3.12 only.** Shapely/geopandas wheels broken on 3.9 and 3.13+.
- **No `torch.compile`, no `bfloat16`, no Hydra, no Lightning, no headless Chrome, no Docker, no live tile services.**
- **GSD Workflow Enforcement:** No direct file edits outside a GSD command.
- **Zero-sum scope rule (PRD §12):** any new feature proposal must be paired with a removal.
- **Runtime freeze H+32, feature freeze H+36.**
- **Pydantic `extra="forbid", frozen=True` everywhere.** Export must only CONSUME schemas.
- **PDF < 1 MB / < 3 s. GeoJSON < 500 KB. E2E < 15 s on CPU laptop.**
- **snake_case modules, 4-space indent, explicit (not wildcard) imports.**
- **Service-layer purity:** endpoint handlers (or CLI handlers) do no business logic — they call service functions. Export follows this — three pure functions, no hidden state.

---

## Standard Stack

### Core (already pinned project-wide, do not touch)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `torch` | ≥ 2.6 (matches user's Kaggle output) | `load_state_dict`, inference | Already pinned. 2.6 is the critical boundary for `torch.load(weights_only=...)` default flip — see §1. |
| `segmentation-models-pytorch` | `>=0.5.0,<0.6.0` | `DualHeadUNetpp` backbone | Already shipped in Phase 1. |
| `matplotlib` | `>=3.9,<3.12` | PDF map rendering to in-memory PNG | Already installed as a Kaggle/training dep — no new dep. |
| `reportlab` | `>=4.2,<5.0` | PDF composition (SimpleDocTemplate + flowables) | Standard PDF stack in scientific Python. No Chrome dependency. |
| `geopandas` | `>=1.0,<1.2` | Reading clipped Natural Earth shapefile; overlay on matplotlib Axes | Already shipped. `gdf.plot(ax=ax)` is the one-liner. |
| `shapely` | `>=2.0,<3.0` | Coastline clipping, waypoint geom | Already shipped. |
| `xml.etree.ElementTree` | stdlib | GPX 1.1 writer | No dep; matches D-07. |
| `hashlib` + `json(sort_keys=True)` | stdlib | Parity hashing per D-14 | No dep. |

### Supporting (Phase 3 may need to install)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `reportlab` | `>=4.2` | **Verify it's installed**; likely missing from current venv | Required for MISSION-03. Run `pip install reportlab` during Wave 0 of Phase 3 and commit via `requirements.txt` bump. |
| `torchmetrics` | `>=1.4` — **OPTIONAL** | `BinaryJaccardIndex`, `BinaryPrecision` | §10. Not strictly required — 20 lines of numpy give same answer. **Recommend: skip**, write manual IoU in `tests/test_metrics_reeval.py` (zero-sum rule favors no new dep). |
| `pypdf` or `pdfplumber` | — | Verifying PDF output in tests | **Skip.** Assert on file size + `PyPDF2`-free test: `assert path.stat().st_size < 1_000_000 and path.read_bytes().startswith(b"%PDF-")`. |

**Installation (new deps only):**
```bash
pip install "reportlab>=4.2,<5.0"
# If Natural Earth shapefile is supplied as a commit (preferred), no additional deps.
```

**Version verification protocol (Wave 0 of Phase 3):** `python -c "import reportlab; print(reportlab.__version__)"` must return ≥ 4.2. `pip install --upgrade` if < 4.2. Windows `cp311` + `cp312` wheels both ship cleanly for reportlab 4.x (pure-Python core + optional Pillow for raster images — already installed).

### Alternatives Considered

| Instead of | Could Use | Tradeoff | Decision |
|------------|-----------|----------|----------|
| `reportlab` | `weasyprint` (HTML→PDF via CSS) | Prettier layout, but pulls cairo/pango native deps (Windows install pain). | **REJECTED** per D-10 and PRD §8.6 "no headless Chrome" spirit. |
| `reportlab` | `fpdf2` | Smaller, pure-Python | Less mature for image flowables + table styling. reportlab is the defensible pick. |
| Hand-rolled GPX XML | `gpxpy` library | Type-safe GPX API | +1 dep for ~20 LOC of output. D-07 picks stdlib. |
| Natural Earth | GSHHG coastline | Higher fidelity at coarse scale | NE is simpler; shapefile + geopandas one-liner. D-11 fixes NE. |
| `torchmetrics` | `sklearn.metrics` / hand-rolled numpy | Fewer deps | **Hand-rolled**, ~20 lines total. IoU = `(pred & mask).sum() / (pred | mask).sum()`. |

---

## Architecture Patterns

### Recommended Project Structure (Phase 3 additions only)

```
backend/
├── ml/
│   ├── checkpoints/           # NEW — gitignored, user-supplied .pt lives here
│   │   └── our_real.pt        # user handoff target
│   ├── weights.py             # EXTEND — add our_real branch (file-load)
│   └── train.py               # NEW — user-supplied (committed after code-review)
├── mission/
│   ├── export.py              # NEW — 3 public functions (gpx/geojson/pdf)
│   └── exports/               # optional helper module folder (Claude's discretion)
│       ├── pdf_layout.py      # matplotlib map rendering helpers
│       └── gpx_writer.py      # ET.Element builder helpers
└── e2e_test.py                # NEW — pytest harness, full chain < 15 s

scripts/
├── run_full_chain_real.py     # NEW — our_real + fallback hooks at each stage
└── prebake_demo.py            # NEW — one-shot generator for fallback JSONs + MANIFEST + parity hashes

data/
├── basemap/
│   └── ne_10m_coastline_indian_eez.{shp,shx,dbf,prj}   # NEW — committed
└── prebaked/
    ├── {aoi}_detections.json
    ├── {aoi}_forecast.json
    ├── {aoi}_mission.json
    └── MANIFEST.json          # freshness + parity-hash table

tests/
├── test_weight_swap.py        # dummy vs. our_real schema-equality + value-inequality
├── test_export.py             # GPX/GeoJSON/PDF roundtrip on synthetic mission
├── test_train_script_review.py # static AST + grep checks of user's training code
└── test_prebake_parity.py     # live-run hash === prebaked hash on 4 AOIs
```

### Pattern 1: Safe Checkpoint Loading (THE load_weights("our_real") body)

**What:** Load a locally-pinned user-supplied checkpoint into `DualHeadUNetpp`, tolerant of the two common key-layout drifts (`module.` prefix from `DataParallel`, pure state_dict vs. full model pickle), but loud on any real mismatch.

**When to use:** In `backend/ml/weights.py`, replacing the current `NotImplementedError` in the `our_real` branch.

**Example:**
```python
# backend/ml/weights.py, new our_real branch
from pathlib import Path

CHECKPOINT_PATH = Path("backend/ml/checkpoints/our_real.pt")

def _strip_module_prefix(sd: dict) -> dict:
    """DataParallel / DDP wrap prepends 'module.' to every key. Strip if present."""
    if all(k.startswith("module.") for k in sd.keys()):
        return {k[len("module."):]: v for k, v in sd.items()}
    return sd

def _unwrap_checkpoint(obj) -> dict:
    """User might hand us raw state_dict OR {'state_dict': ..., 'epoch': ..., 'optimizer': ...}.
    Tolerate both; reject anything else loudly."""
    if isinstance(obj, dict) and "state_dict" in obj:
        return obj["state_dict"]
    if isinstance(obj, dict) and all(hasattr(v, "shape") or hasattr(v, "dtype") for v in obj.values()):
        return obj  # looks like a raw state_dict
    raise ValueError(
        f"Unrecognized checkpoint shape: type={type(obj).__name__}, "
        f"keys_sample={list(obj.keys())[:5] if isinstance(obj, dict) else 'n/a'}. "
        "Expected raw state_dict or {'state_dict': ...} wrapper."
    )

# In load_weights, our_real branch:
if source == "our_real":
    if not CHECKPOINT_PATH.exists():
        raise FileNotFoundError(
            f"our_real checkpoint missing at {CHECKPOINT_PATH}. "
            "User must deliver a .pt/.pth/.pkl file to that path, OR switch "
            "ml.weights_source back to 'dummy' in config.yaml."
        )
    # weights_only=True is PyTorch 2.6+ default and IS what we want for a user-supplied pickle
    # we do not trust arbitrary pickled objects; we want state_dict tensors only.
    # If the user's file embeds a pickled nn.Module wrapper, weights_only=True will raise --
    # that's a signal to fix the handoff, not to disable the safety.
    try:
        raw = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=True)
    except Exception as e:
        raise RuntimeError(
            f"torch.load(weights_only=True) failed on {CHECKPOINT_PATH}: {e}. "
            "User must re-save the checkpoint as `torch.save(model.state_dict(), ...)`, "
            "NOT `torch.save(model, ...)`. We do not disable weights_only for untrusted input."
        ) from e
    sd = _unwrap_checkpoint(raw)
    sd = _strip_module_prefix(sd)

    model = DualHeadUNetpp(in_channels=cfg.ml.in_channels)
    missing, unexpected = model.load_state_dict(sd, strict=False)
    if missing or unexpected:
        raise RuntimeError(
            "State-dict key mismatch:\n"
            f"  missing ({len(missing)}): {missing[:10]}\n"
            f"  unexpected ({len(unexpected)}): {unexpected[:10]}\n"
            "Training script's model class does not match backend/ml/model.py::DualHeadUNetpp."
        )
    return model.eval()
```

**Why this shape:**
- `weights_only=True` is the PyTorch 2.6+ default and the secure posture. If the user pickled a full `nn.Module` with `torch.save(model, ...)`, this fails early with a clear signal. **D-03 requires `strict=True`-equivalent behavior; we use `strict=False` to capture both missing+unexpected, then raise if either is non-empty — gives better error messages than raw `strict=True`.**
- The two drift classes (`module.` prefix, wrapper dict) are handled explicitly; anything beyond them is a real bug that should block the swap.
- Loading on CPU (`map_location="cpu"`) is deliberate — the demo is CPU-only per D-14/PRD §11.

[HIGH confidence — standard pattern from detectron2/mmcv/fvcore, verified against PyTorch 2.11 docs.]

### Pattern 2: Training-Code Review as Mechanical Verification

**What:** A single `tests/test_train_script_review.py` that does grep + AST-level checks on `backend/ml/train.py` (the user's committed script), passing or failing the 8 D-03 checkpoints without running any training.

**When to use:** Once the user commits `train.py`, before wiring the checkpoint.

**Example (sketch):**
```python
# tests/test_train_script_review.py
import ast
import inspect
from pathlib import Path

import pytest

TRAIN_PATH = Path("backend/ml/train.py")

def _tree():
    return ast.parse(TRAIN_PATH.read_text())

def test_d03_1_imports_dualhead_unetpp():
    """D-03.1: training script instantiates our DualHeadUNetpp class, not a local redef."""
    src = TRAIN_PATH.read_text()
    assert "from backend.ml.model import DualHeadUNetpp" in src, \
        "train.py must import DualHeadUNetpp from backend.ml.model (not redefine)"

def test_d03_2_reuses_feature_stack():
    """D-03.2: single source of truth — imports feature_stack, never a local reimpl."""
    src = TRAIN_PATH.read_text()
    assert "from backend.ml.features import feature_stack" in src, \
        "train.py must import feature_stack (single source of truth)"
    # grep for suspicious local redefs of FDI/NDVI/PI
    forbidden = ["def feature_stack(", "def _feature_stack(", "def compute_fdi("]
    for s in forbidden:
        assert s not in src, f"train.py reimplements features — found: {s}"

def test_d03_3_conf_mask_usage():
    """D-03.3: _conf.tif treated as valid_mask = (conf > 0), weight = conf/3.0 * valid_mask."""
    src = TRAIN_PATH.read_text()
    # Both motifs must appear:
    assert ("conf > 0" in src) or ("(conf > 0)" in src), "missing conf>0 mask"
    assert ("/ 3.0" in src) or ("/3.0" in src), "missing conf/3.0 normalization"

def test_d03_4_loss_composition():
    """D-03.4: loss contains Dice + BCE(pos_weight=~40) + MSE."""
    src = TRAIN_PATH.read_text()
    assert "pos_weight" in src, "BCE without pos_weight → class-imbalance collapse (PITFALL C3)"
    assert ("Dice" in src) or ("dice_loss" in src), "missing Dice loss term"
    assert "mse" in src.lower(), "missing MSE term for fraction head"

def test_d03_5_biofouling_mask_gated():
    """D-03.5: NIR augmentation is mask-gated. Look for '[mask ==' or indexing pattern."""
    src = TRAIN_PATH.read_text()
    # Weakest test — look for combined evidence of biofouling + masking in same function
    assert "biofouling" in src.lower() or "nir" in src.lower(), "no biofouling code found"
    # Manual inspection: augmentation must index by mask before multiplying NIR.
    # Programmatic: require comment OR a masked assign pattern; flag for human review if unclear.

def test_d03_6_no_torch_compile_no_bf16():
    """D-03.6: fp16 autocast only. No torch.compile, no bfloat16."""
    src = TRAIN_PATH.read_text()
    assert "torch.compile" not in src, "torch.compile forbidden (P100 sm_60 incompatible)"
    assert "bfloat16" not in src, "bfloat16 forbidden (T4 no bf16 hardware)"
    assert ("autocast" in src) and ("GradScaler" in src), "fp16 path missing"

def test_d03_7_split_discipline():
    """D-03.7: synthetic mixing pulls from train scenes only."""
    src = TRAIN_PATH.read_text()
    # Looser check — mixing code must reference train split
    if "synthetic" in src.lower() or "mix" in src.lower():
        assert "train_X.txt" in src or "train_scenes" in src, \
            "synthetic mixing must assert source scene ∈ train split"

def test_d03_8_state_dict_layer_parity():
    """D-03.8: instantiate our model, run a 0-epoch dry training-side instantiation, compare keys."""
    # Can't run the user's full script; instead instantiate our DualHeadUNetpp, get its state_dict
    # keys, and assert the checkpoint delivered at CHECKPOINT_PATH has the same keys.
    # Deferred to test_weight_swap.py — this test documents the requirement.
    pytest.skip("Covered by tests/test_weight_swap.py")
```

**Why this shape:**
- Pure static analysis — no training cost, no GPU, runs in < 1 s in CI.
- Each test maps 1:1 to a D-03 checkpoint item, so failures are traceable to specific pitfalls.
- D-03.5 (biofouling mask-gating) is **partially mechanical** — full verification requires a human-eyeball review of the relevant function, flagged in the test comment. This is honest: static grep cannot prove "mask-indexed multiply" semantics without full data-flow analysis. **The smoke gate below (§9) closes that gap empirically.**

[HIGH confidence on the pattern. MEDIUM on D-03.5 specifically — may require human review in addition.]

### Pattern 3: PDF via matplotlib → BytesIO → reportlab

**What:** One-page briefing generated deterministically from `MissionPlan` + optional `ForecastEnvelope` in < 3 s, < 1 MB.

**When to use:** `backend/mission/export.py::export_pdf`.

**Example:**
```python
# backend/mission/export.py (excerpt)
from io import BytesIO
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # CRITICAL: non-interactive backend, no Tk/Qt on CPU laptop
import matplotlib.pyplot as plt
import geopandas as gpd
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Image, Table, TableStyle, Paragraph, Spacer, PageBreak,
)
from reportlab.lib import colors

COASTLINE_PATH = Path("data/basemap/ne_10m_coastline_indian_eez.shp")

def _render_map_png(mission, forecast=None, *, dpi=150) -> BytesIO:
    """Returns an in-memory PNG buffer. dpi=150 gives a ~400 KB PNG at 4" × 6" figure."""
    fig, ax = plt.subplots(figsize=(6, 5), dpi=dpi)
    # 1) Coastline offline
    coast = gpd.read_file(COASTLINE_PATH)
    coast.plot(ax=ax, color="#777777", linewidth=0.5)
    # 2) Density overlay at +72h
    if forecast is not None and forecast.frames:
        last = forecast.frames[-1]
        if last.hour == 72 and last.density_polygons.features:
            gdf_dens = gpd.GeoDataFrame.from_features(
                [f.model_dump() for f in last.density_polygons.features], crs="EPSG:4326",
            )
            gdf_dens.plot(ax=ax, alpha=0.3, color="#00A0B0")
    # 3) Route
    route_coords = mission.route.geometry.coordinates
    if route_coords:
        xs, ys = zip(*route_coords)
        ax.plot(xs, ys, color="#C8102E", linewidth=1.5)
    # 4) Waypoints
    for wp in mission.waypoints:
        ax.scatter([wp.lon], [wp.lat], s=30, color="#FFB300", edgecolors="#333", zorder=5)
        ax.annotate(f"WP{wp.order:02d}", (wp.lon, wp.lat), fontsize=7, xytext=(4, 4),
                    textcoords="offset points")
    # 5) Origin
    ax.scatter([mission.origin[0]], [mission.origin[1]], s=80, marker="*",
               color="#1A237E", zorder=6)
    # 6) Extent — tight to route + small buffer
    all_lons = [mission.origin[0]] + [wp.lon for wp in mission.waypoints]
    all_lats = [mission.origin[1]] + [wp.lat for wp in mission.waypoints]
    if all_lons:
        pad = 0.3
        ax.set_xlim(min(all_lons) - pad, max(all_lons) + pad)
        ax.set_ylim(min(all_lats) - pad, max(all_lats) + pad)
    ax.set_aspect("equal")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, alpha=0.3, linestyle=":")

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)  # CRITICAL: release figure to avoid memory accumulation on repeated calls
    buf.seek(0)
    return buf

def export_pdf(mission, forecast, path: Path) -> Path:
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"<b>DRIFT Cleanup Mission Briefing</b>", styles["Title"]))
    story.append(Spacer(1, 0.3*cm))

    # Map panel (left 60% ≈ 11 cm wide, 9 cm tall on A4 portrait)
    map_buf = _render_map_png(mission, forecast, dpi=150)
    story.append(Image(map_buf, width=11*cm, height=9*cm))
    story.append(Spacer(1, 0.3*cm))

    # Waypoint table
    rows = [["#", "Lon", "Lat", "ETA (h)", "Priority"]]
    for wp in mission.waypoints:
        rows.append([str(wp.order), f"{wp.lon:.4f}", f"{wp.lat:.4f}",
                     f"{wp.arrival_hour:.1f}", f"{wp.priority_score:.3f}"])
    table = Table(rows, colWidths=[1*cm, 2.5*cm, 2.5*cm, 2*cm, 2.5*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A237E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#F0F0F0")]),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.3*cm))

    # Fuel panel
    fuel_l_per_km = 2.5
    est_fuel = mission.total_distance_km * fuel_l_per_km
    story.append(Paragraph(
        f"<b>Summary:</b> distance {mission.total_distance_km:.1f} km · "
        f"duration {mission.total_hours:.1f} h · est. fuel {est_fuel:.0f} L", styles["Normal"]))

    doc.build(story)
    return path
```

**Why this shape:**
- `matplotlib.use("Agg")` is the single most important line — without it, importing matplotlib may try to initialize Tk/Qt on Windows/Linux headless contexts and hang the demo.
- `dpi=150` on a 6×5 figure typically yields a 300–500 KB PNG, which after PDF compression is well under the 1 MB total budget.
- `plt.close(fig)` after savefig is mandatory — matplotlib leaks figure state across calls otherwise (the prebake script renders 4 AOIs in sequence; without close, memory climbs).
- `BytesIO` → `reportlab.platypus.Image` is the standard in-memory pattern; no temp files, no race conditions.

[HIGH confidence — canonical reportlab pattern confirmed across multiple sources (see Sources).]

### Pattern 4: GPX 1.1 via stdlib ElementTree

**What:** Minimal valid GPX 1.1 with waypoints + single track, no external library.

**Example:**
```python
# backend/mission/export.py (excerpt)
import xml.etree.ElementTree as ET
from pathlib import Path

GPX_NS = "http://www.topografix.com/GPX/1/1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOC = ("http://www.topografix.com/GPX/1/1 "
              "http://www.topografix.com/GPX/1/1/gpx.xsd")

def export_gpx(mission, path: Path) -> Path:
    # Register the default namespace so serialization writes xmlns="..." not ns0:
    ET.register_namespace("", GPX_NS)

    gpx = ET.Element(f"{{{GPX_NS}}}gpx", {
        "version": "1.1",
        "creator": "DRIFT PlastiTrack v1",
        f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOC,
    })

    # Waypoints: each MissionWaypoint → <wpt lat lon>
    for wp in mission.waypoints:
        wpt = ET.SubElement(gpx, f"{{{GPX_NS}}}wpt", {
            "lat": f"{wp.lat:.6f}", "lon": f"{wp.lon:.6f}",
        })
        ET.SubElement(wpt, f"{{{GPX_NS}}}name").text = f"WP{wp.order:02d}"
        desc = (f"priority={wp.priority_score:.3f} "
                f"eta_h={wp.arrival_hour:.1f}")
        ET.SubElement(wpt, f"{{{GPX_NS}}}desc").text = desc

    # Track: single <trk> with single <trkseg> of all LineString coords
    trk = ET.SubElement(gpx, f"{{{GPX_NS}}}trk")
    ET.SubElement(trk, f"{{{GPX_NS}}}name").text = "DRIFT vessel route"
    trkseg = ET.SubElement(trk, f"{{{GPX_NS}}}trkseg")
    for lon, lat in mission.route.geometry.coordinates:
        ET.SubElement(trkseg, f"{{{GPX_NS}}}trkpt", {
            "lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
        })

    tree = ET.ElementTree(gpx)
    # xml_declaration=True writes <?xml version='1.0' encoding='utf-8'?> — no BOM by default.
    # Google Earth is tolerant of either order of attributes.
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path
```

**Why this shape:**
- `ET.register_namespace("", GPX_NS)` is the single gotcha — without it, the serializer writes `ns0:gpx`, which **some GPS readers tolerate but Google Earth sometimes does not**.
- No XML Schema validation performed at write time (stdlib `ET` has no validator). A single round-trip parse test (`ET.parse(path); assert root.tag.endswith("gpx")`) is sufficient sanity.
- UTF-8 without BOM is GPX 1.1's canonical encoding — `xml_declaration=True` + `encoding="utf-8"` is correct.

[HIGH confidence — matches topografix.com GPX 1.1 schema docs.]

### Pattern 5: Silent Auto-Fallback with Per-Stage Wrapping

**What:** `scripts/run_full_chain_real.py` catches exceptions at each stage boundary. On failure at stage N, loads `data/prebaked/{aoi}_{N+}.json`, validates it against the schema, and continues.

**Example:**
```python
# scripts/run_full_chain_real.py (excerpt)
import json
import logging
import time
from pathlib import Path

from backend.core.schemas import (
    DetectionFeatureCollection, ForecastEnvelope, MissionPlan,
)

PREBAKE_DIR = Path("data/prebaked")
log = logging.getLogger("drift.e2e")

class StageFailed(Exception):
    pass

def _with_fallback(stage_name: str, aoi: str, live_fn, schema_cls, *args, no_fallback=False):
    t0 = time.perf_counter()
    try:
        result = live_fn(*args)
        elapsed = time.perf_counter() - t0
        log.info(f"[OK] stage={stage_name} elapsed={elapsed:.2f}s")
        return result
    except Exception as exc:
        if no_fallback:
            raise
        fallback_path = PREBAKE_DIR / f"{aoi}_{stage_name}.json"
        log.warning(f"[FALLBACK] stage={stage_name} reason={type(exc).__name__}: {exc}")
        if not fallback_path.exists():
            raise StageFailed(
                f"stage={stage_name} failed AND no prebaked fallback at {fallback_path}"
            ) from exc
        # Schema-validate — never trust stale disk
        with fallback_path.open() as f:
            payload = json.load(f)
        try:
            return schema_cls.model_validate(payload)
        except Exception as v_exc:
            raise StageFailed(
                f"stage={stage_name}: live failed ({exc}) AND fallback schema invalid ({v_exc})"
            ) from v_exc

def run_chain(aoi: str, tile_path: Path, origin, cfg, *, no_fallback=False):
    detections = _with_fallback(
        "detections", aoi, lambda: run_inference(tile_path, cfg),
        DetectionFeatureCollection, no_fallback=no_fallback,
    )
    forecast = _with_fallback(
        "forecast", aoi, lambda: forecast_drift(detections, cfg),
        ForecastEnvelope, no_fallback=no_fallback,
    )
    mission = _with_fallback(
        "mission", aoi, lambda: plan_mission(forecast, 200, 8, origin, cfg),
        MissionPlan, no_fallback=no_fallback,
    )
    return detections, forecast, mission
```

**Why this shape:**
- Silent by default (D-12), `--no-fallback` raises for debugging.
- Schema-validates fallback JSON before returning — a stale/corrupt prebake can't poison the demo.
- Uses `logging.warning` not `print` so output can be filtered off the demo screen if needed.

[HIGH confidence — canonical exception-wrapping pattern.]

### Anti-Patterns to Avoid

- **`torch.load(..., weights_only=False)` "because it's convenient"** — this re-enables arbitrary code execution on a file you received from outside your trust boundary. The user's handoff is convenient but not "trusted source" in the supply-chain sense. See §1.
- **Saving full `torch.save(model, path)` instead of `torch.save(model.state_dict(), path)`** — couples the checkpoint to a specific class import path. Training-code review must require state_dict-only saves (part of §2 verification).
- **`matplotlib.use("TkAgg")` or leaving the default backend** — interactive backends will attempt display on headless CI and can hang the prebake script. Always `use("Agg")` at module import time.
- **Reading the coastline shapefile inside `export_pdf` every call** — it's 1–2 MB of parse work; if we render 4 AOIs the cost compounds. **Cache at module scope** (`_COASTLINE = gpd.read_file(...)` once).
- **Hash comparing `model_dump()` dicts directly** — dict key order isn't guaranteed stable across Python interpreters. Always go through `model_dump_json(sort_keys=True)` (D-14 mandates this — documented here as the anti-pattern explanation).
- **Using PDF latency targets (< 3 s) as a proxy for PDF *first-call* latency** — matplotlib's first import is 2–4 s on a cold Python; **warm up** matplotlib in the prebake script and the E2E test fixture so the ≤ 3 s budget is measured on a warm process (D-15).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF composition with tables + images | Custom PostScript / Cairo driver | `reportlab` flowables | Handles pagination, font embedding, byte-range compression. |
| Checkpoint key re-keying | Deep-copy + regex rename | `strict=False` + explicit prefix strip (Pattern 1) | The two real drift modes (`module.` prefix, state_dict wrapper) are exactly 2 code paths; more logic → more bugs. |
| Pydantic → GeoJSON serialization | Manual `json.dumps` + custom encoder | `mission.model_dump_json(indent=2)` | Schema is already RFC-7946 by construction (D-08). |
| GeoJSON schema validation | Custom RFC-7946 validator | `geojson_pydantic` round-trip (already used in `backend/core/schemas.py`) | Available; pydantic raises on drift. |
| IoU / precision metric | Full `torchmetrics` install | 10 lines of numpy: `iou = (pred & mask).sum() / (pred \| mask).sum()` | Phase 3 uses this once in a test. Zero-sum scope rule. |
| Matplotlib geographic basemap | Cartopy | geopandas `.plot(ax=ax)` on a Natural Earth shapefile | Cartopy adds ~300 MB of Conda-Forge deps. geopandas is already installed. |
| Parity normalization of floats | Custom IEEE-754 bit-stripping | `json.dumps(obj, default=lambda x: round(x, 6))` or pydantic model_dump_json with pre-round pass | Overkill for a 6-decimal tolerance. |
| Deterministic dict sorting for hash | Custom recursive sort | `json.dumps(obj, sort_keys=True)` | `sort_keys=True` recurses. |

**Key insight:** Phase 3 is primarily a **glue-code** phase. Every line of custom logic we can replace with a stdlib or already-installed call is a line we don't have to debug at H+34.

---

## Runtime State Inventory

Phase 3 is primarily additive code + config, not a rename/refactor. However, the weight-source flip does touch runtime-state in two narrow ways:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | `data/prebaked/{aoi}_{stage}.json` — generated at H+28, must be regenerated whenever `our_real` checkpoint changes OR when stage-boundary schema shape changes (schema is frozen so latter should not happen). | `scripts/prebake_demo.py` rerun. MANIFEST.json `git_sha` + `weights_source` stamp lets fallback loader detect staleness and warn. |
| **Live service config** | None. | None. Everything is offline-first (D-11, D-12). |
| **OS-registered state** | None. | No daemons, no scheduled tasks, no systemd units. |
| **Secrets/env vars** | `ML__WEIGHTS_SOURCE=our_real` env override replaces the YAML. `PYTHONHASHSEED=0` for parity tests. `CUBLAS_WORKSPACE_CONFIG=:4096:8` only relevant if we ever re-ran on GPU (we don't — CPU-only parity per D-14). | Document `PYTHONHASHSEED=0` and torch seeding in `scripts/prebake_demo.py` and `tests/test_prebake_parity.py` headers. |
| **Build artifacts / installed packages** | `reportlab` added to `requirements.txt` at Wave 0. `backend/ml/checkpoints/our_real.pt` arrives via user handoff — gitignored (per existing `.gitignore` entries for `*.pt`, `*.pth`, `*.ckpt`). | Update `.gitignore` if not already covering `backend/ml/checkpoints/` explicitly. `pip freeze > requirements.lock` at H+32 per D-17. |

**The canonical question answered:** *After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?* → only `data/prebaked/*.json`, and the MANIFEST tracks them for us.

---

## Common Pitfalls

### Pitfall 1: `torch.load(weights_only=True)` Silently Blocks the User's Handoff

**What goes wrong:** PyTorch ≥ 2.6 flipped the default of `torch.load`'s `weights_only` arg from `False` to `True`. If the user saved their checkpoint via `torch.save(model, path)` (not `torch.save(model.state_dict(), path)`), our `weights_only=True` load will raise with a message about `UnsupportedOperationException: cannot unpickle ... module 'backend.ml.model'`.
**Why it happens:** Prior-era tutorials teach `torch.save(model, ...)`. PyTorch 2.6+ security posture forbids this for untrusted input.
**How to avoid:** Require user to re-save as state_dict (part of D-03.8 check). Provide a clear error message that tells them exactly what to re-run (`torch.save(model.state_dict(), "our_real.pt")`). **Do NOT disable `weights_only` as a workaround** — that re-enables arbitrary code execution. The right fix is to correct the handoff.
**Warning signs:** `UnpicklingError` with `GLOBAL` or `FIND_CLASS` in the traceback.

### Pitfall 2: `matplotlib` First-Import Cost Blows the 3 s PDF Budget

**What goes wrong:** Cold `import matplotlib.pyplot` takes 2–4 s on CPython 3.11. First `plt.subplots()` loads fonts and takes another 1–2 s. The first `export_pdf` call in a fresh process can blow the 3 s budget even on the tightest layout.
**How to avoid:** Pre-import matplotlib at module load in `backend/mission/export.py`. Warm fonts in a one-time module init. In the E2E test + prebake script, measure PDF latency on the **second** call after warming.
**Warning signs:** First call 4.5 s, second call 0.8 s.

### Pitfall 3: Parity Hash Drift From Coordinate-Formatting Choices

**What goes wrong:** `model_dump_json()` writes floats at full IEEE-754 precision (e.g., `73.89234567890123`). Two runs producing `73.89234567890124` and `73.89234567890125` (last-bit fp noise) hash differently, failing the parity test even when results are effectively identical.
**How to avoid:** D-14's `normalize_floats(round=6)` pass is mandatory. Implement by walking the pydantic dump dict recursively and rounding any `float` leaf. 6 decimals is ~0.1 m at the equator for lon/lat — well below the KDE/tracker noise floor.
**Warning signs:** Parity test fails on day-1 with zero code changes.

### Pitfall 4: Schema-Invalid Prebaked JSON Masquerading as Healthy

**What goes wrong:** Prebake script at H+28 runs, writes JSON, passes. Later a schema field is added (shouldn't happen per D-05 freeze, but just in case). Fallback loads old JSON at demo, `pydantic.ValidationError` fires mid-stage. Or worse: naïve `json.load` succeeds because pydantic isn't re-invoked, and downstream code fails on a missing attribute.
**How to avoid:** Pattern 5's `_with_fallback` wrapper re-validates via `schema_cls.model_validate(payload)` before returning. MANIFEST `git_sha` check can warn if the prebake was done at a different commit than current HEAD.
**Warning signs:** `ValidationError` in the fallback path.

### Pitfall 5: GPX Namespace Prefix Confusion in Google Earth

**What goes wrong:** Without `ET.register_namespace("", GPX_NS)`, ElementTree serializes as `<ns0:gpx xmlns:ns0="...">`. Some GPX readers (older Garmin devices, strict parsers) reject this; Google Earth tolerates it but some lint tools don't.
**How to avoid:** Always register the default namespace to empty string. Add a smoke test that opens the file and asserts the root tag starts with `{http://www.topografix.com/GPX/1/1}gpx`.
**Warning signs:** `ns0:` prefix in the output file.

### Pitfall 6: Natural Earth Clipping Removes Needed Islands

**What goes wrong:** Clipping `ne_10m_coastline` to `[67, 95, 5, 25]` with `gpd.clip(coast, box)` cuts LineString features at the bbox edge — fine for coastlines but can remove small islands whose bbox extends just outside. Maldives (73°E, 4°N) is just below our `5°` lat threshold and would be lost.
**How to avoid:** Widen the clip bbox to `[65, 97, 3, 27]` (a 2° safety buffer beyond the AOI union). Simplify with `coast.simplify(tolerance=0.01)` only after clipping to keep the file < 2 MB (D-11).
**Warning signs:** Maldives/Lakshadweep/Andaman missing from the PDF map.

### Pitfall 7: `strict=True` Produces Unhelpful Error Messages

**What goes wrong:** `load_state_dict(sd, strict=True)` raises `RuntimeError` with a wall of keys — hard to quickly see if the issue is one typo or a whole-model mismatch.
**How to avoid:** Pattern 1 uses `strict=False` capture + explicit non-empty check + truncated missing/unexpected lists in the error. Equivalent strictness semantically; far better operator experience at H+34.
**Warning signs:** 200-line traceback that crashes the terminal scrollback.

### Pitfall 8: Determinism Theatre (SEED setting with non-deterministic CPU ops)

**What goes wrong:** We set `torch.manual_seed(1410)`, `numpy.random.seed(1410)`, `random.seed(1410)`, `PYTHONHASHSEED=0`. We believe we have determinism. But: `sklearn.neighbors.KernelDensity` with no explicit `random_state` can produce different contour extraction at the matplotlib level; `shapely.buffer(0)` behavior can vary across shapely versions; **CPU matmul in PyTorch for `conv2d`** is deterministic by default (no `benchmark=True` flag needed for CPU), but any op that reduces a large axis may hit non-determinism if we ever parallelize with > 1 thread.
**How to avoid:**
1. Set `torch.set_num_threads(1)` in `scripts/prebake_demo.py` and the parity test — single-threaded CPU is fully deterministic.
2. `torch.use_deterministic_algorithms(True)` — for CPU-only this is cheap. (For GPU it would require `CUBLAS_WORKSPACE_CONFIG=:4096:8`; we skip because GPU parity is not required, D-14.)
3. KDE: instantiate `KernelDensity(kernel="gaussian", bandwidth=...)` — it's analytic (no internal RNG) so it's deterministic by construction. No `random_state` needed.
4. `normalize_floats(round=6)` handles the residual fp drift.
5. Pin `shapely>=2.0,<3.0` already in place; verify `buffer(0)` on a known polygon returns the same WKT across runs.

**Warning signs:** Parity test fails on exactly one of the 4 AOIs, intermittently.

### Pitfall 9: E2E < 15 s Budget Lies When First-Call Costs Dominate

**What goes wrong:** `pytest backend/e2e_test.py` measures from process start → test end. `torch.load` + matplotlib import + rasterio import easily eat 5–8 s just for cold imports. The test "fails" the 15 s budget on imports, not on business logic.
**How to avoid:** The budget measurement should be **inside** the test, using `time.perf_counter()` to bracket the three-stage chain only — not wall-clock of the pytest run. Imports happen before the `t0 = perf_counter()` line.
**Warning signs:** Budget sometimes fails cold, always passes warm.

### Pitfall 10: Prebake Script Runs With Stale Git SHA

**What goes wrong:** Developer runs `scripts/prebake_demo.py` at H+20, commits code changes at H+24, doesn't rerun prebake. MANIFEST's `git_sha` shows older commit; fallback loads slightly-stale data. Live-vs-prebake parity test fails because live is using newer code.
**How to avoid:** Prebake script first checks `git status --porcelain`; aborts if the working tree is dirty. Writes current `HEAD` SHA into MANIFEST. Parity test warns (not fails) if MANIFEST `git_sha` ≠ current HEAD.
**Warning signs:** Parity test fails at H+30 after a pre-H+28 prebake.

---

## Code Examples

Code examples are embedded in **Architecture Patterns** above (Patterns 1–5). Additional small examples:

### Parity hash (D-14)

```python
# scripts/prebake_demo.py / tests/test_prebake_parity.py (shared helper)
import hashlib
import json

def normalize_floats(obj, ndigits=6):
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: normalize_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_floats(x, ndigits) for x in obj]
    return obj

def parity_hash(model) -> str:
    raw = json.loads(model.model_dump_json())
    normalized = normalize_floats(raw, ndigits=6)
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

### Metric re-eval on one MARIDA val scene (≤ 5 min)

```python
# tests/test_metrics_reeval.py
import numpy as np
import rasterio
from pathlib import Path

from backend.core.config import Settings
from backend.ml.inference import run_inference  # emits schema, not raster
# For mask-level IoU we need a simpler hook — load model, forward on one patch, compare to _cl.tif

def _iou(pred: np.ndarray, target: np.ndarray) -> float:
    inter = np.logical_and(pred, target).sum()
    union = np.logical_or(pred, target).sum()
    return float(inter) / float(union) if union else 0.0

def test_marida_iou_sanity(one_val_patch_path, cl_mask_path):
    cfg = Settings()
    # bypass run_inference's polygonization; directly get raster prob
    # (implementation: add a helper in inference.py, or duplicate its 20 LOC pipeline here)
    from backend.ml.weights import load_weights
    from backend.ml.features import feature_stack
    model = load_weights(cfg).eval()
    # ... load bands, feature_stack, sliding_forward → prob map
    # ... prob > 0.5 → pred
    cl = rasterio.open(cl_mask_path).read(1)
    gt_plastic = (cl == 1)  # MARIDA class 1 = plastic
    iou = _iou(pred, gt_plastic)
    # D-04: do NOT fail — log it. Target is 0.45 but we tolerate misses.
    print(f"[metric] IoU on {one_val_patch_path}: {iou:.3f}")
    assert iou >= 0.0  # sanity only
```

### Warming matplotlib before the 3 s budget starts

```python
# backend/mission/export.py (module-level init)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Cheap warm-up: first figure is the slow one
_warm = plt.figure(figsize=(1, 1))
plt.close(_warm)
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| `torch` | checkpoint loading | ✓ | ≥ 2.6 (from Phase 1 install) | — |
| `segmentation-models-pytorch` | model class | ✓ | 0.5.x (from Phase 1) | — |
| `matplotlib` | PDF map | ✓ | 3.9.x (from Phase 1) | — |
| `geopandas` | coastline overlay | ✓ | 1.0.x (from Phase 1) | — |
| `reportlab` | PDF composition | **UNKNOWN — verify Wave 0** | target ≥ 4.2 | **BLOCKING if missing — must `pip install` before H+32 freeze** |
| Natural Earth `ne_10m_coastline` shapefile | offline basemap | ✗ (not yet on disk) | — | **BLOCKING — Wave 0 task: download + clip. Source: [naturalearthdata.com](https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-coastline/) (public domain).** |
| User-supplied `our_real.pt` checkpoint | weight swap | ✗ (user handoff pending) | — | **BLOCKING for weight-swap wave only. Export/fallback/prebake work can proceed in parallel against `dummy` output + synthetic MissionPlan fixtures.** |
| `data/env/cmems_currents_72h.nc` + `era5_winds_72h.nc` | forecast stage in E2E | ✓ (Phase 2 deliverable, already fetched) | — | Synthetic xarray fixture (already demonstrated in Phase 2 tests). |

**Missing dependencies with no fallback:**
- `reportlab` (trivial — `pip install`)
- Natural Earth coastline (download + clip — ~10 min work)
- User's checkpoint (external dependency — blocks weight-swap wave but no other work)

**Missing dependencies with fallback:**
- All export work can proceed against synthetic fixtures built from the Phase 2 `MissionPlan` output.

---

## Validation Architecture

*Phase-level `nyquist_validation` is disabled in `.planning/config.json`. Formal Nyquist test-map section skipped per project policy. Informal "how we'll know it works" notes below.*

### How We'll Know It Works

| Concern | Verification |
|---------|-------------|
| Checkpoint loads and produces valid output | `tests/test_weight_swap.py` — runs `run_inference` on one MARIDA patch with `dummy` AND `our_real`, asserts both schemas validate, asserts the outputs differ byte-wise. |
| Training script is pitfall-safe | `tests/test_train_script_review.py` (8 tests, one per D-03 item). Pure static analysis. |
| Export artifacts open cleanly | `tests/test_export.py` — runs all three exporters on a synthetic mission; asserts GPX parses back; asserts PDF starts with `%PDF-`; asserts GeoJSON schema round-trips. |
| E2E < 15 s on CPU | `backend/e2e_test.py` — `time.perf_counter()` brackets inside the test, after warm-up, with budget knobs documented (D-15). |
| Fallback is silent + correct | `tests/test_fallback.py` — monkeypatch `run_inference` to raise; assert wrapper loads prebake + schema-validates + continues. |
| Parity on 4 AOIs | `tests/test_prebake_parity.py` — runs chain against each AOI, hashes each stage, compares to MANIFEST's recorded hash. CPU-only, fixed seed. Runs after prebake step. |
| Metric sanity re-eval | `tests/test_metrics_reeval.py` — single-patch IoU check, logs result, never fails (D-04 — log and continue). |

### Sampling Rate
- **Per commit in Phase 3 waves:** run the tests relevant to the wave (fast; most tests are < 5 s).
- **Per wave merge:** run `pytest -x backend/ tests/` — ≤ 2 min.
- **Phase gate:** `pytest` all green + `scripts/run_full_chain_real.py` completes in < 15 s + PDF opens + GPX opens in Google Earth + 60 s screen recording produced.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `torch.load(path)` (weights_only=False default) | `torch.load(path, weights_only=True)` default | PyTorch 2.6 (Jan 2025) | Forces state_dict-only saves for untrusted input; a *good* constraint for us. |
| `kagglehub.model_download` as the primary weight-transport channel | User-supplied local checkpoint (D-01/D-02) | 2026-04-17 user directive | Removes network dep at demo time; kagglehub demoted to optional fallback. |
| `torch.save(model, path)` (full module pickle) | `torch.save(model.state_dict(), path)` | PyTorch 2.6 security push | Required by our `weights_only=True` load. Training script must follow. |

**Deprecated/outdated (do not reach for):**
- `pickle.load` on checkpoints (same concern as `weights_only=False`).
- `torchvision.models.segmentation.deeplabv3_resnet50` as a fallback backbone — trained on 3-channel RGB; incompatible with our 14-channel input (carried from Phase 1 research, still relevant).
- `weasyprint` / `wkhtmltopdf` / headless Chrome for PDF — all rejected per D-10/PRD §8.6.

---

## Open Questions

1. **User's exact checkpoint save format** (state_dict vs. wrapped vs. full module)
   - What we know: D-02 says `.pt`/`.pth`/`.pkl`; D-03.8 implies state_dict.
   - What's unclear: whether the user's training script actually saves via `torch.save(model.state_dict(), ...)` or the fuller `{state_dict, optimizer, epoch}` dict.
   - Recommendation: Pattern 1 handles both. If the user hands us a full-module pickle, Pattern 1 errors loudly with a clear fix ("re-save as state_dict"). The planner should allocate ~30 minutes of buffer for a handoff iteration.

2. **D-03.5 biofouling augmentation — static verification limits**
   - What we know: the check is "multiply NIR only where mask == 1".
   - What's unclear: grep can confirm the intent is present; only a unit test (augment a zero-mask sample, assert bands unchanged) can prove semantics. Ideally the user's script ships this test.
   - Recommendation: in `tests/test_train_script_review.py`, include an *integration* test that imports the user's augmentation function and runs it on a zero-mask sample. If the user doesn't expose the function cleanly, flag for human review and accept the grep-only check.

3. **Prebake parity tolerance if a future shapely or numpy patch shifts fp output**
   - What we know: Pitfall 8 prescribes `round=6`, single-threaded CPU, deterministic flags.
   - What's unclear: whether 6 decimals of rounding is actually robust to a pip wheel update between H+28 and H+36.
   - Recommendation: freeze the environment via `pip freeze > requirements.lock` at H+32 (D-17); any wheel drift after freeze is a discipline violation, not a research gap.

4. **PDF first-call latency measurement discipline**
   - What we know: Pitfall 2/9 — matplotlib cold import eats budget.
   - What's unclear: whether the prebake script's first PDF is inside or outside the 3 s budget (which it self-defines).
   - Recommendation: `export_pdf` budget (D-15) is measured on a **warm** process; prebake script documents this explicitly with a banner comment.

5. **Whether to remove the `kagglehub` code path entirely vs. keep as secondary**
   - What we know: D-02 permits either ("optional secondary OR removed entirely at planner's discretion").
   - What's unclear: whether touching that code risks churning a working Phase 1 asset.
   - Recommendation: **keep the code path but un-invoke it by default**. Phase 3 should not edit Phase 1 modules beyond adding the `our_real` branch. Zero-sum scope rule doesn't force deletion here since removing `kagglehub` requires a net code change (subtraction) that still costs review time.

---

## Sources

### Primary (HIGH confidence)
- [PyTorch 2.11 docs — `torch.load`](https://docs.pytorch.org/docs/stable/generated/torch.load.html) — weights_only semantics, safe-globals API.
- [PyTorch 2.8 docs — Reproducibility notes](https://docs.pytorch.org/docs/stable/notes/randomness.html) — deterministic algorithms, CUBLAS_WORKSPACE_CONFIG, seed protocols.
- [PyTorch 2.11 docs — `torch.use_deterministic_algorithms`](https://docs.pytorch.org/docs/stable/generated/torch.use_deterministic_algorithms.html) — flag behavior on CPU and GPU.
- [BC-Breaking: torch.load weights_only=True default (dev-discuss PyTorch)](https://dev-discuss.pytorch.org/t/bc-breaking-change-torch-load-is-being-flipped-to-use-weights-only-true-by-default-in-the-nightlies-after-137602/2573) — official announcement of the 2.6 default flip.
- [TIL: weights-only model loading default in PyTorch 2.6 (Ian Barber)](https://ianbarber.blog/2025/01/08/til-weights-only-model-loading-will-be-the-default-in-pytorch-2-6/) — migration guidance.
- [ReportLab User Guide, Chapter 5 — Platypus](https://docs.reportlab.com/reportlab/userguide/ch5_platypus/) — SimpleDocTemplate, Image, Table, Paragraph flowables canonical usage.
- [ReportLab User Guide, Chapter 11 — Graphics](https://docs.reportlab.com/reportlab/userguide/ch11_graphics/) — ImageReader + BytesIO patterns.
- [Generating charts with ReportLab + matplotlib (Woteq Zone)](https://woteq.com/how-to-generate-charts-with-reportlab-and-matplotlib) — BytesIO → Image flowable verified pattern.
- [GPX 1.1 Schema (topografix.com)](https://www.topografix.com/GPX/1/1/) — schema, namespace, wpt/trkpt/trkseg semantics.
- [GPS Exchange Format (Wikipedia)](https://en.wikipedia.org/wiki/GPS_Exchange_Format) — canonical element names, wptType reuse.
- [Natural Earth Downloads — 10m coastline](https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-coastline/) — public domain vector data, file format, 1:10m scale.
- [Natural Earth homepage](https://www.naturalearthdata.com/) — public-domain licensing statement.

### Secondary (MEDIUM confidence)
- [PyTorch Forums — load_state_dict "module." prefix problem](https://discuss.pytorch.org/t/runtimeerror-error-s-in-loading-state-dict-for-dataparallel-missing-key-s-in-state-dict/31725) — standard prefix-strip workaround.
- [PyTorch Forums — Determinism in inference](https://discuss.pytorch.org/t/determinism-in-inference/208033) — CPU determinism guarantees.
- [Reproducible Deep Learning Using PyTorch (Medium, Darina Bal)](https://darinabal.medium.com/deep-learning-reproducible-results-using-pytorch-42034da5ad7) — seed-protocol checklist.
- [fvcore checkpoint loader (detectron2)](https://detectron2.readthedocs.io/en/latest/_modules/fvcore/common/checkpoint.html) — reference implementation for the tolerant load pattern.
- [mmcv checkpoint loader](https://mmcv.readthedocs.io/en/v1.4.5/_modules/mmcv/runner/checkpoint.html) — alternative canonical loader with prefix-strip and shape-mismatch handling.
- [GPX 1.0 Developer's Manual (TopoGrafix)](https://www.topografix.com/gpx_manual.asp) — historical reference, confirms wptType reuse across rtept/trkpt/wpt.

### Tertiary (LOW confidence — flagged for empirical validation during Phase 3)
- Specific matplotlib cold-import latency number (2–4 s) — varies by installation; measure on the actual demo laptop during Wave 0.
- Specific reportlab PDF output size for a 6×5 inch 150 dpi map — depends on PNG content complexity; measure with a representative mission fixture.
- Natural Earth shapefile size after clip + simplify — depends on simplification tolerance; empirically tune during basemap preparation.

---

## Metadata

**Confidence breakdown:**
- **Safe checkpoint loading (§1):** HIGH — standard pattern, PyTorch 2.6 behavior verified, `DataParallel` prefix handling is canonical.
- **Training-code review (§2):** MEDIUM — AST/grep patterns are solid; D-03.5 biofouling mask-gating is only partially statically verifiable.
- **PDF stack (§3):** HIGH — canonical reportlab + matplotlib BytesIO pattern verified across multiple sources.
- **GPX 1.1 schema (§4):** HIGH — topografix.com is the authoritative spec; minimum structure confirmed.
- **Natural Earth coastline (§5):** HIGH — public domain confirmed via naturalearthdata.com homepage; geopandas read/clip workflow standard.
- **Determinism (§6):** HIGH for CPU-only + single-threaded + deterministic flags; MEDIUM for empirical fp rounding tolerance.
- **E2E latency (§7):** MEDIUM — per-stage budget from D-15 is reasonable on a modern CPU laptop; warm-vs-cold discipline matters more than theoretical numbers.
- **Fallback architecture (§8):** HIGH — canonical exception-wrapping pattern; schema-validation on load is essential.
- **Training-script smoke (§9):** MEDIUM — AST check is cheap; real integration smoke depends on user's script structure.
- **Metric re-eval (§10):** HIGH — hand-rolled numpy IoU is 10 lines; torchmetrics unnecessary.

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (30 days; reportlab/matplotlib/torch 2.6 APIs are stable). Revisit only if a user-facing library pins change.

---

*Phase: 03-real-training-weight-swap-mission-export-e2e*
*Research compiled: 2026-04-17*
