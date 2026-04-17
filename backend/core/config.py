"""Typed configuration for DRIFT. Loads backend/config.yaml with env overrides.

Env override examples:
    ML__WEIGHTS_SOURCE=our_real python -m backend.ml tile.tif
    PHYSICS__WINDAGE_ALPHA=0.03 python -m backend.physics det.json

The settings_customise_sources override is REQUIRED -- pydantic-settings does
NOT load YAML by default. Without this override, backend/config.yaml is
ignored and all values fall back to hardcoded defaults. See PITFALL 8 in
.planning/phases/01-schema-foundation-dummy-inference/01-RESEARCH.md.
"""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

WeightsSource = Literal["dummy", "marccoru_baseline", "our_real"]


class MLSettings(BaseModel):
    weights_source: WeightsSource = "dummy"
    kagglehub_handle: str = "manastiwari1410/drift-unetpp/pytorch/v1"
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    min_area_m2: float = Field(default=200.0, ge=0.0)
    patch_size: int = 256
    stride: int = 128
    in_channels: int = 14
    biofouling_tau_days: float = 30.0
    dummy_seed: int = 42


class PhysicsSettings(BaseModel):
    windage_alpha: float = Field(default=0.02, ge=0.0, le=0.1)
    horizon_hours: int = 72
    dt_seconds: int = 3600
    particles_per_detection: int = 20
    cmems_path: Path = Path("data/env/cmems_currents_72h.nc")
    era5_path: Path = Path("data/env/era5_winds_72h.nc")
    max_cutoff_days: int = 90
    active_horizon_days: int = 15


class MissionSettings(BaseModel):
    top_k: int = 10
    weight_density: float = 0.5
    weight_accessibility: float = 0.3
    weight_convergence: float = 0.2
    avg_speed_kmh: float = Field(default=20.0, gt=0.0, le=60.0)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file=Path("backend/config.yaml"),
        env_file=Path(".env"),
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )
    ml: MLSettings = MLSettings()
    physics: PhysicsSettings = PhysicsSettings()
    mission: MissionSettings = MissionSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init kwargs > env vars > YAML > defaults
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls),
        )
