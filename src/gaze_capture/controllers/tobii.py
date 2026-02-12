import json
import logging
import datetime
import asyncio
from pathlib import Path
from typing import Optional, TypeVar

import tobii_research as tr
from screeninfo import get_monitors

from .base import GazeTrackerController, require_tracker
from ..acquisition import TobiiSource
from ..configs import DisplayAreaSettings, CalibrationSettings
from ..ui import TkinterCalibrationView

logger = logging.getLogger(__name__)

T = TypeVar("T")

class TobiiController(GazeTrackerController):
    def __init__(self, bridge):
        super().__init__(bridge)
        self.tracker: Optional[tr.EyeTracker] = None

    @property
    def is_connected(self) -> bool:
        return self.tracker is not None

    @property
    def tracker_name(self) -> str:
        return self.tracker.device_name if self.tracker else "N/A"

    async def connect(self, display_settings: DisplayAreaSettings) -> bool:
        try:
            # 1. Screen Discovery
            self.screen_width, self.screen_height = display_settings.width_px, display_settings.height_px

            # 2. Tracker Discovery
            trackers = await asyncio.to_thread(tr.find_all_eyetrackers)
            if not trackers:
                return False

            self.tracker = trackers[0]
            
            # 3. Apply Display Geometry
            await self._apply_display_area(display_settings)
            return True
        except Exception as e:
            logger.error(f"Hardware connection failed: {e}")
            return False

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
            return True
        except Exception as e:
            logger.error(f"Load calibration failed: {e}")
            return False

    @require_tracker
    async def calibrate(
        self, 
        save_folder: Path, 
        calib_settings: CalibrationSettings, 
        view: TkinterCalibrationView
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
            for x, y in calib_settings.points_to_calibrate:
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
        self.tracker = None

    async def _apply_display_area(self, cfg: DisplayAreaSettings) -> None:
        w, h = cfg.width_mm, cfg.height_mm
        vo, ho, d = cfg.vertical_offset_mm, cfg.horizontal_offset_mm, cfg.depth_offset_mm

        coords = {
            "top_left": (-(w/2) + ho, h + vo, d),
            "top_right": ((w/2) + ho, h + vo, d),
            "bottom_left": (-(w/2) + ho, vo, d),
        }

        try:
            area = tr.DisplayArea(coords)
            await asyncio.to_thread(self.tracker.set_display_area, area)
            logger.info(f"Display Area applied: {self.screen_width}x{self.screen_height}")
        except Exception:
            logger.exception("Hardware rejected DisplayArea configuration.")
        
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