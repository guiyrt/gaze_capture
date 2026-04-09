import json
import logging
import datetime
import asyncio
from pathlib import Path
from typing import Optional, TypeVar, Callable

import tobii_research as tr

from .base import GazeTrackerController, require_tracker
from ..acquisition import TobiiSource
from ..configs import DisplayAreaSettings
from ..core.protocols import CalibrationView

logger = logging.getLogger(__name__)

T = TypeVar("T")

class TobiiController(GazeTrackerController):
    def __init__(self):
        super().__init__()
        self.tracker: Optional[tr.EyeTracker] = None

    @property
    def is_connected(self) -> bool:
        return self.tracker is not None

    @property
    def tracker_name(self) -> str:
        return f"{self.tracker.device_name} ({self.tracker.serial_number})" if self.tracker else "N/A"
    
    def set_connection_callbacks(self, on_lost: Callable[[], None], on_restored: Callable[[], None]):
        """Allows the Manager to register callbacks for hardware events."""
        self._on_connection_lost = on_lost
        self._on_connection_restored = on_restored

    async def connect(self, display_settings: DisplayAreaSettings) -> bool:
        try:
            trackers = await asyncio.to_thread(tr.find_all_eyetrackers)
            
            if not trackers:
                return False

            self.tracker = trackers[0]

            self._subscribe_notifications()
            
            await self.apply_display_settings(display_settings)

        except Exception as e:
            logger.error(f"Hardware connection failed: {e}")
            return False
        
        return True
    
    def _subscribe_notifications(self):
        """Subscribes to Tobii connection events."""
        if self.tracker is None:
            return
        
        loop = asyncio.get_running_loop()

        def notification_callback(notification, _):
            if notification == tr.EYETRACKER_NOTIFICATION_CONNECTION_LOST:
                logger.warning("Tobii Tracker LOST connection!")
                if self._on_connection_lost:
                    loop.call_soon_threadsafe(self._on_connection_lost)

            elif notification == tr.EYETRACKER_NOTIFICATION_CONNECTION_RESTORED:
                logger.info("Tobii Tracker RESTORED signal received!")
                loop.call_soon_threadsafe(lambda: asyncio.create_task(self._recover_state()))

        for notification in {tr.EYETRACKER_NOTIFICATION_CONNECTION_LOST, tr.EYETRACKER_NOTIFICATION_CONNECTION_RESTORED}:
            self.tracker.subscribe_to(
                notification,
                lambda x, n=notification: notification_callback(n, x)
            )
        logger.info("Subscribed to Tobii hardware notifications.")

    async def _recover_state(self):
        """Automatically called when tracker reconnects to re-apply geometry and calibration."""
        logger.info("Attempting to recover hardware settings...")
        if self.last_display_settings:
            await self.apply_display_settings(self.last_display_settings)
        if self.last_calibration_path:
            await self.load_calibration(self.last_calibration_path)
            
        if self._on_connection_restored is not None:
            self._on_connection_restored()

    def create_source(self) -> TobiiSource:
        return TobiiSource(self.tracker, self.screen_width, self.screen_height)

    @require_tracker
    async def load_calibration(self, folder: Path) -> bool:
        bin_path = folder / "calibration.bin"
        if not bin_path.exists():
            return False
        
        try:
            data = await asyncio.to_thread(bin_path.read_bytes)
            await asyncio.to_thread(self.tracker.apply_calibration_data, data)
            self.last_calibration_path = folder # Cache it so we can re-apply on connection restore
            logger.info("Loaded calibration: %s", bin_path)

        except Exception as e:
            logger.error(f"Load calibration failed: {e}")
            return False
        
        return True


    @require_tracker
    async def calibrate(
        self, 
        save_folder: Path, 
        view: CalibrationView
    ) -> bool:
        """
        Orchestrates the calibration sequence: UI -> Hardware -> UI -> Hardware.
        """
        calib_obj = tr.ScreenBasedCalibration(self.tracker)

        try:
            await view.open()
            await view.show_message("Preparing hardware...")
            
            # 1. Enter Mode
            await asyncio.to_thread(calib_obj.enter_calibration_mode)
            
            # 2. Collect Points
            for x, y in self.CALIBRATION_POINTS:
                # UI Draw
                await view.show_point(x, y)
                # Stabilization Wait
                await asyncio.sleep(0.5) 
                # Hardware Sample
                status = await asyncio.to_thread(calib_obj.collect_data, x, y)
                if status != tr.CALIBRATION_STATUS_SUCCESS:
                    logger.warning(f"Calibration point ({x}, {y}) failed.")

            # 3. Compute
            await view.show_message("Computing result...")
            result = await asyncio.to_thread(calib_obj.compute_and_apply)
            
            # 4. Leave Mode
            await asyncio.to_thread(calib_obj.leave_calibration_mode)

            # 5. Handle Result
            if result.status == tr.CALIBRATION_STATUS_SUCCESS:
                # Save calibration
                bin_data = self.tracker.retrieve_calibration_data()
                (save_folder / "calibration.bin").write_bytes(bin_data)
                self.last_calibration_path = save_folder
                
                # Save results
                results = self._map_to_dict(result)
                results["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                with open(save_folder / "calibration_result.json", "w") as f:
                    json.dump(results, f, indent=2)
                
                # Show visualization to user
                await view.show_results(results)
                return True
            
            return False

        except Exception as e:
            logger.error(f"Calibration sequence failed: {e}", exc_info=True)
            try:
                await asyncio.to_thread(calib_obj.leave_calibration_mode)
            except:
                pass
            return False
        finally:
            await view.close()

    def shutdown(self) -> None:
        if self.tracker:
            try:
                self.tracker.unsubscribe_from(tr.EYETRACKER_NOTIFICATION_CONNECTION_LOST)
                self.tracker.unsubscribe_from(tr.EYETRACKER_NOTIFICATION_CONNECTION_RESTORED)
            except Exception as e:
                logger.debug(f"Failed to cleanly unsubscribe notifications: {e}")
        
        self.tracker = None

    async def apply_display_settings(self, cfg: DisplayAreaSettings) -> bool:
        w, h = cfg.width_mm, cfg.height_mm
        vo, ho, d = cfg.vertical_offset_mm, cfg.horizontal_offset_mm, cfg.depth_offset_mm

        self.screen_height, self.screen_width = cfg.height_px, cfg.width_px
        self.last_display_settings = cfg

        coords = {
            "top_left": (-(w/2) + ho, h + vo, d),
            "top_right": ((w/2) + ho, h + vo, d),
            "bottom_left": (-(w/2) + ho, vo, d),
        }

        try:
            area = tr.DisplayArea(coords)
            await asyncio.to_thread(self.tracker.set_display_area, area)
            logger.info(f"Display Area applied: {self.screen_width}x{self.screen_height}")
            return True

        except Exception:
            logger.exception("Hardware rejected DisplayArea configuration.")
            return False
        
    def _map_to_dict(self, result: tr.CalibrationResult) -> dict:
        """Converts SDK object to clean dict."""
        if result.status != tr.CALIBRATION_STATUS_SUCCESS:
            return {"status": str(result.status), "points": []}
        
        points = []
        for cp in result.calibration_points:
            p_data = {
                "target": {"x": cp.position_on_display_area[0], "y": cp.position_on_display_area[1]},
                "samples": []
            }

            for s in cp.calibration_samples:
                sample = {}
                
                for name, eye in [("left", s.left_eye), ("right", s.right_eye)]:
                    if eye and eye.validity == tr.VALIDITY_VALID_AND_USED:
                        sample[name] = {
                            "x": eye.position_on_display_area[0],
                            "y": eye.position_on_display_area[1]
                        }
                
                if sample:
                    p_data["samples"].append(sample)
            
            points.append(p_data)

        return {"status": "success", "points": points}