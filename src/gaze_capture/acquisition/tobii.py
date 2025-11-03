import asyncio
import logging
from typing import Optional

import tobii_research as tr

from gaze_capture.models.gaze import GazeData
from .base import GazeSource

logger = logging.getLogger(__name__)


class TobiiGazeSource(GazeSource):
    """
    A GazeSource that acquires data from a connected Tobii eye tracker.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker: Optional[tr.EyeTracker] = None
        self._loop = asyncio.get_running_loop()

    def _gaze_data_callback(self, gaze_data: dict) -> None:
        """
        Thread-safe callback bridge from the Tobii SDK to the asyncio world.

        This method is called by a background thread from the Tobii SDK.
        It converts the raw dictionary data into a structured GazeData object
        and safely puts it into the asyncio queue.
        """
        try:
            # Convert dict to our standardized GazeData object
            model = GazeData(
                device_time_stamp=gaze_data["device_time_stamp"],
                system_time_stamp=gaze_data["system_time_stamp"],
                left_gaze_point=(
                    gaze_data["left_gaze_point_on_display_area"]
                    if gaze_data["left_gaze_point_validity"]
                    else None
                ),
                right_gaze_point=(
                    gaze_data["right_gaze_point_on_display_area"]
                    if gaze_data["right_gaze_point_validity"]
                    else None
                ),
            )
            # Use call_soon_threadsafe to safely interact with the asyncio loop
            self._loop.call_soon_threadsafe(self._output_queue.put_nowait, model)
        except RuntimeError:
            # This can happen if the event loop is closed during shutdown.
            # It's safe to ignore.
            pass
        except Exception:
            logger.exception("Error processing gaze data from Tobii callback.")

    async def _find_tracker(self) -> Optional[tr.EyeTracker]:
        """
        Asynchronously finds the first available Tobii eye tracker.

        Runs the blocking `find_all_eyetrackers` call in a separate thread
        to avoid blocking the asyncio event loop.
        """
        logger.info("Searching for eye trackers...")
        eyetrackers = await self._loop.run_in_executor(
            None, tr.find_all_eyetrackers
        )

        if not eyetrackers:
            logger.error("No eye trackers found.")
            return None

        tracker = eyetrackers[0]
        logger.info(f"Found tracker: {tracker.device_name} ({tracker.serial_number})")
        return tracker

    async def run(self) -> None:
        """
        Main execution loop for the Tobii source.

        Finds a tracker, subscribes to its gaze data stream, and waits until
        the stop event is set before cleaning up.
        """
        self.tracker = await self._find_tracker()
        
        if not self.tracker:
            logger.error("Failed to find a Tobii tracker. Stopping source.")
            return
        
        if self._stop_event.is_set():
            logger.info("Stop event was set during tracker search. Aborting run.")
            return

        subscribed = False
        try:
            logger.info("Subscribing to gaze data stream...")
            self.tracker.subscribe_to(
                tr.EYETRACKER_GAZE_DATA, self._gaze_data_callback, as_dictionary=True
            )
            subscribed = True

            await self._stop_event.wait()
            
            logger.info("Stop event received, shutting down Tobii source.")

        except tr.EyeTrackerException as e:
            logger.error(f"A Tobii SDK error occurred: {e}", exc_info=True)
        
        except Exception:
            logger.exception("An unexpected error occurred in the Tobii source run loop.")
        
        finally:
            logger.info("Unsubscribing from gaze data stream...")
            if subscribed and self.tracker:
                self.tracker.unsubscribe_from(
                    tr.EYETRACKER_GAZE_DATA, self._gaze_data_callback
                )
            
            logger.info("Tobii source has been cleaned up.")