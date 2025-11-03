import asyncio
import logging
from typing import Optional

import tobii_research as tr

from gaze_capture.config import settings
from gaze_capture.app.bridge import AsyncioTkinterBridge

logger = logging.getLogger(__name__)


class TrackerController:
    """
    Encapsulates all direct interactions with the Tobii Pro SDK.

    This class is responsible for finding, connecting to, and configuring the
    eye tracker. It provides a clean, asynchronous interface for the UI and
    other application components to use without needing to know the specifics
    of the Tobii SDK's blocking nature.
    """

    def __init__(self, bridge: AsyncioTkinterBridge):
        """
        Initializes the TrackerController.

        Args:
            bridge: The application's bridge to the asyncio world, used to
                    run blocking SDK calls in a thread-safe manner.
        """
        self.eyetracker: Optional[tr.EyeTracker] = None
        self._bridge = bridge

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Convenience property to access the asyncio event loop."""
        return self._bridge.loop

    async def initialize(self) -> bool:
        """
        Searches for and connects to the first available Tobii eye tracker.

        This method runs the blocking SDK call `find_all_eyetrackers` in an
        executor thread to avoid freezing the application.

        Returns:
            True if a tracker was successfully found and configured, False otherwise.
        """
        logger.info("Searching for eye trackers...")
        try:
            # run_in_executor is crucial for running blocking I/O without
            # stalling the asyncio event loop.
            eyetrackers = await self.loop.run_in_executor(None, tr.find_all_eyetrackers)

            if not eyetrackers:
                logger.error("No eye trackers found.")
                return False

            self.eyetracker = eyetrackers[0]
            logger.info(
                f"Connected to tracker: {self.eyetracker.device_name} "
                f"({self.eyetracker.serial_number})"
            )

            # After connecting, immediately apply the display area configuration.
            await self._set_display_area()
            return True

        except Exception:
            logger.exception("An unexpected error occurred during tracker initialization.")
            self.eyetracker = None
            return False

    async def _set_display_area(self) -> None:
        """
        Configures the tracker with physical screen dimensions from settings.
        This is also run in an executor as it involves hardware communication.
        """
        if not self.eyetracker:
            logger.warning("Cannot set display area, no eye tracker connected.")
            return

        cfg = settings.display_area
        width, height = cfg.width_mm, cfg.height_mm
        v_off, h_off, d_off = cfg.vertical_offset_mm, cfg.horizontal_offset_mm, cfg.depth_offset_mm

        display_area_coords = {
            "top_left": (-(width / 2) + h_off, height + v_off, d_off),
            "top_right": ((width / 2) + h_off, height + v_off, d_off),
            "bottom_left": (-(width / 2) + h_off, v_off, d_off),
        }
        display_area = tr.DisplayArea(display_area_coords)

        try:
            await self.loop.run_in_executor(None, self.eyetracker.set_display_area, display_area)
            logger.info(f"Display area set for tracker: {display_area_coords}")
        except tr.EyeTrackerException:
            logger.exception("Failed to set display area on the tracker.")

    def get_calibration_controller(self) -> Optional[tr.ScreenBasedCalibration]:
        """
        Returns a ScreenBasedCalibration object for the connected tracker.

        This is a lightweight, non-blocking call, so it doesn't need to be async.

        Returns:
            A calibration object if the tracker is connected, otherwise None.
        """
        return tr.ScreenBasedCalibration(self.eyetracker) if self.eyetracker else None
    
    # --- Calibration Primitives ---

    async def enter_calibration_mode(self) -> None:
        """Enters calibration mode. A blocking SDK call."""
        if not self._calibration:
            raise RuntimeError("Calibration not initialized.")
        logger.info("Entering calibration mode.")
        await self.loop.run_in_executor(None, self._calibration.enter_calibration_mode)

    async def leave_calibration_mode(self) -> None:
        """Leaves calibration mode. A blocking SDK call."""
        if not self._calibration:
            return # No-op if not initialized
        logger.info("Leaving calibration mode.")
        await self.loop.run_in_executor(None, self._calibration.leave_calibration_mode)

    async def collect_calibration_data(self, x: float, y: float) -> bool:
        """
        Collects calibration data for a specific point. A blocking SDK call.

        Args:
            x: Normalized horizontal screen coordinate (0.0 to 1.0).
            y: Normalized vertical screen coordinate (0.0 to 1.0).
        
        Returns:
            True if data collection was successful, False otherwise.
        """
        if not self._calibration:
            raise RuntimeError("Calibration not initialized.")
        
        status = await self.loop.run_in_executor(None, self._calibration.collect_data, x, y)
        if status != tr.CALIBRATION_STATUS_SUCCESS:
            logger.warning(f"Failed to collect calibration data for point ({x:.2f}, {y:.2f}). Status: {status}")
            return False
        return True

    async def compute_and_apply_calibration(self) -> Optional[tr.CalibrationResult]:
        """Computes and applies the calibration. A blocking SDK call."""
        if not self._calibration:
            raise RuntimeError("Calibration not initialized.")
        
        logger.info("Computing and applying calibration...")
        result = await self.loop.run_in_executor(None, self._calibration.compute_and_apply)
        logger.info(f"Calibration computation finished with status: {result.status}")
        return result

    async def retrieve_calibration_data(self) -> Optional[bytes]:
        """Retrieves binary calibration data from the tracker."""
        if not self.eyetracker:
            raise RuntimeError("Eye tracker not initialized.")
        return await self.loop.run_in_executor(None, self.eyetracker.retrieve_calibration_data)
        
    async def apply_calibration_data(self, data: bytes) -> None:
        """Applies binary calibration data to the tracker."""
        if not self.eyetracker:
            raise RuntimeError("Eye tracker not initialized.")
        await self.loop.run_in_executor(None, self.eyetracker.apply_calibration_data, data)