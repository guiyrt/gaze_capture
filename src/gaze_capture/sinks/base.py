from abc import ABC, abstractmethod
from ..models import GazeData

class GazeSink(ABC):
    """
    Abstract Base Class for all data sinks.
    Provides common context manager logic for simplified lifecycle management.
    """

    @abstractmethod
    async def start(self) -> None:
        """Initialize sink resources."""
        pass

    @abstractmethod
    async def send(self, data: GazeData) -> None:
        """
        Push data to the sink. 
        Must be non-blocking to the caller.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up sink resources."""
        pass

    # --- Shared Logic (Code Reuse) ---

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.close()