"""Coastal hit-density alert service (OceanTrace).

Bins beached particle positions into 5-km coastline segments via a
simple lat/lon grid (degrees-per-km approximation; good enough for an
operations alert layer). When a segment crosses the threshold, builds
an Alert and dispatches via webhook + email placeholders. If creds
unset, append-logs alerts to alerts.jsonl so the alert history survives.
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEG_PER_KM = 1.0 / 111.0
ALERT_LOG = Path("alerts.jsonl")


class Alert(BaseModel):
    segment_id: str
    centroid: tuple[float, float]
    hit_count: int
    severity: Literal["low", "elevated", "critical"]
    aoi_id: str | None = None
    timestamp: str | None = None


def _segment_key(lon: float, lat: float, segment_km: float) -> str:
    cell = segment_km * DEG_PER_KM
    ix = int(lon // cell)
    iy = int(lat // cell)
    return f"{ix}:{iy}"


def _segment_centroid(seg_id: str, segment_km: float) -> tuple[float, float]:
    cell = segment_km * DEG_PER_KM
    ix, iy = (int(p) for p in seg_id.split(":"))
    return (ix * cell + cell / 2, iy * cell + cell / 2)


def _severity(count: int, threshold: int) -> Literal["low", "elevated", "critical"]:
    if count >= threshold * 4:
        return "critical"
    if count >= threshold * 2:
        return "elevated"
    return "low"


def coastline_hit_density(
    deposited_lonlat: list[tuple[float, float, float]] | list[tuple[float, float]],
    segment_length_km: float = 5.0,
    threshold: int = 10,
    aoi_id: str | None = None,
) -> list[Alert]:
    """Bin beached particles into 5km cells. Emit Alert per cell hit_count >= threshold."""
    counts: dict[str, int] = defaultdict(int)
    for entry in deposited_lonlat:
        lon, lat = float(entry[0]), float(entry[1])
        counts[_segment_key(lon, lat, segment_length_km)] += 1

    alerts: list[Alert] = []
    ts = datetime.utcnow().isoformat() + "Z"
    for seg_id, n in counts.items():
        if n < threshold:
            continue
        alerts.append(Alert(
            segment_id=seg_id,
            centroid=_segment_centroid(seg_id, segment_length_km),
            hit_count=n,
            severity=_severity(n, threshold),
            aoi_id=aoi_id,
            timestamp=ts,
        ))
    return sorted(alerts, key=lambda a: -a.hit_count)


def dispatch_alerts(alerts: list[Alert]) -> dict:
    """Send to webhook + email if env vars set, else append-log to alerts.jsonl.

    Returns a small report dict with dispatched/logged counts.
    """
    webhook = os.environ.get("ALERT_WEBHOOK_URL")
    email_to = os.environ.get("ALERT_EMAIL_TO")
    dispatched = 0
    logged = 0

    for a in alerts:
        payload = a.model_dump()
        if webhook:
            try:
                import requests
                requests.post(webhook, json=payload, timeout=5)
                dispatched += 1
            except Exception as e:
                logger.warning("alert webhook failed: %s", e)
        if email_to:
            logger.info("alert email placeholder -> %s: %s", email_to, payload)
        try:
            with ALERT_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
            logged += 1
        except Exception as e:
            logger.warning("alert log write failed: %s", e)

    return {"dispatched": dispatched, "logged": logged, "alerts": len(alerts)}
