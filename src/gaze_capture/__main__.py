import asyncio
import threading
import logging

from gaze_capture.core.manager import SessionManager
from gaze_capture.ui import GazeCaptureApp
from gaze_capture.configs.app import AppSettings
from gaze_capture.controllers import TobiiController, DummyController

def main():
    settings = AppSettings()
    logging.basicConfig(level=settings.logging.level, format=settings.logging.format)
    logger = logging.getLogger(__name__)

    # Create the high-performance background loop
    loop = asyncio.new_event_loop()
    
    # Start the loop in a dedicated thread
    thread = threading.Thread(target=loop.run_forever, name="AsyncioEngine", daemon=True)
    thread.start()

    # Instantiate components
    controller = TobiiController() if not settings.use_dummy_mode else DummyController()
    manager = SessionManager(controller, settings, loop)

    # Start UI on the Main Thread
    app = GazeCaptureApp(manager)
    
    try:
        app.mainloop()
    finally:
        loop.call_soon_threadsafe(loop.stop)
        logger.info("Application closed.")

if __name__ == "__main__":
    main()