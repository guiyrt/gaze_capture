import nats
import asyncio
import time
from pathlib import Path
import logging
import json

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

    def update_heartbeat(self):
        """Called by NATS subscriber when a heartbeat arrives."""
        self._last_heartbeat = time.time()
        if self._state == ServiceState.UNAVAILABLE:
            self._set_state(ServiceState.READY)

    async def _subscribe_health(self):
        """Listens for the 1Hz ping from the container."""
        async def cb(_):
            self.update_heartbeat()
            
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
                    self._set_state(ServiceState.UNAVAILABLE)
        except asyncio.CancelledError:
            pass

    async def start(self, session_id: str) -> bool:
        if self._state != ServiceState.READY:
            return False
        
        payload = json.dumps({"cmd": "start", "session_id": session_id}).encode()

        try:
            # We REQUEST so we know for a fact the container successfully started
            msg = await self.nc.request(self.cmds_subject, payload, timeout=2.0)
            response = json.loads(msg.data.decode())
            
            if response.get("status") == "ok":
                self._set_state(ServiceState.RECORDING)
                return True
            else:
                logging.error(f"{self.name} rejected start command: {response.get('error')}")
                return False
        
         # If it times out, we assume it's dead. Watchdog will fix it if it's not.
        except TimeoutError:
            logging.error(f"{self.name} timed out responding to start command.")
            self._set_state(ServiceState.UNAVAILABLE)
            return False

    async def stop(self) -> None:
        if self._state != ServiceState.RECORDING:
            return
        
        payload = json.dumps({"cmd": "stop"}).encode()

        try:
            msg = await self.nc.request(self.cmds_subject, payload, timeout=2.0)
            response = json.loads(msg.data.decode())
            
            if response.get("status") == "ok":
                self._set_state(ServiceState.READY)
        
        except TimeoutError:
            logging.error(f"{self.name} timed out responding to stop command. Forcing UNAVAILABLE state.")
            self._set_state(ServiceState.UNAVAILABLE)

    async def shutdown(self) -> None:
        """Cancels infinite background tasks to prevent Asyncio errors."""
        self._watchdog_task.cancel()
        self._health_task.cancel()

        await asyncio.gather(*(self._watchdog_task, self._health_task), return_exceptions=True)