from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class GazeData:
    """
    Flattened 120Hz Gaze Frame.
    Contains raw sensor data and processed pixel coordinates for midpoint.
    """
    # Precise Unix Epoch in milliseconds (derived from PC-Hardware sync)
    epoch_timestamp_ms: int

    # Calculated Midpoint (Derived)
    mid_x_px: int | None
    mid_y_px: int | None
    mid_x: float | None
    mid_y: float | None

    # Raw Timestamps (Microseconds)
    device_timestamp_us: int
    system_timestamp_us: int
    
    # Raw Sensor Data (Normalized 0.0 to 1.0)
    left_x: float | None
    left_y: float | None
    right_x: float | None
    right_y: float | None
    
    # Pupil Diameter (mm)
    left_pupil: float | None
    right_pupil: float | None
    
    # 3D Position and Origin (User Coordinates in mm)
    left_3d: tuple[float, float, float] | None
    right_3d: tuple[float, float, float] | None
    left_origin: tuple[float, float, float] | None
    right_origin: tuple[float, float, float] | None