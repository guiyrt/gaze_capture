import time

from .base import BaseService, ServiceState
from ...core.manager import EyeTrackingManager
from ...core.state import AppState

class GazeService(BaseService):
    """Stateless Adapter bridging EyeTrackingManager to the Service interface."""
    def __init__(self, manager: EyeTrackingManager):
        # Do not call super() to avoid inheriting internal state logic
        self.name = "gaze"
        self.manager = manager
        self._record_start_time = 0.0
        self._was_recording = False

    @property
    def current_state(self) -> ServiceState:
        """Computed on-the-fly directly from the GazeManager."""
        app_state = self.manager.current_state
        
        if app_state == AppState.RECORDING:
            # Catch the exact moment recording starts to reset the timer
            if not self._was_recording:
                self._record_start_time = time.time()
                self._was_recording = True
            return ServiceState.RECORDING
            
        self._was_recording = False
        
        # If it's connected, healthy, and calibrated, it's READY.
        if app_state == AppState.IDLE and self.manager.is_calibrated:
            return ServiceState.READY
            
        # Otherwise (NO_TRACKER, TRACKER_LOST, CALIBRATING, uncalibrated IDLE), it's UNAVAILABLE.
        return ServiceState.UNAVAILABLE

    def get_duration_str(self) -> str:
        if self.current_state != ServiceState.RECORDING:
            return "00:00"
        elapsed = int(time.time() - self._record_start_time)
        return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

    async def start(self, session_id: str) -> bool:
        if self.current_state != ServiceState.READY:
            return False
        return await self.manager.start_recording(f"{session_id}/ET/")

    async def stop(self) -> None:
        await self.manager.stop_recording()