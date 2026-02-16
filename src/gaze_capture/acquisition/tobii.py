import asyncio
import logging
from typing import Any, Final
import tobii_research as tr

from .base import GazeSource
from ..models.gaze import GazeData
from ..utils.clock import TimeProbe

logger = logging.getLogger(__name__)

class TobiiSource(GazeSource):
    """
    Real Hardware Source.
    """

    _N_TIME_PROBES: Final[int] = 500

    def __init__(
        self,
        tracker: tr.EyeTracker,
        screen_width: int,
        screen_height: int,

    ) -> None:
        super().__init__(screen_width, screen_height)
        self.tracker = tracker
        self._loop = asyncio.get_running_loop()
        self._time_offset: TimeProbe | None = None

    def _callback(self, data: dict[str, Any]) -> None:
        try:
            # Extract validities
            l_valid = data["left_gaze_point_validity"]
            r_valid = data["right_gaze_point_validity"]
            
            # Extract coordinates
            lx, ly = data["left_gaze_point_on_display_area"] if l_valid else (None, None)
            rx, ry = data["right_gaze_point_on_display_area"] if r_valid else (None, None)
            
            # Calculate midpoint
            if l_valid and r_valid:
                mid_x = (lx + rx) / 2
                mid_y = (ly + ry) / 2
            elif l_valid:
                mid_x, mid_y = lx, ly
            elif r_valid:
                mid_x, mid_y = rx, ry
            else:
                mid_x, mid_y = None, None

            #  Must be inside screen limits
            mid_x_valid = mid_x is not None and 0. <= mid_x < 1.
            mid_y_valid = mid_y is not None and 0. <= mid_y < 1.
            
            # Round to nearest pixel
            if mid_x_valid and mid_y_valid:
                mid_x_px = int(mid_x * self.screen_width)
                mid_y_px = int(mid_y * self.screen_height)
            else:
                mid_x_px, mid_y_px = None, None

            # Create object
            model = GazeData(
                epoch_timestamp_ms=self._time_offset.to_utc_ms(data["system_time_stamp"]),
                device_timestamp_us=data["device_time_stamp"],
                system_timestamp_us=data["system_time_stamp"],
                mid_x_px=mid_x_px,
                mid_y_px=mid_y_px,
                mid_x=mid_x,
                mid_y=mid_y,
                left_x=lx,
                left_y=ly,
                right_x=rx,
                right_y=ry,
                left_pupil=data["left_pupil_diameter"] if data["left_pupil_validity"] else None,
                right_pupil=data["right_pupil_diameter"] if data["right_pupil_validity"] else None,
                left_origin=data["left_gaze_origin_in_user_coordinate_system"] if data["left_gaze_origin_validity"] else None,
                right_origin=data["right_gaze_origin_in_user_coordinate_system"] if data["right_gaze_origin_validity"] else None,
                left_3d=data["left_gaze_point_in_user_coordinate_system"] if l_valid else None,
                right_3d=data["right_gaze_point_in_user_coordinate_system"] if r_valid else None,
            )

            self._loop.call_soon_threadsafe(self.output_queue.put_nowait, model)

        except Exception as e:
            # Log and continue to prevent crashing C-thread
            logger.error(e)

    async def _collect_data(self) -> None:
        self._time_offset = min(TimeProbe(tr.get_system_time_stamp) for _ in range(self._N_TIME_PROBES))

        try:
            logger.info(f"Subscribing to {self.tracker.device_name} (Res: {self.screen_width}x{self.screen_height})")
            self.tracker.subscribe_to(tr.EYETRACKER_GAZE_DATA, self._callback, as_dictionary=True)

            await self._stop_event.wait()
            logger.info("Stop event received, shutting down Tobii eye-tracker.")
        
        finally:
            logger.info("Unsubscribing from gaze data stream...")
            self.tracker.unsubscribe_from(tr.EYETRACKER_GAZE_DATA, self._callback)