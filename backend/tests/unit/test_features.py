"""Unit tests for backend/ml/features.py — Biermann FDI reference + ranges."""
import numpy as np

from backend.ml.features import (
    B4_IDX, B6_IDX, B8_IDX, B11_IDX,
    compute_fdi, compute_ndvi, compute_pi, feature_stack,
)


# Biermann 2020 Table 2 — floating-plastic pixel near Accra, Ghana.
# RESEARCH.md §"Biermann 2020 Reference Pixel"
BIERMANN_B6 = 0.078
BIERMANN_B8 = 0.095
BIERMANN_B11 = 0.063
# Expected FDI: NIR' = 0.078 + (0.063 - 0.078) * 0.10601 = 0.07641
# FDI = 0.095 - 0.07641 = 0.01859
EXPECTED_FDI = 0.01859


def _make_pixel(b4=0.0, b6=0.0, b8=0.0, b11=0.0) -> np.ndarray:
    bands = np.zeros((1, 1, 11), dtype=np.float32)
    bands[0, 0, B4_IDX] = b4
    bands[0, 0, B6_IDX] = b6
    bands[0, 0, B8_IDX] = b8
    bands[0, 0, B11_IDX] = b11
    return bands


def test_fdi_biermann_reference():
    """The non-negotiable unit test for ML-01."""
    bands = _make_pixel(b6=BIERMANN_B6, b8=BIERMANN_B8, b11=BIERMANN_B11)
    fdi = compute_fdi(bands)
    assert fdi.shape == (1, 1)
    assert abs(float(fdi[0, 0]) - EXPECTED_FDI) < 0.001, (
        f"FDI = {float(fdi[0, 0]):.6f}, expected {EXPECTED_FDI:.6f} "
        f"(tolerance 0.001)"
    )


def test_fdi_zero_when_baseline_equals_nir():
    """Constant spectrum => FDI ~ 0."""
    bands = _make_pixel(b6=0.05, b8=0.05, b11=0.05)
    fdi = compute_fdi(bands)
    assert abs(float(fdi[0, 0])) < 1e-6


def test_ndvi_water_range():
    bands = _make_pixel(b4=0.05, b8=0.06)
    ndvi = compute_ndvi(bands)
    assert -0.3 < float(ndvi[0, 0]) < 0.3


def test_pi_water_range():
    bands = _make_pixel(b4=0.05, b8=0.06)
    pi = compute_pi(bands)
    assert 0.0 < float(pi[0, 0]) < 1.0


def test_feature_stack_shape_and_dtype():
    bands = np.random.rand(64, 64, 11).astype(np.float32) * 0.3
    feats = feature_stack(bands)
    assert feats.shape == (64, 64, 14)
    assert feats.dtype == np.float32


def test_feature_stack_drops_extra_channels():
    """If SCL is appended as channel 11 or more, it must be dropped before indices."""
    bands = np.random.rand(32, 32, 12).astype(np.float32) * 0.3
    feats = feature_stack(bands)
    assert feats.shape == (32, 32, 14)


def test_feature_stack_finite():
    bands = np.random.rand(16, 16, 11).astype(np.float32) * 0.3
    feats = feature_stack(bands)
    assert np.isfinite(feats).all()
