from enum import Enum, auto


class AppState(Enum):
    """
    Defines the distinct operational states of the Gaze Capture application.

    This enum is used for centralized state management, ensuring the UI
    behaves consistently and predictably.
    """
    INITIALIZING = auto()  # Application is starting, searching for tracker.
    NO_TRACKER = auto() # Initialization failed, no tracker found.
    IDLE = auto() # Tracker found, ready for calibration or recording.
    CALIBRATING = auto() # The calibration window is active.
    RECORDING = auto() # The data pipeline is active and recording data.