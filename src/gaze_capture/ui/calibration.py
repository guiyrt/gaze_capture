import logging
import asyncio
import tkinter as tk
from tkinter import Toplevel, Canvas
from typing import Optional, Any, Callable
from functools import wraps

from ..core.protocols import CalibrationView

logger = logging.getLogger(__name__)

def require_window(func):
    """Decorator: Ensures window and canvas exist before drawing."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self._window or not self._canvas:
            return
        return func(self, *args, **kwargs)
    return wrapper

class CalibrationWindow(CalibrationView):
    """
    Manages the Fullscreen Calibration Window.
    Bridges background Controller calls to the Main Thread via root.after().
    """
    def __init__(self, root: tk.Tk, width: int, height: int):
        # We need the root to schedule updates on the main thread
        self._root = root
        
        # UI Elements
        self._window: Optional[Toplevel] = None
        self._canvas: Optional[Canvas] = None
        
        # State
        self._width: int = width
        self._height: int = height

    # --- Async Public Interface (Called by Controller) ---

    async def open(self) -> None:
        await self._run_on_ui(self._create_window)

    async def show_point(self, x: float, y: float) -> None:
        await self._run_on_ui(self._draw_target, x, y)

    async def show_message(self, text: str) -> None:
        await self._run_on_ui(self._draw_text, text)

    async def show_results(self, result_dict: dict) -> None:
        close_event = asyncio.Event()

        loop = asyncio.get_running_loop()
        
        def on_close(_=None):
            loop.call_soon_threadsafe(close_event.set)

        await self._run_on_ui(self._draw_results_ui, result_dict, on_close)
        await close_event.wait()

    async def close(self) -> None:
        await self._run_on_ui(self._destroy_window)

    # --- Thread Bridge Helper ---

    def _run_on_ui(self, func: Callable, *args) -> asyncio.Future:
        """
        Schedules a sync UI function on the Main Thread and awaits completion.
        """
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def _ui_task():
            try:
                func(*args)
                # Signal back to the background thread that we are done
                loop.call_soon_threadsafe(future.set_result, None)
            except Exception as e:
                loop.call_soon_threadsafe(future.set_exception, e)

        # root.after(0, ...) is the standard thread-safe Tkinter injector
        self._root.after(0, _ui_task)
        return future

    # --- Private Sync Methods (Main Thread) ---

    def _create_window(self) -> None:
        if self._window: return

        self._window = Toplevel(self._root)
        self._window.attributes("-fullscreen", True)
        self._window.attributes("-topmost", True)
        self._window.configure(bg="black", cursor="none")
        self._window.focus_force()

        self._canvas = Canvas(
            self._window, 
            width=self._width, 
            height=self._height, 
            bg="black", 
            highlightthickness=0
        )
        self._canvas.pack(fill="both", expand=True)
        self._window.update_idletasks()

    @require_window
    def _destroy_window(self) -> None:
        self._window.destroy()
        self._window = None
        self._canvas = None

    @require_window
    def _clear(self) -> None:
        self._canvas.delete("all")

    @require_window
    def _draw_target(self, nx: float, ny: float) -> None:
        self._clear()
        
        cx = int(nx * self._width)
        cy = int(ny * self._height)
        
        r1, r2 = 20, 5
        self._canvas.create_oval(cx-r1, cy-r1, cx+r1, cy+r1, outline="white", width=4)
        self._canvas.create_oval(cx-r2, cy-r2, cx+r2, cy+r2, fill="white")
        
        self._canvas.update()

    @require_window
    def _draw_text(self, text: str) -> None:
        self._clear()
        
        self._canvas.create_text(
            self._width / 2, self._height / 2,
            text=text, font=("Helvetica", 24, "bold"), fill="white"
        )
        self._canvas.update()

    @require_window
    def _draw_results_ui(self, data: dict, close_cb: Any) -> None:
        self._clear()
        
        self._window.bind("<Escape>", close_cb)
        self._window.config(cursor="arrow") # Show cursor for interaction

        self._canvas.create_text(
            self._width / 2, 50,
            text="Calibration Result (Press ESC to Close)", 
            font=("Helvetica", 16), fill="gray"
        )

        for point in data.get("points", []):
            # Target Crosshair
            tx = int(point["target"]["x"] * self._width)
            ty = int(point["target"]["y"] * self._height)
            size = 15
            self._canvas.create_line(tx-size, ty, tx+size, ty, fill="white", width=2)
            self._canvas.create_line(tx, ty-size, tx, ty+size, fill="white", width=2)

            # Gaze Samples
            for sample in point.get("samples", []):
                for eye, color in [("left", "#00FFFF"), ("right", "#FF00FF")]:
                    if eye in sample:
                        sx = int(sample[eye]["x"] * self._width)
                        sy = int(sample[eye]["y"] * self._height)
                        self._canvas.create_oval(sx-2, sy-2, sx+2, sy+2, fill=color, outline="")
        
        self._canvas.update()