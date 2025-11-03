from dataclasses import dataclass
from typing import Optional

@dataclass(slots=True, frozen=True)
class GazeData:
    """
    A standardized, immutable container for a single gaze data sample.

    This object is the canonical representation of gaze data as it flows
    through the pipeline, from source to bundler.
    """
    device_time_stamp: int
    system_time_stamp: int
    left_gaze_point: Optional[tuple[float, float]]
    right_gaze_point: Optional[tuple[float, float]]