import asyncio
import logging
from asyncio import Queue, Event
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import tobii_research as tr

from gaze_capture.acquisition import GazeSource, TobiiGazeSource, DummyGazeSource
from gaze_capture.config import settings
from gaze_capture.models.gaze import GazeData
from gaze_capture.pipeline.bundler import Bundler
from gaze_capture.pipeline.distributor import Distributor
from gaze_capture.protos import gaze_pb2
from gaze_capture.sinks.csv import CSVSink
from gaze_capture.sinks.http import HTTPSink

logger = logging.getLogger(__name__)


class PipelineManager:
    """
    Builds, starts, and stops the data acquisition and sink pipeline.

    This class orchestrates the various asyncio components (source, distributor,
    sinks) into a cohesive data processing pipeline. It is configured
    dynamically based on user selections in the UI.
    """

    def __init__(self, use_dummy_source: bool = False):
        """
        Initializes the PipelineManager.

        Args:
            use_dummy_source: If True, uses a simulated gaze source instead of
                              the Tobii hardware. Useful for development.
        """
        self._tasks: List[asyncio.Task] = []
        self._source: Optional[GazeSource] = None
        self._use_dummy_source = use_dummy_source

    @property
    def is_running(self) -> bool:
        """Returns True if the pipeline is currently active."""
        return bool(self._tasks)

    async def start(
        self,
        tracker: tr.EyeTracker,
        participant_dir: Path,
        enabled_sinks: List[str]
    ) -> None:
        """
        Constructs and starts all pipeline components as asyncio tasks.

        Args:
            tracker: The connected Tobii EyeTracker object.
            participant_dir: The directory to save participant-specific data (like CSVs).
            enabled_sinks: A list of strings specifying which sinks to activate,
                           e.g., ["csv", "http"].
        """
        if self.is_running:
            logger.warning("Pipeline is already running. Stop it before starting again.")
            return

        logger.info(f"Building and starting data pipeline with sinks: {enabled_sinks}")
        stop_event = Event()

        # 1. Create the primary queue for data from the source.
        source_q = Queue[GazeData](maxsize=1000)

        # 2. Instantiate the appropriate GazeSource.
        if self._use_dummy_source:
            self._source = DummyGazeSource(source_q, stop_event, frequency=120)
        else:
            self._source = TobiiGazeSource(source_q, stop_event)
            # The source requires the active tracker to subscribe to its data stream.
            self._source.tracker = tracker

        distributor_output_queues = []
        
        # 3. Dynamically build the sink branches of the pipeline.
        if "csv" in enabled_sinks:
            csv_sink_q = Queue[GazeData]()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = participant_dir / f"gaze_data_{timestamp}.csv"
            csv_sink = CSVSink(csv_sink_q, csv_path)

            self._tasks.append(asyncio.create_task(csv_sink.run()))
            distributor_output_queues.append(csv_sink_q)
            logger.info(f"CSV sink enabled. Output to: {csv_path}")

        if "http" in enabled_sinks:
            http_sink_q = Queue[gaze_pb2.GazeBundle]()
            bundler_input_q = Queue[GazeData]()
            
            bundler = Bundler(
                input_queue=bundler_input_q,
                output_queue=http_sink_q,
                bundle_size=settings.pipeline.bundle_size,
                max_interval_s=settings.pipeline.max_bundle_interval_s
            )
            http_sink = HTTPSink(
                input_queue=http_sink_q,
                server_url=settings.http_sink.server_url,
                max_concurrent_sends=settings.http_sink.max_concurrent_sends,
                retry_attempts=settings.http_sink.retry_attempts,
                backoff_factor_s=settings.http_sink.retry_backoff_factor_s
            )

            self._tasks.extend([
                asyncio.create_task(bundler.run()),
                asyncio.create_task(http_sink.run())
            ])
            distributor_output_queues.append(bundler_input_q)
            logger.info(f"HTTP sink enabled. Sending to: {settings.http_sink.server_url}")

        # 4. Create the Distributor to fan-out data to all active sinks.
        distributor = Distributor(source_q, distributor_output_queues)

        # 5. Add the source and distributor tasks to be managed.
        self._tasks.extend([
            asyncio.create_task(self._source.run()),
            asyncio.create_task(distributor.run())
        ])

        logger.info(f"Pipeline started with {len(self._tasks)} running tasks.")

    async def stop(self) -> None:
        """
        Stops the source and gracefully cancels all running pipeline tasks.
        
        This method ensures a clean shutdown by first stopping data production,
        allowing queues to drain, and then cancelling consumer tasks.
        """
        if not self.is_running:
            return
        
        logger.info("Stopping data pipeline...")
        if self._source:
            # This signals the GazeSource to stop producing new data.
            await self._source.stop()
        
        # Allow a grace period for in-flight data to be processed by sinks.
        # This is especially important for the Bundler.
        grace_period = settings.pipeline.max_bundle_interval_s + 0.5
        logger.info(f"Waiting {grace_period:.1f}s for queues to drain...")
        await asyncio.sleep(grace_period)

        # Cancel all running tasks (sinks, bundler, distributor, etc.).
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        # Wait for all tasks to acknowledge cancellation and finish cleanup.
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        self._source = None
        logger.info("Pipeline stopped successfully.")