"""Round-trip + extra=forbid + alias + frozen + bounds tests for core schemas."""
import json
import pytest
from pydantic import ValidationError

from backend.core.schemas import (
    DetectionFeature,
    DetectionFeatureCollection,
    DetectionProperties,
)


def _sample_props(i: int) -> DetectionProperties:
    return DetectionProperties(
        conf_raw=0.5 + i * 0.01,
        conf_adj=0.4 + i * 0.01,
        fraction_plastic=0.1 + i * 0.01,
        area_m2=500.0 + i * 10,
        age_days_est=i,
    )


def _sample_feature(i: int) -> DetectionFeature:
    eps = 0.001 * (i + 1)
    return DetectionFeature(
        type="Feature",
        geometry={
            "type": "Polygon",
            "coordinates": [[[0, 0], [eps, 0], [eps, eps], [0, eps], [0, 0]]],
        },
        properties=_sample_props(i),
    )


def test_feature_collection_round_trip():
    fc = DetectionFeatureCollection(
        type="FeatureCollection",
        features=[_sample_feature(i) for i in range(10)],
    )
    text = fc.model_dump_json(by_alias=True)
    back = DetectionFeatureCollection.model_validate_json(text)
    assert back.model_dump(by_alias=True) == fc.model_dump(by_alias=True)


def test_extra_forbid_rejects_unknown_field():
    with pytest.raises(ValidationError):
        DetectionProperties(
            conf_raw=0.5, conf_adj=0.4, fraction_plastic=0.1,
            area_m2=500.0, age_days_est=0,
            age_days=0,  # INTENTIONAL typo -- must fail
        )


def test_class_alias_both_ways():
    p1 = DetectionProperties(conf_raw=0.5, conf_adj=0.4, fraction_plastic=0.1,
                             area_m2=500.0, age_days_est=0)
    p2 = DetectionProperties.model_validate({
        "conf_raw": 0.5, "conf_adj": 0.4, "fraction_plastic": 0.1,
        "area_m2": 500.0, "age_days_est": 0, "class": "plastic",
    })
    dumped = json.loads(p1.model_dump_json(by_alias=True))
    assert dumped["class"] == "plastic"
    assert p1 == p2


def test_frozen_rejects_mutation():
    p = DetectionProperties(conf_raw=0.5, conf_adj=0.4, fraction_plastic=0.1,
                            area_m2=500.0, age_days_est=0)
    with pytest.raises((TypeError, ValidationError)):
        p.conf_raw = 0.9  # frozen=True must block this


def test_bounds_enforced():
    with pytest.raises(ValidationError):
        DetectionProperties(conf_raw=1.5, conf_adj=0.4, fraction_plastic=0.1,
                            area_m2=500.0, age_days_est=0)
    with pytest.raises(ValidationError):
        DetectionProperties(conf_raw=0.5, conf_adj=0.4, fraction_plastic=0.1,
                            area_m2=-1.0, age_days_est=0)
    with pytest.raises(ValidationError):
        DetectionProperties(conf_raw=0.5, conf_adj=0.4, fraction_plastic=0.1,
                            area_m2=500.0, age_days_est=-1)
