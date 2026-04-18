"""Trajectory-aware biofouling confidence utilities."""
from __future__ import annotations

import math
from typing import Any

from geojson_pydantic import Polygon

from backend.core.schemas import (
    DetectionFeature,
    DetectionFeatureCollection,
    DetectionProperties,
)


def decay_constant_k(water_temp_c: float, chlorophyll_mg_m3: float) -> float:
    """Compute environmental decay constant k (day^-1)."""
    t_norm = min(max((water_temp_c - 15.0) / 20.0, 0.0), 1.0)
    c_norm = min(max(chlorophyll_mg_m3 / 1.5, 0.0), 1.0)
    return 0.030 * (1.0 + 0.45 * c_norm + 0.30 * t_norm)


def tau_days_from_environment(water_temp_c: float, chlorophyll_mg_m3: float) -> float:
    k = decay_constant_k(water_temp_c, chlorophyll_mg_m3)
    return 1.0 / max(k, 1e-6)


def adjusted_confidence(
    conf_raw: float,
    age_days: int,
    water_temp_c: float,
    chlorophyll_mg_m3: float,
    *,
    uncertainty_std: float = 0.08,
) -> dict[str, float]:
    """Compute environment-aware confidence with simple uncertainty bounds."""
    k = decay_constant_k(water_temp_c, chlorophyll_mg_m3)
    age = max(0.0, float(age_days))
    conf_adj = max(0.0, min(1.0, conf_raw * math.exp(-k * age)))
    spread = max(0.0, conf_adj * uncertainty_std)
    return {
        "k": float(k),
        "tau_days": float(1.0 / max(k, 1e-6)),
        "conf_adj": float(conf_adj),
        "conf_low": float(max(0.0, conf_adj - spread)),
        "conf_high": float(min(1.0, conf_adj + spread)),
    }


def apply_environmental_biofouling(
    fc: DetectionFeatureCollection,
    *,
    water_temp_c: float,
    chlorophyll_mg_m3: float,
) -> tuple[DetectionFeatureCollection, dict[str, Any]]:
    """Adjust `conf_adj` per detection based on environmental decay."""
    updated_features: list[DetectionFeature] = []
    k_values: list[float] = []

    for feat in fc.features:
        p = feat.properties
        stats = adjusted_confidence(
            conf_raw=float(p.conf_raw),
            age_days=int(p.age_days_est),
            water_temp_c=water_temp_c,
            chlorophyll_mg_m3=chlorophyll_mg_m3,
        )
        k_values.append(stats["k"])
        new_props = DetectionProperties(
            conf_raw=p.conf_raw,
            conf_adj=stats["conf_adj"],
            fraction_plastic=p.fraction_plastic,
            area_m2=p.area_m2,
            age_days_est=p.age_days_est,
            cls=p.cls,
        )
        geom_dict = feat.geometry.model_dump() if hasattr(feat.geometry, "model_dump") else feat.geometry
        updated_features.append(
            DetectionFeature(
                type="Feature",
                geometry=Polygon(**geom_dict),
                properties=new_props,
            )
        )

    meta = {
        "water_temp_c": round(float(water_temp_c), 3),
        "chlorophyll_mg_m3": round(float(chlorophyll_mg_m3), 4),
        "confidence_decay_k": round(sum(k_values) / len(k_values), 6) if k_values else 0.03,
    }
    return DetectionFeatureCollection(type="FeatureCollection", features=updated_features), meta
