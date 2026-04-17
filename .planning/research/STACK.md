# Stack Research — DRIFT / PlastiTrack Intelligence Layer

**Domain:** Satellite marine-plastic detection (Sentinel-2 semantic segmentation) + Lagrangian ocean-drift forecasting (CMEMS currents + ERA5 winds), trained on Kaggle P100/T4 kernels
**Researched:** 2026-04-17
**Overall confidence:** HIGH for pinned core versions (PyTorch, SMP, rasterio, xarray verified against PyPI/release notes as of 2026-04-17); MEDIUM for Kaggle-runtime specifics (pre-installed package list moves weekly); MEDIUM for `marccoru/marinedebrisdetector` exact input spec (README confirms 12-channel, but band-order/normalization-scale is not cleanly documented in search results — must be verified by reading the repo's `hubconf.py` at kickoff).

---

## Recommended Stack

### Core Technologies (pin these in `backend/requirements.txt`)

| Technology | Version (pin) | Purpose | Why Recommended |
|------------|---------------|---------|-----------------|
| **Python** | `3.11.x` | Interpreter | **Sweet spot for Q2 2026.** `xarray>=2026.2.0` drops Python 3.9; `shapely 2.x`/`geopandas 1.x`/`rasterio 1.5.x` all ship cp311 wheels for Linux + Windows. 3.10 still works for PyTorch but is rapidly losing wheel coverage in the geospatial stack (xarray maintainers are on SPEC-0 cadence — 3.10 drop is imminent). 3.12 also works but on Kaggle the base image is conservative — stick to 3.11 to match the kernel. **Do NOT use 3.13+**: shapely/geopandas binary wheels on Windows are still patchy and the Kaggle image does not ship 3.13. [HIGH] |
| **PyTorch** | `torch==2.7.0+cu121` (local) / whatever Kaggle ships (currently `torch==2.7.x` with CUDA 12.1) | Deep-learning framework | PyTorch 2.7 (Apr 2025) is the last release with full, validated support for **both** P100 (compute capability 6.0) and T4 (7.5) — the two Kaggle GPUs. PyTorch 2.8+ starts dropping sm_60 in some CUDA wheels. `torch.compile`/Triton does NOT work on the P100 (Triton requires ≥7.0) — if the notebook gets a P100, `model = model.to("cuda")` only, no `torch.compile`. On T4 use `torch.cuda.amp.autocast(dtype=torch.float16)` — **bfloat16 is NOT supported on T4**; mixing that up is a classic silent-slowdown/NaN trap. [HIGH] |
| **torchvision** | `0.22.0` (matches `torch==2.7.0`) | Image I/O, pretrained backbones | Co-versioned with torch. Needed by SMP under the hood for the ResNet-18 encoder weights. Don't install separately with pip — let SMP or Kaggle pull the matched pair. [HIGH] |
| **segmentation-models-pytorch (SMP)** | `>=0.5.0,<0.6.0` (latest stable 2026) | UNet++ with pretrained ResNet-18 encoder | This is the lowest-friction path from "pip install" to "trained dual-head UNet++ on 14-channel Sentinel-2". `smp.UnetPlusPlus(encoder_name="resnet18", encoder_weights="imagenet", in_channels=14, classes=1)` is a one-liner. **Critical compatibility note below on `in_channels>4`.** Supports 500+ backbones via `timm` — a fallback to ResNet-50 or EfficientNet-B0 is a one-line swap if IoU stalls. [HIGH] |
| **rasterio** | `>=1.5.0,<1.6.0` | Sentinel-2 COG reading, GeoJSON polygonization from probability rasters | 1.5.0 (Jan 2026) requires GDAL 3.8+, which is bundled in the Linux/Mac wheels and works on Windows via the bundled GDAL in the cp311 wheel. `rasterio.features.shapes()` with `connectivity=8` is the standard way to go from a binary `(prob > threshold)` mask to a list of `(polygon, value)` pairs → `shapely.geometry.shape(p)` → `geopandas.GeoDataFrame` → `.to_json()` for GeoJSON. [HIGH] |
| **xarray** | `>=2026.2.0,<2027.0.0` | NetCDF I/O for CMEMS (u/v currents) + ERA5 (u10/v10 winds); bilinear interpolation at `(lon, lat, t)` | 2026 xarray has first-class `ds.interp(lon=..., lat=..., time=..., method="linear")` which is exactly the Lagrangian-tracker requirement. Works seamlessly with dask-backed lazy arrays from the `copernicusmarine` client if you decide to pull live data later. **Does NOT support Python 3.9/3.10** in 2026.2.0 — this is the critical version gate. [HIGH] |
| **netCDF4** | `>=1.7.2` | xarray backend for `.nc` files (CMEMS + ERA5) | Default engine for `xr.open_dataset(..., engine="netcdf4")`. h5netcdf is a faster alternative for large files but for our ~500MB demo NetCDFs the netcdf4 backend is battle-tested and handles CF conventions + calendar attributes from CMEMS correctly. [HIGH] |
| **NumPy** | `>=1.26,<2.0` — **strongly recommended**; `2.1+` possible but adds risk | Array ops under everything | NumPy 2.0 (Jun 2024) changed scalar precision and C-API. rasterio 1.5 and SMP support NumPy 2, but older NetCDF4/xarray combinations sometimes produce "inconsistent results" per the xarray team ("xarray<2024.7.0 with numpy>=2.0.0 leads to inconsistent results"). Kaggle's Q2-2026 image may be on NumPy 2.1 already; if so, upgrade xarray to `>=2026.2.0` and netCDF4 `>=1.7.2` together. For a local dev pin, `1.26.4` is the "no-drama" choice. [HIGH] |
| **SciPy** | `>=1.14,<1.18` | `scipy.interpolate.RegularGridInterpolator` (fallback if xarray `.interp` is too slow for 20 × 72 × N-detections particle queries) | Standard; already pulled as a transitive dep by SMP/rasterio. Use it only if the xarray-based interpolation is the hot-path bottleneck. [HIGH] |
| **Shapely** | `>=2.0,<3.0` | Polygon geometry, area_m2 computation, KDE polygon hulls | Shapely 2.x is the only version supported by `geopandas>=1.0`. Use `from shapely.geometry import shape, Polygon, Point, LineString`. [HIGH] |
| **GeoPandas** | `>=1.0,<1.2` | Spatial dataframe; GeoJSON serialization with CRS metadata | Used to emit the contract-frozen `FeatureCollection` out of `run_inference`. `gdf.to_json()` plus setting `gdf.crs = "EPSG:4326"` → ready-to-serve GeoJSON. 1.0 dropped PyGEOS — don't try to install the two side-by-side. [HIGH] |
| **pyproj** | `>=3.7` | CRS transformations (Sentinel-2 UTM tile → WGS84 for GeoJSON output) | Transitive via GeoPandas/Rasterio; explicit pin avoids surprise downgrades. Used implicitly whenever we reproject detection polygons from Sentinel-2 tile UTM to lon/lat for the frontend. [HIGH] |

### Supporting Libraries (specific-purpose; install only if needed)

| Library | Version (pin) | Purpose | When to Use |
|---------|---------------|---------|-------------|
| **albumentations** | `2.0.x` (last maintained release) **OR** `albumentationsx>=2.1` | Training augmentation (flips, rotations, brightness jitter, coarse dropout) | **Trap:** the original `albumentations` project is no longer actively maintained as of June 2025; `AlbumentationsX` is the successor. For a 48h hackathon, stick with `albumentations==2.0.14` (last maint release, Apr 2026) — it works fine for our simple flip/rotate/noise pipeline. **Do NOT pull `albumentationsx`** unless you need a new feature: it is AGPL-3.0 dual-licensed and commercial-restricted, which is needless complexity. Write the biofouling-NIR-scaling augmentation as a custom `torch.utils.data.Dataset.__getitem__` block — it's 10 lines and doesn't need Albumentations at all. [HIGH] |
| **scikit-image** | `>=0.24,<0.26` | Morphological post-processing on probability masks (`skimage.morphology.remove_small_objects`, `opening`) before polygonization to kill noise | Optional but recommended — rasterio's `shapes()` will produce 1000s of single-pixel polygons on a raw probability map without denoising. One `opening(mask, footprint=disk(2))` call reduces that to ~50 clean patches. [HIGH] |
| **scikit-learn** | `>=1.5,<1.7` | KDE for particle-density polygons (`sklearn.neighbors.KernelDensity` → contour → polygon at 25/50/75 percentile) | Required by PRD §8.5 "KDE density polygons at +24/+48/+72 h". Already preinstalled on Kaggle. [HIGH] |
| **pandas** | `>=2.2,<3.0` | Tabular ops for trajectories (particle_id, t, lon, lat) and mission waypoints | Transitive via GeoPandas; explicit pin helps avoid accidental `pandas 3.x` upgrades (still pre-release in Q2 2026). [HIGH] |
| **tqdm** | `>=4.66` | Training / inference progress bars | Trivial but judges-during-live-demo-friendly. [HIGH] |
| **matplotlib** | `>=3.9,<3.12` | Training-curve plots, notebook visualization of patches | Needed inside the Kaggle notebook for quick sanity checks on MARIDA patches. Not shipped in the production pipeline. [HIGH] |
| **pillow** | `>=10.4` | Image I/O for quick-look RGB composites (optional) | Transitive via torchvision; explicit pin ensures cp311 wheel availability. [HIGH] |
| **kornia** | `>=0.7.3` — **only** if torchgeo is adopted | GPU-accelerated augmentation for multispectral | If we decide to use torchgeo's spectral-index transforms, Kornia is a hard dependency. Otherwise skip — it adds ~150 MB to the environment. [MEDIUM] |
| **kaggle** (CLI) | `>=1.6` | Pushing notebook + kernel-metadata.json to Kaggle (local dev machine) | Only used on the developer laptop, not inside the kernel. Auth via `~/.kaggle/kaggle.json`. [HIGH] |
| **wandb** | — | Training metrics dashboard | **Skip.** The `marinedebrisdetector` repo uses W&B, but for a 48h build the Kaggle "Logs" tab + `tqdm` + a matplotlib loss curve is sufficient. W&B adds a login flow and an API-key secret that is more friction than value. [HIGH] |
| **pytorch-lightning** | — | Training loop abstraction | **Skip on Kaggle.** The `marinedebrisdetector` repo uses Lightning for training, but for inference-only (our Phase 1) it is not needed; `torch.hub.load` returns a `torch.nn.Module` directly. For Phase 3 training, a hand-rolled loop in 80 LOC is more debuggable on a 12h kernel budget than wrestling with Lightning trainer callbacks. [HIGH — opinionated] |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **pytest** `>=8.2` | Unit tests for `features.py` (FDI sanity), `tracker.py` (43.2 km synthetic displacement), E2E smoke | Preinstalled on Kaggle; pin for local |
| **pip-tools** `>=7.4` | Optional — generate `requirements.lock` from `requirements.in` | Lockfile missing today per `STACK.md`; for a 48h build `pip freeze > requirements.txt` at the end is adequate |
| **ruff** `>=0.5` (optional) | Linting | Preinstalled on Kaggle; don't spend time configuring rules during hackathon |

---

## Installation

### Local dev (Windows / Linux / macOS — Python 3.11)

```bash
# Create env
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel

# Core ML
pip install "torch==2.7.0" "torchvision==0.22.0" --index-url https://download.pytorch.org/whl/cu121
pip install "segmentation-models-pytorch>=0.5.0,<0.6.0"

# Geospatial + scientific (order matters on Windows — install rasterio + geopandas from wheels first)
pip install "rasterio>=1.5.0,<1.6.0"
pip install "shapely>=2.0,<3.0" "pyproj>=3.7" "geopandas>=1.0,<1.2"
pip install "xarray>=2026.2.0,<2027.0.0" "netCDF4>=1.7.2" "scipy>=1.14" "numpy>=1.26,<2.0"

# Support
pip install "scikit-image>=0.24,<0.26" "scikit-learn>=1.5,<1.7" "albumentations==2.0.14"
pip install "pandas>=2.2,<3.0" "tqdm>=4.66" "matplotlib>=3.9,<3.12" "pillow>=10.4"

# Dev
pip install "pytest>=8.2"
```

**Windows-specific fallback** (if rasterio wheel fails — rare in 1.5.x but documented in `backend/README.md`):
```bash
conda install -c conda-forge "rasterio>=1.5" "geopandas>=1.0" "shapely>=2.0" "gdal>=3.8"
```

### Kaggle kernel (`ManasTiwari1410/drift-model`)

**Do NOT `pip install` torch/torchvision/numpy/pandas/scipy/rasterio/geopandas/shapely/xarray/netCDF4/scikit-image/scikit-learn/matplotlib/tqdm** — they are all pre-installed in the Kaggle Docker image (`gcr.io/kaggle-gpu-images/python`) as of Q1 2026 and swapping versions can break CUDA linkage.

Only these need explicit pip install at kernel startup (first cell):
```python
!pip install -q "segmentation-models-pytorch>=0.5.0,<0.6.0" "albumentations==2.0.14"
```

Kernel-metadata.json (critical fields):
```json
{
  "id": "manastiwari1410/drift-model",
  "title": "DRIFT Model Training",
  "code_file": "train.ipynb",
  "language": "python",
  "kernel_type": "notebook",
  "is_private": true,
  "enable_gpu": true,
  "enable_tpu": false,
  "enable_internet": true,
  "dataset_sources": ["manastiwari1410/marida-dataset"],
  "competition_sources": [],
  "kernel_sources": []
}
```
**Kaggle GPU assignment is non-deterministic**: you ask for GPU, you may get P100 or T4x2. Write inference code to be agnostic (`device = "cuda" if torch.cuda.is_available() else "cpu"`, `autocast(dtype=torch.float16)` — works on both).

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **segmentation-models-pytorch + hand-rolled dual head** | **torchgeo** + pretrained ResNet-18 SENTINEL2_ALL_MOCO weights | If we had 5 days instead of 48 hours. torchgeo's transforms module computes spectral indices (`AppendFDI`, `AppendNDVI`) natively and its `ResNet18_Weights.SENTINEL2_ALL_MOCO` is pretrained on actual Sentinel-2 (not ImageNet) — objectively better initialization for 11-band input. **But:** torchgeo's UNet-style architectures are less mature than SMP's, and onboarding its dataset API on top of MARIDA is 3–5 hours we don't have. Recommended as a Phase 4 "if time allows" swap, not for the critical path. [MEDIUM] |
| **PyTorch (2.7)** | **JAX / Flax** | Never for this project. MARIDA's Lightning/torch.hub ecosystem is PyTorch-only; fighting the ecosystem in 48h is lethal. |
| **marccoru/marinedebrisdetector torch.hub** (Phase 1) | **mados (Kakogeorgiou 2023) repo** — slightly higher F1 on MADOS | `mados` is NOT packaged for `torch.hub`; requires manual clone, pip install, Lightning checkpoint loading. **Use for inspiration only**, not as the Phase 1 baseline. [HIGH] |
| **rasterio 1.5** | **GDAL Python bindings direct** | Never — GDAL's Python API is harder to use correctly and has worse error messages. rasterio is the Pythonic wrapper. |
| **xarray + copernicusmarine client** (future live mode) | **motuclient + OPeNDAP** | **DEPRECATED** — `motuclient` and OPeNDAP were removed from CMEMS in April 2024. `copernicusmarine` (the official Python toolbox) is the only supported path for live CMEMS data; for this MVP we pre-stage NetCDFs and don't need the client. [HIGH] |
| **Hand-rolled Euler Lagrangian tracker (~100 LOC)** | **OpenDrift** | OpenDrift is the "right" answer for production marine-drift modeling. **But:** it ships its own Lightning-Flask-Matplotlib stack, and its configuration model is a 200-line YAML. For a 72h 2D windage+currents problem, `scipy.interpolate` + a `for t in range(72)` loop is 50 LOC and unit-testable against synthetic fields. Explicit PRD exclusion (§12). [HIGH] |
| **xarray `.interp`** | **scipy.interpolate.RegularGridInterpolator** | Use RegularGridInterpolator **only if** `ds.interp()` becomes a bottleneck for 20 × 72 × N-detection queries. Pre-convert the 4D xarray to NumPy arrays once and pass to RegularGridInterpolator for 10–50× speedup. Premature optimization for Phase 2; drop in if Phase 3 benchmarks show >2s interp time. [HIGH] |
| **Albumentations** | **kornia.augmentation** | Kornia is GPU-accelerated and first-class multispectral, but **for 256×256 patches on a P100 the bottleneck is the model, not augmentation**. CPU-side Albumentations (or custom `Dataset.__getitem__`) is simpler and equivalent throughput. [HIGH] |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **`torch.compile` on Kaggle P100** | P100 has compute capability 6.0; Triton (the backend for `torch.compile`) requires ≥7.0. Silent NaN/slowdown trap. | Run eager mode. `model.to("cuda")` is enough. |
| **bfloat16 on T4** | T4 (compute 7.5, Turing) has no bfloat16 hardware. `autocast(dtype=torch.bfloat16)` falls back to float32 with no warning — you lose the speedup and don't know it. | `torch.cuda.amp.autocast(dtype=torch.float16)` + `GradScaler`. Works on both P100 and T4. |
| **Python 3.9 or 3.13** | Python 3.9: xarray 2026.2.0 dropped it; also below PyTorch 2.7's stated minimum in its Kaggle wheels. Python 3.13: shapely/geopandas Windows wheels still unreliable, and Kaggle kernel is on 3.11 — mismatch breaks `pickle`-based checkpoint loading. | Python 3.11. Matches Kaggle, has all wheels. |
| **NumPy 2.0.0 specifically (as an explicit pin)** | Inconsistent results documented between `xarray<2024.7.0` and `numpy>=2.0.0`. If you MUST use NumPy 2, upgrade xarray to `>=2026.2.0` and netCDF4 to `>=1.7.2` in lockstep. | `numpy>=1.26,<2.0` for the hackathon — zero drama path. Upgrade to 2.x only if Kaggle image forces it (in which case all deps are already NumPy-2-compatible in their new versions). |
| **`motuclient` / CMEMS OPeNDAP / FTP / ERDDAP** | **Dead.** Shut down April 2024 by Copernicus Marine. Any code/blog from before 2024 referencing these is broken. | Pre-staged NetCDFs (PRD §4). Future-live: `copernicusmarine.open_dataset()` only. |
| **`albumentationsx`** for the hackathon | AGPL-3.0 dual license; commercial restrictions; and the original `albumentations` 2.0.14 still works identically for our flip/rotate/brightness needs. | `albumentations==2.0.14` pinned. |
| **W&B / Neptune / MLflow** for training tracking | Auth flow + API key + dashboard setup = 30 minutes of zero-value friction on H16. | Kaggle's built-in "Logs" tab + a simple `losses = []` Python list + `matplotlib` at the end. |
| **PyTorch Lightning** for the training loop on Kaggle | Trainer callback config is a known debugging hole under time pressure. Lightning's checkpoint saving interacts poorly with Kaggle's `/kaggle/working` persistence rules. The MarcCoru repo uses Lightning, but that's *their* choice — we only need to `torch.hub.load` the result, not retrain with Lightning. | Hand-rolled loop: `for epoch in range(25): for batch in loader: ... opt.step()` — 80 LOC, fully debuggable, full control over biofouling augmentation insertion. |
| **`torchvision.models.segmentation.deeplabv3_resnet50`** | Trained on PASCAL VOC (3-channel RGB); surgery to 14-channel input is nontrivial. | `smp.UnetPlusPlus(encoder_name="resnet18", in_channels=14, ...)` — SMP handles channel adaptation internally. |
| **`cv2.imread` / OpenCV for reading Sentinel-2 TIFs** | OpenCV doesn't preserve CRS/geotransform. Will silently strip georeferencing. | `rasterio.open(path).read()` — returns `(bands, H, W)` float32 with `.transform` and `.crs` preserved. |
| **JSON output via `geojson` package** | Does not integrate with GeoPandas CRS metadata, produces schema-violating `FeatureCollection`s when hand-built. | `gdf.to_json()` — GeoPandas emits RFC-7946-compliant GeoJSON with proper `"type": "FeatureCollection"` + `"crs"` (with the right setup) fields. |

---

## Stack Patterns by Phase

### Phase 1 — Dummy inference with `marccoru/marinedebrisdetector`

- **Load:** `model = torch.hub.load("marccoru/marinedebrisdetector", "unetpp", trust_repo=True).eval()` — verified usage from README [MEDIUM confidence — the exact argument set is documented but the model expects **12-channel** Sentinel-2 input, not the 14-channel stack we'll feed our own UNet++ in Phase 3; the channel ordering is repo-specific and must be read from the MarcCoru repo's preprocessing code on kickoff].
- **Input spec:** The pretrained model expects **12 Sentinel-2 bands** (not 11) — verified in the repo's README ("Pre-trained weights are provided for 12-channel Sentinel-2 imagery"). MARIDA ships 11 bands. **You will need to zero-pad or duplicate a band** (typically B10 or B9 is the "missing" one from L2A products — the MarcCoru hubconf docstring must be checked for the exact ordering).
- **Output:** Per-pixel probability map, same H×W as input patch. Threshold at 0.5 → binary mask → `rasterio.features.shapes()` → polygons.
- **Dual head:** **Not available in pretrained baseline.** For Phase 1, emit `fraction_plastic = conf_raw * 0.3` (stub constant) so the contract schema is populated and downstream code can be built. Swap for real regression head in Phase 3.

### Phase 2 — Lagrangian tracker on pre-staged NetCDFs

- **Load:** `ds_currents = xr.open_dataset("data/env/cmems_surface_currents_72h.nc")`; `ds_wind = xr.open_dataset("data/env/era5_wind_10m_72h.nc", engine="netcdf4")`.
- **Interp:** `u = ds_currents["uo"].interp(longitude=lon, latitude=lat, time=t, method="linear").item()` per particle per hour. **Vectorize** across particles with `.interp(longitude=xr.DataArray(lons, dims="particle"), latitude=..., ...)` — a 20-particle × 72-step × N-detection loop is 1440 × N evaluations; vectorizing cuts this to 72 × N calls. [HIGH]
- **Integration:** `dx = (u_c + 0.02 * u_w) * dt_sec` per hourly step (per PRD §8.5 formula, verbatim). No RK4, no Stokes.

### Phase 3 — Fine-tune UNet++ dual-head on Kaggle

- **Arch:**
  ```python
  import segmentation_models_pytorch as smp
  class DualHeadUNetpp(nn.Module):
      def __init__(self, in_channels=14):
          super().__init__()
          self.backbone = smp.UnetPlusPlus(
              encoder_name="resnet18",
              encoder_weights="imagenet",
              in_channels=in_channels,
              classes=16,  # feature map, not final prediction
              activation=None,
          )
          # Replace segmentation head with two heads
          self.mask_head = nn.Conv2d(16, 1, kernel_size=1)
          self.frac_head = nn.Conv2d(16, 1, kernel_size=1)
          # Optional SE attention on encoder output — insert in forward
      def forward(self, x):
          features = self.backbone(x)
          return {
              "mask": self.mask_head(features),           # BCE target
              "fraction": torch.sigmoid(self.frac_head(features))  # MSE target, ∈ [0,1]
          }
  ```
- **Critical SMP gotcha — `in_channels > 4`:** When `in_channels=14` and `encoder_weights="imagenet"`, **SMP will initialize the first conv layer with either (a) random weights OR (b) weights tiled `pretrained[:, i % 3]` and scaled `* 3/14`, depending on the exact SMP version.** Search results are inconsistent between 0.3.x and 0.5.x behaviors. **Verify at kickoff** by inspecting `model.encoder.conv1.weight.std()` after instantiation — if it's ~0.02 we got tiled-pretrained; if ~0.1 we got random. **Recommended workaround:** after `smp.UnetPlusPlus(...)`, manually set `model.encoder.conv1.weight.data[:, :3] = pretrained_rgb_weights.mean(dim=0, keepdim=True).repeat(1, 3, 1, 1)` for the first 3 channels (B4/B3/B2) and leave channels 3–13 with whatever init SMP chose. This gives pretrained RGB "head start" on the visual bands without blowing up the spectral/index channels. [MEDIUM confidence — exact code path is version-dependent]
- **Loss:** `Dice(mask, y_mask) + BCE(mask, y_mask) + 0.1 * MSE(fraction, y_frac)` — the 0.1 weight keeps mask learning dominant. [HIGH]
- **Augmentation:** flip H, flip V, rotate90 (4 values), brightness jitter ±10% — all inside a custom `Dataset.__getitem__` using NumPy. Separately, biofouling sim: with p=0.4, `patch[6:8] *= torch.empty(1).uniform_(0.5, 1.0).item()` (band indices 6, 7 = B6 RedEdge + B8 NIR per MARIDA ordering). [HIGH — matches PRD §4/§8.4]
- **Training compute:** Kaggle P100 — batch size 16, 256×256, ~25 epochs ≈ 60–90 min. Kaggle T4x2 — batch size 32, ~45 min with `DataParallel`. **Do not** use `DistributedDataParallel` on T4x2 — not worth the 30-min setup on a 12h kernel budget. [HIGH]
- **Checkpoint:** `torch.save(model.state_dict(), "/kaggle/working/drift_unetpp_dualhead.pt")` — Kaggle makes `/kaggle/working/` downloadable after the kernel completes. Load locally with `torch.load(..., map_location="cpu")` then `.to("cpu")` for demo inference (laptop is CPU-only). [HIGH]

---

## Version Compatibility Matrix

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `torch==2.7.0+cu121` | `torchvision==0.22.0` | Strict pair; mismatch → AttributeError on `models.resnet18()`. |
| `torch==2.7.0` | Kaggle P100 (sm_60) + T4 (sm_75) | Last version with full dual support. Do not upgrade to 2.8/2.9 for this project. |
| `segmentation-models-pytorch>=0.5` | `torch>=1.12,<3.0`, `timm>=0.9` | `timm` is a transitive dep; pin `timm>=0.9,<1.1` implicitly. |
| `xarray>=2026.2.0` | `python>=3.11`, `numpy>=1.26` (works on 2.x), `netCDF4>=1.7` | Drops 3.9/3.10 as of 2026.2.0. |
| `rasterio>=1.5.0` | `GDAL>=3.8` (bundled in wheels), `python>=3.10` | cp311/cp312 Windows wheels ship GDAL 3.8.x bundled — no external GDAL install needed. Windows cp39 is **not shipped**. |
| `geopandas>=1.0` | `shapely>=2.0` (hard req), `pyproj>=3.3`, `pandas>=2.0` | PyGEOS removed. Install shapely **before** geopandas to avoid a C-library race condition on Windows. |
| `shapely>=2.0` | `python>=3.9,<3.14` on Linux/Mac; `<3.13` on Windows (as of 2026-Q1) | Windows 3.13 wheels still unreliable. |
| `albumentations==2.0.14` | `numpy>=1.24`, `opencv-python>=4.9` (opt-in separately), `python>=3.9` | As of 2.0.14, OpenCV is NOT auto-installed. Add `opencv-python-headless>=4.10` if you use any augmentation that needs OpenCV. |
| `xarray + numpy 2.x` | `xarray>=2024.7.0` | Pre-2024.7 + NumPy 2 → silent wrong results (doc'd on CMEMS help page). |

---

## Kaggle-Specific Gotchas (critical for Phase 3)

1. **Internet must be enabled** in the notebook settings panel (gear icon → "Internet: On"). Without it, `torch.hub.load("marccoru/marinedebrisdetector", ...)` can't fetch the repo. Also required for `pip install segmentation-models-pytorch`. Setting in `kernel-metadata.json`: `"enable_internet": true`. [HIGH]
2. **GPU is OFF by default** on your scaffolded kernel (per PROJECT.md Key Decisions). Flip `"enable_gpu": true` in `kernel-metadata.json` **before** pushing, or toggle in the UI. The Kaggle API has historically not honored `enable_gpu` reliably for all account tiers — if `nvidia-smi` in the first cell returns empty, toggle in UI and re-run. [HIGH]
3. **12 GPU-hours per week** is the free-tier quota. 25 epochs of UNet++ on 1,381 MARIDA patches × batch 16 ≈ 60–90 min on P100. Budget **two training runs** max — one to iterate hyperparameters, one to run the "for keeps" submission training. [HIGH]
4. **`/kaggle/working/`** is the only writable persistent path; contents are preserved after the kernel completes and can be downloaded as a dataset or attached to another kernel. Write your checkpoint here, never to `/kaggle/input/` (read-only) or `/tmp` (ephemeral). [HIGH]
5. **`/kaggle/input/<dataset-slug>/`** is where uploaded datasets mount read-only. Upload MARIDA as a private Kaggle dataset (the 1.4GB tarball); reference it in `kernel-metadata.json` via `"dataset_sources": ["<your-slug>/marida-dataset"]`. **Do not** try to `git clone` MARIDA from within the kernel — it's faster and more reliable as a dataset mount. [HIGH]
6. **GPU type is non-deterministic.** When you request GPU, Kaggle gives you whatever is free — P100 OR T4x2. Your code must handle both: `if torch.cuda.device_count() > 1: model = nn.DataParallel(model)`. [HIGH]
7. **Kernel runtime limit is 12 hours** (9h for non-internet kernels). Training must fit within one session; no resume semantics in Kaggle free tier. If 25 epochs won't fit, drop to 15 or switch to batch-32 on T4x2. [HIGH]
8. **Pre-installed package list is NOT stable across weeks.** What works in Week 15 may break in Week 17 after Kaggle rolls a new Docker image. **Pin via first cell** `!pip list | grep -E 'torch|segmentation|rasterio|xarray|numpy' > /kaggle/working/env_snapshot.txt` and save the snapshot — it's your "it worked on my kernel" receipt. [HIGH]
9. **No `xformers`, no `flash-attn`, no `triton` pre-installed** (or they're old). Don't write code that depends on them. UNet++ doesn't need them anyway. [HIGH]
10. **W&B / Weights-and-biases** is available but requires an API key via Kaggle Secrets. **Skip for 48h build.** [HIGH]

---

## marccoru/marinedebrisdetector torch.hub — Verified Usage

Per the project README (verified via web search against https://github.com/MarcCoru/marinedebrisdetector):

```python
import torch

# Primary recommendation — UNet++
model = torch.hub.load(
    "marccoru/marinedebrisdetector",  # Note: lowercase in torch.hub; case-sensitive on some setups
    "unetpp",
    trust_repo=True,  # required in recent torch versions to bypass the "Are you sure?" prompt
)
model.eval()

# Alternative — plain UNet
# model = torch.hub.load("marccoru/marinedebrisdetector", "unet", trust_repo=True)

# Variant without label-refinement (as per README)
# model = torch.hub.load("marccoru/marinedebrisdetector", "unetpp", label_refinement=False, trust_repo=True)
```

**Input expectations** (from README):
- **12 Sentinel-2 channels** (not 11). Band ordering is `[B1, B2, B3, B4, B5, B6, B7, B8, B8A, B9, B11, B12]` per MARIDA/marine-debris convention, but **verify in the repo's preprocessing code at kickoff**. [MEDIUM]
- Reflectance values scaled to `[0, 1]` (float32). MARIDA patches are stored as `int16` scaled by 10000 — divide before feeding to the model. [HIGH]
- Patch size `256 × 256`. [HIGH]

**Output:**
- Single-channel logits `(B, 1, 256, 256)`; apply `torch.sigmoid()` to get probability `[0, 1]`. [HIGH]
- No fractional-cover regression head in the pretrained baseline — that's ours to add in Phase 3.

**The repo is MIT-licensed** (verified search result pointing to LICENSE at `main` branch — full text not retrieved in this research but MIT is standard for this author). Safe for hackathon redistribution; attribute in the demo/README. [MEDIUM — license type inferred from search snippets, verify file contents at kickoff]

**Pinning the hub repo:** By default `torch.hub.load` pulls latest main. To pin to a known-good commit (recommended for hackathon reproducibility), pass `ref=<commit-sha>`: e.g., `torch.hub.load("marccoru/marinedebrisdetector", "unetpp", source="github", ref="main", trust_repo=True)`. Replace `"main"` with a specific SHA **after** verifying the model loads and produces reasonable outputs on Durban example scene. [HIGH]

---

## Sources

- **GitHub — MarcCoru/marinedebrisdetector** (project README, hubconf, pyproject.toml): https://github.com/MarcCoru/marinedebrisdetector — verified `torch.hub.load("marccoru/marinedebrisdetector", "unetpp")` usage, 12-channel Sentinel-2 input, pretrained weights hosting [MEDIUM — full README not scraped, key claims triangulated across multiple search snippets]
- **PyPI — rasterio 1.5.0** (released 2026-01-05): https://pypi.org/project/rasterio/ — Python 3.12+ support, GDAL 3.8+ requirement, cp311/cp312/cp313 wheels for Linux/Mac/Win [HIGH]
- **PyPI — xarray 2026.2.0**: https://pypi.org/project/xarray/ — Python 3.11+ required, drops 3.9/3.10, release notes April 2026 [HIGH]
- **xarray What's New** (v2026.04.0 notes): https://docs.xarray.dev/en/stable/whats-new.html — drops 3.9 support, multi-array groupby added [HIGH]
- **PyPI — segmentation-models-pytorch 0.5.x**: https://pypi.org/project/segmentation-models-pytorch/ — UnetPlusPlus with `in_channels` arbitrary, encoder_weights semantics, interpolation_mode extended to UNet++ [HIGH]
- **SMP docs — Insights page**: https://smp.readthedocs.io/en/latest/insights.html — first-conv init behavior for `in_channels > 4` (random vs. tiled-and-scaled — version-dependent) [MEDIUM — behavior inconsistent between docs]
- **PyPI — AlbumentationsX and albumentations 2.0.14** (April 2026): https://pypi.org/project/albumentations/, https://pypi.org/project/albumentationsx/ — maintenance status, license differences [HIGH]
- **PyTorch 2.7 release blog** (April 2025): https://pytorch.org/blog/pytorch-2-7/ — Blackwell support, CUDA 12.8 wheels, last version with broad sm_60 coverage [HIGH]
- **Copernicus Marine help — Switching from old to new services**: https://help.marine.copernicus.eu/en/articles/8612591-switching-from-old-to-new-services — motuclient/OPeNDAP/FTP deprecation (April 2024) [HIGH]
- **Copernicus Marine Toolbox — Open dataset**: https://help.marine.copernicus.eu/en/articles/8287609-copernicus-marine-toolbox-api-open-a-dataset-or-read-a-dataframe-remotely — `copernicusmarine.open_dataset()` lazy-loading semantics [HIGH]
- **NVIDIA CUDA GPU compute capability matrix**: https://developer.nvidia.com/cuda/gpus — P100 = 6.0, T4 = 7.5 [HIGH]
- **PyTorch forums — Triton compute capability requirement**: triton requires ≥7.0 ⇒ `torch.compile` does not work on P100 [HIGH]
- **Kaggle docker-python releases**: https://github.com/Kaggle/docker-python/releases — image contents, pre-installed package snapshots [MEDIUM — contents drift weekly]
- **Kaggle kernel-metadata schema**: https://github.com/Kaggle/kaggle-api/wiki/Kernel-Metadata — `enable_gpu`, `enable_internet`, `dataset_sources`, `is_private` fields [HIGH]
- **rasterio.features docs**: https://rasterio.readthedocs.io/en/latest/api/rasterio.features.html — `shapes(mask, connectivity=8)` for polygonizing probability rasters [HIGH]
- **GeoPandas installation docs**: https://geopandas.org/en/stable/getting_started/install.html — GeoPandas 1.0 drops PyGEOS, requires shapely≥2.0 [HIGH]
- **arxiv 2307.02465 — Large-scale Detection of Marine Debris (Rußwurm et al.)**: https://arxiv.org/html/2307.02465 — paper behind the `marinedebrisdetector` repo, confirms architecture + training recipe [HIGH]

---

*Stack research for: DRIFT / PlastiTrack Intelligence Layer — satellite marine-plastic detection + Lagrangian drift forecasting on Kaggle, Python 3.11, PyTorch 2.7*
*Researched: 2026-04-17*
