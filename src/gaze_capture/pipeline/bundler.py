import asyncio
import logging
from asyncio import Queue

from gaze_capture.models.gaze import GazeData
from gaze_capture.protos import gaze_pb2

logger = logging.getLogger(__name__)


class Bundler:
    """
    A pipeline component that consumes GazeData samples and bundles them.

    It reads from a single input queue and collects samples into a GazeBundle
    protobuf message. A bundle is emitted to a single output queue when either
    the bundle size reaches a specified threshold or a maximum time interval
    has passed since the first sample was added. This component is designed
    to be a reusable piece of a larger data processing pipeline.
    """

    def __init__(
        self,
        input_queue: Queue[GazeData],
        output_queue: Queue[gaze_pb2.GazeBundle],
        bundle_size: int,
        max_interval_s: float,
    ):
        """
        Initializes the Bundler.

        Args:
            input_queue: The queue from which to consume GazeData samples.
            output_queue: The queue to which GazeBundle messages will be sent.
            bundle_size: The maximum number of samples to include in a bundle.
            max_interval_s: The maximum time in seconds to wait before emitting
                            a partially filled bundle.
        """
        if bundle_size <= 0:
            raise ValueError("bundle_size must be a positive integer.")
        if max_interval_s <= 0:
            raise ValueError("max_interval_s must be a positive float.")

        self._input_queue = input_queue
        self._output_queue = output_queue
        self._bundle_size = bundle_size
        self._max_interval_s = max_interval_s
        self._loop = asyncio.get_running_loop()

    async def run(self) -> None:
        """
        Main execution loop for the Bundler.

        Continuously collects data from the input queue into bundles and puts
        them on the output queue. The loop handles graceful shutdown via
        asyncio.CancelledError.
        """
        logger.info(
            f"Bundler started. Max size: {self._bundle_size}, "
            f"Max interval: {self._max_interval_s}s."
        )
        try:
            while True:
                bundle = await self._collect_bundle()

                # Only emit a bundle if it contains samples. This can happen
                # if the timeout is reached while the input queue is empty.
                if bundle.samples:
                    logger.debug(f"Emitting a bundle with {len(bundle.samples)} samples.")
                    await self._output_queue.put(bundle)

        except asyncio.CancelledError:
            logger.info("Bundler process cancelled. Shutting down.")
        
        except Exception:
            logger.exception("An unexpected error occurred in the Bundler.")
            # In a production system, this might trigger a health check failure.
            # A short sleep prevents a tight loop of continuous failures.
            await asyncio.sleep(1)

    async def _collect_bundle(self) -> gaze_pb2.GazeBundle:
        """
        Collects samples for a single bundle until size or time limit is reached.
        """
        bundle = gaze_pb2.GazeBundle()
        
        # Set a deadline for this bundle collection process.
        deadline = self._loop.time() + self._max_interval_s

        while len(bundle.samples) < self._bundle_size:
            remaining_time = deadline - self._loop.time()
            if remaining_time <= 0:
                # Time limit for the bundle has been reached.
                break

            try:
                # Wait for the next item, but no longer than the remaining time.
                gaze_data = await asyncio.wait_for(
                    self._input_queue.get(), timeout=remaining_time
                )
                self._add_sample_to_bundle(bundle, gaze_data)

            except asyncio.TimeoutError:
                # This is an expected outcome when the input queue is empty
                # and the bundle interval expires.
                break

        return bundle

    @staticmethod
    def _add_sample_to_bundle(bundle: gaze_pb2.GazeBundle, gaze_data: GazeData) -> None:
        """Populates a GazeSample protobuf message from a GazeData object."""
        sample = bundle.samples.add()
        sample.device_timestamp_us = gaze_data.device_time_stamp
        sample.system_timestamp_us = gaze_data.system_time_stamp

        if gaze_data.left_gaze_point:
            sample.left_eye.x, sample.left_eye.y = gaze_data.left_gaze_point
        if gaze_data.right_gaze_point:
            sample.right_eye.x, sample.right_eye.y = gaze_data.right_gaze_point