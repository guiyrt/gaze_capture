# src/gaze_capture/sinks/http.py

import asyncio
import logging
from asyncio import Queue, Semaphore
from typing import Set

import aiohttp

from gaze_capture.protos import gaze_pb2
from .base import Sink

logger = logging.getLogger(__name__)


class HTTPSink(Sink[gaze_pb2.GazeBundle]):
    """
    A Sink that serializes protobuf GazeBundle messages and sends them to an
    HTTP endpoint.

    This sink is designed for high-throughput, resilient data transfer. It
    features:
    - Automatic retries with exponential backoff for transient network issues.
    - Concurrency limiting to avoid overwhelming the network or the server.
    - Graceful shutdown to ensure all in-flight data is sent before exiting.
    """

    def __init__(
        self,
        input_queue: Queue[gaze_pb2.GazeBundle],
        server_url: str,
        max_concurrent_sends: int = 10,
        retry_attempts: int = 3,
        backoff_factor_s: float = 0.5,
    ):
        """
        Initializes the HTTPSink.

        Args:
            input_queue: The queue from which to consume GazeBundle messages.
            server_url: The URL of the HTTP endpoint to send data to.
            max_concurrent_sends: The maximum number of parallel HTTP requests.
            retry_attempts: The number of times to retry a failed request.
            backoff_factor_s: The base factor for exponential backoff delay.
        """
        super().__init__(input_queue)
        self._server_url = server_url
        self._retry_attempts = retry_attempts
        self._backoff_factor_s = backoff_factor_s
        self._semaphore = Semaphore(max_concurrent_sends)
        self._active_sends: Set[asyncio.Task] = set()

    async def _send_with_retry(self, session: aiohttp.ClientSession, payload: bytes) -> bool:
        """Sends a data payload with an exponential backoff retry mechanism."""
        for attempt in range(self._retry_attempts):
            try:
                # Use a timeout for each individual request attempt.
                timeout = aiohttp.ClientTimeout(total=5.0)
                async with session.post(
                    self._server_url,
                    data=payload,
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=timeout,
                ) as response:
                    if 200 <= response.status < 300:
                        logger.debug(f"Successfully sent bundle, status: {response.status}")
                        return True
                    else:
                        response_text = await response.text()
                        logger.warning(
                            f"Server returned non-success status: {response.status} "
                            f"on attempt {attempt + 1}. Response: {response_text}"
                        )

            except aiohttp.ClientError as e:
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
            except asyncio.TimeoutError:
                logger.warning(f"Request timed out on attempt {attempt + 1}")

            if attempt < self._retry_attempts - 1:
                backoff_time = self._backoff_factor_s * (2**attempt)
                logger.info(f"Retrying in {backoff_time:.2f} seconds...")
                await asyncio.sleep(backoff_time)

        logger.error("Failed to send bundle after all %d retries.", self._retry_attempts)
        return False

    async def _managed_send_task(
        self, session: aiohttp.ClientSession, bundle: gaze_pb2.GazeBundle
    ) -> None:
        """
        A wrapper task that handles serialization, sending, and semaphore release.

        This ensures that the semaphore is always released, even if the sending
        process fails.
        """
        try:
            payload = bundle.SerializeToString()
            await self._send_with_retry(session, payload)
        finally:
            self._semaphore.release()
            logger.debug("Semaphore released. Current concurrent sends: %d", self._semaphore._value)

    async def run(self) -> None:
        """
        Main execution loop for the HTTPSink.

        Continuously takes bundles from the input queue, and creates managed,
        concurrent tasks to send them to the server.
        """
        logger.info(
            f"HTTPSink started. Sending to {self._server_url} "
            f"with max concurrency of {self._semaphore._value}."
        )
        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    bundle = await self._input_queue.get()

                    # Wait until a slot is available for a new concurrent request.
                    # This naturally applies backpressure if the network is slow.
                    await self._semaphore.acquire()

                    # Create a non-blocking task to send the data.
                    task = asyncio.create_task(self._managed_send_task(session, bundle))
                    self._active_sends.add(task)
                    # When the task is done, remove it from the active set.
                    task.add_done_callback(self._active_sends.discard)

        except asyncio.CancelledError:
            logger.info(
                "HTTPSink cancelling. Waiting for %d pending sends to complete...",
                len(self._active_sends),
            )
            # Wait for all tasks that were already started to finish their work.
            if self._active_sends:
                await asyncio.gather(*self._active_sends, return_exceptions=True)
            logger.info("All pending sends finished. HTTPSink shut down.")

        except Exception:
            logger.exception("An unexpected error occurred in the HTTPSink run loop.")