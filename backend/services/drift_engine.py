"""drift_engine — thin service wrapper over backend.physics.tracker.forecast_drift.

Integration layer:
- Accepts API-shape `detected_geojson` from ai_detector
- Rebuilds a `DetectionFeatureCollection` (FROZEN pydantic)
- Runs the real Euler Lagrangian tracker (UTM meters, windage α=0.02)
- Adapts the ForecastEnvelope back to the legacy API dict shape
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.services.env_service import fetch_or_load_env_assets

logger = logging.getLogger(__name__)


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

    Legacy /forecast shape: a single GeoJSON FeatureCollection of "drifted
    polygons" with `forecast_hour` property. We surface the density polygons
    from the requested horizon frame (+24/+48/+72), plus the source-detection
    polygons snapped to the final particle positions as "drifted" polygons.
    """
    # Pick the closest available density frame to the requested horizon.
    target_hour = int(forecast_hours)
    frame = next((f for f in env.frames if f.hour == target_hour), None)
    if frame is None:
        # Fall back to the latest frame with density content.
        with_density = [f for f in env.frames if f.density_polygons.features]
        frame = with_density[-1] if with_density else env.frames[-1]

    features: list[dict[str, Any]] = []

    # Density polygons (isodensity contours) — the headline output.
    for dp in frame.density_polygons.features:
        geom = dp.geometry.model_dump() if hasattr(dp.geometry, "model_dump") else dp.geometry
        props = dict(dp.properties) if dp.properties else {}
        feature_type = str(props.get("type", "density_contour"))
        layer = str(props.get("layer", "drift_heatmap"))
        props.update({
            "forecast_hour": target_hour,
            "aoi_id": aoi_id,
            "type": feature_type,
            "layer": layer,
        })
        if feature_type == "deposition_hotspot":
            props.setdefault("render_color", "#ef4444")
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": props,
        })

    # Raw particle positions for the frame (for UI overlays).
    # Represent as small point-wrapped polygons? Cleanest: emit them as a single
    # MultiPoint-like set in a "particles" property. We'll keep it simple:
    # emit one Point feature per detection cluster (first particle of each).
    # Legacy shape tolerates extra features, so this is additive.
    n_particles = len(frame.particle_positions)
    if n_particles > 0:
        step = max(1, n_particles // 50)   # cap at ~50 points for UI smoothness
        for i in range(0, n_particles, step):
            lon, lat = frame.particle_positions[i]
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "forecast_hour": target_hour,
                    "aoi_id": aoi_id,
                    "type": "particle",
                },
            })

    tracker_metadata = dict(getattr(env, "tracker_metadata", {}) or {})
    tracker_metadata.setdefault("requested_forecast_hour", target_hour)
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": tracker_metadata,
    }


def simulate_drift(
    detected_geojson: dict[str, Any],
    aoi_id: str,
    forecast_hours: int,
) -> dict[str, Any]:
    """Forecast plastic drift over `forecast_hours` given detected polygons.
    """
    if not detected_geojson.get("features"):
        raise RuntimeError(f"drift_engine: zero detections for {aoi_id}; cannot run drift")

    try:
        from backend.core.config import Settings
        from backend.physics.tracker import forecast_drift
        from backend.physics.env_data import load_env_stack

        cfg = Settings()
        # Clamp horizon to requested forecast_hours so tracker doesn't integrate past it.
        cfg.physics.horizon_hours = int(forecast_hours)
        # API latency knob: use a small particle budget on hot endpoints.
        # Heavier pre-bake/offline flows can run with larger values.
        cfg.physics.particles_per_detection = 3

        detections_fc = _api_shape_to_detection_fc(detected_geojson)
        if not detections_fc.features:
            raise RuntimeError(f"drift_engine: detection conversion dropped all features for {aoi_id}")

        # Try dynamic cached live env assets first, then static prebaked files.
        env = None
        env_source = ""
        env_errors: list[str] = []
        bbox = _api_detection_bounds(detected_geojson)

        if bbox is not None:
            try:
                live_assets = fetch_or_load_env_assets(
                    aoi_id,
                    [bbox[0], bbox[1], bbox[2], bbox[3]],
                    horizon_hours=int(forecast_hours),
                )
                paths = live_assets.get("paths", {}) if isinstance(live_assets, dict) else {}
                live_cmems = Path(paths["currents"]) if isinstance(paths, dict) and paths.get("currents") else None
                live_era5 = Path(paths["winds"]) if isinstance(paths, dict) and paths.get("winds") else None
                if live_cmems and live_era5 and live_cmems.exists() and live_era5.exists():
                    env = load_env_stack(live_cmems, live_era5, int(forecast_hours))
                    env_source = str(live_assets.get("source") if isinstance(live_assets, dict) else "live_fetch")
                    logger.info(
                        "drift_engine: loaded dynamic env assets for %s (source=%s)",
                        aoi_id,
                        live_assets.get("source") if isinstance(live_assets, dict) else "unknown",
                    )
                else:
                    env_errors.append("dynamic env assets unavailable or incomplete")
            except Exception as env_e:
                env_errors.append(f"dynamic env asset path failed: {env_e}")

        cmems = cfg.physics.cmems_path
        era5 = cfg.physics.era5_path
        if env is None and cmems.exists() and era5.exists():
            try:
                env = load_env_stack(cmems, era5, int(forecast_hours))
                env_source = "static_prebaked"
                logger.info("drift_engine: loaded real CMEMS+ERA5 for %s", aoi_id)
            except Exception as env_e:
                env_errors.append(f"static env load failed: {env_e}")
        elif env is None:
            env_errors.append(
                f"static env files not found at {cmems} and {era5}"
            )

        if env is None:
            details = "; ".join(env_errors) if env_errors else "unknown environment loading error"
            raise RuntimeError(
                "drift_engine: real environment data unavailable. "
                "Provide live CMEMS/ERA5 credentials or valid static env files. "
                f"Details: {details}"
            )

        envelope = forecast_drift(detections_fc, cfg, env=env)
        if isinstance(envelope.tracker_metadata, dict):
            merged_meta = dict(envelope.tracker_metadata)
            merged_meta["environment_source"] = env_source
            envelope = envelope.model_copy(update={"tracker_metadata": merged_meta})
        logger.info(
            "drift_engine: real tracker OK for %s (frames=%d, particles/det=%d)",
            aoi_id, len(envelope.frames), cfg.physics.particles_per_detection,
        )
        return _envelope_to_api_shape(envelope, aoi_id, forecast_hours)
    except Exception as e:
        raise RuntimeError(f"drift_engine: real forecast failed for {aoi_id}: {e}") from e
