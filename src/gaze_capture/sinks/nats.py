import logging
import nats
from nats.errors import OutboundBufferLimitError

from .base import GazeSink
from ..models import GazeData

from aware_protos.zhaw.protobuf import gaze_pb2

logger = logging.getLogger(__name__)

class NATSSink(GazeSink):
    def __init__(self, host: str, subject: str = "intent.gaze"):
        self.host = host
        self.subject = subject
        self.nc = nats.NATS()

        self._proto = gaze_pb2.GazeScreenPosition()

    async def start(self) -> None:
        async def disconnected_cb():
            logger.warning("NATS disconnected. NATS will auto-reconnect...")
            
        async def reconnected_cb():
            logger.info(f"NATS reconnected to {self.nc.connected_url.netloc}")

        await self.nc.connect(
            self.host,
            allow_reconnect=True,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            disconnected_cb=disconnected_cb,
            reconnected_cb=reconnected_cb
        )
        logger.info(f"NATSSink connected on subject '{self.subject}'")

    async def send(self, data: GazeData) -> None:
        if not self.nc.is_connected:
            return

        try:
            is_valid = data.gaze_x_px is not None and data.gaze_y_px is not None
            
            p = self._proto
            p.Clear()

            p.timestamp.FromMilliseconds(data.timestamp_ms)
            p.x = data.gaze_x_px if is_valid else -1
            p.y = data.gaze_y_px if is_valid else -1
            p.is_valid = is_valid
            
            # Serialize and publish
            await self.nc.publish(self.subject, p.SerializeToString())
            
        except OutboundBufferLimitError:
            pass # Drop frame gracefully if NATS is offline
        except Exception as e:
            logger.error(f"Failed to publish prediction to NATS: {e}")

    async def close(self) -> None:
        if self.nc.is_connected:
            await self.nc.drain()