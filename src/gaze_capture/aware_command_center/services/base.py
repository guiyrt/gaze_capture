import time
from abc import ABC, abstractmethod
from enum import Enum, auto
from pathlib import Path
from typing import Callable

class ServiceState(Enum):
    UNAVAILABLE = auto() # Offline, disconnected, or error
    READY = auto() # Online and waiting to record
    RECORDING = auto() # Actively recording data

class BaseService(ABC):
    """Abstract interface for all experimental services (Local or Remote)."""
    def __init__(self, name: str):
        self.name = name
        self._state = ServiceState.UNAVAILABLE
        self._start_time: float = 0.0
        self._listeners: list[Callable[[str, ServiceState], None]] = []

    @property
    def current_state(self) -> ServiceState:
        return self._state

    def get_duration_str(self) -> str:
        """Returns mm:ss formatting for the UI."""
        if self._state != ServiceState.RECORDING:
            return "00:00"
        elapsed = int(time.time() - self._start_time)
        mins, secs = divmod(elapsed, 60)
        return f"{mins:02d}:{secs:02d}"

    def on_state_change(self, listener: Callable[[str, ServiceState], None]):
        """Allows UI to listen to changes on this specific service."""
        self._listeners.append(listener)
        listener(self.name, self._state)

    def _set_state(self, new_state: ServiceState):
        if self._state != new_state:
            self._state = new_state
            if new_state == ServiceState.RECORDING:
                self._start_time = time.time()
            for listener in self._listeners:
                listener(self.name, self._state)

    @abstractmethod
    async def start(self, session_dir: Path) -> bool:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    def refresh_state(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass