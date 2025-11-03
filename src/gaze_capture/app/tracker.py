import asyncio
import logging
from typing import Optional
from types import SimpleNamespace

import tobii_research as tr

from gaze_capture.config import settings
from gaze_capture.app.bridge import AsyncioTkinterBridge

logger = logging.getLogger(__name__)


class TrackerController:
    """
    Encapsulates all direct interactions with the Tobii Pro SDK.

    This class provides a clean, asynchronous interface for the UI and other
    application components, handling the thread-safe execution of blocking
    SDK calls.
    """

    def __init__(self, bridge: AsyncioTkinterBridge):
        self.eyetracker: Optional[tr.EyeTracker] = None
        self._bridge = bridge
        self._calibration: Optional[tr.ScreenBasedCalibration] = None

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Convenience property to access the asyncio event loop."""
        return self._bridge.loop

    async def initialize(self) -> bool:
        """
        Searches for and connects to the first available Tobii eye tracker.
        """
        logger.info("Searching for eye trackers...")
        try:
            eyetrackers = await self.loop.run_in_executor(None, tr.find_all_eyetrackers)

            if not eyetrackers:
                logger.error("No eye trackers found.")
                return False

            self.eyetracker = eyetrackers[0]
            logger.info(
                f"Connected to tracker: {self.eyetracker.device_name} "
                f"({self.eyetracker.serial_number})"
            )
            
            # Create and store the single calibration object upon initialization.
            self._calibration = tr.ScreenBasedCalibration(self.eyetracker)
            
            await self._set_display_area()
            return True

        except Exception:
            logger.exception("An unexpected error occurred during tracker initialization.")
            self.eyetracker = None
            self._calibration = None
            return False
    
    @property
    def has_valid_calibration(self) -> bool:
        """Checks if the eye tracker has active calibration data."""
        if not self.eyetracker:
            return False

        return self.eyetracker.calibration_data is not None

    def shutdown(self) -> None:
        """De-initializes the Tobii SDK library to release resources."""
        logger.info("De-initializing Tobii SDK library.")
        self.eyetracker = None
        self._calibration = None

    async def _set_display_area(self) -> None:
        """
        Configures the tracker with physical screen dimensions from settings.
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
    
    # --- Calibration Primitives ---

    async def enter_calibration_mode(self) -> None:
        """Enters calibration mode. A blocking SDK call."""
        if not self._calibration:
            raise RuntimeError("Calibration not initialized. Is the tracker connected?")
        logger.info("Entering calibration mode.")
        await self.loop.run_in_executor(None, self._calibration.enter_calibration_mode)

    async def leave_calibration_mode(self) -> None:
        """Leaves calibration mode. A blocking SDK call."""
        if not self._calibration:
            return
        logger.info("Leaving calibration mode.")
        await self.loop.run_in_executor(None, self._calibration.leave_calibration_mode)

    async def collect_calibration_data(self, x: float, y: float) -> bool:
        """
        Collects calibration data for a specific point. A blocking SDK call.
        """
        if not self._calibration:
            raise RuntimeError("Calibration not initialized. Is the tracker connected?")
        
        status = await self.loop.run_in_executor(None, self._calibration.collect_data, x, y)
        if status != tr.CALIBRATION_STATUS_SUCCESS:
            logger.warning(f"Failed to collect calibration data for point ({x:.2f}, {y:.2f}). Status: {status}")
            return False
        return True

    async def compute_and_apply_calibration(self) -> Optional[tr.CalibrationResult]:
        """Computes and applies the calibration. A blocking SDK call."""
        if not self._calibration:
            raise RuntimeError("Calibration not initialized. Is the tracker connected?")
        
        logger.info("Computing and applying calibration...")
        result = await self.loop.run_in_executor(None, self._calibration.compute_and_apply)
        logger.info(f"Calibration computation finished with status: {result.status}")
        return result
    
    def get_calibration_result_as_dict(self, result: tr.CalibrationResult) -> dict:
        """
        Converts a Tobii CalibrationResult object to a JSON-serializable dictionary
        containing detailed raw sample data.
        """
        if result.status != tr.CALIBRATION_STATUS_SUCCESS:
            return {"status": str(result.status), "points": {}}

        result_dict = {
            "status": str(result.status),
            "points": []
        }
        
        for cp in result.calibration_points:
            point_entry = {
                "target": {"x": cp.position_on_display_area[0], "y": cp.position_on_display_area[1]},
                "samples": []
            }
            for s in cp.calibration_samples:
                sample_data = {}
                for eye_label, eye in (("left", s.left_eye), ("right", s.right_eye)):
                    if eye and eye.validity == tr.VALIDITY_VALID_AND_USED:
                        sample_data[eye_label] = {
                            "validity": str(eye.validity),
                            "x": eye.position_on_display_area[0],
                            "y": eye.position_on_display_area[1]
                        }
                if sample_data:
                    point_entry["samples"].append(sample_data)
            result_dict["points"].append(point_entry)
            
        return result_dict

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


class DummyTrackerController:
    """
    A dummy implementation of TrackerController for offline testing and development.

    This class provides the same public interface as the real TrackerController
    but simulates successful operations without requiring any hardware.
    """
    def __init__(self, bridge: AsyncioTkinterBridge):
        # We don't use the bridge, but accept it to match the signature.
        self._bridge = bridge
        # ## FAKE: Simulate the eyetracker object with required attributes.
        self.eyetracker = SimpleNamespace(
            device_name="Dummy Tracker",
            serial_number="DUM-111"
        )
        self._is_calibrated = False

    @property
    def has_valid_calibration(self) -> bool:
        """In dummy mode, calibration is 'valid' after it has been 'run'."""
        return self._is_calibrated

    async def initialize(self) -> bool:
        """Simulates a successful and fast initialization."""
        logger.info("Initializing Dummy Tracker... Success!")
        await asyncio.sleep(0.1)  # Simulate a tiny bit of work
        return True

    def shutdown(self) -> None:
        """No-op shutdown for the dummy controller."""
        logger.info("Shutting down Dummy Tracker.")
        pass

    # --- Calibration Primitives ---

    async def enter_calibration_mode(self) -> None:
        logger.info("[Dummy] Entering calibration mode.")
        await asyncio.sleep(0)

    async def leave_calibration_mode(self) -> None:
        logger.info("[Dummy] Leaving calibration mode.")
        await asyncio.sleep(0)

    async def collect_calibration_data(self, x: float, y: float) -> bool:
        logger.info(f"[Dummy] Collecting data for point ({x:.2f}, {y:.2f})... Success.")
        await asyncio.sleep(0.1) # Simulate collection time
        return True

    async def compute_and_apply_calibration(self) -> SimpleNamespace:
        """Simulates a successful calibration computation."""
        logger.info("[Dummy] Computing and applying calibration... Success.")
        await asyncio.sleep(0.5) # Simulate computation time
        self._is_calibrated = True
        # Return an object that looks like the real tr.CalibrationResult
        return SimpleNamespace(status='calibration_status_success')

    async def retrieve_calibration_data(self) -> Optional[bytes]:
        """Returns dummy calibration data if 'calibrated'."""
        if self._is_calibrated:
            logger.info("[Dummy] Retrieving dummy calibration data.")
            return b"dummy_calibration_data_string"
        logger.warning("[Dummy] No calibration to retrieve.")
        return None

    async def apply_calibration_data(self, data: bytes) -> None:
        """Simulates applying calibration data."""
        logger.info(f"[Dummy] Applying calibration data: {data!r}")
        self._is_calibrated = True
        await asyncio.sleep(0.1)

    def get_calibration_result_as_dict(self, _: SimpleNamespace) -> dict:
        """Simulates the creation of a detailed calibration result dictionary."""
        if not self._is_calibrated:
            return {"status": "calibration_status_failure", "points": {}}

        # Create some plausible-looking fake data for testing
        return {
            "status": "calibration_status_success",
            "points": [
                {
                    "target": {"x": 0.5, "y": 0.5},
                    "samples": [
                        {
                            "left": {"validity": "validity_valid_and_used", "x": 0.51, "y": 0.49},
                            "right": {"validity": "validity_valid_and_used", "x": 0.50, "y": 0.51}
                        }
                    ]
                }
            ]
        }