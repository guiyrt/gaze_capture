import logging
from pathlib import Path
from importlib.metadata import version

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, PositiveInt, model_validator, Field

from .utils import LoggingConfig

logger = logging.getLogger(__name__)

class DisplayAreaSettings(BaseModel):
    """
    Physical dimensions and position of the display relative to the tracker.
    All measurements are in millimeters (mm).
    """
    height_px: int = Field(2160)
    width_px: int = Field(3840)
    width_mm: float = Field(344.0, description="Width of the active display area.")
    height_mm: float = Field(193.0, description="Height of the active display area.")
    vertical_offset_mm: float = Field(60.0, description="Vertical distance from tracker center to bottom edge of screen.")
    horizontal_offset_mm: float = Field(0.0, description="Horizontal distance from tracker center to screen center.")
    depth_offset_mm: float = Field(0.0, description="Depth distance from the tracker to the screen plane.")

class ParquetSinkConfig(BaseModel):
    enabled: bool = True
    output_dir: Path = Path("./recordings")
    drop_when_full: bool = True
    max_buffer_size: PositiveInt = 120 * 5 # Flushes every 5 seconds at 120 Hz
    queue_size: PositiveInt = 120 * 5 * 60 # Holds 5 minutes of data at 120 Hz

    @model_validator(mode='after')
    def validate_buffer_sizes(self) -> "ParquetSinkConfig":
        if self.queue_size <= self.max_buffer_size:
            raise ValueError('Queue must be bigger than buffer.')
        return self
    
class ZmqSinkConfig(BaseModel):
    enabled: bool = True
    host: str = "tcp://*:5555"

class CalibrationSettings(BaseModel):
    """Settings for the calibration procedure."""
    points_to_calibrate: list[tuple[float, float]] = Field(
        default=[
            (0.5, 0.5),
            (0.1, 0.1), (0.1, 0.9),
            (0.9, 0.1), (0.9, 0.9),
            (0.3, 0.7), (0.7, 0.3)
        ],
        description="List of normalized (0-1) screen coordinates to use as calibration targets."
    )

class AppSettings(BaseSettings):
    """
    Main application settings, loaded from environment variables and defaults.
    """
    # Data
    use_dummy_mode: bool = False
    data_dir: Path = Field(default_factory=lambda: Path.cwd() / "recordings", description="Path to directory where local data is stored.")

    # Hardware
    display_area: DisplayAreaSettings = Field(default_factory=DisplayAreaSettings)
    calibration: CalibrationSettings = Field(default_factory=CalibrationSettings)

    # Sinks
    parquet: ParquetSinkConfig = Field(default_factory=ParquetSinkConfig)
    zmq: ZmqSinkConfig = Field(default_factory=ZmqSinkConfig)

    # Logging
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    __version__: str = version("gaze-capture")

    model_config = SettingsConfigDict(
        env_prefix="GAZE__",
        env_file=".env",
        env_nested_delimiter='__',
        case_sensitive=False
    )