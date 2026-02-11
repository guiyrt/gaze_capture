import logging
import struct
from typing import Final

import zmq
import zmq.asyncio

from .base import GazeSink
from ..models import GazeData

logger = logging.getLogger(__name__)

class ZMQSink(GazeSink):
    """
    Real-time broadcast sink using ZMQ PUB/SUB.
    Broadcasts binary-packed high-priority data (TS, X, Y, Validity).
    
    Wire Format (17 bytes + 4 byte topic):
    - Topic: 'gaze' (4 bytes)
    - Epoch TS: int64 (8 bytes)
    - Mid X Px: int32 (4 bytes)
    - Mid Y Px: int32 (4 bytes)
    - Validity: bool  (1 byte)
    """
    
    # ! = Network (Big Endian)
    # q = int64 (timestamp)
    # i = int32 (x)
    # i = int32 (y)
    # ? = bool  (validity)
    _PACKER: Final[struct.Struct] = struct.Struct("!qii?")
    _TOPIC: Final[bytes] = b"gaze"

    def __init__(self, host: str = "tcp://*:5555"):
        """
        Args:
            host: The ZMQ binding address. Default binds to all interfaces on port 5555.
        """
        self.host = host
        
        # Async ZMQ setup
        self._ctx = zmq.asyncio.Context()
        self._sock = self._ctx.socket(zmq.PUB)
        
        # Set High Water Mark to prevent memory bloating if subscribers are slow
        # Buffer of 10 seconds at 120Hz
        self._sock.setsockopt(zmq.SNDHWM, 120 * 10)

    async def start(self) -> None:
        """Bind the publisher socket."""
        try:
            self._sock.bind(self.host)
            logger.info(f"ZMQSink bound to {self.host}")
        except Exception as e:
            logger.error(f"Failed to bind ZMQSink to {self.host}: {e}")
            raise e

    async def send(self, data: GazeData) -> None:
        """
        Serializes and broadcasts the gaze frame.
        This is a non-blocking operation (ZMQ hands off to internal buffer).
        """
        try:
            # Determine validity
            is_valid = data.mid_x_px is not None and data.mid_y_px is not None
            
            # Pack binary payload
            payload = self._PACKER.pack(
                data.epoch_timestamp_ms,
                data.mid_x_px if is_valid else -1,
                data.mid_y_px if is_valid else -1,
                is_valid
            )
            
            # Send as single multipart-compatible message [Topic][Payload]
            await self._sock.send(self._TOPIC + payload)
            
        except Exception as e:
            # We log network errors to ensure the Eye Tracker hardware thread never hangs.
            logger.error(f"ZMQ broadcast failed: {e}")

    async def close(self) -> None:
        """Shut down the ZMQ context."""
        logger.info("Closing ZMQSink...")
        # Close immediately, don't wait for unsent messages
        self._sock.close(linger=0)
        self._ctx.term()