import logging
import nats
from nats.errors import OutboundBufferLimitError

from .base import GazeSink
from ..models import GazeData

from aware_protos.zhaw.protobuf import gaze_pb2

logger = logging.getLogger(__name__)

class NATSSink(GazeSink):
    def __init__(
        self,
        nc: nats.NATS,
        subject: str = "intent.gaze"
    ):
        self.nc = nc
        self.subject = subject

        self._proto = gaze_pb2.GazeScreenPosition()

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
            logger.error("Failed to publish prediction to NATS: %s", e)