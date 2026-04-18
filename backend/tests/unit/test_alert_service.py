from backend.services.alert_service import evaluate_deposition_alerts


def _polygon(center_lon: float, center_lat: float, d: float = 0.01) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [center_lon - d, center_lat - d],
            [center_lon + d, center_lat - d],
            [center_lon + d, center_lat + d],
            [center_lon - d, center_lat + d],
            [center_lon - d, center_lat - d],
        ]],
    }


def test_segment_triggered_when_density_and_persistence_cross_threshold() -> None:
    forecast_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": _polygon(80.27, 13.08),
                "properties": {
                    "type": "deposition_hotspot",
                    "density": 4.2,
                    "forecast_hour": 96,
                },
            }
        ],
    }
    payload = evaluate_deposition_alerts(
        forecast_fc,
        aoi_id="chennai",
        forecast_hours=96,
        density_threshold_per_segment=3,
        persistence_hours_threshold=72,
    )

    assert payload["triggered"] is True
    assert payload["coastal_segments_triggered"] >= 1
    assert payload["segment_alerts"]
    assert any(seg.get("triggered") for seg in payload["segment_alerts"])
    assert payload["notifications"]


def test_segment_not_triggered_when_below_density_threshold() -> None:
    forecast_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": _polygon(80.27, 13.08),
                "properties": {
                    "type": "deposition_hotspot",
                    "density": 0.8,
                    "forecast_hour": 120,
                },
            }
        ],
    }
    payload = evaluate_deposition_alerts(
        forecast_fc,
        aoi_id="chennai",
        forecast_hours=120,
        density_threshold_per_segment=3,
        persistence_hours_threshold=72,
    )

    assert payload["triggered"] is False
    assert payload["coastal_segments_triggered"] == 0
    assert payload["notifications"] == []
