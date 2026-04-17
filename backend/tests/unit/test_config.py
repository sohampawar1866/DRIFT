"""Tests for pydantic-settings YAML + env-nested-delimiter override."""
import pytest

from backend.core.config import Settings


def test_yaml_loaded_by_default():
    s = Settings()
    # Values below are what config.yaml says (not hardcoded defaults).
    assert s.ml.weights_source == "dummy"
    assert s.ml.min_area_m2 == 200.0
    assert s.ml.patch_size == 256
    assert s.physics.windage_alpha == 0.02
    assert s.physics.horizon_hours == 72
    assert s.mission.top_k == 10


def test_env_override_ml_weights_source(monkeypatch):
    monkeypatch.setenv("ML__WEIGHTS_SOURCE", "our_real")
    s = Settings()
    assert s.ml.weights_source == "our_real"


def test_env_override_nested_physics(monkeypatch):
    monkeypatch.setenv("PHYSICS__WINDAGE_ALPHA", "0.05")
    s = Settings()
    assert s.physics.windage_alpha == 0.05


def test_nested_submodels_all_constructible():
    s = Settings()
    assert s.ml is not None
    assert s.physics is not None
    assert s.mission is not None
