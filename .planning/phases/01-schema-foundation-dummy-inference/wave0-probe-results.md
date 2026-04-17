# Wave 0 Probe Results

**Run date:** 2026-04-17
**Python:** 3.11.3 (C:\Users\offic\anaconda3\python.exe)
**Host:** TUF
**Install path used:** pip (no conda fallback needed — rasterio wheel installed cleanly on Windows Py3.11)

## Probe 1 — MARIDA band ordering & reflectance scale

- **Sample patch:** `MARIDA/patches/S2_1-12-19_48MYU/S2_1-12-19_48MYU_0.tif`
- **Band count:** `11` (expected 11)
- **Descriptions:** `(None, None, None, None, None, None, None, None, None, None, None)` — no embedded band names; use the RESEARCH.md documented MARIDA order.
- **Dtypes:** `('float32', ) x 11` — all bands float32
- **Raster shape:** `(256, 256)` per band
- **CRS:** `EPSG:32748` (UTM zone 48S — western Indonesia, as expected for the `48MYU` MGRS tile)
- **Pixel transform:** `| 10.00, 0.00, 706740.00 |  | 0.00, -10.00, 9340960.00 |  | 0.00, 0.00, 1.00 |` — 10 m pixels, origin at (706740 E, 9340960 N)
- **Array min / max / mean:** `0.01437 / 0.27129 / 0.05331`

**Reflectance scale decision:**
- Observed max = 0.271 (well below 1.5), so MARIDA ships **pre-scaled reflectance in [0, 1]**.
- **Resolved to:** NO RESCALE NEEDED. `_read_tile_bands` in `backend/ml/features.py` should pass MARIDA bands through directly. Only apply `(DN - 1000) / 10000` when ingesting RAW Sentinel-2 L2A COGs (post-2022-01-25 with BOA_ADD_OFFSET), not MARIDA.
- **Sanity flag for Plan 03:** if a future tile loads with max > 1.5, it's raw S2 DN (not MARIDA). The loader should branch on `arr.max() > 1.5` to apply the DN rescale.

**Band index mapping (to write into `backend/ml/features.py`):**

Descriptions are `None`, so fall back to the RESEARCH.md-documented MARIDA band ordering (from the Kikaki 2022 paper + MARIDA metadata):

| Index | Band | Purpose |
|-------|------|---------|
| 0 | B2  | Blue (492 nm, 10 m) |
| 1 | B3  | Green (560 nm, 10 m) |
| 2 | B4  | Red (665 nm, 10 m) |
| 3 | B5  | RedEdge1 (704 nm, 20 m resampled to 10 m) |
| 4 | B6  | RedEdge2 (740 nm, 20 m resampled) |
| 5 | B7  | RedEdge3 (783 nm, 20 m resampled) |
| 6 | B8  | NIR (833 nm, 10 m) |
| 7 | B8A | NIR narrow (865 nm, 20 m resampled) |
| 8 | B11 | SWIR1 (1613 nm, 20 m resampled) |
| 9 | B12 | SWIR2 (2202 nm, 20 m resampled) |
| 10 | SCL | Scene Classification Layer (categorical, 20 m resampled) |

Plan 03 (`features.py`) should define these as module-level constants: `B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12, SCL = range(11)`.

FDI (Biermann 2020) uses: `B8 - (B6 + (B11 - B6) * (832 - 665) / (1613 - 665))`. Wavelength constants should be in the same file.
NDVI: `(B8 - B4) / (B8 + B4)`.
PI (Themistocleous 2020 plastic index): `B8 / (B8 + B4)`.

## Probe 2 — geojson-pydantic version & generic surface

- **Version:** `2.1.1` (newer than the plan's >=1.2 minimum; 2.x is fully backward compatible for `Feature[G, P]` generics per the 2.0 release notes)
- **Feature[Polygon, Props] generic works:** **yes**
- **Feature type emitted:** `<class 'geojson_pydantic.features.Feature[Polygon, P]'>`
- **FeatureCollection[Feature[...]] works:** yes
- **Error message (if any):** none
- **Decision:** use RESEARCH.md **Pattern 1** (standard generic `Feature[Polygon, DetectionProps]`). No BaseModel fallback needed.
- **Import surface for Plan 02 (`schemas.py`):**
  ```python
  from geojson_pydantic import Feature, FeatureCollection, Polygon, LineString, Point
  from pydantic import BaseModel

  class DetectionProps(BaseModel, extra="forbid"):
      conf_raw: float
      conf_adj: float
      fraction_plastic: float
      area_m2: float
      age_days_est: float
      class_: str  # serialized via Field(alias="class")

  DetectionFeature = Feature[Polygon, DetectionProps]
  DetectionFC = FeatureCollection[DetectionFeature]
  ```

## Probe 3 — SMP in_channels=14 init probe

- **conv1.weight.std:** `0.028185242787003517`
- **conv1.weight.shape:** `(64, 14, 7, 7)` (matches expected — 64 output channels, 14 input channels as configured)
- **Classification:** **tiled-pretrained (~0.02 regime)** — SMP 0.5 successfully tiled the 3-channel ImageNet resnet18 conv1 weights across all 14 input channels (via its HuggingFace-hub encoder-weights mechanism).
- **Phase 1 policy:** the `>1e-4` assert in `weights.py` (RESEARCH.md Pattern 4) will PASS comfortably (0.028 >> 1e-4).
- **Phase 3 note:** std = 0.028 is in the tiled-pretrained band (not ~0.1 random-init). This means **no manual RGB-head init workaround is needed** in Phase 3. The SMP-tiled init is a reasonable starting point; Phase 3 training can proceed without the RGB-conv1 re-init trick.
- **Encoder-weights fetch mechanism:** SMP 0.5 downloads from HuggingFace hub (`smp-hub/resnet18.imagenet`) — cached at `~/.cache/huggingface/hub/models--smp-hub--resnet18.imagenet/`, NOT at the legacy `~/.cache/torch/hub/checkpoints/resnet18-*.pth` path. Phase 3 notebook must pre-populate the HF hub cache on Kaggle for offline-safe instantiation.

## Installed versions

- torch: `2.7.0+cpu`
- torchvision: `0.22.0+cpu`
- segmentation-models-pytorch: `0.5.0`
- rasterio: `1.4.4`  (**note:** plan requested 1.5.x but that requires Py3.12; we're on Py3.11 per PITFALL mi2)
- numpy: `1.26.4`
- geopandas: `1.1.3`
- shapely: `2.1.2`
- pyproj: `3.7.2`
- pydantic: `2.12.5`
- pydantic-settings: `2.13.1`
- geojson-pydantic: `2.1.1`
- scikit-image: `0.25.2`
- PyYAML: `6.0`
- pytest: `9.0.3`

## Blockers / surprises

1. **Plan pin mismatch for rasterio (resolved inline as deviation Rule 1).**
   - Plan pinned `rasterio>=1.5.0,<1.6.0` — but rasterio 1.5+ requires Python >=3.12. Since Phase 1 is locked to Py3.11 (PITFALL mi2 / CLAUDE.md), the pin was relaxed to `>=1.3,<1.6` in `backend/pyproject.toml`. Resolved to rasterio 1.4.4. No API differences affect Phase 1 usage (`rasterio.open`, `src.read()`, `src.descriptions`, `src.transform`, `src.crs` are all stable across 1.3–1.4).

2. **SMP 0.5 uses HuggingFace hub, not torch.hub, for encoder weights.**
   - Plan acceptance criterion mentioned `~/.cache/torch/hub/checkpoints/resnet18-*.pth`. The actual cache path is `~/.cache/huggingface/hub/models--smp-hub--resnet18.imagenet/`. This is a library evolution (SMP 0.4→0.5 migrated). Plan 04 weight-loading code should not assume the legacy torch.hub path; rely on SMP's `encoder_weights="imagenet"` which auto-resolves to HF hub.

3. **geojson-pydantic 2.1.1 available — newer than plan's `>=1.2,<3.0`.**
   - The 2.x generic surface is identical to 1.x for our usage. No action needed; Pattern 1 works.

4. **MARIDA tif descriptions are all `None`.**
   - Band names are NOT embedded in the GeoTIFF metadata. Plan 03 MUST hardcode the index→band mapping (above) rather than relying on `rasterio.open(tif).descriptions`. This is a hard contract — if MARIDA re-packages with embedded descriptions in future, great, but for now the mapping is positional.

5. **`torchaudio 2.2.2` dependency conflict warning.**
   - Legacy `torchaudio 2.2.2` remains in the env and complains that `torch==2.7.0` is installed. torchaudio is NOT used in Phase 1 (no audio). Safe to ignore; if Phase 3 surfaces a spurious import error, `pip uninstall torchaudio` fixes it.

6. **MARIDA tile reflectance range is ~0.01–0.27.**
   - Consistent with ocean+land pixels; no values near 1.0 (no clouds in this patch). No saturation concerns for Phase 1 inference.

## Handoff to Plans 02–05

- **Plan 02 (`schemas.py`):** use `geojson_pydantic.Feature[Polygon, DetectionProps]` with `extra="forbid"` — see Probe 2 snippet above.
- **Plan 03 (`features.py`):** use the positional band-index constants from Probe 1; do NOT rescale MARIDA reflectance; DO branch-rescale (DN − 1000) / 10000 for raw S2 L2A input.
- **Plan 04 (`model.py` / `weights.py`):** instantiate `smp.UnetPlusPlus(encoder_name='resnet18', encoder_weights='imagenet', in_channels=14, classes=1, decoder_attention_type='scse')`. Assert `conv1.weight.std() > 1e-4`. Expect ~0.028.
- **Plan 05 (inference glue):** no changes needed beyond the schema; tile dtype is already float32 at 10 m.
