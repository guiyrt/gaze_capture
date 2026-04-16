import asyncio
import threading
import logging
import nats
from nats.errors import NoServersError

from gaze_capture.core.manager import EyeTrackingManager
from gaze_capture.configs.app import AppSettings, LoggingConfig
from gaze_capture.controllers import TobiiController, DummyController

from gaze_capture.aware_command_center.services import GazeService, RemoteService
from gaze_capture.aware_command_center.orchestrator import ExperimentOrchestrator
from gaze_capture.aware_command_center.ui import CommandCenterUI

logger = logging.getLogger(__name__)

async def setup_nats(host: str) -> nats.NATS:
    """
    Initializes NATS with custom logging to prevent traceback spam.
    """
    nc = nats.NATS()

    async def disconnected_cb():
        logger.warning("NATS: Connection disconnected.")

    async def reconnected_cb():
        logger.info(f"NATS: Connection restored to {nc.connected_url.netloc}")

    async def error_cb(e):
        # Ignore common network noise during background reconnect attempts
        if isinstance(e, (asyncio.TimeoutError, ConnectionRefusedError, OSError)):
            return

        err_msg = str(e).strip()

        # Some NATS specific EOF/disconnect errors might bypass the instance check
        if "empty response from server" in err_msg or "UnexpectedEOF" in err_msg:
            return

        # If it's an error with an empty string, log its class name instead
        if not err_msg:
            err_msg = type(e).__name__
            
        logger.error(f"NATS Internal Error: {err_msg}")

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
    threading.Thread(target=loop.run_forever, daemon=True).start()

    future = asyncio.run_coroutine_threadsafe(setup_nats(settings.nats_host), loop)
    nc = future.result()

    # Instantiate components
    controller = TobiiController() if not settings.use_dummy_mode else DummyController()
    eye_tracking_manager = EyeTrackingManager(controller, settings, loop, nc)

    # Define Services
    services = [
        GazeService(eye_tracking_manager),
        RemoteService("Task Prediction", loop, nc, "intent.health.task_pred", "intent.cmds.task_pred"),
        RemoteService("Attention Target", loop, nc, "intent.health.attention", "intent.cmds.attention"),
        RemoteService("Screen Recorder", loop, nc, "screen.health", "screen.cmds"),
    ]

    orchestrator = ExperimentOrchestrator(settings, eye_tracking_manager, services)
    app = CommandCenterUI(orchestrator, loop)
    
    try:
        app.mainloop()
    finally:
        asyncio.run_coroutine_threadsafe(nc.drain(), loop).result()
        loop.call_soon_threadsafe(loop.stop)
        logger.info("Application closed.")

if __name__ == "__main__":
    main()