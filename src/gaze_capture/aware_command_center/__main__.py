import asyncio
import threading
import logging
import nats

from gaze_capture.core.manager import EyeTrackingManager
from gaze_capture.configs.app import AppSettings
from gaze_capture.controllers import TobiiController, DummyController

from gaze_capture.aware_command_center.services import GazeService, RemoteService
from gaze_capture.aware_command_center.orchestrator import ExperimentOrchestrator
from gaze_capture.aware_command_center.ui import CommandCenterUI

async def setup_nats(host: str) -> nats.NATS:
    """Robust top-level NATS connection."""
    nc = nats.NATS()

    while True:
        try:
            await nc.connect(
                host,
                allow_reconnect=True,
                max_reconnect_attempts=-1,
            )
            logging.info("NATS Connected.")
            return nc
        except Exception as e:
            logging.error(f"NATS connection failed: {e}. Retrying in 5s...")
            await asyncio.sleep(5)

def main():
    settings = AppSettings()
    logging.basicConfig(level=settings.logging.level, format=settings.logging.format)
    logger = logging.getLogger(__name__)

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