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
    output_dir: Path = Path("./data")
    drop_when_full: bool = True
    max_buffer_size: PositiveInt = 120 * 5 # Flushes every 5 seconds at 120 Hz
    queue_size: PositiveInt = 120 * 5 * 60 # Holds 5 minutes of data at 120 Hz

    @model_validator(mode='after')
    def validate_buffer_sizes(self) -> "ParquetSinkConfig":
        if self.queue_size <= self.max_buffer_size:
            raise ValueError('Queue must be bigger than buffer.')
        return self
    
class NatsSinkConfig(BaseModel):
    enabled: bool = True
    subject: str = "intent.gaze"

class AppSettings(BaseSettings):
    """
    Main application settings, loaded from environment variables and defaults.
    """
    # Data
    use_dummy_mode: bool = False
    data_dir: Path = Field(default=Path("./data"), description="Path to directory where local data is stored.")
    nats_host: str = "nats://localhost:4222"

    # Hardware
    display_area: DisplayAreaSettings = Field(default_factory=DisplayAreaSettings)

    # Sinks
    parquet: ParquetSinkConfig = Field(default_factory=ParquetSinkConfig)
    nats: NatsSinkConfig = Field(default_factory=NatsSinkConfig)

    # Logging
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    __version__: str = version("gaze-capture")

    model_config = SettingsConfigDict(
        env_prefix="GAZE__",
        env_file=".env",
        env_nested_delimiter='__',
        case_sensitive=False
    )