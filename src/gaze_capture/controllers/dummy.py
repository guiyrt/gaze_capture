import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone
import json

from .base import GazeTrackerController
from ..acquisition import DummySource
from ..configs import DisplayAreaSettings
from ..core.protocols import CalibrationView

logger = logging.getLogger(__name__)

class DummyController(GazeTrackerController):
    def __init__(self):
        super().__init__()
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
        await self.apply_display_settings(settings)
        self._connected = True
        return True

    def create_source(self) -> DummySource:
        return DummySource(self.screen_width, self.screen_height)

    async def load_calibration(self, folder: Path) -> bool:
        self._calibrated = (folder / "calibration.bin").exists()
        self.last_calibration_path = folder
        return self._calibrated
    
    async def apply_display_settings(self, cfg: DisplayAreaSettings) -> bool:
        self.last_display_settings = cfg
        self.screen_width, self.screen_height = cfg.width_px, cfg.height_px
        return True

    async def calibrate(
        self,
        save_folder: Path,
        view: CalibrationView
    ) -> bool:
        try:
            await view.open()
            await view.show_message("Simulating Hardware...")
            
            for x, y in self.CALIBRATION_POINTS:
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
            self.last_calibration_path = save_folder
            self._calibrated = True

            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            with open(save_folder / "calibration_result.json", "w") as f:
                json.dump(result, f, indent=2)
            
            await view.show_results(result)
            return True
            
        finally:
            await view.close()

    def shutdown(self) -> None:
        self._connected = False