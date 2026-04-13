import asyncio
import time
import logging
import json

import nats
from nats.errors import TimeoutError

from .base import BaseService, ServiceState

logger = logging.getLogger(__name__)

class RemoteService(BaseService):
    """
    Wrapper for Docker containers controlled via NATS.
    Requires a NATS client instance to publish commands and listen to heartbeats.
    """
    def __init__(
        self,
        name: str,
        loop: asyncio.AbstractEventLoop,
        nc: nats.NATS,
        health_subject: str,
        cmds_subject: str
    ) -> None:
        super().__init__(name=name)
        self.loop = loop
        self.nc = nc
        self.health_subject = health_subject
        self.cmds_subject = cmds_subject

        self._heartbeat_timeout_sec = 3.0
        self._last_heartbeat: float = 0.0
        
        self._watchdog_task = self.loop.create_task(self._watchdog())
        self._health_task = self.loop.create_task(self._subscribe_health())

    async def _subscribe_health(self):
        """Listens for the 1Hz ping from the container."""
        async def cb(msg):
            self._last_heartbeat = time.time()
            
            # 2. Parse the boolean stateful heartbeat
            try:
                data = json.loads(msg.data.decode())
                is_recording = data.get("is_recording", False)
                
                # Map boolean directly to ServiceState
                self._set_state(ServiceState.RECORDING if is_recording else ServiceState.READY)
                    
            except Exception as e:
                logger.warning(f"[{self.name}] Received malformed heartbeat: {e}")
            
        try:
            # Wait until NATS is actually connected before subscribing
            while not self.nc.is_connected:
                await asyncio.sleep(0.5)
                
            await self.nc.subscribe(self.health_subject, cb=cb)
            logger.info(f"[{self.name}] Subscribed to health check.")
        except Exception as e:
            logger.error(f"[{self.name}] Failed to subscribe to health: {e}")

    async def _watchdog(self):
        """Monitors heartbeat timestamps to detect dead containers."""
        try:
            while True:
                await asyncio.sleep(1)
                if self._state == ServiceState.UNAVAILABLE:
                    continue
                    
                time_since = time.time() - self._last_heartbeat
                if time_since > self._heartbeat_timeout_sec:
                    logger.warning(f"[{self.name}] Heartbeat timeout. Marking UNAVAILABLE.")
                    self._set_state(ServiceState.UNAVAILABLE)
        except asyncio.CancelledError:
            pass

    async def start(self, session_id: str) -> bool:
        if self._state != ServiceState.READY:
            return False
        
        payload = json.dumps({"cmd": "start", "session_id": session_id}).encode()

        try:
            msg = await self.nc.request(self.cmds_subject, payload, timeout=2.0)
            response = json.loads(msg.data.decode())
            
            if response.get("status") == "ok":
                # State will automatically flip to RECORDING on the next heartbeat
                return True
            else:
                logger.error(f"[{self.name}] rejected start command: {response.get('error')}")
                return False
        
        except TimeoutError:
            logger.error(f"[{self.name}] timed out responding to start command.")
            return False

    async def stop(self) -> None:
        if self._state != ServiceState.RECORDING:
            return
        
        payload = json.dumps({"cmd": "stop"}).encode()

        try:
            msg = await self.nc.request(self.cmds_subject, payload, timeout=2.0)
            response = json.loads(msg.data.decode())
            
            # State will automatically flip to READY on the next heartbeat
            if response.get("status") != "ok":
                logger.error(f"[{self.name}] rejected stop command: {response.get('error')}")
                
        except TimeoutError:
            logger.error(f"[{self.name}] timed out responding to stop command.")

    async def shutdown(self) -> None:
        """Cancels infinite background tasks to prevent Asyncio errors."""
        self._watchdog_task.cancel()
        self._health_task.cancel()
        await asyncio.gather(self._watchdog_task, self._health_task, return_exceptions=True)