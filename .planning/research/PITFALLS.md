# Domain Pitfalls — DRIFT / PlastiTrack Backend Intelligence

**Domain:** Marine-plastic sub-pixel detection + Lagrangian ocean-drift forecast + cleanup-mission planning from Sentinel-2 imagery
**Researched:** 2026-04-17
**Confidence:** HIGH (Context7-verified for Sentinel-2 scaling, rasterio, Kaggle; MEDIUM for MARIDA-specific training gotchas; LOW on a few ecosystem-folklore items explicitly flagged)
**Scope window:** 24–48 h hackathon build; three-phase split (P1 dummy inference → P2 trajectory → P3 real training + mission + schema-freeze enforcement)

This file is written for the roadmap author and the three implementers. Every pitfall is something that has killed a similar project — not generic "write tests" advice. Each has a warning sign you can check, a prevention strategy you can implement in <30 min, and a phase it belongs to.

---

## Critical Pitfalls

Mistakes that cause rewrites, demo-time crashes, or wholesale loss of the 48-hour window.

### C1. Sentinel-2 L2A Reflectance Offset Bug (Processing Baseline ≥ 04.00)

**What goes wrong:** Starting 2022-01-25, all new Sentinel-2 L2A products (Processing Baseline 04.00+) ship with a band-dependent `BOA_ADD_OFFSET` (value -1000 DN, i.e. -0.1 in reflectance units) that must be added before dividing by QUANTIFICATION_VALUE=10000. Teams that do the naive `reflectance = DN / 10000.0` will have their inputs shifted by -0.1 relative to the MARIDA training distribution (which was assembled from older baselines).

**Why it happens:** The offset was introduced to avoid clipping dark-scene noise after quantization. It is documented in scene metadata, not in the most popular tutorials. MARIDA's own README was written before this baseline change.

**Consequences:** Model outputs collapse to uniform low-probability everywhere (because B8 and B11 values are ~0.1 lower than training). Silent failure — no exception, no obvious artifact. Team spends 4 hours debugging what looks like a model-quality issue but is a preprocessing bug.

**Warning signs:**
- Any tile with a `PROCESSING_BASELINE` metadata value ≥ 04.00 (check `MTD_MSIL2A.xml`).
- Model confidence histogram is unimodal near 0.0 on real tiles but looks normal on MARIDA patches.
- Inputs to the network have mean ~0.0 instead of ~0.1 for water pixels.

**Prevention:**
```python
# backend/ml/features.py — treat offset explicitly
def load_s2_reflectance(path, band_offsets_dn):
    with rasterio.open(path) as src:
        dn = src.read(1).astype("float32")
    # band_offsets_dn typically -1000 for PB>=04.00, 0 for older products
    return (dn + band_offsets_dn) / 10000.0
```
Parse `BOA_ADD_OFFSET_VALUES_LIST` from scene metadata. If unavailable (e.g., demo-tile baseline pre-04.00), set to 0. Add a unit test: "a known water pixel from a PB≥04.00 tile should produce B8 ≈ 0.08, not ≈ -0.02."

**Phase:** **Phase 1** — must be correct before the dummy `run_inference` uses real B2–B11 data, because the schema output (`fraction_plastic`, `conf_raw`) depends on this scaling.

**Confidence:** HIGH — [ESA Sentinel-2 Processing Baseline docs](https://sentinel.esa.int/web/sentinel/technical-guides/sentinel-2-msi/processing-baseline), [ClearSKY Sentinel-2 scaling knowledge base](https://clearsky.vision/knowledge/sentinel2-scaling-harmonization).

---

### C2. MARIDA Confidence Mask Misuse (the `_conf.tif` Trap)

**What goes wrong:** Each MARIDA patch ships with `*_cl.tif` (class labels, 15 classes, plastic=1) AND `*_conf.tif` (weak-supervision annotator confidence, values 1/2/3 or 0 for nodata). The natural-looking loop is:
```python
loss = bce(pred, mask) * conf  # WRONG — loss weighting by conf per pixel
```
But `conf` contains zeros for unlabelled pixels. If those zeros are multiplied into the loss without excluding nodata, the model learns *not* to care about the majority of its input. Alternatively, teams treat conf==0 as "confident negative" and train the model to predict "no plastic" everywhere.

**Why it happens:** The distinction between "no label" (conf=0) and "confident no-plastic" (conf=3 on a water pixel) is subtle. The MARIDA paper describes it but the starter code does not enforce it.

**Consequences:** Model IoU caps around 0.1–0.2 regardless of epoch count. Looks like the architecture is wrong; it's the data loader. Rewrite under deadline = project dead.

**Warning signs:**
- Val IoU plateaus below 0.3 after 10 epochs on MARIDA (expected: 0.45+).
- Train loss decreases but recall on plastic class stays near zero.
- Output confidence histogram is tightly concentrated near zero.

**Prevention:**
```python
# backend/ml/dataset.py
valid_mask = (conf > 0)        # only labeled pixels contribute
weights = conf.astype("float32") / 3.0   # 1/3, 2/3, 1.0
weights *= valid_mask          # zero out nodata
# In training loop:
loss = (bce(pred, mask) * weights).sum() / weights.sum().clamp_min(1.0)
```
Write a 5-line unit test: load a single MARIDA patch, assert `(conf == 0).any() and (conf > 0).any()`, assert loss is a finite scalar.

**Phase:** **Phase 3** — real training. Phase 1 uses pretrained weights so the bug doesn't bite until training starts.

**Confidence:** HIGH — [MARIDA Zenodo record](https://zenodo.org/records/5151941) + [MarcCoru/marinedebrisdetector](https://github.com/MarcCoru/marinedebrisdetector) reference implementation.

---

### C3. Plastic Class Imbalance (~2% Pixels → MSE / BCE Collapse to Zero Predictions)

**What goes wrong:** Plastic pixels are roughly 1–3% of labeled pixels in MARIDA (most pixels are water, Sargassum, or unlabelled). With unweighted BCE or MSE, the loss is minimized by predicting 0.0 everywhere. The network will happily do this and report a "95%+ accuracy" metric.

**Why it happens:** The default losses in `segmentation_models_pytorch` are fine for balanced tasks. Remote-sensing semantic segmentation is rarely balanced. Teams copy-paste the tutorial loss and move on.

**Consequences:** At 25 epochs, model outputs all-zero masks. Demo shows an empty map. No false positives, no true positives — no detections. Recoverable only by re-training with corrected loss, which costs another 60–90 min on Kaggle T4 — if you have GPU budget left.

**Warning signs:**
- First-epoch train loss drops to a tiny value instantly (< 0.05 when it should be ~0.3).
- Dice loss stays at ~1.0 (perfect mismatch) even as BCE drops.
- On val, predicted mask `.sum()` ≈ 0 for every patch.

**Prevention:**
- Use **Dice loss + weighted BCE** summed: `loss = 1.0 * dice(pred, mask) + 0.5 * bce_weighted(pred, mask)`.
- Positive-class weight for BCE: set to `(N_negative / N_positive)` computed on training set → typically 30–60x.
- Or use Focal Loss with γ=2.0 (common in Sentinel-2 debris papers).
- Prefer class-frequency weighting over batch-normalized weighting because the denominator varies across tiles.
- Smoke test after epoch 1: compute `(pred > 0.5).sum() / total_pixels`. If < 0.1%, stop and fix the loss.

**Phase:** **Phase 3** — real training only. But the loss design must be pre-committed before the Kaggle run starts, because mid-run loss tweaks cost an entire GPU-hour budget.

**Confidence:** HIGH — [Frontiers 2026 cross-dataset MARIDA/MADOS study](https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2026.1765021/full) explicitly recommends "composite imbalance-aware loss and rarity-aware sampling"; [MARIDA PLoS ONE paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0262247) uses inverse-frequency class weighting.

---

### C4. CRS Unit Confusion in Lagrangian Tracker (lon/lat degrees vs. UTM meters)

**What goes wrong:** CMEMS currents and ERA5 winds are given in m/s. The particle tracker needs to integrate position. If position is stored in lon/lat degrees and the naive update `lon += u * dt` is applied, a 0.5 m/s eastward current moves a particle 0.5 degrees in one second — roughly 55 km at the equator, 20× too fast.

**Why it happens:** Intuitive Python: "degrees are the units of coordinates." Wrong — meters-per-second does not divide into degrees without a conversion factor that depends on latitude.

**Consequences:** 72-hour trajectories cross continents. Particles beach in the Himalayas. The verification test in PRD §15 ("0.5 m/s eastward → 43.2 km in 24 h") fails by orders of magnitude. Unit test catches it if written; without the test, the bug goes undetected until demo.

**Warning signs:**
- 24-hour particle displacement measured in *degrees*, not km.
- Final positions land outside any ocean basin.
- Test-synthetic "43.2 km in 24 h" integrator asserts `assert abs(dx_km - 43.2) < 0.5` and fails by a factor of 100+.

**Prevention — two acceptable approaches:**

**A. Integrate in UTM meters, convert for display only (preferred):**
```python
from pyproj import Transformer
# Compute local UTM zone once for the AOI
to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:326{utm_zone:02d}", always_xy=True)
to_wgs = Transformer.from_crs(f"EPSG:326{utm_zone:02d}", "EPSG:4326", always_xy=True)
x_m, y_m = to_utm.transform(lon, lat)
x_m += u_c * 3600          # dt=1 hr = 3600 s
y_m += v_c * 3600
lon, lat = to_wgs.transform(x_m, y_m)
```

**B. Degree-based with explicit conversion:**
```python
m_per_deg_lat = 111_320.0
m_per_deg_lon = 111_320.0 * np.cos(np.deg2rad(lat))
lon += (u_total * 3600) / m_per_deg_lon
lat += (v_total * 3600) / m_per_deg_lat
```

Then validate with PRD §15 synthetic test: uniform `u=0.5 m/s, v=0`, integrate for 24 h, assert `displacement_km ∈ [43.1, 43.3]`.

**Phase:** **Phase 2** — before any real CMEMS data is plugged in. Write the unit test FIRST, let it fail, then implement.

**Confidence:** HIGH — [pyproj Transformer docs](https://pyproj4.github.io/pyproj/stable/api/transformer.html); corroborated by Parcels (the reference Lagrangian framework) documentation.

---

### C5. Detection GeoJSON Schema Drift Between Phase 1 (Dummy) and Phase 3 (Real)

**What goes wrong:** Phase 1 ships a dummy `run_inference` returning `{conf_raw, conf_adj, fraction_plastic, area_m2, age_days_est, class}` with hand-filled plausible values. Phase 3 starts, the trained model actually needs `conf_raw` to come from a sigmoid, `fraction_plastic` to come from a regression head, `age_days_est` to come from somewhere — and the implementer quietly renames a key to `age_days` "for consistency." Every downstream consumer (tracker, planner, the existing FastAPI mock in `backend/services/mock_data.py`) silently breaks.

**Why it happens:** Schemas look like suggestions during a fast build. They are not. PRD §Appendix B and `.planning/codebase/CONCERNS.md` both already flag that the existing mock schema doesn't match the PRD schema — this pitfall is already materialized once in this repo.

**Consequences:** Tracker crashes with `KeyError: 'conf_adj'` 30 min before demo. Worse: silent fallback to a default value (e.g., `.get('conf_adj', 1.0)`) masks the bug during dev and shows wrong confidences during judging Q&A.

**Warning signs:**
- Any rename in `backend/ml/inference.py` during Phase 3.
- Two files refer to the same field by different names (`age_days` vs `age_days_est`).
- `mock_data.py` and `inference.py` drift out of sync.

**Prevention:**
1. **Freeze the schema in Phase 1** as a Pydantic model:
```python
# backend/ml/schema.py
from pydantic import BaseModel, Field
class DetectionProperties(BaseModel):
    conf_raw: float = Field(ge=0, le=1)
    conf_adj: float = Field(ge=0, le=1)
    fraction_plastic: float = Field(ge=0, le=1)
    area_m2: float = Field(gt=0)
    age_days_est: int = Field(ge=0)
    class_: str = Field(alias="class")
```
2. Use it to validate output of every stage:
```python
for feat in geojson["features"]:
    DetectionProperties(**feat["properties"])  # raises on drift
```
3. Add a one-line regression test: `test_schema_frozen.py` runs both dummy and real inference through the validator.
4. **Update `mock_data.py` in Phase 1** to match the frozen schema so the fallback demo path doesn't use stale field names.

**Phase:** **Phase 1** — schema freeze is an explicit exit criterion. Enforce with a `.planning/milestones/.../contracts/detection_schema.json` that lives in git.

**Confidence:** HIGH — Already identified in `.planning/codebase/CONCERNS.md` as tech debt; PRD §Key Decisions row 8 calls it out as a hard freeze point.

---

### C6. Kaggle Kernel GPU Disabled (Current Project Default)

**What goes wrong:** `kaggle.yml` currently has `enable_gpu: false` (stated in `.planning/PROJECT.md` Key Decisions). If Phase 3 training kicks off without first flipping this, the Kaggle kernel runs on CPU. A 25-epoch UNet++ that takes 90 min on T4 will take 12–18 hours on CPU, exceeding the 9-hour session timeout before a single epoch completes.

**Why it happens:** Kaggle's `kernel-metadata.json` respects the repo-committed value; toggling it requires either editing the YAML or using the web UI before run. "I thought it was on by default" is the failure mode.

**Consequences:** Discovered 2 hours into a Phase 3 run that the model is training at 1/100th speed. Phase 3 compute budget destroyed. Fall back to the pretrained `marccoru/marinedebrisdetector` weights only — the 25-epoch fine-tuning story for judges is gone.

**Warning signs:**
- Kaggle notebook shows "CPU" under accelerator.
- Epoch 1 elapsed time > 10 minutes on batch size 16.
- `torch.cuda.is_available()` returns False in a notebook cell.

**Prevention:**
1. First cell of Phase 3 notebook:
```python
import torch, sys
assert torch.cuda.is_available(), "GPU NOT ENABLED — stop and flip kaggle.yml enable_gpu: true"
print(f"GPU: {torch.cuda.get_device_name(0)}, VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
```
2. Set `enable_gpu: true` in `kaggle.yml` before H+24 (Phase 3 ramp-up).
3. Add a 5-epoch smoke run early in the session to confirm time-per-epoch is ~3 min, not 30 min.
4. **Checkpoint every epoch** to `/kaggle/working/model_epoch_N.pth` — if the 9-hour limit hits mid-training, a later session can resume.

**Phase:** **Phase 3** — but the YAML flip must be done before the Phase 3 kickoff, so it's really a late-Phase-2 preparation task.

**Confidence:** HIGH — [Kaggle docs: efficient GPU usage](https://www.kaggle.com/docs/efficient-gpu-usage), [Kaggle kernel session timeout = 9 hours](https://www.kaggle.com/general/202701), weekly GPU cap ~30 h.

---

### C7. Live Demo Laptop Crashes / Docker / CUDA Headaches

**What goes wrong:** Demo laptop runs the full stack (model + tracker + planner + any late FastAPI wire-up). Five minutes before presentation, one of: GPU driver mismatch, CUDA version conflict after a fresh pytorch install, Docker Desktop stuck updating, Windows forcing a reboot. Entire demo nuked.

**Why it happens:** Hackathons reward "works on my machine" thinking until it doesn't. CUDA/pytorch version coupling is notoriously fragile (pytorch 2.x requires CUDA 11.8 or 12.1; nvidia-smi showing 12.4 doesn't mean 12.4 is what torch sees).

**Consequences:** PRD §16 explicitly lists this as Low-likelihood / Critical-impact. The mitigation (pre-recorded fallback video, static precomputed cache) must exist — or the demo is dead.

**Warning signs:**
- Late pytorch upgrade within 6 hours of demo.
- New CUDA install within 12 hours of demo.
- Docker Compose unused until the morning of demo.
- "I'll figure out the environment later" attitude.

**Prevention:**
1. **Freeze the runtime environment at H+32.** No new `pip install`, no `apt upgrade`, no `docker pull` after H+32.
2. **Precompute all 4 AOI responses by H+28** and commit as static JSON: `data/precomputed/{aoi}_detections.geojson`, `{aoi}_forecast.geojson`, `{aoi}_mission.gpx`. Demo code can fall back to these if inference fails.
3. **Record a 60-second screen capture** of a successful end-to-end run at H+36. Play it if live breaks.
4. **Avoid Docker for Phase 3 intelligence layer.** Run on Python venv. Docker is for the future integration milestone, not this scope.
5. **Pin the torch version:** `torch==2.3.1+cu121` or whatever the Kaggle kernel exports, and install locally with the matching `--index-url https://download.pytorch.org/whl/cu121`.

**Phase:** **Phase 3** polish (H+32 onwards). Do NOT wait until H+46.

**Confidence:** HIGH — PRD §16 row 5 calls it out; [Kaggle output 20 GB limit](https://www.kaggle.com/docs/efficient-gpu-usage) affects checkpoint transfer.

---

## Moderate Pitfalls

Mistakes that eat 1–4 hours if not anticipated.

### M1. Sentinel-2 Band Resolution Mismatch (B1/B9 @ 60m, B5–B7/B8A/B11/B12 @ 20m, B2–B4/B8 @ 10m)

**What goes wrong:** Stacking 11 Sentinel-2 bands into a single `(11, H, W)` tensor without resampling throws a shape mismatch. Or worse: silent broadcasting / padding that puts B11 (SWIR) values in the wrong spatial cells. MARIDA ships pre-resampled patches to 10 m; local staged tiles may not be.

**Why it happens:** Native S2 L2A COGs preserve original resolution per band. Rasterio reads each band in its native grid. The 9-channel feature stack assumed in the model needs all bands on one grid.

**Consequences:** Model throws on first forward pass; or, if silently reshaped, learns garbage because B11 values are misaligned by 10 m. Biermann FDI formula (`B8 vs. B6 vs. B11`) produces pure noise.

**Warning signs:**
- `ValueError: all input arrays must have the same shape` on `np.stack`.
- FDI output has a regular grid pattern (indicates resampling aliasing).
- A pure water pixel shows high NDVI (indicates band misregistration).

**Prevention:**
```python
# backend/ml/features.py — resample once, to 10 m, with Rasterio warp
from rasterio.enums import Resampling
def resample_to_10m(band_path, ref_transform, ref_shape):
    with rasterio.open(band_path) as src:
        out = np.empty(ref_shape, dtype="float32")
        rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=out,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=ref_transform, dst_crs=src.crs,
            resampling=Resampling.bilinear,
        )
    return out
```
Use B2 (10 m) as reference grid. Resample all other bands (B1, B5, B6, B7, B8A, B9, B11, B12) to B2's transform. Save the stacked result as a single 11-band COG for downstream.

**Phase:** **Phase 1** — feature stack must be correct before the dummy model runs.

**Confidence:** HIGH — [Sentinel-2 Spatial Resolutions (ESA)](https://sentinel.esa.int/web/sentinel/user-guides/Sentinel%202-msi/resolutions/spatial), [rasterio resampling docs](https://rasterio.readthedocs.io/en/stable/topics/resampling.html).

---

### M2. Particles Crossing Land (No Beaching Logic)

**What goes wrong:** CMEMS currents near coastlines have fill values (NaN or -32767) at land pixels. Bilinear interpolation over the coast gives spurious extrapolated velocities that fling particles inland, or — with xarray's default behavior — returns NaN, causing `x += NaN * dt` and the particle's position becomes NaN forever.

**Why it happens:** Open-ocean particle-tracker tutorials assume no coastline. Real AOIs (Gulf of Mannar, Mumbai offshore) have coastlines in every direction.

**Consequences:** 72-hour forecast shows half the particles in Rajasthan or the Western Ghats. KDE density polygons cover land. Judge Q&A: "Why are your plastic patches over Mumbai airport?"

**Warning signs:**
- Any particle final-position longitude/latitude is outside the AOI bounding box.
- Particles' NaN count grows with each timestep.
- Density heatmap has bright pixels far from any water body.

**Prevention:**
1. **Detect land at interpolation:** if `np.isnan(u) or np.isnan(v)`, the particle is on land — freeze it (beached):
```python
u, v = interp_currents(x, y, t)
if np.isnan(u) or np.isnan(v):
    path.append((x, y, t, "beached"))
    continue   # skip the update
```
2. **Mask the density KDE** with a coastline polygon (Natural Earth 10 m coastline) before rasterizing — intersect the KDE polygons with the ocean polygon so land fringes are trimmed.
3. **Initial-position sanity check:** on seeding, assert every particle is inside the ocean mask.

**Phase:** **Phase 2** — tracker implementation. Ship a basic "beach on NaN" approach; coastline-intersect polishing only if ahead of schedule.

**Confidence:** MEDIUM — Parcels documentation [describes the impermeable-at-coast behavior](https://arxiv.org/pdf/1707.05163) but our minimal Euler integrator doesn't implement it. Our strategy is the documented workaround.

---

### M3. CMEMS / ERA5 Time-Axis Misalignment

**What goes wrong:** CMEMS surface currents are hourly with timestamps at the top of each hour (UTC). ERA5 winds are hourly with timestamps at the top of each hour (UTC) — but ERA5 is released with a 5-day lag and the "current analysis" vs. "forecast" fields differ. If you request `ERA5 u10 at 2026-04-15T14:00` but the underlying NetCDF only has values up to 2026-04-10, you get NaN. Worse: if the CMEMS slice and the ERA5 slice don't cover the same `(tmin, tmax)` window, the tracker runs off the edge of one field while the other still has valid data.

**Why it happens:** Academic ocean-modeling tutorials use synthetic or pre-clipped data. Real downloads have different temporal extents.

**Consequences:** Mid-forecast, `interp_winds` returns NaN → windage term is NaN → positions become NaN → same failure mode as M2.

**Warning signs:**
- `ds.time.min()` differs between currents and winds NetCDFs.
- Forecast "works" for +0h to +48h but fails at +72h.
- Any timestamp in the tracker loop doesn't exist in either dataset.

**Prevention:**
```python
# backend/physics/env_data.py
t_start = max(ds_currents.time.min(), ds_winds.time.min())
t_end   = min(ds_currents.time.max(), ds_winds.time.max())
assert (t_end - t_start) >= np.timedelta64(72, 'h'), \
    f"Env coverage too short: {t_start} to {t_end}"
# clip the forecast horizon to available data
forecast_hours = min(72, int((t_end - detection_time) / np.timedelta64(1, 'h')))
```
Also: request CMEMS + ERA5 with a 7-day window centered on the demo tile acquisition date, not a 72-hour window.

**Phase:** **Phase 2** — env_data.py loader.

**Confidence:** HIGH — [CMEMS PUM documentation](https://documentation.marine.copernicus.eu/PUM/CMEMS-GLO-PUM-001-031.pdf), [ERA5 CDS dataset page](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download) (ERA5 has a 5-day release lag + 2-month ERA5T→ERA5 finalization lag).

---

### M4. CMEMS Longitude Convention (0–360 vs. −180–180)

**What goes wrong:** Some legacy CMEMS products use longitude in [0, 360) while newer ARCO/NetCDF outputs use [−180, 180). If your AOI is in the Indian Ocean (lon ~72–90°E) both conventions work — but Arabian Sea gyre extends to ~45°E, Gulf of Mannar is ~78°E, and if you ever extend demo AOIs westward you'll cross either the 0° or 180° meridian and one convention will give empty slices.

**Why it happens:** CMEMS documentation explicitly states: "Original CMEMS datasets use a mix of [0, 360[ and [−180, 180[ longitude intervals." The ARCO format standardizes to [−180, 180), but legacy NetCDF may not.

**Consequences:** `ds.sel(longitude=slice(-180, 180))` returns empty for a [0, 360)-formatted dataset. Tracker seeds with no currents. Silent failure → particles don't move → forecast shows static dots.

**Warning signs:**
- `ds.longitude.min() >= 0 and ds.longitude.max() > 180` means 0–360 convention.
- Your AOI bbox is in [−180, 180) and subset returns empty.
- Currents have all zeros near your seed points but nonzero elsewhere.

**Prevention:**
```python
# backend/physics/env_data.py
def normalize_lon(ds):
    if ds.longitude.min() >= 0 and ds.longitude.max() > 180:
        # convert 0-360 to -180-180
        ds = ds.assign_coords(longitude=(((ds.longitude + 180) % 360) - 180))
        ds = ds.sortby("longitude")
    return ds
```
Also: log `ds.longitude.min(), ds.longitude.max()` on load. Eyes on the numbers once per session.

**Phase:** **Phase 2**.

**Confidence:** HIGH — [CMEMS docs on ARCO/NetCDF differences](https://help.marine.copernicus.eu/en/articles/8656000-differences-between-netcdf-and-arco-formats), [ECMWF confluence on longitude conversion](https://confluence.ecmwf.int/display/CUSF/Longitude+conversion+0~360+to+-180~180).

---

### M5. Windage Applied to Wrong Vector Component

**What goes wrong:** The formula `v_total = v_current + α * v_wind` requires both vectors in the same reference (both in m/s, both in map-east-north or both in geographic lon-lat velocity components). A classic bug is applying windage to ERA5 `u10 / v10` (which are meteorological, with v positive northward — standard) but accidentally using CMEMS `uo / vo` in a rotated grid (some regional CMEMS products use curvilinear coordinates where u/v are grid-aligned, not east/north).

**Why it happens:** The global CMEMS product (GLORYS) is on a regular lat-lon grid with u=east, v=north. But regional nested models sometimes aren't. Teams copy the formula and don't check.

**Consequences:** Particles drift in a consistent but wrong direction (e.g., 10° off true current). 72-hour forecast error doubles. May be invisible in demo but catastrophic in the validation test against a drifter buoy (PRD §15).

**Warning signs:**
- CMEMS NetCDF has a `grid_mapping` attribute other than `latitude_longitude`.
- Variable names like `u_component` or `velocity_zonal` without explicit east/north docs.
- Drift direction rotates systematically vs. wind direction.

**Prevention:**
1. Use ONLY the CMEMS Global Physics Analysis and Forecast (GLOBAL_ANALYSISFORECAST_PHY_001_024 or newer) — regular 1/12° lat-lon grid, u=east, v=north, units m/s.
2. Verify on load: `assert ds.uo.attrs.get("standard_name") == "eastward_sea_water_velocity"`.
3. Same check for ERA5: `assert ds.u10.attrs.get("standard_name") == "eastward_wind"`.
4. Synthetic test: wind at (u10=10 m/s, v10=0) applied with α=0.02 should displace particles eastward, not in any other direction.

**Phase:** **Phase 2**.

**Confidence:** HIGH — [CMEMS Global PUM](https://documentation.marine.copernicus.eu/PUM/CMEMS-GLO-PUM-001-024.pdf), CF-conventions `standard_name` registry.

---

### M6. Cloud-Contaminated Pixels Treated as Ocean (SCL Mask Misuse)

**What goes wrong:** Sentinel-2 L2A includes an SCL (Scene Classification Layer) band with values 0–11. Clouds are values 8, 9, 10 (medium, high, thin cirrus); cloud shadows are 3; snow/ice 11; unclassified 7. Teams either (a) skip SCL entirely and feed cloudy pixels to the model — clouds have high NIR reflectance and look like plastic to a naive detector, (b) use an incorrect threshold like "SCL ≥ 8" which misses shadows and cirrus, or (c) use the wrong SCL band (L1C products don't have one).

**Why it happens:** SCL is underdocumented in most tutorials. The "easy" path of skipping it produces visually passable outputs that are wrong.

**Consequences:** Demo shows dozens of "plastic" detections over a cloud bank. Judges visibly skeptical. Precision collapses.

**Warning signs:**
- High-confidence detections concentrated in bright patches visible in true-color.
- Detection density correlates with cloud cover percentage.
- Demo tile SCL band is missing or all zeros.

**Prevention:**
```python
# backend/ml/features.py
CLOUD_VALUES = {3, 7, 8, 9, 10, 11}  # shadows, unclass, clouds(med/high/cirrus), snow
scl = rasterio.open(scl_path).read(1)
cloud_mask = np.isin(scl, list(CLOUD_VALUES))
# Either: nodata the cloudy pixels before inference
features[cloud_mask, :] = np.nan
# Or: zero out detections post-hoc
pred[cloud_mask] = 0.0
```
For the 4 demo AOIs, **pre-select tiles with <10% cloud cover** during the staging phase so this pitfall mostly doesn't bite at demo time.

**Phase:** **Phase 1** — feature engineering. Even with pretrained weights, cloud contamination will show.

**Confidence:** HIGH — [Sentinel Hub SCL script](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/scene-classification/), [GEE Harmonized S2 L2A catalog entry](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED).

---

### M7. Biofouling Augmentation Teaching the Wrong Direction

**What goes wrong:** The intent is: plastic's NIR signal decays as biofilm accumulates → augmentation multiplies B8 (NIR) and B6 (RedEdge) by a factor in [0.5, 1.0] on 40% of positive samples. The model should learn "even with lower NIR, this is still plastic." But a common bug: apply the augmentation factor to *every* band or to *water* pixels too. The model then learns "plastic is distinguished by low NIR" — opposite of what's true for fresh plastic (high NIR relative to water).

**Why it happens:** Augmentation pipelines typically apply transforms to the whole sample, not just to masked positive pixels.

**Consequences:** Model predicts plastic wherever NIR is low — including Sargassum (which has high NIR) as NOT plastic (good) but also dark water, shadowed areas, and foam (bad).

**Warning signs:**
- Predicted plastic correlates inversely with NIR brightness across the tile.
- Fresh floating-debris patches (high NIR) are missed.
- Sargassum false-positive rate is low but water false-positive rate is high.

**Prevention:**
```python
# backend/ml/dataset.py
def augment_biofouling(sample, mask, probability=0.4):
    if random.random() < probability:
        age_factor = random.uniform(0.5, 1.0)
        # Apply ONLY where plastic is present
        plastic_pixels = (mask == 1)
        for band_idx in [NIR_IDX, REDEDGE2_IDX]:   # B8, B6
            sample[band_idx][plastic_pixels] *= age_factor
        sample['age_days'] = int((1.0 - age_factor) * 60)
    return sample, mask
```
Also: log the augmentation factor distribution; the mean should cluster toward 0.75, not 0.0 or 1.0.

**Phase:** **Phase 3** — dataset/training. Trivially add a unit test: augment a sample with mask of all zeros → bands must be unchanged.

**Confidence:** MEDIUM — Derived from PRD §8.4 and general augmentation best-practice. The bug mode is plausible from how `segmentation_models_pytorch` augmentation pipelines work by default.

---

### M8. Sub-Pixel Fraction MSE Loss Collapsing to Zero

**What goes wrong:** The regression head predicts `fraction_plastic ∈ [0, 1]`. Synthetic mixing labels are mostly small (most mixed pixels have fraction ∈ {0.05, 0.1, 0.2}) and most non-plastic pixels have fraction = 0. MSE loss is minimized by predicting a constant near the mean, which is near 0. The model appears to regress but the output is effectively a constant ~0.02 everywhere.

**Why it happens:** Same mechanism as C3 — imbalanced targets + unconstrained MSE → trivial constant-solution minimum.

**Consequences:** `fraction_plastic` in output GeoJSON is always ~0.02. Downstream consumer (mission planner weighting by fraction) treats all hotspots as equal density → greedy TSP degenerates to geographic proximity only.

**Warning signs:**
- Val MSE is low (say 0.003) but correlation between predicted and true fractions is near 0.
- Histogram of predicted `fraction_plastic` is a tight spike near 0.02.
- `fraction_plastic` does not discriminate between MARIDA's 10% vs 40% synthetic-mix labels.

**Prevention:**
1. **Only compute the regression loss on positive pixels** (where mask == 1). Let the binary head handle the plastic-vs-not-plastic decision; let the regression head handle "how much."
```python
loss_reg = F.mse_loss(pred_frac[mask==1], true_frac[mask==1])
loss = 1.0 * loss_binary + 0.5 * loss_reg
```
2. Consider log-transformed target: `log(fraction + 1e-3)` to balance the dynamic range.
3. Verify: Pearson correlation between predicted and true fraction on val set ≥ 0.5.

**Phase:** **Phase 3**.

**Confidence:** MEDIUM — Analogous to the C3 failure mode, observed in [Tandfonline 2022 sub-pixel unmixing paper](https://www.tandfonline.com/doi/full/10.1080/2150704X.2022.2088253) for regression heads.

---

### M9. Rasterio Polygonization: Tiny Specks, Invalid Geometries, Missing CRS

**What goes wrong:** After `rasterio.features.shapes(mask > 0.5)`, the output includes:
- 1-pixel and 2-pixel "specks" that produce degenerate polygons — not GeoJSON-invalid, but noise.
- Diagonal-only-connected pixels (connectivity=8) create self-intersecting polygons that fail `shapely.is_valid()`.
- The returned geometries have no CRS attached — GeoPandas or downstream JSON thinks they're in EPSG:4326 when they're actually in the tile's native UTM.

**Why it happens:** `shapes()` is a raw conversion. It does not filter small features, does not guarantee validity, does not attach CRS metadata.

**Consequences:** GeoJSON output has 500+ features, most 100 m² garbage. Mapbox renders as noise. Some polygons throw on `mapping()` serialization. Downstream `area_m2` computation wrong because geometries are in pixel space when the code assumed meters.

**Warning signs:**
- `len(features) > 200` for a single AOI (should be <50 for meaningful hotspots).
- `shapely.Polygon(coords).is_valid` returns False for some features.
- `area_m2` values are either extremely large (indicating degree-space) or unrealistically small.

**Prevention:**
```python
# backend/ml/inference.py
from rasterio.features import shapes
from shapely.geometry import shape
MIN_AREA_M2 = 200.0   # two S2 pixels; tune to AOI scale

polygons = []
for geom_dict, val in shapes(mask.astype("uint8"), mask=(mask > 0.5), transform=tile_transform, connectivity=4):
    poly = shape(geom_dict)
    if not poly.is_valid:
        poly = poly.buffer(0)   # fix self-intersections
    if poly.is_valid and poly.area >= MIN_AREA_M2:
        polygons.append(poly)

gdf = gpd.GeoDataFrame(geometry=polygons, crs=tile_crs)
gdf = gdf.to_crs("EPSG:4326")   # reproject before GeoJSON export
```
Key choices:
- `connectivity=4` not 8 (fewer self-intersections, [rasterio 8-connectivity known issue](https://github.com/rasterio/rasterio/issues/2244)).
- `.buffer(0)` to fix self-intersections ([standard workaround](https://github.com/rasterio/rasterio/issues/1126)).
- Explicit `crs=` assignment on the GeoDataFrame.
- `to_crs("EPSG:4326")` before dump — GeoJSON standard is lat-lon.
- `area_m2` computed in projected CRS, not EPSG:4326: `poly_utm = poly_wgs84.to_crs(utm_crs); area_m2 = poly_utm.area`.

**Phase:** **Phase 1** — polygonization is part of the dummy inference output path.

**Confidence:** HIGH — [Rasterio features module docs](https://rasterio.readthedocs.io/en/stable/api/rasterio.features.html), multiple documented issues in rasterio repo.

---

### M10. Greedy TSP Edge Cases (Singleton, No-Route, Range Overflow)

**What goes wrong:** `plan_mission(detections, vessel_range_km, hours, origin_lonlat)` with a greedy-nearest-neighbor TSP breaks in several ways:
- **Singleton hotspots:** if only one detection exists, the "TSP" returns `[origin, hotspot, origin]` — or worse, `[hotspot]` alone — depending on how the code handles n=1. Downstream GPX export may produce a zero-length route.
- **No-route case:** every detection is outside `vessel_range_km`. What does the planner return — empty waypoints? Error? User confusion.
- **Range overflow:** greedy nearest-neighbor doesn't respect a cumulative range budget. It picks the nearest next hotspot even if that commits the vessel to exceeding its range on the return.
- **Zero detections:** `plan_mission([], ...)` — division-by-zero on priority score.

**Why it happens:** Tutorials show TSP on 10+ cities without constraints. Real ops have N ∈ {0, 1, 2+} and a range budget.

**Consequences:** Demo modal shows "NaN waypoints" or crashes. Or vessel plan shows a route longer than the stated range — judge calls it out.

**Warning signs:**
- Empty test AOI produces a traceback.
- A demo AOI with 1 detection produces a visibly wrong route.
- Total route length > `vessel_range_km`.

**Prevention:**
```python
# backend/mission/planner.py
def plan_mission(detections, vessel_range_km, hours, origin):
    if len(detections) == 0:
        return {"waypoints": [], "route": None, "summary": "No detections in range."}

    # Filter: only hotspots reachable one-way
    reachable = [d for d in detections if haversine_km(origin, d["centroid"]) <= vessel_range_km / 2.0]
    if len(reachable) == 0:
        return {"waypoints": [], "route": None, "summary": f"All detections > {vessel_range_km/2} km from origin."}

    if len(reachable) == 1:
        return {"waypoints": [origin, reachable[0]["centroid"], origin], "route": line, "summary": "Single hotspot run."}

    # Greedy nearest-neighbor with cumulative range budget
    visited = [origin]
    budget_km = vessel_range_km
    remaining = list(reachable)
    while remaining:
        last = visited[-1]
        # Consider only next hops that still allow return to origin
        candidates = [(d, haversine_km(last, d["centroid"]) + haversine_km(d["centroid"], origin)) for d in remaining]
        candidates = [c for c in candidates if c[1] <= budget_km]
        if not candidates:
            break   # budget exhausted
        next_d = min(candidates, key=lambda c: haversine_km(last, c[0]["centroid"]))[0]
        visited.append(next_d["centroid"])
        budget_km -= haversine_km(last, next_d["centroid"])
        remaining.remove(next_d)
    visited.append(origin)   # return to base
    return {"waypoints": visited, ...}
```
Edge case tests (five lines each): `test_zero_detections`, `test_singleton`, `test_all_out_of_range`, `test_budget_exhausted_mid_route`, `test_single_port`.

**Phase:** **Phase 3** — mission planner.

**Confidence:** HIGH — [NetworkX greedy_tsp docs](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.approximation.traveling_salesman.greedy_tsp.html); the budget-aware modification is a standard CVRP-style constraint.

---

### M11. Val/Test Split Contamination from Synthetic Mixing

**What goes wrong:** Synthetic sub-pixel mixing training (PRD §8.3) blends pure-plastic pixels with water pixels to create training samples with known fractions. If the pure-plastic pixels come from MARIDA scene X, and scene X also appears in MARIDA's val split, the model has effectively seen val-scene pixels during train — val IoU is inflated.

**Why it happens:** MARIDA's split files partition by scene ID, but the synthetic-mixing library doesn't know which scenes are train vs. val. A team member writes a quick mixing loop over all pure-plastic samples without filtering.

**Consequences:** Val IoU looks great (0.5+) during training. Real test performance on unseen tiles is 0.2. Model doesn't generalize; bug discovered in the last hour.

**Warning signs:**
- Val IoU trajectory looks too smooth / too good.
- Train and val IoU are within 0.05 of each other (should be gap of 0.1–0.2).
- Model performs worse on the 4 demo tiles than on val.

**Prevention:**
```python
# backend/ml/dataset.py — enforce split-awareness in mixing
train_scenes = set(open("MARIDA/splits/train_X.txt").read().splitlines())
def generate_synthetic_mixed_pixel(plastic_source_patch_id, water_source_patch_id):
    assert plastic_source_patch_id.split('_')[0] in train_scenes, \
        f"Leaking scene {plastic_source_patch_id} into synthetic training"
    # ... mix ...
```
Also: before training, assert `set(train_scenes) & set(val_scenes) == set()`.

**Phase:** **Phase 3**.

**Confidence:** MEDIUM — Best-practice; specific to synthetic-augmentation designs. MARIDA split files use scene-level disjoint sets, so the risk is entirely in how sub-pixel mixing is implemented.

---

### M12. Model Checkpoint Transfer Kaggle → Laptop

**What goes wrong:** Phase 3 trains on Kaggle. The resulting `.pth` file is in `/kaggle/working/`. Options for moving to the demo laptop:
- **Kaggle output download:** files <20 GB, but downloading a 150 MB checkpoint through the Kaggle web UI is slow and requires the notebook to have been "committed" (saved as a new version).
- **Commit to GitHub:** checkpoint > GitHub's 100 MB file limit; requires LFS or Release attachment.
- **Save as Kaggle Dataset:** can be done from the kernel, but private dataset → need auth on laptop to download.

Naive approach: just commit `model.pth` to the repo → push fails with "file too large." Team spends 30 min learning git-lfs under deadline.

**Why it happens:** Kaggle workflow is notebook-centric; getting artifacts out to a specific laptop is awkward.

**Consequences:** Phase 3 training completes at H+30, but the weights aren't on the demo laptop until H+33 (or worse). Integration window shrinks.

**Warning signs:**
- Final notebook cell says "training done" but you have no file locally.
- `git push` fails with a size error.
- Kaggle "Output" tab shows files but download is slow/unclear.

**Prevention:**
1. **Save as Kaggle Dataset from within the notebook** at end of training:
```python
import os
os.makedirs("/kaggle/working/drift_model_weights", exist_ok=True)
torch.save(model.state_dict(), "/kaggle/working/drift_model_weights/drift_unetpp_v1.pth")
# Then use the Kaggle web UI to publish as a new dataset.
```
2. **OR GitHub Release attachment:** `gh release create v1 drift_unetpp_v1.pth` — GitHub Releases support up to 2 GB per file, with no LFS overhead.
3. **AND commit a small `weights_sha256.txt` to the repo** so the laptop can verify integrity of the downloaded file.
4. Use a well-known filename convention: `drift_unetpp_v{N}.pth`. Version bumps on every retrain.
5. Model weights do NOT go in git. Add `*.pth`, `*.ckpt` to `.gitignore` alongside `MARIDA/` (the repo's CONCERNS.md already flags MARIDA not being in .gitignore).

**Phase:** **Phase 3** — immediately after training completes.

**Confidence:** HIGH — [Kaggle Datasets + notebook outputs docs](https://www.kaggle.com/docs/datasets), [GitHub Releases file-size limits](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

---

## Minor Pitfalls

Low-impact but fast-to-prevent. 15-minute costs if unaddressed.

### mi1. `torch.hub.load("marccoru/marinedebrisdetector", "unetpp")` First-Run Download Cost & Offline Mode

**What goes wrong:** First call to `torch.hub.load(...)` downloads the repo + weights. On a Kaggle kernel with internet disabled (default for competitions, sometimes disabled on notebooks), this fails. On a demo laptop with spotty wifi, takes 2+ min and blocks the demo.

**Prevention:**
- Locally cache the hub download early (before demo) via `torch.hub.set_dir("./.torch_hub_cache")`.
- For Kaggle: enable internet in `kaggle.yml` (alongside `enable_gpu: true`) or pre-attach the marccoru repo as a Kaggle dataset.
- Include a `scripts/prefetch_marccoru.py` that pre-downloads before H+28.

**Phase:** **Phase 1**.

**Confidence:** HIGH — [torch.hub docs](https://docs.pytorch.org/docs/stable/hub.html).

---

### mi2. Python 3.13+ Breaks `shapely` / `geopandas` Wheels

**What goes wrong:** Running `pip install -r requirements.txt` on Python 3.13+ fails with "Failed to build shapely wheel." Already documented in `backend/README.md:8–11` and `.planning/codebase/CONCERNS.md`.

**Prevention:**
- Pin Python in `pyproject.toml`: `requires-python = ">=3.10,<3.13"`.
- Document in README.
- Add `.python-version` file (pyenv) or use a Python-version-matrix CI.

**Phase:** **Phase 1** (H0–H4 setup).

**Confidence:** HIGH — Already identified in-repo.

---

### mi3. MARIDA Directory Not in `.gitignore` (4.5 GB Accidental Push)

**What goes wrong:** `MARIDA/` at repo root, not ignored. A careless `git add .` adds 4 GB to the staging area. Push fails or succeeds-and-bloats-remote.

**Prevention:** Add `MARIDA/` and `**/.pth` to `.gitignore` immediately. Verified in `.planning/codebase/CONCERNS.md`.

**Phase:** **Phase 1**.

**Confidence:** HIGH.

---

### mi4. xarray Default "nearest" Interpolation on Curvilinear CMEMS Grids

**What goes wrong:** `ds.interp(longitude=lon, latitude=lat)` defaults to linear interpolation, which requires the underlying grid to be structured. For curvilinear regional products (less common; Arabian Sea specifically is covered by the global regular-grid GLORYS so this is minor for our AOIs), linear interp silently produces wrong values.

**Prevention:** Use CMEMS Global Physics product (GLOBAL_ANALYSISFORECAST_PHY_001_024), which is regular lat-lon. Don't use regional products unless explicitly verified.

**Phase:** **Phase 2**.

**Confidence:** MEDIUM.

---

### mi5. Confidence Decay `exp(-age/30)` Calibration Drift Between Phases

**What goes wrong:** Phase 1 dummy decay uses τ=30. Phase 3 real-age estimator says "all detections are 15 days old" (or whatever the regressor learned). `conf_adj = conf_raw * exp(-15/30) = 0.61 * conf_raw` — a uniform 40% discount. This hides real variance.

**Prevention:**
- Cap estimated age at 45 days: `age_days_est = min(age_regressor_output, 45)`.
- Visualize `age_days_est` distribution in a notebook cell at end of Phase 3 to confirm it varies.
- Keep τ=30 as a named constant in `backend/ml/inference.py`; don't scatter magic numbers.

**Phase:** **Phase 3**.

**Confidence:** MEDIUM.

---

### mi6. deck.gl Frontend Polish Leaking Into Intelligence Scope

**What goes wrong:** Team member starts adding deck.gl particle animations "because it's the wow moment." This is explicitly out of scope for this milestone (PROJECT.md: frontend is a later milestone). Hours drained.

**Prevention:** Milestone guardrail. The intelligence layer's job ends at producing GeoJSON + GPX files. Visualization is the next milestone. Decline all frontend work until the three functions `run_inference`, `forecast_drift`, `plan_mission` pass the end-to-end smoke test.

**Phase:** All phases — scope enforcement.

**Confidence:** HIGH — explicit in `.planning/PROJECT.md`.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|-----------|
| **Phase 1: Dummy Inference + Schema Freeze** | Schema drift between dummy mock and real (C5). Cloud-contaminated tiles producing garbage (M6). S2 L2A offset bug (C1). Band resolution mismatch (M1). Polygonization artifacts (M9). | Pydantic schema validator; SCL mask applied up front; offset-aware reflectance loader; single 10 m reference grid for all bands; `.buffer(0)` + MIN_AREA_M2 filter on polygons. |
| **Phase 2: Trajectory Engine** | CRS unit confusion (C4). Particles beaching on land (M2). CMEMS/ERA5 time misalignment (M3). Longitude convention (M4). Windage to wrong component (M5). | UTM-meter integration; NaN-detect-and-freeze for beaching; time-axis coverage assertion at load; `normalize_lon` helper; verify `standard_name` attrs. Unit test: 0.5 m/s × 24h = 43.2 km ±1%. |
| **Phase 3: Training + Mission + Integration** | Confidence mask misuse (C2). Class imbalance collapse (C3). Kaggle GPU disabled (C6). Sub-pixel regression collapse (M8). Val contamination (M11). Biofouling augmentation wrong (M7). Checkpoint transfer (M12). Greedy TSP edge cases (M10). Demo crashes (C7). | Weighted loss with explicit nodata exclusion; Dice+weighted BCE; `torch.cuda.is_available()` assertion first cell; regression loss only on positive pixels; split-aware mixing; augmentation only on plastic-masked pixels; Kaggle Dataset or GitHub Release for weights; budget-aware greedy TSP with edge-case tests; precomputed fallback JSONs at H+28 + screen recording at H+36. |

---

## Summary — Highest-Leverage Preventions (ranked)

If the team can only do 5 things, do these:

1. **Pydantic schema validator enforced at every stage boundary** (C5) — prevents 1–3 hours of end-of-run integration pain.
2. **Offset-aware S2 L2A reflectance loader with PB metadata parsing** (C1) — the invisible bug that fakes model failure.
3. **UTM-meter Lagrangian integration with synthetic 43.2 km test** (C4) — single unit test catches the #1 physics bug.
4. **Kaggle GPU assertion as cell #1 + checkpoint per epoch** (C6) — saves the 9-hour training budget.
5. **Precomputed 4-AOI JSON fallback + 60s screen recording at H+36** (C7) — guarantees a demo even if the laptop dies.

If time permits, also:

6. Dice + weighted BCE loss with per-class frequency weights (C3).
7. MARIDA `_conf.tif` handled as "only labeled pixels contribute" (C2).
8. `buffer(0)` + MIN_AREA_M2 + explicit CRS on polygonization output (M9).
9. Budget-aware greedy TSP with 5 edge-case tests (M10).

---

## Sources

Primary documentation:
- [ESA Sentinel-2 Processing Baseline](https://sentinel.esa.int/web/sentinel/technical-guides/sentinel-2-msi/processing-baseline)
- [Sentinel-2 L2A Scene Classification Map (Sentinel Hub custom scripts)](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/scene-classification/)
- [Sentinel-2 Spatial Resolutions](https://sentinel.esa.int/web/sentinel/user-guides/Sentinel%202-msi/resolutions/spatial)
- [Rasterio features module 1.4.4](https://rasterio.readthedocs.io/en/stable/api/rasterio.features.html)
- [Rasterio resampling docs](https://rasterio.readthedocs.io/en/stable/topics/resampling.html)
- [pyproj Transformer docs](https://pyproj4.github.io/pyproj/stable/api/transformer.html)
- [CMEMS PUM Global Ocean Physics Analysis and Forecast](https://documentation.marine.copernicus.eu/PUM/CMEMS-GLO-PUM-001-031.pdf)
- [CMEMS NetCDF vs ARCO format differences](https://help.marine.copernicus.eu/en/articles/8656000-differences-between-netcdf-and-arco-formats)
- [ECMWF Confluence — Longitude conversion 0~360 to -180~180](https://confluence.ecmwf.int/display/CUSF/Longitude+conversion+0~360+to+-180~180)
- [ERA5 single-levels CDS page](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download)
- [Kaggle docs — efficient GPU usage](https://www.kaggle.com/docs/efficient-gpu-usage)
- [torch.hub docs](https://docs.pytorch.org/docs/stable/hub.html)

Authoritative academic/dataset sources:
- [MARIDA: A benchmark for Marine Debris detection from Sentinel-2 (PLoS ONE, Kikaki 2022)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0262247)
- [MARIDA Zenodo record (data + conf masks)](https://zenodo.org/records/5151941)
- [MarcCoru/marinedebrisdetector GitHub (pretrained weights, U-Net++ baseline)](https://github.com/MarcCoru/marinedebrisdetector)
- [Large-scale Detection of Marine Debris in Coastal Areas with Sentinel-2 (iScience 2023)](https://www.cell.com/iscience/fulltext/S2589-0042(23)02479-3)
- [Frontiers 2026 — Binary reformulation for marine debris detection, MARIDA/MADOS cross-validation](https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2026.1765021/full)
- [Parcels Lagrangian Ocean Analysis Framework paper](https://arxiv.org/pdf/1707.05163)

Infrastructure / operational:
- [ClearSKY — Sentinel-2 Scaling & Harmonization](https://clearsky.vision/knowledge/sentinel2-scaling-harmonization)
- [ClearSKY — Sentinel-2 Indices Cheat Sheet](https://clearsky.vision/knowledge/sentinel2-indices-cheatsheet)
- [Rasterio issue #2244 — 8-connectivity invalid geometries](https://github.com/rasterio/rasterio/issues/2244)
- [Rasterio issue #1126 — shapes() returns invalid geometries + `.buffer(0)` workaround](https://github.com/rasterio/rasterio/issues/1126)
- [NetworkX greedy_tsp algorithm reference](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.approximation.traveling_salesman.greedy_tsp.html)

Repo-internal context (already validated):
- `C:\Users\offic\OneDrive\Desktop\DRIFT\.planning\PROJECT.md`
- `C:\Users\offic\OneDrive\Desktop\DRIFT\.planning\codebase\CONCERNS.md`
- `C:\Users\offic\OneDrive\Desktop\DRIFT\PRD.md` §8, §15, §16

---

*PITFALLS audit: 2026-04-17*
