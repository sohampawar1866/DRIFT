"""PHYS-05 real-data smoke test. Skips if data/env/*.nc absent."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.core.config import Settings
from backend.core.schemas import (
    DetectionFeature,
    DetectionFeatureCollection,
    DetectionProperties,
)
from backend.physics.env_data import load_env_stack
from backend.physics.tracker import forecast_drift


CMEMS = Path("data/env/cmems_currents_72h.nc")
ERA5 = Path("data/env/era5_winds_72h.nc")

# PHYS-05 Deccan Plateau exclusion box (lon_min, lon_max, lat_min, lat_max).
# Any particle landing inside this rectangle has crossed land -- tracker bug.
# Beached particles (D-15) retain their last valid sea position, so they
# naturally pass this check; only propagation-across-land would fail it.
DECCAN_BBOX = (80.0, 88.0, 15.0, 24.0)


def _mannar_detection(lon: float, lat: float) -> DetectionFeature:
    d = 0.001  # ~200 m side
    coords = [[
        [lon - d, lat - d], [lon + d, lat - d],
        [lon + d, lat + d], [lon - d, lat + d],
        [lon - d, lat - d],
    ]]
    return DetectionFeature(
        type="Feature",
        geometry={"type": "Polygon", "coordinates": coords},
        properties=DetectionProperties(
            conf_raw=0.8, conf_adj=0.8, fraction_plastic=0.3,
            area_m2=400.0, age_days_est=0,
        ),
    )


@pytest.mark.skipif(
    not (CMEMS.exists() and ERA5.exists()),
    reason="data/env/*.nc not present (run scripts/fetch_demo_env.py)",
)
def test_gulf_of_mannar_72h_smoke():
    rng = np.random.default_rng(0)
    feats = []
    for _ in range(10):
        dlon = rng.normal(0, 0.02)
        dlat = rng.normal(0, 0.02)
        feats.append(_mannar_detection(78.9 + dlon, 9.2 + dlat))
    fc = DetectionFeatureCollection(type="FeatureCollection", features=feats)
    cfg = Settings()
    env = load_env_stack(CMEMS, ERA5, cfg.physics.horizon_hours)
    envelope = forecast_drift(fc, cfg, env=env)

    assert len(envelope.frames) == 73

    lon_min, lon_max, lat_min, lat_max = DECCAN_BBOX
    for frame in envelope.frames:
        for (lon, lat) in frame.particle_positions:
            assert np.isfinite(lon) and np.isfinite(lat), \
                f"NaN at hour={frame.hour}: ({lon}, {lat})"
            assert 68.0 <= lon <= 95.0, f"lon out of basin at hour={frame.hour}: {lon}"
            assert 0.0 <= lat <= 25.0, f"lat out of basin at hour={frame.hour}: {lat}"
            assert not (lon_min < lon < lon_max and lat_min < lat < lat_max), \
                f"particle entered Deccan Plateau at hour {frame.hour}: ({lon:.3f}, {lat:.3f})"

    final = envelope.frames[-1]
    min_survivors = 10 * cfg.physics.particles_per_detection // 4
    assert len(final.particle_positions) >= min_survivors, \
        f"only {len(final.particle_positions)} particles survived (need >= {min_survivors})"
