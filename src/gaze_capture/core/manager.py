import asyncio
import logging

from .runner import GazeRunner
from .factories import create_session_sinks
from ..controllers import GazeTrackerController
from ..configs import AppSettings
from ..core.protocols import CalibrationView


logger = logging.getLogger(__name__)

class SessionManager:
    """
    The Headless Core of the Gaze Capture application.
    
    This class handles the high-level logic and state, allowing the UI 
    (Tkinter, CLI, or Web) to be a thin layer.
    """
    def __init__(self, controller, settings, loop):
        self.controller: GazeTrackerController = controller
        self.settings: AppSettings = settings
        self.loop: asyncio.AbstractEventLoop = loop
        
        self.participant_id: str | None = None
        self.is_calibrated: bool = False
        self.runner: GazeRunner  = None

    def run_task(self, coro):
        """
        The UI calls this. It handles the transition to the background 
        thread and ensures that errors are NEVER silent.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        
        def _on_complete(fut):
            try:
                fut.result() # This forces any hidden exception to be raised
            except Exception as e:
                logger.exception("Background Task Crash: %s", e)

        future.add_done_callback(_on_complete)
        return future
    @property
    def is_recording(self) -> bool:
        return self.runner is not None

    @property
    def is_connected(self) -> bool:
        return self.controller.is_connected

    @property
    def tracker_name(self) -> str:
        return self.controller.tracker_name

    # --- Actions ---

    async def set_participant(self, pid: str) -> bool:
        """
        Logic: Setup directories and attempt to load existing calibration.
        Returns: True if a calibration was successfully loaded.
        """
        self.participant_id = pid
        self.participant_dir = self.settings.data_dir / pid
        self.participant_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Participant set to: {pid}")

        # Hardware Logic: Load calibration from the newly set directory
        self.is_calibrated = await self.controller.load_calibration(self.participant_dir)
        return self.is_calibrated

    async def run_calibration(self, view: CalibrationView) -> bool:
        """
        Logic: Orchestrates the calibration lifecycle using the provided view.
        """
        if not self.participant_dir:
            logger.error("Cannot calibrate: No participant set.")
            return False

        logger.info("Starting calibration sequence...")
        self.is_calibrated = await self.controller.calibrate(
            save_folder=self.participant_dir,
            calib_settings=self.settings.calibration,
            view=view
        )
        return self.is_calibrated

    async def start_recording(self) -> bool:
        """
        Logic: Prepares sinks, source, and runner, then starts the session.
        Returns: True if recording started successfully.
        """
        if not self.participant_id or not self.is_calibrated:
            logger.warning("Start recording aborted: Check participant and calibration.")
            return False

        if self.runner:
            logger.warning("Recording already in progress.")
            return True

        try:
            # 1. Create session components via factories
            source = self.controller.create_source()
            sinks = create_session_sinks(self.settings, self.participant_dir)
            
            # 2. Instantiate and start Runner
            self.runner = GazeRunner(source, sinks)
            await self.runner.start()
            
            logger.info(f"Recording started for {self.participant_id}")
            return True
            
        except Exception as e:
            logger.exception("Failed to initialize recording session")
            self.runner = None
            return False

    async def stop_recording(self):
        """
        Logic: Stops the active runner and clears the session state.
        """
        if self.runner:
            logger.info("Stopping recording session...")
            await self.runner.stop()
            self.runner = None
            logger.info("Recording stopped.")

    def shutdown(self):
        """
        Logic: Graceful cleanup of hardware before application exit.
        """
        self.controller.shutdown()