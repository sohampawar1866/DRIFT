"""run_inference: tile path -> DetectionFeatureCollection via dummy weights.

Pipeline (per RESEARCH.md Pattern 7):
    1. Read 11-band MARIDA patch via rasterio; reflectance rescale if needed.
    2. Build 14-channel feature stack via features.feature_stack (single source
       of truth -- same function Phase 3 training will use).
    3. Sliding-window forward pass (256x256 patches, stride 128, cosine-Hann
       blending with >= 1e-3 floor).
    4. Threshold + rasterio.features.shapes(connectivity=4) polygonization.
    5. .buffer(0) fix for self-intersecting polygons; MIN_AREA_M2 filter.
    6. Compute area on UTM polygon; reproject vertices to WGS84 for GeoJSON.
    7. Emit DetectionFeatureCollection with pydantic validation.
"""
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
import torch
from pyproj import Transformer
from shapely.geometry import shape

from backend.core.config import Settings
from backend.core.schemas import (
    DetectionFeature,
    DetectionFeatureCollection,
    DetectionProperties,
)
from backend.ml.features import feature_stack
from backend.ml.weights import load_weights


# ----------------------- Cosine window ------------------------------------

def _cosine_window_2d(size: int) -> np.ndarray:
    """2D separable Hann window for overlap-blending, clamped to 1e-3 floor
    to avoid div-by-zero at tile corners (PITFALL 7).
    """
    w1d = np.hanning(size).astype(np.float32)
    w2d = np.outer(w1d, w1d)
    return np.maximum(w2d, 1e-3)


# ----------------------- Tile reading -------------------------------------

def _read_tile_bands(tile_path: Path) -> tuple[np.ndarray, rasterio.Affine, str]:
    """Read N-band tile at native resolution as float32, shape (N, H, W).

    BOA_ADD_OFFSET handling (PITFALL C1): MARIDA patches ship pre-scaled to
    [0,1]. For defensive future-proofing against live L2A tiles with PB>=04.00,
    we apply the heuristic (bands.max() > 1.5) -> treat as raw DN and rescale
    via (DN - 1000) / 10000. For MARIDA, the branch is a no-op.
    """
    with rasterio.open(tile_path) as src:
        bands = src.read().astype(np.float32)  # (N_bands, H, W)
        transform = src.transform
        crs = src.crs.to_string()

    # STAC fallbacks can provide only a subset of bands (e.g., red/nir/tci).
    # Pad to 11 channels so downstream feature extraction remains operational.
    if bands.shape[0] < 11:
        padded = np.zeros((11, bands.shape[1], bands.shape[2]), dtype=np.float32)
        padded[:bands.shape[0], :, :] = bands
        bands = padded
    elif bands.shape[0] > 11:
        bands = bands[:11, :, :]

    if bands.max() > 1.5:  # heuristic: raw DN
        bands = (bands - 1000.0) / 10000.0
    return bands, transform, crs


# ----------------------- Sliding window forward ---------------------------

def _sliding_forward(
    feats: np.ndarray,  # (C=14, H, W)
    model: torch.nn.Module,
    patch: int,
    stride: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (prob_map, fraction_map), both (H, W), cosine-stitched."""
    C, H, W = feats.shape
    prob_accum = np.zeros((H, W), dtype=np.float32)
    frac_accum = np.zeros((H, W), dtype=np.float32)
    weight = np.zeros((H, W), dtype=np.float32)
    window = _cosine_window_2d(patch)

    # Anchor grid: flush endpoints so the last row/col covers H-patch / W-patch.
    ys = list(range(0, max(1, H - patch + 1), stride))
    xs = list(range(0, max(1, W - patch + 1), stride))
    if ys and ys[-1] + patch < H:
        ys.append(H - patch)
    if xs and xs[-1] + patch < W:
        xs.append(W - patch)
    if not ys:
        ys = [0]
    if not xs:
        xs = [0]

    with torch.no_grad():
        for y in ys:
            for x in xs:
                tile = feats[:, y:y + patch, x:x + patch]
                if tile.shape[1] != patch or tile.shape[2] != patch:
                    pad = np.zeros((C, patch, patch), dtype=np.float32)
                    pad[:, :tile.shape[1], :tile.shape[2]] = tile
                    tile = pad
                x_t = torch.from_numpy(tile).unsqueeze(0)  # (1, C, p, p)
                out = model(x_t)
                prob = torch.sigmoid(out["mask_logit"])[0, 0].numpy()
                frac = out["fraction"][0, 0].numpy()
                h = min(patch, H - y)
                w = min(patch, W - x)
                prob_accum[y:y + h, x:x + w] += prob[:h, :w] * window[:h, :w]
                frac_accum[y:y + h, x:x + w] += frac[:h, :w] * window[:h, :w]
                weight[y:y + h, x:x + w] += window[:h, :w]

    weight = np.maximum(weight, 1e-6)
    return prob_accum / weight, frac_accum / weight


# ----------------------- Polygonization -----------------------------------

def _polygonize(
    prob: np.ndarray,
    frac: np.ndarray,
    threshold: float,
    min_area_m2: float,
    transform: rasterio.Affine,
    src_crs: str,
) -> list[DetectionFeature]:
    """Threshold + shapes + buffer(0) + area filter. Reprojects vertices to WGS84.

    Crucial orderings per PITFALL M9:
      - connectivity=4 (not 8) to avoid self-intersecting polygons
      - .buffer(0) to fix any invalid output geometries
      - area computed on UTM polygon BEFORE reprojection (gives m2 directly)
      - reproject vertices to WGS84 only for the GeoJSON output
    """
    mask = (prob >= threshold).astype(np.uint8)

    features: list[DetectionFeature] = []
    to_wgs = Transformer.from_crs(src_crs, "EPSG:4326", always_xy=True)

    for geom_dict, _val in rasterio.features.shapes(
        mask,
        mask=mask.astype(bool),
        transform=transform,
        connectivity=4,  # PITFALL M9: connectivity=4 not 8
    ):
        poly = shape(geom_dict)
        if not poly.is_valid:
            poly = poly.buffer(0)  # PITFALL M9 fix
        if not poly.is_valid or poly.is_empty:
            continue
        area_m2 = poly.area  # already in UTM meters (S2 tiles are UTM)
        if area_m2 < min_area_m2:
            continue

        # Reproject exterior ring UTM -> WGS84
        xs, ys = zip(*list(poly.exterior.coords))
        lons, lats = to_wgs.transform(xs, ys)
        wgs_coords = [list(zip(lons, lats))]

        # Average probability / fraction inside polygon (bbox-approx is fine)
        minx, miny, maxx, maxy = poly.bounds
        col_min, row_max = ~transform * (minx, miny)
        col_max, row_min = ~transform * (maxx, maxy)
        r0, r1 = int(max(0, row_min)), int(min(prob.shape[0], row_max + 1))
        c0, c1 = int(max(0, col_min)), int(min(prob.shape[1], col_max + 1))
        if r1 > r0 and c1 > c0:
            conf_raw = float(prob[r0:r1, c0:c1].mean())
            frac_val = float(frac[r0:r1, c0:c1].mean())
        else:
            conf_raw = float(threshold)
            frac_val = 0.0

        props = DetectionProperties(
            conf_raw=min(max(conf_raw, 0.0), 1.0),
            conf_adj=min(max(conf_raw, 0.0), 1.0),   # Phase 1: no biofouling decay
            fraction_plastic=min(max(frac_val, 0.0), 1.0),
            area_m2=float(area_m2),
            age_days_est=0,                           # Phase 1: no age model
        )
        features.append(DetectionFeature(
            type="Feature",
            geometry={"type": "Polygon", "coordinates": wgs_coords},
            properties=props,
        ))
    return features


# ----------------------- Public entry -------------------------------------

def run_inference(tile_path: Path, cfg: Settings) -> DetectionFeatureCollection:
    """Public entry: Sentinel-2 patch -> schema-valid DetectionFeatureCollection.

    Phase 1: `dummy` weights. Phase 3 will swap to `our_real` via YAML flip.
    """
    bands, transform, crs = _read_tile_bands(tile_path)
    # features.feature_stack takes (H, W, N_bands) -> (H, W, 14); rearrange.
    bands_hwc = np.transpose(bands, (1, 2, 0))
    feats_hwc = feature_stack(bands_hwc)
    feats_chw = np.transpose(feats_hwc, (2, 0, 1)).astype(np.float32)

    model = load_weights(cfg)
    prob, frac = _sliding_forward(
        feats_chw,
        model,
        patch=cfg.ml.patch_size,
        stride=cfg.ml.stride,
    )
    features = _polygonize(
        prob,
        frac,
        threshold=cfg.ml.confidence_threshold,
        min_area_m2=cfg.ml.min_area_m2,
        transform=transform,
        src_crs=crs,
    )
    return DetectionFeatureCollection(type="FeatureCollection", features=features)
