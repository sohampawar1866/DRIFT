"""Pure numpy spectral indices. Single source of truth for train+serve.

FDI formula: Biermann et al. 2020, Scientific Reports (eq. 2). Reference
pixel values and unit test in backend/tests/unit/test_features.py.

Band indices below match MARIDA patches (11-band, 10m resampled). The Wave-0
probe artifact `wave0-probe-results.md` was not available at authoring time;
fallback to the MARIDA documented ordering per the RESEARCH.md recommendation:
[B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12, SCL]. If the probe later reveals
a different ordering, update these constants in one place — all consumers
(train + inference) import from this module.
"""
import numpy as np

# MARIDA documented band ordering (fallback when probe descriptions are None).
B2_IDX = 0
B3_IDX = 1
B4_IDX = 2
B5_IDX = 3
B6_IDX = 4
B7_IDX = 5
B8_IDX = 6
B8A_IDX = 7
B11_IDX = 8
B12_IDX = 9
# SCL (if present) would be at index 10; explicitly excluded from feature_stack.

# Sentinel-2 central wavelengths (nm) — Biermann 2020 FDI baseline interpolation.
LAMBDA_NIR = 832.8    # B8
LAMBDA_RE2 = 740.2    # B6
LAMBDA_SWIR1 = 1613.7 # B11
COEF_FDI = (LAMBDA_NIR - LAMBDA_RE2) / (LAMBDA_SWIR1 - LAMBDA_RE2)  # ~0.10601
EPS = 1e-9


def compute_fdi(bands: np.ndarray) -> np.ndarray:
    """Floating Debris Index (Biermann 2020, eq. 2).

    NIR_baseline = RE2 + (SWIR1 - RE2) * ((lambda_NIR - lambda_RE2) / (lambda_SWIR1 - lambda_RE2))
    FDI = NIR - NIR_baseline

    Args:
        bands: shape (..., N_bands) with N_bands >= 9 so B11_IDX=8 is reachable.
               Reflectance in [0, 1] (float32).
    Returns:
        FDI shape (...) matching leading dims of bands.
    """
    re2 = bands[..., B6_IDX]
    nir = bands[..., B8_IDX]
    swir = bands[..., B11_IDX]
    nir_baseline = re2 + (swir - re2) * COEF_FDI
    return nir - nir_baseline


def compute_ndvi(bands: np.ndarray) -> np.ndarray:
    """Normalized Difference Vegetation Index. (NIR - Red) / (NIR + Red)."""
    nir = bands[..., B8_IDX]
    red = bands[..., B4_IDX]
    return (nir - red) / (nir + red + EPS)


def compute_pi(bands: np.ndarray) -> np.ndarray:
    """Themistocleous 2020 Plastic Index. NIR / (NIR + Red)."""
    nir = bands[..., B8_IDX]
    red = bands[..., B4_IDX]
    return nir / (nir + red + EPS)


def feature_stack(bands: np.ndarray) -> np.ndarray:
    """Build 14-channel feature tensor: 11 bands + FDI + NDVI + PI.

    Args:
        bands: (H, W, N_bands). If N_bands > 11, extra channels (e.g., SCL at
               index 10 or 11) are dropped. If N_bands == 11, used as-is.
    Returns:
        (H, W, 14) float32.
    """
    if bands.shape[-1] > 11:
        bands = bands[..., :11]
    fdi = compute_fdi(bands)[..., None]
    ndvi = compute_ndvi(bands)[..., None]
    pi = compute_pi(bands)[..., None]
    return np.concatenate([bands, fdi, ndvi, pi], axis=-1).astype(np.float32)
