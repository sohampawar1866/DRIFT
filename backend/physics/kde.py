"""2D KDE -> isodensity polygons in WGS84.

Pattern (D-07):
  1. sklearn.neighbors.KernelDensity with Gaussian kernel, Scott's bandwidth
     in meters (bandwidth = std * n^(-1/6)) -- safe default for UTM-meter
     inputs.
  2. Evaluate log-density on a 128x128 grid spanning positions_utm + pad.
  3. Threshold at the density value enclosing `level` fraction of total mass.
  4. skimage.measure.find_contours -> shapely Polygon -> .buffer(0) fix.
  5. Reproject each polygon UTM -> WGS84 via pyproj.Transformer(always_xy=True).

Returns an empty list when fewer than 3 positions are supplied (KDE undefined)
or when contour extraction fails.
"""
from __future__ import annotations

import numpy as np
from pyproj import Transformer
from shapely.geometry import Polygon
from skimage import measure
from sklearn.neighbors import KernelDensity


def _scotts_bandwidth(positions: np.ndarray) -> float:
    """Scott's-rule bandwidth in meters for UTM-meter inputs.

    Uses the combined std (sqrt of mean of per-axis variance) times n^(-1/6),
    floored at 1 m so degenerate (single-cluster, zero-variance) inputs still
    produce a well-defined KDE.
    """
    n = max(positions.shape[0], 2)
    # Per-axis std then RMS-combined; fall back to 1 m if degenerate.
    std = float(np.sqrt(np.mean(positions.std(axis=0) ** 2)))
    if not np.isfinite(std) or std < 1.0:
        std = 1.0
    return std * n ** (-1.0 / 6.0)


def kde_contour_polygons(
    positions_utm: np.ndarray,      # (N, 2) meters in zone `utm_epsg`
    utm_epsg: int,
    level: float = 0.90,             # fraction of mass enclosed
    grid_size: int = 128,
    pad_m: float = 5000.0,
) -> list[Polygon]:
    """Return list of WGS84 shapely Polygons enclosing `level` of the density.

    Parameters
    ----------
    positions_utm : np.ndarray, shape (N, 2)
        Particle positions in UTM meters.
    utm_epsg : int
        UTM EPSG code (e.g., 32643 for zone 43N). Used only to reproject
        the extracted contours back to WGS84.
    level : float, default 0.90
        Mass fraction enclosed by the returned contour (e.g., 0.90 = 90%
        highest-density region).
    grid_size : int, default 128
        Evaluation grid resolution along each axis.
    pad_m : float, default 5000.0
        Padding in meters added to the positions bounding box for the
        evaluation grid.

    Returns
    -------
    list[shapely.geometry.Polygon]
        WGS84 (lon, lat) polygons. Empty list if < 3 positions or contour
        extraction fails.
    """
    if positions_utm is None or positions_utm.shape[0] < 3:
        return []

    positions_utm = np.asarray(positions_utm, dtype=np.float64)
    bw = _scotts_bandwidth(positions_utm)
    kde = KernelDensity(kernel="gaussian", bandwidth=bw).fit(positions_utm)

    xmin, ymin = positions_utm.min(axis=0) - pad_m
    xmax, ymax = positions_utm.max(axis=0) + pad_m
    # Avoid a zero-extent axis (degenerate single-point inputs pass the >=3
    # guard when N>=3 but variance is ~0; pad guarantees a finite box).
    if xmax <= xmin:
        xmax = xmin + 1.0
    if ymax <= ymin:
        ymax = ymin + 1.0

    xs = np.linspace(xmin, xmax, grid_size)
    ys = np.linspace(ymin, ymax, grid_size)
    gx, gy = np.meshgrid(xs, ys)
    grid = np.column_stack([gx.ravel(), gy.ravel()])
    log_d = kde.score_samples(grid).reshape(grid_size, grid_size)
    d = np.exp(log_d)

    # Threshold enclosing `level` of mass: sort densities descending, cumsum,
    # pick the density value where cumulative mass crosses `level`.
    flat = d.ravel()
    order = np.argsort(flat)[::-1]
    cum = np.cumsum(flat[order])
    if cum[-1] <= 0:
        return []
    cutoff_idx = int(np.searchsorted(cum, level * cum[-1]))
    cutoff_idx = min(cutoff_idx, len(flat) - 1)
    threshold = float(flat[order[cutoff_idx]])

    contours = measure.find_contours(d, level=threshold)
    if not contours:
        return []

    to_wgs = Transformer.from_crs(
        f"EPSG:{utm_epsg}", "EPSG:4326", always_xy=True
    )
    out: list[Polygon] = []
    for c in contours:
        if len(c) < 4:
            continue
        # c columns are (row, col) in grid indices; map back to meter coords.
        rows, cols = c[:, 0], c[:, 1]
        xm = xmin + cols / (grid_size - 1) * (xmax - xmin)
        ym = ymin + rows / (grid_size - 1) * (ymax - ymin)
        lons, lats = to_wgs.transform(xm, ym)
        try:
            poly = Polygon(list(zip(lons, lats)))
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_valid and not poly.is_empty:
                # buffer(0) may yield a MultiPolygon; split into parts.
                if poly.geom_type == "MultiPolygon":
                    for sub in poly.geoms:
                        if sub.is_valid and not sub.is_empty:
                            out.append(sub)
                else:
                    out.append(poly)
        except Exception:
            continue
    return out
