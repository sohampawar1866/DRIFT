"""Phase 1 stub for forecast_drift. Returns schema-valid empty envelope.

Real implementation (Euler Lagrangian tracker, UTM-meter integration, 20
particles per detection, 72 h horizon, CMEMS + ERA5) lands in Phase 2.
"""
from backend.core.config import Settings
from backend.core.schemas import DetectionFeatureCollection, ForecastEnvelope


def forecast_drift(
    detections: DetectionFeatureCollection,
    cfg: Settings,
) -> ForecastEnvelope:
    """Phase 1 stub. Returns a schema-valid empty ForecastEnvelope so the
    full CLI chain (ml -> physics -> mission) can round-trip JSON cleanly
    before Phase 2 implements the real tracker.
    """
    return ForecastEnvelope(
        source_detections=detections,
        frames=[],
        windage_alpha=cfg.physics.windage_alpha,
    )
