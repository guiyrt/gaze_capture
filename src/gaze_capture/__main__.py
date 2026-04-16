import asyncio
import threading
import logging
import nats
from nats.errors import NoServersError

from gaze_capture.core.manager import EyeTrackingManager
from gaze_capture.ui.main_window import GazeCaptureApp
from gaze_capture.configs.app import AppSettings, LoggingConfig
from gaze_capture.controllers import TobiiController, DummyController

logger = logging.getLogger(__name__)

async def setup_nats(host: str) -> nats.NATS:
    """
    Initializes NATS with custom logging to prevent traceback spam.
    """
    nc = nats.NATS()

    async def disconnected_cb():
        logger.warning("NATS: Connection lost. Client is in buffering mode...")

    async def reconnected_cb():
        logger.info(f"NATS: Connection restored to {nc.connected_url.netloc}")

    async def error_cb(e):
        # This catches background errors (like heartbeats failing)
        logger.error(f"NATS Internal Error: {e}")

    async def closed_cb():
        logger.info("NATS: Connection closed.")

    # Connection Loop
    while True:
        try:
            await nc.connect(
                host,
                allow_reconnect=True,
                max_reconnect_attempts=-1, # Infinite reconnection
                reconnect_time_wait=2, # Wait 2s between attempts
                disconnected_cb=disconnected_cb,
                reconnected_cb=reconnected_cb,
                error_cb=error_cb,
                closed_cb=closed_cb,
            )
            logger.info(f"NATS: Initial connection established to {host}")
            return nc
        except (asyncio.TimeoutError, NoServersError, OSError) as e:
            logger.warning(f"NATS: Waiting for server at {host}... ({e})")
            await asyncio.sleep(5)

def setup_logger(settings: LoggingConfig):
    logging.getLogger("nats.aio.client").setLevel(logging.CRITICAL)
    logging.getLogger("nats").setLevel(logging.ERROR)
    logging.basicConfig(level=settings.level, format=settings.format)

def main():
    settings = AppSettings()
    setup_logger(settings.logging)

    # Create the high-performance background loop
    loop = asyncio.new_event_loop()
    
    # Start the loop in a dedicated thread
    thread = threading.Thread(target=loop.run_forever, name="AsyncioEngine", daemon=True)
    thread.start()

    # Wait for NATS to connect synchronously before starting the app
    future = asyncio.run_coroutine_threadsafe(setup_nats(settings.nats_host), loop)
    nc = future.result()

    # Instantiate components
    controller = TobiiController() if not settings.use_dummy_mode else DummyController()
    manager = EyeTrackingManager(controller, settings, loop, nc)

    # Start UI on the Main Thread
    app = GazeCaptureApp(manager)
    
    try:
        app.mainloop()
    finally:
        asyncio.run_coroutine_threadsafe(nc.drain(), loop).result()
        loop.call_soon_threadsafe(loop.stop)
        logger.info("Application closed.")

if __name__ == "__main__":
    main()