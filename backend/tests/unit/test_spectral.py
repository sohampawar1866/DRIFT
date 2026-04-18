from backend.ml.spectral import PolygonSpectralStats, gate_polygon


def test_gate_polygon_rejects_hard_ndvi() -> None:
    stats = PolygonSpectralStats(fdi_mean=0.01, ndvi_mean=0.35, pi_mean=0.6)
    decision = gate_polygon(0.8, stats)
    assert decision.accept is False
    assert decision.reject_reason == "ndvi_hard_ceiling"


def test_gate_polygon_accepts_and_adjusts_confidence() -> None:
    stats = PolygonSpectralStats(fdi_mean=-0.005, ndvi_mean=0.16, pi_mean=0.49)
    decision = gate_polygon(0.9, stats)
    assert decision.accept is True
    assert 0.0 <= decision.confidence_adjusted <= 1.0
    assert decision.confidence_adjusted < 0.9
    assert 0 <= decision.age_days_est <= 90
