import asyncio
import logging
import math
import time

from gaze_capture.models.gaze import GazeData
from .base import GazeSource

logger = logging.getLogger(__name__)


class DummyGazeSource(GazeSource):
    """
    A GazeSource that simulates gaze data for development and testing.

    This class generates a continuous stream of `GazeData` objects at a
    specified frequency, following a predictable pattern (a circular path).
    It is useful for developing and testing the rest of the pipeline without
    requiring a physical eye tracker.
    """

    def __init__(
        self,
        *args,
        frequency: int = 120,
        radius: float = 0.2,
        center: tuple[float, float] = (0.5, 0.5),
        speed: float = 0.5,
        **kwargs,
    ):
        """
        Initializes the DummyGazeSource.

        Args:
            frequency: The frequency in Hz to emit gaze data.
            radius: The radius of the circular path for the gaze point.
            center: The (x, y) center of the circular path.
            speed: The speed of the gaze point's movement along the circle
                   (in revolutions per second).
        """
        super().__init__(*args, **kwargs)
        if frequency <= 0:
            raise ValueError("Frequency must be positive.")

        self._frequency = frequency
        self._interval_s = 1.0 / self._frequency
        self._radius = radius
        self._center_x, self._center_y = center
        self._speed = speed  # Revolutions per second

        logger.info(
            f"DummyGazeSource initialized to run at {self._frequency} Hz."
        )

    async def run(self) -> None:
        """
        Main execution loop for the dummy source.

        Generates and queues GazeData at the configured frequency until the
        stop event is set.
        """
        start_time = time.monotonic()
        frame_counter = 0

        logger.info("Starting dummy gaze data stream...")
        try:
            while not self._stop_event.is_set():
                # --- Calculate precise timing for this frame ---
                target_time = start_time + (frame_counter * self._interval_s)

                # --- Generate simulated data ---
                current_loop_time = time.monotonic() - start_time
                system_time_stamp = time.monotonic_ns() // 1000

                # Simulate a device clock that started at 0 and increments steadily
                device_time_stamp = int(current_loop_time * 1_000_000)

                # Calculate position in a circular path
                angle = current_loop_time * self._speed * 2 * math.pi
                gaze_x = self._center_x + self._radius * math.cos(angle)
                gaze_y = self._center_y + self._radius * math.sin(angle)

                # Create the data model, slightly offsetting eyes for realism
                model = GazeData(
                    device_time_stamp=device_time_stamp,
                    system_time_stamp=system_time_stamp,
                    left_gaze_point=(gaze_x - 0.01, gaze_y),
                    right_gaze_point=(gaze_x + 0.01, gaze_y),
                )

                # --- Queue the data and wait for next frame ---
                await self._output_queue.put(model)

                # Sleep until the next frame's target time
                sleep_duration = target_time - time.monotonic()
                if sleep_duration > 0:
                    await asyncio.sleep(sleep_duration)

                frame_counter += 1

        except asyncio.CancelledError:
            logger.info("Dummy source run task was cancelled.")
        finally:
            logger.info("DummyGazeSource has stopped.")