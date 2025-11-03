# src/gaze_capture/sinks/csv.py

import asyncio
import csv
import logging
from asyncio import Queue
from pathlib import Path
from typing import TextIO

from gaze_capture.models.gaze import GazeData
from .base import Sink

logger = logging.getLogger(__name__)


class CSVSink(Sink[GazeData]):
    """
    A sink that consumes GazeData objects and writes them to a CSV file.

    This sink is designed for simple, line-by-line logging of gaze data,
    making it ideal for straightforward data collection and analysis.
    """

    # Define the CSV header for consistency.
    _CSV_HEADER = [
        "device_time_stamp",
        "system_time_stamp",
        "left_gaze_point_x",
        "left_gaze_point_y",
        "right_gaze_point_x",
        "right_gaze_point_y",
    ]

    def __init__(self, input_queue: Queue[GazeData], output_filepath: Path):
        """
        Initializes the CSVSink.

        Args:
            input_queue: The queue from which to consume GazeData objects.
            output_filepath: The path to the CSV file to be created.
        """
        super().__init__(input_queue)
        self._output_filepath = output_filepath
        self._csv_file: TextIO | None = None
        self._csv_writer = None

    def _open_file(self) -> None:
        """Opens the specified CSV file and writes the header row."""
        try:
            self._output_filepath.parent.mkdir(parents=True, exist_ok=True)
            # Use 'w' mode to create a new file, overwriting if it exists.
            self._csv_file = self._output_filepath.open("w", newline="", encoding="utf-8")
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow(self._CSV_HEADER)
            logger.info(f"Opened CSV file for writing: {self._output_filepath}")
        except IOError:
            logger.exception(f"Failed to open file for writing: {self._output_filepath}")
            # Re-raise the exception to stop the sink's run() method if the
            # file cannot be opened.
            raise

    def _close_file(self) -> None:
        """Closes the CSV file if it is open."""
        if self._csv_file:
            self._csv_file.close()
            logger.info(f"Closed CSV file: {self._output_filepath}")
            self._csv_file = None

    async def run(self) -> None:
        """
        Main execution loop for the CSVSink.

        Continuously takes GazeData objects from the input queue and writes
        them as rows to the CSV file.
        """
        try:
            self._open_file()
            while True:
                sample = await self._input_queue.get()
                
                left_x, left_y = (
                    sample.left_gaze_point if sample.left_gaze_point else (None, None)
                )
                right_x, right_y = (
                    sample.right_gaze_point if sample.right_gaze_point else (None, None)
                )

                self._csv_writer.writerow([
                    sample.device_time_stamp,
                    sample.system_time_stamp,
                    left_x,
                    left_y,
                    right_x,
                    right_y,
                ])
                
                # Signal that the item from the queue has been processed.
                # Useful for pipeline management, e.g., with queue.join().
                self._input_queue.task_done()

        except asyncio.CancelledError:
            logger.info("CSVSink process cancelled.")
        except IOError:
            # This will catch errors from _open_file and subsequent write errors.
            logger.error("CSVSink is stopping due to a file I/O error.")
        except Exception:
            logger.exception("An unexpected error occurred in the CSVSink.")
        finally:
            self._close_file()