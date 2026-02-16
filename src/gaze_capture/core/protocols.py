from typing import Protocol, runtime_checkable

@runtime_checkable
class CalibrationView(Protocol):
    """
    Defines the methods required for any UI that handles calibration.
    Whether it's Tkinter, Web, or a CLI, it must support these calls.
    """
    async def open(self, width: int, height: int) -> None: ...
    
    async def show_point(self, x: float, y: float) -> None: ...
    
    async def show_message(self, text: str) -> None: ...
    
    async def show_results(self, result_dict: dict) -> None: ...
    
    async def close(self) -> None: ...