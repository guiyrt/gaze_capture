from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class GazeData:
    """
    Flattened 120Hz Gaze Frame.
    Contains raw sensor data and processed pixel coordinates for midpoint.
    """
    # Precise Unix Epoch in milliseconds (derived from PC-Hardware sync)
    timestamp_ms: int

    # Calculated Midpoint (Derived)
    gaze_x_px: int | None
    gaze_y_px: int | None
    gaze_x_norm: float | None
    gaze_y_norm: float | None

    # Raw Timestamps (Microseconds)
    device_timestamp_us: int
    system_timestamp_us: int
    
    # Raw Sensor Data (Normalized 0.0 to 1.0)
    left_x_norm: float | None
    left_y_norm: float | None
    right_x_norm: float | None
    right_y_norm: float | None
    
    # Pupil Diameter (mm)
    left_pupil_mm: float | None
    right_pupil_mm: float | None
    
    # 3D Position and Origin (User Coordinates in mm)
    left_3d_mm: tuple[float, float, float] | None
    right_3d_mm: tuple[float, float, float] | None
    left_origin_mm: tuple[float, float, float] | None
    right_origin_mm: tuple[float, float, float] | None