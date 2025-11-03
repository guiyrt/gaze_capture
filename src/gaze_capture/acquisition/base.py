from abc import ABC, abstractmethod
from asyncio import Queue, Event
from typing import final

from gaze_capture.models.gaze import GazeData


class GazeSource(ABC):
    """
    Abstract Base Class for all gaze data sources.

    A GazeSource is a runnable component that acquires gaze data from a specific
    origin (e.g., hardware, file) and puts `GazeData` objects into an
    output queue for further processing.
    """

    def __init__(self, output_queue: Queue[GazeData], stop_event: Event):
        self._output_queue = output_queue
        self._stop_event = stop_event

    @abstractmethod
    async def run(self) -> None:
        """
        Starts the data acquisition process.

        This method should run continuously, acquiring data and placing it
        into the output queue until the `stop_event` is set. It must be
        implemented by all concrete subclasses.
        """
        raise NotImplementedError

    @final
    async def stop(self) -> None:
        """
        Signals the source to stop acquiring data.

        This is a final method and should not be overridden. Subclasses can
        perform cleanup in their 'run' method's finally block.
        """
        self._stop_event.set()