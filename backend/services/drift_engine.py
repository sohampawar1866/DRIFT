"""drift_engine — thin service wrapper over backend.physics.tracker.forecast_drift.

Integration layer:
- Accepts API-shape `detected_geojson` from ai_detector
- Rebuilds a `DetectionFeatureCollection` (FROZEN pydantic)
- Runs the real Euler Lagrangian tracker (UTM meters, windage α=0.02)
- Adapts the ForecastEnvelope back to the legacy API dict shape

Environment data policy:
    1. If `data/env/cmems_currents_72h.nc` + `data/env/era5_winds_72h.nc` exist,
       use them (real CMEMS + ERA5 pre-staged via scripts/fetch_demo_env.py).
    2. Otherwise, build a minimal synthetic EnvStack in-memory (uniform weak
       eastward current, zero wind) so the tracker still produces a defensible
       drift trajectory for demo. The pipeline stays real; only the forcing
       degrades gracefully.
    3. If even that fails, fall back to mock_data.get_mock_forecast_geojson.

This mirrors CONTEXT D-12 (silent auto-fallback, demo never crashes) and D-05
(fail-loud only for the fetch script, not the service layer).
"""
from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

from backend.services.mock_data import get_mock_forecast_geojson
from backend.services.runtime_flags import strict_mode_enabled

logger = logging.getLogger(__name__)

_SYNTH_LON_MIN, _SYNTH_LON_MAX = -180.0, 180.0
_SYNTH_LAT_MIN, _SYNTH_LAT_MAX = -60.0, 60.0
_SYNTH_GRID_STEP = 2.0     # degrees — coarse grid keeps env dataset small
_SYNTH_GRID_STEP_MIN = 0.25
_SYNTH_U_CURRENT = 0.15    # m/s eastward (gentle monsoon-scale drift)
_SYNTH_V_CURRENT = -0.05   # m/s northward (slight southward component)


def _iter_coords(node):
    if not isinstance(node, (list, tuple)):
        return
    if len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
        yield float(node[0]), float(node[1])
        return
    for child in node:
        yield from _iter_coords(child)


def _api_detection_bounds(api_fc: dict[str, Any]) -> tuple[float, float, float, float] | None:
    min_lon = min_lat = float("inf")
    max_lon = max_lat = float("-inf")

    for feat in api_fc.get("features", []):
        geom = feat.get("geometry", {})
        for lon, lat in _iter_coords(geom.get("coordinates", [])):
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)

    if min_lon == float("inf"):
        return None
    return (min_lon, min_lat, max_lon, max_lat)


def _build_synthetic_env(horizon_hours: int, bbox: tuple[float, float, float, float] | None = None):
    """Construct a minimal EnvStack with uniform weak currents + zero wind.

    Only used when real CMEMS/ERA5 NetCDFs are not pre-staged on disk.
    Produces a constant-current field (0.15 m/s east, -0.05 m/s north) over
    the Indian Ocean bbox and zero wind. The tracker integrates this into a
    gentle eastward drift — not scientifically accurate, but good enough to
    demonstrate the chain when live data isn't available.
    """
    import xarray as xr

    from backend.physics.env_data import from_synthetic

    if bbox is None:
        lon_min, lat_min, lon_max, lat_max = (
            _SYNTH_LON_MIN,
            _SYNTH_LAT_MIN,
            _SYNTH_LON_MAX,
            _SYNTH_LAT_MAX,
        )
        step = _SYNTH_GRID_STEP
    else:
        min_lon, min_lat, max_lon, max_lat = bbox
        margin = 2.0
        lon_min = max(_SYNTH_LON_MIN, min_lon - margin)
        lon_max = min(_SYNTH_LON_MAX, max_lon + margin)
        lat_min = max(_SYNTH_LAT_MIN, min_lat - margin)
        lat_max = min(_SYNTH_LAT_MAX, max_lat + margin)

        lon_span = max(0.5, lon_max - lon_min)
        lat_span = max(0.5, lat_max - lat_min)
        # Keep synthetic env light for API latency while preserving interpolation stability.
        step = max(_SYNTH_GRID_STEP_MIN, max(lon_span / 48.0, lat_span / 48.0))

    lons = np.arange(lon_min, lon_max + step, step)
    lats = np.arange(lat_min, lat_max + step, step)
    hours = np.arange(horizon_hours + 2)  # +2 buffer for interpolation at t=horizon
    times = np.datetime64("2024-01-01T00:00:00", "ns") + (hours * np.timedelta64(3600, "s"))

    shape = (len(times), len(lats), len(lons))
    uo = np.full(shape, _SYNTH_U_CURRENT, dtype=np.float32)
    vo = np.full(shape, _SYNTH_V_CURRENT, dtype=np.float32)
    u10 = np.zeros(shape, dtype=np.float32)
    v10 = np.zeros(shape, dtype=np.float32)

    currents = xr.Dataset(
        data_vars={
            "uo": (("time", "latitude", "longitude"), uo,
                   {"standard_name": "eastward_sea_water_velocity", "units": "m s-1"}),
            "vo": (("time", "latitude", "longitude"), vo,
                   {"standard_name": "northward_sea_water_velocity", "units": "m s-1"}),
        },
        coords={"time": times, "latitude": lats, "longitude": lons},
    )
    winds = xr.Dataset(
        data_vars={
            "u10": (("time", "latitude", "longitude"), u10,
                    {"standard_name": "eastward_wind", "units": "m s-1"}),
            "v10": (("time", "latitude", "longitude"), v10,
                    {"standard_name": "northward_wind", "units": "m s-1"}),
        },
        coords={"time": times, "latitude": lats, "longitude": lons},
    )
    return from_synthetic(currents, winds, horizon_hours=horizon_hours)


def _api_shape_to_detection_fc(api_fc: dict[str, Any]):
    """Reconstruct a DetectionFeatureCollection from the legacy API dict shape.

    Builds DetectionProperties from the adapter fields (confidence, area, etc.),
    synthesizing any missing properties with sensible defaults so the pydantic
    validator passes.
    """
    from backend.core.schemas import (
        DetectionFeature,
        DetectionFeatureCollection,
        DetectionProperties,
    )
    from geojson_pydantic import Polygon

    features: list[DetectionFeature] = []
    for api_feat in api_fc.get("features", []):
        props_raw = api_feat.get("properties", {})
        conf = float(props_raw.get("confidence", 0.5))
        # Legacy mock shape uses "age_days"; real shape uses "age_days_est".
        age = int(props_raw.get("age_days", props_raw.get("age_days_est", 0)))
        area = float(props_raw.get("area_sq_meters", props_raw.get("area_m2", 200.0)))
        frac = float(props_raw.get("fraction_plastic", min(conf, 1.0)))
        props = DetectionProperties(
            conf_raw=min(max(conf, 0.0), 1.0),
            conf_adj=min(max(conf, 0.0), 1.0),
            fraction_plastic=min(max(frac, 0.0), 1.0),
            area_m2=max(area, 0.0),
            age_days_est=max(age, 0),
        )
        geom = Polygon(**api_feat["geometry"])
        features.append(DetectionFeature(type="Feature", geometry=geom, properties=props))
    return DetectionFeatureCollection(type="FeatureCollection", features=features)


def _envelope_to_api_shape(env, aoi_id: str, forecast_hours: int) -> dict[str, Any]:
    """Adapt FROZEN ForecastEnvelope → legacy API dict shape.
    
    Includes both drifting clusters and red-hue deposition clusters.
    """
    target_hour = int(forecast_hours)
    frame = next((f for f in env.frames if f.hour == target_hour), None)
    if frame is None:
        frame = env.frames[-1]

    features: list[dict[str, Any]] = []

    # 1. Drifting plume density contours
    for dp in frame.density_polygons.features:
        geom = dp.geometry.model_dump() if hasattr(dp.geometry, "model_dump") else dp.geometry
        props = dict(dp.properties) if dp.properties else {}
        props.update({"forecast_hour": target_hour, "aoi_id": aoi_id, "type": "density_contour"})
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    # 2. Deposition (Beached) hotspots - RED HUE
    for dp in frame.deposition_polygons.features:
        geom = dp.geometry.model_dump() if hasattr(dp.geometry, "model_dump") else dp.geometry
        props = dict(dp.properties) if dp.properties else {}
        props.update({
            "forecast_hour": target_hour, 
            "aoi_id": aoi_id, 
            "type": "deposition_hotspot",
            "fill": "#ff0000",
            "stroke": "#8b0000",
            "description": "Predicted landfall point (Red Hue)"
        })
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    # 3. Individual drifting particle points
    n_particles = len(frame.particle_positions)
    if n_particles > 0:
        step = max(1, n_particles // 30)
        for i in range(0, n_particles, step):
            lon, lat = frame.particle_positions[i]
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"forecast_hour": target_hour, "aoi_id": aoi_id, "type": "particle"}
            })

    return {"type": "FeatureCollection", "features": features}


def simulate_drift(
    detected_geojson: dict[str, Any],
    aoi_id: str,
    forecast_hours: int,
) -> dict[str, Any]:
<<<<<<< HEAD
    """Forecast plastic drift over `forecast_hours` given detected polygons.

    Falls back to mock forecast on failures unless strict mode is enabled.
    """
    strict = strict_mode_enabled()

=======
    """Forecast plastic drift and deposition using live environmental data."""
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
    if os.environ.get("DRIFT_FORCE_MOCK", "").strip() == "1":
        return get_mock_forecast_geojson(aoi_id, forecast_hours)

    if not detected_geojson.get("features"):
<<<<<<< HEAD
        if strict:
            raise RuntimeError(
                f"drift_engine: zero detections for {aoi_id}; strict mode disallows mock fallback"
            )
        logger.info("drift_engine: zero detections for %s → mock forecast (nothing to drift)", aoi_id)
=======
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
        return get_mock_forecast_geojson(aoi_id, forecast_hours)

    try:
        from backend.core.config import Settings
        from backend.physics.tracker import forecast_drift
        from backend.services.env_service import EnvService

        cfg = Settings()
<<<<<<< HEAD
        # Clamp horizon to requested forecast_hours so tracker doesn't integrate past it.
        cfg.physics.horizon_hours = int(forecast_hours)
        # API latency knob: use a small particle budget on hot endpoints.
        # Heavier pre-bake/offline flows can run with larger values.
        cfg.physics.particles_per_detection = 3

        detections_fc = _api_shape_to_detection_fc(detected_geojson)
        if not detections_fc.features:
            if strict:
                raise RuntimeError(
                    f"drift_engine: detection conversion dropped all features for {aoi_id}"
                )
            logger.info("drift_engine: detections dropped in conversion → mock for %s", aoi_id)
            return get_mock_forecast_geojson(aoi_id, forecast_hours)

        # Try real CMEMS/ERA5 first; if missing, build synthetic.
        env = None
        cmems = cfg.physics.cmems_path
        era5 = cfg.physics.era5_path
        if cmems.exists() and era5.exists():
            try:
                from backend.physics.env_data import load_env_stack
                env = load_env_stack(cmems, era5, int(forecast_hours))
                logger.info("drift_engine: loaded real CMEMS+ERA5 for %s", aoi_id)
            except Exception as env_e:
                logger.warning(
                    "drift_engine: real env data load failed (%s) — falling to synthetic", env_e,
                )
                env = None
        if env is None:
            bbox = _api_detection_bounds(detected_geojson)
            env = _build_synthetic_env(int(forecast_hours), bbox=bbox)
            logger.info("drift_engine: using synthetic env (constant eastward current)")

=======
        env_svc = EnvService(cfg)

        # 1. Extract coordinates for live subsetting
        lons, lats = [], []
        for f in detected_geojson["features"]:
            coords = f["geometry"]["coordinates"][0] # Polygon exterior
            lons.extend([c[0] for c in coords])
            lats.extend([c[1] for c in coords])

        # 2. Fetch LIVE environment stack (Currents, Winds, SST)
        env = env_svc.fetch_live_stack(lons, lats)
        logger.info("drift_engine: using live curated environment for %s", aoi_id)

        detections_fc = _api_shape_to_detection_fc(detected_geojson)
        
        # 3. Run the tracking with beached support
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)
        envelope = forecast_drift(detections_fc, cfg, env=env)
        
        # 4. (Optional) Run Alerting logic
        try:
            from backend.services.alert_service import AlertService
            alert_svc = AlertService(cfg)
            alert_svc.analyze_and_trigger(aoi_id, envelope)
        except Exception as alert_e:
            logger.warning("drift_engine: alerting failed: %s", alert_e)

        return _envelope_to_api_shape(envelope, aoi_id, forecast_hours)
    except Exception as e:
        if strict:
            raise RuntimeError(f"drift_engine: real forecast failed for {aoi_id}: {e}") from e
        logger.warning("drift_engine: real forecast failed for %s: %s → mock", aoi_id, e)
        return get_mock_forecast_geojson(aoi_id, forecast_hours)
