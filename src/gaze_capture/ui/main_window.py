import logging
import asyncio
import tkinter as tk
from tkinter import messagebox, simpledialog
from pathlib import Path
from typing import Optional, Callable

from ..app.bridge import AsyncioTkinterBridge
from ..controllers import GazeTrackerController
from ..runner import GazeRunner
from .calibration import TkinterCalibrationView
from ..app.state import AppState
from ..configs.app import AppSettings
from ..factories import create_session_sinks

logger = logging.getLogger(__name__)

class GazeCaptureApp(tk.Tk):
    def __init__(
        self, 
        bridge: AsyncioTkinterBridge, 
        controller: GazeTrackerController,
        settings: AppSettings
    ):
        super().__init__()
        self.bridge = bridge
        self.controller = controller
        self.settings = settings
        
        self.title(f"Gaze Capture v{settings.__version__}")
        self.geometry("350x500")
        
        # State
        self.app_state: AppState = AppState.INITIALIZING
        self.participant_id: Optional[str] = None
        self.participant_dir: Optional[Path] = None
        self.is_calibrated: bool = False
        self.runner: Optional[GazeRunner] = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start connection process
        self.after(100, lambda: self.run_async(self.startup_sequence))

    def run_async(self, coro_func: Callable, *args):
        """Helper to fire-and-forget async tasks from UI events."""
        self.bridge.run_coro_threadsafe(coro_func(*args))

    async def run_on_ui(self, func: Callable, *args):
        """Helper to run sync UI updates from async thread."""
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.after(0, lambda: self._resolve_future(future, func, *args))
        return await future

    def _resolve_future(self, future, func, *args):
        try:
            res = func(*args)
            self.bridge.loop.call_soon_threadsafe(future.set_result, res)
        except Exception as e:
            self.bridge.loop.call_soon_threadsafe(future.set_exception, e)

    # --- Logic Flow ---

    async def startup_sequence(self):
        self.set_state(AppState.INITIALIZING)
        success = await self.controller.connect(self.settings.display_area)
        
        if success:
            tracker_name = self.controller.tracker_name
            await self.run_on_ui(messagebox.showinfo, "Connected", f"Connected to: {tracker_name}")
            self.set_state(AppState.IDLE)
        else:
            self.set_state(AppState.NO_TRACKER)
            await self.run_on_ui(messagebox.showerror, "Error", "Eye tracker not found.")

    async def start_calibration(self):
        if not self.participant_dir:
            return
            
        self.set_state(AppState.CALIBRATING)
        
        # Create the View
        view = TkinterCalibrationView(self)
        
        # Delegate to Controller
        success = await self.controller.calibrate(
            save_folder=self.participant_dir,
            calib_settings=self.settings.calibration,
            view=view
        )
        
        self.is_calibrated = success
        if success:
            await self.run_on_ui(messagebox.showinfo, "Success", "Calibration saved.")
        
        self.set_state(AppState.IDLE)

    async def start_recording(self):
        if not self.participant_dir or not self.is_calibrated:
            await self.run_on_ui(messagebox.showwarning, "Error", "Setup participant and calibration first.")
            return

        if self.runner: return

        try:
            # 1. Create Session Components
            source = self.controller.create_source()
            sinks = create_session_sinks(self.settings, self.participant_dir)
            
            # 2. Start Runner
            self.runner = GazeRunner(source, sinks)
            await self.runner.start()
            
            self.set_state(AppState.RECORDING)
            
        except Exception as e:
            logger.exception("Failed to start recording")
            self.runner = None
            await self.run_on_ui(messagebox.showerror, "Error", f"Failed to start: {e}")

    async def stop_recording(self):
        if not self.runner: return
        
        # Graceful shutdown
        await self.runner.stop()
        self.runner = None
        
        self.set_state(AppState.IDLE)
        await self.run_on_ui(messagebox.showinfo, "Saved", "Recording session finished.")

    async def set_participant(self):
        pid = await self.run_on_ui(simpledialog.askstring, "ID", "Enter Participant ID:")
        if not pid: return
        
        self.participant_id = pid
        self.participant_dir = self.settings.data_dir / pid
        self.participant_dir.mkdir(parents=True, exist_ok=True)
        
        # Check for existing calibration
        self.is_calibrated = await self.controller.load_calibration(self.participant_dir)
        
        self.lbl_part.config(text=f"ID: {pid} | Calibrated: {self.is_calibrated}")
        self.set_state(AppState.IDLE)

    # --- UI Boilerplate ---
    
    def _build_ui(self):
        # Simplified Layout
        f_main = tk.Frame(self, padx=20, pady=20)
        f_main.pack(fill="both", expand=True)
        
        tk.Label(f_main, text="Gaze Capture", font=("Helvetica", 16, "bold")).pack(pady=10)
        
        self.lbl_part = tk.Label(f_main, text="No Participant")
        self.lbl_part.pack(pady=5)
        
        self.btn_part = tk.Button(f_main, text="Set Participant", command=lambda: self.run_async(self.set_participant))
        self.btn_part.pack(fill="x", pady=5)
        
        self.btn_calib = tk.Button(f_main, text="Calibrate", command=lambda: self.run_async(self.start_calibration))
        self.btn_calib.pack(fill="x", pady=5)
        
        self.btn_rec = tk.Button(f_main, text="Start Recording", bg="#ddffdd", command=lambda: self.run_async(self.start_recording))
        self.btn_rec.pack(fill="x", pady=20)
        
        self.btn_stop = tk.Button(f_main, text="Stop", bg="#ffdddd", command=lambda: self.run_async(self.stop_recording))
        self.btn_stop.pack(fill="x")
        
        self.lbl_status = tk.Label(self, text="Init...", relief=tk.SUNKEN, anchor="w")
        self.lbl_status.pack(side="bottom", fill="x")

    def set_state(self, state: AppState):
        self.app_state = state
        self.lbl_status.config(text=f"State: {state.name}")
        
        # Simple State Machine Logic
        is_ready = (state == AppState.IDLE) and (self.participant_id is not None)
        is_rec = (state == AppState.RECORDING)
        
        self.btn_part.config(state="normal" if not is_rec else "disabled")
        self.btn_calib.config(state="normal" if is_ready else "disabled")
        self.btn_rec.config(state="normal" if (is_ready and self.is_calibrated) else "disabled")
        self.btn_stop.config(state="normal" if is_rec else "disabled")

    def on_closing(self):
        if self.app_state == AppState.RECORDING:
            messagebox.showwarning("Warning", "Stop recording before closing.")
            return
        
        # Shutdown Sequence
        self.controller.shutdown()
        self.bridge.stop()
        self.destroy()