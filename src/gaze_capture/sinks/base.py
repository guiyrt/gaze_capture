# src/gaze_capture/sinks/base.py

from abc import ABC, abstractmethod
from asyncio import Queue
from typing import Generic, TypeVar

# Define a generic type variable for the data the sink will consume.
InputType = TypeVar("InputType")


class Sink(ABC, Generic[InputType]):
    """
    Abstract Base Class for all data sinks.

    A Sink is a runnable component that consumes data of a specific type
    from an input queue and forwards it to a final destination (e.g., an
    HTTP server, a file, a database). This class is generic, allowing
    implementations to specify the type of data they expect.
    """

    def __init__(self, input_queue: Queue[InputType]):
        """
        Initializes the Sink with its input queue.

        Args:
            input_queue: The asyncio queue from which the sink will consume items.
        """
        self._input_queue = input_queue

    @abstractmethod
    async def run(self) -> None:
        """
        Starts the data consumption and sending process.

        This method should run continuously, taking data from the input queue
        and processing it until the task is cancelled. It must be
        implemented by all concrete subclasses.
        """
        raise NotImplementedError