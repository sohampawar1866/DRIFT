"""Frozen pydantic contracts for DRIFT intelligence pipeline.

FROZEN at Phase 1 exit. Any field edit requires an explicit entry in
.planning/STATE.md and a re-run of tests/unit/test_schemas.py.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from geojson_pydantic import Feature, FeatureCollection, LineString, Polygon


class DetectionProperties(BaseModel):
    """Per-detection metadata attached to each polygon feature.

    'class' is a Python reserved word; we expose it via alias. Producers
    should write `DetectionProperties(...)` (cls defaults to 'plastic') or
    accept `{"class": "plastic", ...}` via populate_by_name. JSON round-trips
    as '{"class": "plastic", ...}' when serialized with `by_alias=True`.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    conf_raw: float = Field(ge=0.0, le=1.0)
    conf_adj: float = Field(ge=0.0, le=1.0)
    fraction_plastic: float = Field(ge=0.0, le=1.0)
    area_m2: float = Field(ge=0.0)
    age_days_est: int = Field(ge=0)
    cls: Literal["plastic"] = Field(default="plastic", alias="class")
    water_temp: float | None = None
    chlorophyll: float | None = None
    k_factor: float | None = None
    conf_range: list[float] | None = None
    class_est: str | None = None


# Typed GeoJSON composition via geojson-pydantic generics.
DetectionFeature = Feature[Polygon, DetectionProperties]
DetectionFeatureCollection = FeatureCollection[DetectionFeature]


# Phase 2 / Phase 3 contracts -- frozen NOW to prevent schema drift later.
class ForecastFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
<<<<<<< HEAD
    hour: int = Field(ge=0, le=72)
    particle_positions: list[tuple[float, float]]  # (lon, lat)
    density_polygons: FeatureCollection
=======
    hour: int = Field(ge=0, le=2160)  # Extended for 90-day cutoff
    particle_positions: list[tuple[float, float]]  # (lon, lat) drifting
    beached_positions: list[tuple[float, float]] = [] # (lon, lat) deposited
    density_polygons: FeatureCollection[Feature[Polygon, dict]]
    deposition_polygons: FeatureCollection[Feature[Polygon, dict]] = Field(default_factory=lambda: FeatureCollection(type="FeatureCollection", features=[]))
>>>>>>> 1bbdf90 (Add environmental services, spectral monitoring, biofouling modeling, and update .gitignore)


class ForecastEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    source_detections: DetectionFeatureCollection
    frames: list[ForecastFrame]
    trajectories: FeatureCollection | None = None
    windage_alpha: float = Field(ge=0.0, le=0.1)


class MissionWaypoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    order: int = Field(ge=0)
    lon: float
    lat: float
    arrival_hour: float = Field(ge=0.0)
    priority_score: float = Field(ge=0.0)


class MissionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    waypoints: list[MissionWaypoint]
    route: Feature[LineString, dict]
    total_distance_km: float = Field(ge=0.0)
    total_hours: float = Field(ge=0.0)
    origin: tuple[float, float]
