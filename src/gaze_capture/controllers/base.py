import asyncio
import json
import inspect
from abc import ABC, abstractmethod
from pathlib import Path
from functools import wraps
import logging

from ..app.bridge import AsyncioTkinterBridge
from ..acquisition import GazeSource
from ..configs import CalibrationSettings, DisplayAreaSettings
from ..ui import TkinterCalibrationView

logger = logging.getLogger(__name__)

def require_tracker(func):
    """
    Universal decorator for Python 3.10.
    Detects if the wrapped function is async or sync and behaves accordingly.
    """
    @wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        if not self.is_connected:
            logger.warning(f"Hardware action '{func.__name__}' aborted: Tracker disconnected.")
            return False
        return await func(self, *args, **kwargs)
    return async_wrapper

class GazeTrackerController(ABC):
    """
    Abstract Hardware Manager.
    AUTHORITY on: Connection, Calibration, and Screen Geometry.
    """
    def __init__(self, bridge: AsyncioTkinterBridge):
        self._bridge = bridge
        
        # Geometry Authority
        self.screen_width: int = 0
        self.screen_height: int = 0

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._bridge.loop

    @abstractmethod
    def create_source(self) -> GazeSource:
        """Factory: Returns a fresh GazeSource for a recording session."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Returns True if hardware is initialized and ready."""
        ...

    @property
    @abstractmethod
    def tracker_name(self) -> str:
        """Returns a human-readable name of the hardware."""
        ...
    
    @require_tracker
    @abstractmethod
    async def connect(self, cfg: DisplayAreaSettings) -> bool:
        """Finds tracker, detects screen resolution, applies settings. Returns success."""
        ...

    @require_tracker
    @abstractmethod
    async def calibrate(self, cfg: CalibrationSettings, folder: Path) -> bool:
        ...
    
    @require_tracker
    @abstractmethod
    async def load_calibration(self, folder: Path) -> bool:
        """Loads binary calibration from disk and applies it to hardware."""
        ...

    async def show_calibration_results(self, folder: Path, view: TkinterCalibrationView) -> bool:
        """
        Loads the JSON report from disk and displays it on the provided view.
        Returns False if no calibration exists.
        """
        json_path = folder / "calibration_result.json"
        if not json_path.exists():
            logger.warning("Calibration results '%s' does not exist.", json_path)
            return False

        try:
            # Offload file read
            content = await asyncio.to_thread(json_path.read_text)
            result_dict = json.loads(content)
            
            await view.open()
            await view.show_results(result_dict)
            await view.close()
            return True
        except Exception as e:
            logger.error(f"Failed to show calibration: {e}")
            # Ensure view closes if we crash mid-show
            await view.close()
            return False
    
    @abstractmethod
    def shutdown(self) -> None:
        """Cleanup hardware resources."""
        ...