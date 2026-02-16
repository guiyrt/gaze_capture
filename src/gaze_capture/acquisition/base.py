from abc import ABC, abstractmethod
from asyncio import Queue, Event
from typing import final

from ..models import GazeData
from ..utils.types import _END, EndToken

class GazeSource(ABC):
    """
    Abstract Base Class for Data Acquisition.
    Responsible for bridging Hardware Callbacks -> Asyncio Queue.
    """
    def __init__(self, screen_width: int, screen_height: int):
        self.output_queue: Queue[GazeData | EndToken] = Queue()
        self._stop_event = Event()
        self.screen_width = screen_width
        self.screen_height = screen_height

    @abstractmethod
    async def _collect_data(self) -> None:
        """
        Connects to hardware/stream and keeps running until stopped.
        Should handle its own cleanup/unsubscribing in a finally block.
        """
        ...

    @final
    async def run(self) -> None:
        """
        Public entry point. Wraps run() to guarantee End-of-Stream signal.
        """
        try:
            await self._collect_data()
        finally:
            await self.output_queue.put(_END)

    @final
    async def stop(self) -> None:
        """
        Signals the source to stop acquiring data.

        This is a final method and should not be overridden. Subclasses can
        perform cleanup in their 'run' method's finally block.
        """
        self._stop_event.set()