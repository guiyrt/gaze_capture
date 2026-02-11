import time
import math
import asyncio
import logging

from gaze_capture.models.gaze import GazeData
from .base import GazeSource

logger = logging.getLogger(__name__)

class DummySource(GazeSource):
    """
    Simulated Source for Testing.
    """
    def __init__(self, screen_width: int, screen_height: int, frequency: int = 120):
        super().__init__(screen_width, screen_height)
        self.frequency = frequency

    async def _collect_data(self) -> None:
        logger.info(f"Starting Dummy Source @ {self.frequency}Hz")
        interval_ns = 1_000_000_000 // self.frequency
        t0_ns = time.monotonic_ns()
        frame = 0
        
        # Center of screen
        cx, cy = 0.5, 0.5
        radius = 0.3

        while not self._stop_event.is_set():
            now_ns = time.monotonic_ns()
            elapsed_s = (now_ns - t0_ns) / 1e9
            
            # Circle Math
            angle = elapsed_s * 2 * math.pi * 0.5
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            
            # Pixels
            x_px = int(x * self.screen_width)
            y_px = int(y * self.screen_height)

            model = GazeData(
                epoch_timestamp_ms=int(time.time() * 1_000),
                device_timestamp_us=(now_ns - t0_ns) // 1_000,
                system_timestamp_us=now_ns // 1_000,
                mid_x_px=x_px,
                mid_y_px=y_px,
                mid_x=x,
                mid_y=y,
                left_x=x,
                left_y=y,
                right_x=x,
                right_y=y,
                left_pupil=None,
                right_pupil=None,
                left_origin=None,
                right_origin=None,
                left_3d= None,
                right_3d=None,
            )
            
            await self.output_queue.put(model)
            
            # Sleep
            frame += 1
            target_ns = t0_ns + (frame * interval_ns)
            delay_s = (target_ns - time.monotonic_ns()) / 1e9
            if delay_s > 0:
                await asyncio.sleep(delay_s)