"""Integration test: run_inference on a real MARIDA patch with real weights.

This is the Phase 1 exit gate for ML-04. Asserts:
  - Output is a schema-valid DetectionFeatureCollection (round-trip via JSON).
  - Polygon count is in a sane band (0 < N < 500) -- neither dead model nor noise storm.
  - Every DetectionProperties field is within declared bounds.
  - area_m2 >= MIN_AREA_M2 (the filter is working).
"""
from pathlib import Path
import pytest

from backend.core.config import Settings
from backend.core.schemas import DetectionFeatureCollection
from backend.ml.inference import run_inference


MARIDA_ROOT = Path("MARIDA/patches")


@pytest.fixture(scope="module")
def sample_tile() -> Path:
    """Find any MARIDA patch .tif (excluding _cl.tif and _conf.tif)."""
    if not MARIDA_ROOT.exists():
        pytest.skip(f"MARIDA dataset not at {MARIDA_ROOT}")
    for scene in MARIDA_ROOT.iterdir():
        if not scene.is_dir():
            continue
        for f in sorted(scene.iterdir()):
            if f.suffix == ".tif" and "_cl" not in f.stem and "_conf" not in f.stem:
                return f
    pytest.skip("No MARIDA patch found")


def test_real_inference_emits_schema_valid_fc(sample_tile: Path):
    cfg = Settings()
    fc = run_inference(sample_tile, cfg)

    # Type check
    assert isinstance(fc, DetectionFeatureCollection)

    # Round-trip via JSON (this is the schema round-trip at the inference boundary)
    text = fc.model_dump_json(by_alias=True)
    back = DetectionFeatureCollection.model_validate_json(text)
    assert back.model_dump(by_alias=True) == fc.model_dump(by_alias=True)


def test_real_inference_polygon_count_sane(sample_tile: Path):
    cfg = Settings()
    fc = run_inference(sample_tile, cfg)
    n = len(fc.features)
    # Real inference should detect at least one polygon and avoid pathological
    # over-segmentation on a single patch.
    # If N > 500: noise storm -- bump min_area_m2 or threshold in config.yaml.
    assert n > 0, (
        "Real inference produced 0 polygons on a MARIDA patch. "
        "Check checkpoint compatibility and confidence threshold settings."
    )
    assert n < 500, f"Noise storm: {n} polygons (>=500 means tune config.yaml)"


def test_real_inference_properties_in_bounds(sample_tile: Path):
    cfg = Settings()
    fc = run_inference(sample_tile, cfg)
    for feat in fc.features:
        p = feat.properties
        assert 0.0 <= p.conf_raw <= 1.0
        assert 0.0 <= p.conf_adj <= 1.0
        assert 0.0 <= p.fraction_plastic <= 1.0
        assert p.area_m2 >= cfg.ml.min_area_m2, (
            f"area_m2 {p.area_m2} < min_area_m2 {cfg.ml.min_area_m2}"
        )
        assert 0 <= p.age_days_est <= 90
        assert p.cls == "plastic"
