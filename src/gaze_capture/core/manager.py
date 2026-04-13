import asyncio
import logging
from typing import Callable
from pathlib import Path
import nats

from .runner import GazeRunner
from .factories import create_sinks
from ..controllers import GazeTrackerController
from ..configs import AppSettings, DisplayAreaSettings
from ..core.protocols import CalibrationView
from .state import AppState

logger = logging.getLogger(__name__)

class EyeTrackingManager:
    """
    The Headless Core of the Gaze Capture application.
    
    This class handles the high-level logic and state, allowing the UI 
    (Tkinter, CLI, or Web) to be a thin layer.
    """
    def __init__(
        self,
        controller: GazeTrackerController,
        settings: AppSettings,
        loop: asyncio.AbstractEventLoop,
        nc: nats.NATS,
        auto_resume: bool = True
    ):
        self.controller = controller
        self.settings = settings
        self.loop = loop
        self.nc = nc

        self.controller.set_connection_callbacks(
            on_lost=self._on_hardware_lost,
            on_restored=self._on_hardware_restored
        )

        self._state: AppState = AppState.INITIALIZING
        self._listeners: list[Callable[[AppState], None]] = []
        self._auto_resume: bool = auto_resume
        self._runner: GazeRunner | None = None

        self._current_recording_path: str | None = None
        self.is_calibrated: bool = False
        self.data_dir = settings.data_dir

    @property
    def current_state(self) -> AppState:
        return self._state

    def add_state_listener(self, listener: Callable[[AppState], None]):
        self._listeners.append(listener)
        listener(self._state)

    def _set_state(self, new_state: AppState):
        if self._state != new_state:
            self._state = new_state
            for listener in self._listeners:
                self.loop.call_soon_threadsafe(listener, new_state)

    async def connect(self, display_settings: DisplayAreaSettings) -> bool:
        """Wraps controller connection to update internal state."""
        success = await self.controller.connect(display_settings)
        self._set_state(AppState.IDLE if success else AppState.NO_TRACKER)
        return success

    def _on_hardware_lost(self):
        logger.warning("GazeManager: Hardware Lost.")
        
        if self.is_recording:
            # Cleanly stop the pipeline, flush files, but KEEP the auto-resume flag!
            logger.info("Suspending recording pipeline due to hardware loss...")
            self.loop.create_task(self._suspend_recording())
        
    def _on_hardware_restored(self):
        logger.info("GazeManager: Hardware Restored.")
        
        if self._auto_resume and self._current_recording_path:
            logger.info("Auto-resuming suspended recording...")
            self.loop.create_task(self.start_recording(self._current_recording_path))
        else:
            self._set_state(AppState.IDLE)

    @property
    def is_recording(self) -> bool:
        return self._runner is not None

    async def load_calibration(self, target_folder: Path) -> bool:
        self.is_calibrated = await self.controller.load_calibration(target_folder)
        return self.is_calibrated

    async def run_calibration(self, save_folder: Path, view: CalibrationView) -> bool:
        self._set_state(AppState.CALIBRATING)
        self.is_calibrated = await self.controller.calibrate(save_folder, view)
        self._set_state(AppState.IDLE)
        return self.is_calibrated

    async def start_recording(self, sub_dir: str | None = None) -> bool:
        if self._runner or not self.is_calibrated:
            return False
        
        # Fresh start, if interrupted _current_recording_path is not None
        if self._current_recording_path is None:
            self._current_recording_path = (
                self.data_dir/sub_dir
                if sub_dir is not None
                else self.data_dir
            )

        try:
            self._runner = GazeRunner(
                source=self.controller.create_source(),
                sinks=create_sinks(self.settings, self._current_recording_path, self.nc)
            )
            await self._runner.start()
            self._set_state(AppState.RECORDING)
            return True

        except Exception as e:
            logger.exception("Failed to start Gaze Runner: %s", e)
            await self.stop_recording()
            return False
        
    async def _suspend_recording(self):
        if self._runner is not None:
            await self._runner.stop()
            self._runner = None
        
        self._set_state(AppState.TRACKER_LOST)

    async def stop_recording(self):
        if self._runner is not None:
            await self._runner.stop()
            self._runner = None
            self._current_recording_path = None

            self._set_state(AppState.IDLE)

    def run_task(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        future.add_done_callback(lambda fut: fut.exception() if fut.exception() else None)
        return future

    def shutdown(self):
        self.controller.shutdown()