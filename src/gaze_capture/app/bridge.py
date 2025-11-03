import asyncio
import logging
import threading
from typing import Coroutine

logger = logging.getLogger(__name__)


class AsyncioTkinterBridge:
    """
    Manages the asyncio event loop in a separate thread.

    This allows the asyncio loop to run concurrently with the Tkinter main loop,
    preventing the UI from freezing while asynchronous operations (like network
    requests or hardware I/O) are in progress. It provides a thread-safe
    method to schedule coroutines on the asyncio loop from the Tkinter thread.
    """

    def __init__(self):
        """Initializes the bridge and the asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="AsyncioEventLoopThread",
            daemon=True
        )
        self._is_running = False

    def _run_loop(self) -> None:
        """The target function for the background thread."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()
            logger.info("Asyncio event loop closed.")

    def start(self) -> None:
        """Starts the background thread and the asyncio event loop."""
        if self._is_running:
            logger.warning("Bridge is already running.")
            return

        logger.info("Starting asyncio event loop thread.")
        self._is_running = True
        self._thread.start()

    def stop(self) -> None:
        """Signals the asyncio event loop to stop and waits for the thread."""
        if not self._is_running:
            return

        logger.info("Stopping asyncio event loop...")
        # call_soon_threadsafe is the key to safe cross-thread communication.
        self._loop.call_soon_threadsafe(self._loop.stop)
        # Wait for the thread to finish its cleanup.
        self._thread.join()
        self._is_running = False
        logger.info("Asyncio bridge stopped.")

    def run_coro_threadsafe(self, coro: Coroutine) -> asyncio.Future:
        """
        Schedules a coroutine to be executed on the asyncio event loop.

        This method is safe to call from any thread, including the main
        Tkinter thread.

        Args:
            coro: The coroutine to execute.

        Returns:
            An asyncio.Future that can be used to get the result of the
            coroutine.
        """
        if not self._is_running:
            raise RuntimeError("Cannot schedule coroutine, the bridge is not running.")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Provides access to the underlying asyncio event loop."""
        return self._loop