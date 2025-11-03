# src/gaze_capture/config.py

import logging
from pathlib import Path
from typing import List, Literal, Tuple

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class DisplayAreaSettings(BaseModel):
    """
    Physical dimensions and position of the display relative to the tracker.
    All measurements are in millimeters (mm).
    """
    width_mm: float = Field(344.0, description="Width of the active display area.")
    height_mm: float = Field(193.0, description="Height of the active display area.")
    vertical_offset_mm: float = Field(
        60.0,
        description="Vertical distance from tracker center to bottom edge of screen."
    )
    horizontal_offset_mm: float = Field(
        0.0,
        description="Horizontal distance from tracker center to screen center."
    )
    depth_offset_mm: float = Field(
        0.0,
        description="Depth distance from the tracker to the screen plane."
    )


class PipelineSettings(BaseModel):
    """Settings for the data processing pipeline."""
    enabled_sinks: List[Literal["csv", "http"]] = Field(
        default=["csv", "http"],
        description="Which sinks to activate during recording."
    )
    bundle_size: int = Field(
        default=60, gt=0, description="Number of samples to collect per bundle."
    )
    max_bundle_interval_s: float = Field(
        default=1.0,
        gt=0,
        description="Maximum time in seconds to wait before sending a partial bundle.",
    )


class HTTPSinkSettings(BaseModel):
    """Settings specific to the HTTPSink."""
    server_url: str = Field(
        default="http://localhost:8000/api/gaze",
        description="The URL of the server endpoint to send gaze data to.",
    )
    max_concurrent_sends: int = Field(
        default=10,
        gt=0,
        description="Maximum number of parallel HTTP requests."
    )
    retry_attempts: int = Field(
        default=3, ge=0, description="Number of retry attempts for failed HTTP requests."
    )
    retry_backoff_factor_s: float = Field(
        default=0.5,
        ge=0,
        description="Base factor for exponential backoff between retries.",
    )


class CalibrationSettings(BaseModel):
    """Settings for the calibration procedure."""
    points_to_calibrate: List[Tuple[float, float]] = Field(
        default=[
            (0.5, 0.5),
            (0.1, 0.1), (0.1, 0.9),
            (0.9, 0.1), (0.9, 0.9),
            (0.3, 0.7), (0.7, 0.3)
        ],
        description="List of normalized (0-1) screen coordinates to use as calibration targets."
    )


class Settings(BaseSettings):
    """
    Main application settings, loaded from environment variables and defaults.
    """
    log_level: str = Field(
        default="INFO",
        description="Logging level (e.g., DEBUG, INFO, WARNING)."
    )
    data_dir: Path = Field(
        default_factory=lambda: Path.cwd() / "recordings",
        description="Path to directory where local data is stored."
    )

    display_area: DisplayAreaSettings = Field(default_factory=DisplayAreaSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    http_sink: HTTPSinkSettings = Field(default_factory=HTTPSinkSettings)
    calibration: CalibrationSettings = Field(default_factory=CalibrationSettings)

    model_config = SettingsConfigDict(
        env_prefix="GAZE_",  # e.g., GAZE_LOG_LEVEL=DEBUG
        case_sensitive=False,
        env_nested_delimiter='__', # e.g., GAZE_PIPELINE__BUNDLE_SIZE=100
    )


# Create a single, globally accessible instance of the settings.
try:
    settings = Settings()
except Exception:
    logger.exception("Failed to initialize application settings. Check environment variables.")
    exit(1)