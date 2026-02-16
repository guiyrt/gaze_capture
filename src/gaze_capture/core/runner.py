import asyncio
import logging
from typing import Sequence

from ..acquisition import GazeSource
from ..sinks import GazeSink
from ..utils.types import _END

logger = logging.getLogger(__name__)

class GazeRunner:
    """
    Orchestrates the 120Hz data flow from Source -> Sinks.
    Created fresh for every recording session.
    """
    def __init__(self, source: GazeSource, sinks: Sequence[GazeSink]):
        self.source = source
        self.sinks = sinks
        self._running = False
        self._loop_task: asyncio.Task | None = None
        self._source_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._running:
            return
        
        logger.info("Starting GazeRunner...")
        self._running = True
        
        # Start sinks
        await asyncio.gather(*(s.start() for s in self.sinks))
        
        # Start source
        self._source_task = asyncio.create_task(self.source.run())
        
        # Start data loop
        self._loop_task = asyncio.create_task(self._process_loop())
        logger.info("GazeRunner active.")

    async def stop(self) -> None:
        if not self._running:
            return
            
        logger.info("Stopping GazeRunner...")
        self._running = False
        
        # Stop source
        await self.source.stop()
        if self._source_task:
            await self._source_task
        
        # Stop data loop
        if self._loop_task:
            await self._loop_task
        
        # Close sinks
        await asyncio.gather(*(s.close() for s in self.sinks))
        
        logger.info("GazeRunner stopped.")

    async def _process_loop(self) -> None:
        """Hot loop."""
        queue = self.source.output_queue

        try:
            while True:
                item = await queue.get()

                if item is _END:
                    break

                await asyncio.gather(*(s.send(item) for s in self.sinks))

        except asyncio.CancelledError:
            logger.info("Runner loop cancelled unexpectedly.")