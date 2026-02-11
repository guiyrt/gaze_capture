import sys
import logging
from gaze_capture.app.bridge import AsyncioTkinterBridge
from gaze_capture.ui.main_window import GazeCaptureApp
from gaze_capture.configs.app import AppSettings
from gaze_capture.controllers import TobiiController, DummyController

def main():
    # 1. Load Configuration
    try:
        settings = AppSettings()
    except Exception as e:
        print(f"Configuration Error: {e}")
        sys.exit(1)

    # 2. Setup Logging
    logging.basicConfig(
        level=settings.logging.level,
        format=settings.logging.format,
        stream=sys.stdout
    )
    logger = logging.getLogger("main")
    logger.info(f"Starting Gaze Capture v{settings.__version__}")

    # 3. Setup Infrastructure
    bridge = AsyncioTkinterBridge()
    bridge.start()

    # 4. Dependency Injection (Controller Strategy)
    if settings.use_dummy_mode:
        logger.warning("Initializing DUMMY Controller (Simulation Mode)")
        controller = DummyController(bridge)
    else:
        logger.info("Initializing TOBII Controller")
        controller = TobiiController(bridge)

    # 5. Launch UI
    try:
        app = GazeCaptureApp(bridge, controller, settings)
        app.mainloop()
    except Exception:
        logger.exception("Fatal Application Error")
    finally:
        # Emergency cleanup if UI crashes without closing
        logger.info("Shutdown sequence initiated.")
        if bridge._is_running:
            bridge.stop()

if __name__ == "__main__":
    main()