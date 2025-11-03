import argparse
import logging
import sys

from gaze_capture.app.bridge import AsyncioTkinterBridge
from gaze_capture.app.main_window import GazeCaptureApp
from gaze_capture.config import settings


def main():
    """
    The main entry point for the Gaze Capture application.
    """
    # 1. Setup Command-Line Argument Parsing
    parser = argparse.ArgumentParser(description="Gaze Capture Application")
    parser.add_argument(
        "--dummy",
        action="store_true",
        help="Run the application with a simulated dummy gaze source instead of a real eye tracker."
    )
    args = parser.parse_args()

    # 2. Configure Logging
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s [%(levelname)-8s] [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger(__name__)
    logger.info("Starting Gaze Capture application...")
    if args.dummy:
        logger.info("RUNNING IN DUMMY MODE.")

    # 3. Setup Core Components (Dependency Injection)
    try:
        bridge = AsyncioTkinterBridge()
        bridge.start()

        # 4. Create and run the application, injecting the pre-configured components.
        app = GazeCaptureApp(
            bridge=bridge,
            is_dummy_mode=args.dummy
        )
        app.mainloop()

    except Exception:
        logging.getLogger(__name__).exception("A fatal error occurred. The application will now exit.")
    finally:
        logger.info("Gaze Capture application has shut down.")