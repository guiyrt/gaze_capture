import logging
import nats
from nats.errors import OutboundBufferLimitError

from .base import GazeSink
from ..models import GazeData

from aware_protos.zhaw.protobuf.gaze_pb2 import GazeScreenPosition

logger = logging.getLogger(__name__)

class NATSSink(GazeSink):
    def __init__(self, host: str, subject: str = "gaze"):
        self.host = host
        self.subject = subject
        self.nc = nats.NATS()

    async def start(self) -> None:
        await self.nc.connect(
            servers=self.host,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            pending_size=1024 * 50, # 50KB memory limit to protect RAM on disconnect
        )
        logger.info(f"NATSSink connected on subject '{self.subject}'")

    async def send(self, data: GazeData) -> None:
        if not self.nc.is_connected:
            return

        try:
            is_valid = data.gaze_x_px is not None and data.gaze_y_px is not None
            
            proto_msg = GazeScreenPosition()

            proto_msg.timestamp.FromMilliseconds(data.timestamp_ms)
            proto_msg.x = data.gaze_x_px if is_valid else -1
            proto_msg.y = data.gaze_y_px if is_valid else -1
            proto_msg.is_valid = is_valid
            
            # Serialize and publish
            await self.nc.publish(self.subject, proto_msg.SerializeToString())
            
        except OutboundBufferLimitError:
            pass # Drop frame gracefully if NATS is offline
        except Exception as e:
            logger.error(f"NATS broadcast failed: {e}")

    async def close(self) -> None:
        if self.nc.is_connected:
            await self.nc.drain()