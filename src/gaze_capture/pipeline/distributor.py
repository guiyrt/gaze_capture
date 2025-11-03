import asyncio
import logging
from asyncio import Queue
from typing import TypeVar, List

T = TypeVar("T")  # Generic type for the data being distributed
logger = logging.getLogger(__name__)


class Distributor:
    """
    A pipeline component that fans-out data from a single input queue
    to multiple output queues.
    """

    def __init__(self, input_queue: Queue[T], output_queues: List[Queue[T]]):
        self._input_queue = input_queue
        self._output_queues = output_queues
        logger.info(f"Distributor initialized to fan-out to {len(self._output_queues)} queues.")

    async def run(self) -> None:
        """
        Continuously reads from the input queue and puts a reference to
        the item into each output queue.
        """
        if not self._output_queues:
            logger.warning("Distributor has no output queues; it will run idly.")
            return
            
        while True:
            try:
                item = await self._input_queue.get()
                # Fan-out the item to all registered output queues
                for q in self._output_queues:
                    await q.put(item)
            
            except asyncio.CancelledError:
                logger.info("Distributor process cancelled.")
                break
            
            except Exception:
                logger.exception("An unexpected error occurred in the Distributor.")