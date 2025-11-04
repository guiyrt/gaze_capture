import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Optional

from screeninfo import get_monitors

logger = logging.getLogger(__name__)


class ScreenRecorder:
    """
    Manages an ffmpeg subprocess to record the screen during a session.
    
    This is not a pipeline sink, but rather an independent process that is
    started and stopped in sync with the main data recording pipeline.
    """

    def __init__(self, video_path: Path):
        self._video_path = video_path
        self._ffmpeg_process: Optional[asyncio.subprocess.Process] = None

    async def run(self) -> None:
        """Starts and monitors the ffmpeg subprocess."""
        if self._ffmpeg_process is not None:
            logger.warning("Screen recording process is already running.")
            return

        w, h = get_monitors()[0].width, get_monitors()[0].height

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "x11grab",
            "-framerate", "30",
            "-video_size", f"{w}x{h}",
            "-i", os.environ.get("DISPLAY", ":0"),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            str(self._video_path)
        ]

        logger.info(f"Starting screen recording: {' '.join(ffmpeg_cmd)}")
        try:
            self._ffmpeg_process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            return_code = await self._ffmpeg_process.wait()
            if return_code not in (0, 255): # 0 is clean exit, 255 can be from SIGINT
                _, stderr_output = await self._ffmpeg_process.communicate()
                logger.error(
                    f"FFmpeg exited with code {return_code}. Error: {stderr_output.decode(errors='ignore').strip()}"
                )
        except FileNotFoundError:
            logger.error("`ffmpeg` command not found. Please ensure it is installed and in your PATH.")
            # We could also raise an exception here to notify the UI
        except Exception:
            logger.exception("An error occurred while running the screen recorder.")
        finally:
            self._ffmpeg_process = None

    async def stop(self) -> None:
        """Stops the ffmpeg subprocess gracefully."""
        if self._ffmpeg_process is None or self._ffmpeg_process.returncode is not None:
            return

        logger.info("Stopping screen recording process...")
        try:
            self._ffmpeg_process.send_signal(signal.SIGINT)
            await asyncio.wait_for(self._ffmpeg_process.wait(), timeout=5.0)
            logger.info("Screen recording process stopped successfully.")
        except asyncio.TimeoutError:
            logger.warning("FFmpeg did not stop gracefully. Killing process.")
            self._ffmpeg_process.kill()
        except Exception:
            logger.exception("Error while stopping ffmpeg process.")
        finally:
            self._ffmpeg_process = None