"""Heuristic FDI/NDVI plastic detector.

Used when ML weights are weak (dummy or untrained `our_real`). Operates
directly on real Sentinel-2 reflectance to surface floating-debris
candidates inside the user's drawn bbox, instead of returning empty
or hallucinating polygons elsewhere.

Pipeline:
  1. Open the STAC-fetched tile (rasterio).
  2. If a bbox is provided, window-read only that subset (saves memory).
  3. Compute FDI (Biermann 2020) + NDVI from the available bands.
  4. Threshold FDI > FDI_MIN AND NDVI < NDVI_MAX (Sargassum filter).
  5. Polygonize with rasterio.features.shapes (connectivity=4, buffer(0)).
  6. Filter by min_area_m2.
  7. Reproject UTM -> WGS84 and emit a DetectionFeatureCollection.

Output is schema-compatible with `run_inference` so it slots into
the existing `_detection_fc_to_api_shape` adapter without changes.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
import rasterio.windows
from pyproj import Transformer
from shapely.geometry import shape

from backend.core.schemas import (
    DetectionFeature,
    DetectionFeatureCollection,
    DetectionProperties,
)

logger = logging.getLogger(__name__)

FDI_MIN = 0.005
NDVI_MAX = 0.20
MIN_AREA_M2 = 200.0
MAX_FEATURES = 25


def _read_window(tile_path: Path, bbox: list[float] | None):
    """Open tile; if bbox given, window-read the intersecting pixels.

    Returns (bands_array, transform, crs_str) where bands_array is
    (N_bands, H, W) float32.
    """
    with rasterio.open(tile_path) as src:
        if bbox is not None and src.crs is not None:
            try:
                to_src = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                xs, ys = to_src.transform([bbox[0], bbox[2]], [bbox[1], bbox[3]])
                left, right = min(xs), max(xs)
                bottom, top = min(ys), max(ys)
                win = rasterio.windows.from_bounds(left, bottom, right, top, src.transform)
                win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
                if win.width >= 4 and win.height >= 4:
                    bands = src.read(window=win).astype(np.float32)
                    transform = src.window_transform(win)
                    return bands, transform, src.crs.to_string()
            except Exception as e:
                logger.info("heuristic: bbox window failed (%s) — reading full tile", e)
        bands = src.read().astype(np.float32)
        return bands, src.transform, src.crs.to_string() if src.crs else "EPSG:4326"


def _bands_to_fdi_ndvi(bands: np.ndarray) -> tuple[np.ndarray | None, np.ndarray, np.ndarray]:
    """Compute (fdi_or_none, ndvi, nir) from whatever band ordering the tile has.

    STAC-fetched tiles often only have 2 bands (nir, red). MARIDA tiles
    have 11. We adapt: FDI requires nir + redge2 + swir1; if redge2/swir1
    are missing we set FDI=None and rely on NDVI alone.
    """
    if bands.max() > 1.5:
        bands = (bands - 1000.0) / 10000.0
    n = bands.shape[0]
    if n >= 11:
        red = bands[2]
        redge2 = bands[4]
        nir = bands[6]
        swir1 = bands[8]
    elif n >= 6:
        red = bands[2]
        nir = bands[3] if n < 5 else bands[4] if n == 5 else bands[3]
        redge2 = bands[3]
        swir1 = bands[5] if n > 5 else None
    elif n == 2:
        nir = bands[0]
        red = bands[1]
        redge2 = None
        swir1 = None
    else:
        nir = bands[0]
        red = bands[-1]
        redge2 = None
        swir1 = None

    eps = 1e-9
    ndvi = (nir - red) / (nir + red + eps)
    fdi = None
    if redge2 is not None and swir1 is not None:
        coef = (832.8 - 740.2) / (1613.7 - 740.2)
        nir_baseline = redge2 + (swir1 - redge2) * coef
        fdi = nir - nir_baseline
    return fdi, ndvi, nir


def detect_via_fdi(
    tile_path: Path,
    bbox: list[float] | None = None,
    aoi_id: str = "",
    fdi_min: float = FDI_MIN,
    ndvi_max: float = NDVI_MAX,
    min_area_m2: float = MIN_AREA_M2,
    max_features: int = MAX_FEATURES,
) -> DetectionFeatureCollection:
    """Threshold FDI + NDVI on the (clipped) tile and polygonize.

    Returns a schema-valid DetectionFeatureCollection with polygons in
    real WGS84 coordinates inside `bbox`. Falls back to NDVI-only
    threshold when FDI bands are absent.
    """
    bands, transform, crs = _read_window(Path(tile_path), bbox)
    fdi, ndvi, nir = _bands_to_fdi_ndvi(bands)

    if fdi is not None:
        candidate = (fdi > fdi_min) & (ndvi < ndvi_max) & np.isfinite(fdi) & np.isfinite(ndvi)
        score = fdi
    else:
        thresh = float(np.nanpercentile(nir, 92))
        candidate = (nir > thresh) & (ndvi < ndvi_max) & np.isfinite(nir)
        score = nir

    mask = candidate.astype(np.uint8)
    if mask.sum() == 0:
        logger.info("heuristic: zero candidate pixels for tile=%s", Path(tile_path).name)
        return DetectionFeatureCollection(type="FeatureCollection", features=[])

    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    feats: list[DetectionFeature] = []
    raw_polys = []
    for geom_dict, _val in rasterio.features.shapes(
        mask, mask=mask.astype(bool), transform=transform, connectivity=4,
    ):
        poly = shape(geom_dict)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_valid or poly.is_empty:
            continue
        area_m2 = poly.area
        if area_m2 < min_area_m2:
            continue
        raw_polys.append((area_m2, poly))

    raw_polys.sort(key=lambda x: -x[0])
    for i, (area_m2, poly) in enumerate(raw_polys[:max_features]):
        xs, ys = zip(*list(poly.exterior.coords))
        lons, lats = to_wgs.transform(xs, ys)
        wgs_coords = [list(zip(lons, lats))]
        # Mean FDI/NDVI inside polygon for confidence
        try:
            from rasterio.features import geometry_mask
            pmask = ~geometry_mask(
                [poly.__geo_interface__], out_shape=mask.shape,
                transform=transform, invert=False,
            )
            score_inside = score[pmask]
            score_inside = score_inside[np.isfinite(score_inside)]
            mean_score = float(score_inside.mean()) if score_inside.size else 0.0
        except Exception:
            mean_score = 0.0
        if fdi is not None:
            conf = float(min(0.95, max(0.40, 0.4 + mean_score / 0.05)))
            frac = float(min(1.0, max(0.0, mean_score / 0.05)))
        else:
            conf = float(min(0.85, max(0.35, mean_score)))
            frac = float(min(1.0, max(0.0, mean_score)))
        from geojson_pydantic import Polygon
        feats.append(DetectionFeature(
            type="Feature",
            geometry=Polygon(type="Polygon", coordinates=wgs_coords),
            properties=DetectionProperties(
                conf_raw=conf,
                conf_adj=conf,
                fraction_plastic=frac,
                area_m2=float(area_m2),
                age_days_est=0,
            ),
        ))

    logger.info(
        "heuristic: detected %d candidates for %s (fdi=%s, tile=%s)",
        len(feats), aoi_id or "<bbox>", "yes" if fdi is not None else "no", Path(tile_path).name,
    )
    return DetectionFeatureCollection(type="FeatureCollection", features=feats)
