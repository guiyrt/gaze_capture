import asyncio
import logging
from pathlib import Path

from .base import GazeTrackerController
from ..acquisition import DummySource
from ..configs import DisplayAreaSettings, CalibrationSettings
from ..ui import TkinterCalibrationView

logger = logging.getLogger(__name__)

class DummyController(GazeTrackerController):
    def __init__(self, bridge):
        super().__init__(bridge)
        self._connected = False
        self._calibrated = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def tracker_name(self) -> str:
        return "DUM8-7RACKER"

    async def connect(self, settings: DisplayAreaSettings) -> bool:
        await asyncio.sleep(0.5) # Simulate discovery
        self.screen_width, self.screen_height = 3840, 2160
        self._connected = True
        return True

    def create_source(self) -> DummySource:
        return DummySource(self.screen_width, self.screen_height)

    async def load_calibration(self, folder: Path) -> bool:
        self._calibrated = (folder / "calibration.bin").exists()
        return self._calibrated

    async def calibrate(
        self,
        save_folder: Path,
        calib_settings: CalibrationSettings, 
        view: TkinterCalibrationView
    ) -> bool:
        try:
            await view.open()
            await view.show_message("Simulating Hardware...")
            
            for x, y in calib_settings.points_to_calibrate:
                await view.show_point(x, y)
                await asyncio.sleep(0.5)
            
            await view.show_message("Computing...")
            await asyncio.sleep(1.0)
            
            # Create a fake result to show the graph
            result = {
                "status": "success",
                "points": [
                    {"target": {"x": 0.5, "y": 0.5}, "samples": [{"left": {"x": 0.51, "y": 0.49}}]}
                ]
            }
            
            # Simulate save
            await asyncio.to_thread((save_folder / "calibration.bin").write_text, "dummy")
            self._calibrated = True
            
            await view.show_results(result)
            return True
            
        finally:
            await view.close()

    def shutdown(self) -> None:
        self._connected = False