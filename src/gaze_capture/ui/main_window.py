# /home/regd/gaze_capture/src/gaze_capture/ui/main_window.py

import logging
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Any

from .calibration import CalibrationWindow 
from ..core.manager import EyeTrackingManager
from ..core.state import AppState

logger = logging.getLogger(__name__)

class GazeCaptureApp(tk.Tk):
    """
    Thin UI Layer (Standalone Presenter).
    Responsibility: User input and visual state feedback.
    Logic: Delegated entirely to EyeTrackingManager.
    """
    def __init__(self, manager: EyeTrackingManager):
        super().__init__()
        self.manager = manager
        
        self.title(f"Gaze Capture Standalone v{manager.settings.__version__}")
        self.geometry("350x400") # Made the window slightly smaller and tighter

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Subscribe to hardware state changes
        self.manager.add_state_listener(self._on_state_changed)
        
        # Initialize hardware
        self.after(100, lambda: self.manager.run_task(self._initialize_system()))

    # --- UI Thread Helpers ---
    def run_on_ui(self, func: Callable, *args: Any):
        """Schedules a function to run on the Tkinter main thread."""
        self.after(0, lambda: func(*args))

    def _on_state_changed(self, new_state: AppState):
        """Observer callback triggered by the Manager."""
        self.run_on_ui(self.set_ui_state, new_state)

    # --- Sync UI Event Handlers (Run on Main Thread) ---

    def on_calibrate(self):
        self.manager.run_task(self._async_calibrate_flow())

    def on_record_toggle(self):
        self.manager.run_task(self._async_record_flow())

    # --- Async Logic Flows (Run on Background Thread) ---

    async def _initialize_system(self):
        # 1. Connect hardware
        success = await self.manager.connect(self.manager.settings.display_area)
        
        if success:
            # 2. Auto-load calibration directly from data_dir if it exists
            self.manager.data_dir.mkdir(parents=True, exist_ok=True)
            if (self.manager.data_dir / "calibration.bin").exists():
                await self.manager.load_calibration(self.manager.data_dir)
                logger.info("Loaded existing calibration from data_dir.")
                
            self.run_on_ui(messagebox.showinfo, "Connected", f"Tracker: {self.manager.controller.tracker_name}")
        else:
            self.run_on_ui(messagebox.showerror, "Error", "No eye tracker found.")

    async def _async_calibrate_flow(self):
        view = CalibrationWindow(self, self.manager.settings.display_area.width_px, self.manager.settings.display_area.height_px)
        
        # Save directly into data_dir
        self.manager.data_dir.mkdir(parents=True, exist_ok=True)
        success = await self.manager.run_calibration(self.manager.data_dir, view)
        
        if success:
            self.run_on_ui(messagebox.showinfo, "Success", "Calibration saved.")

    async def _async_record_flow(self):
        if not self.manager.is_recording:
            # Passing "" (empty string) means data_dir / "" -> writes directly to data_dir root
            success = await self.manager.start_recording()
            if not success:
                self.run_on_ui(messagebox.showwarning, "Warning", "Check settings/calibration.")
        else:
            await self.manager.stop_recording()
            self.run_on_ui(messagebox.showinfo, "Info", "Recording saved.")

    # --- UI Polish & Lifecycle ---

    def set_ui_state(self, state: AppState):
        """Updates button availability based on Manager state."""
        is_calibrated = self.manager.is_calibrated
        is_recording = self.manager.is_recording

        # Disable buttons during recording, calibration, or missing hardware
        hardware_ok = state in (AppState.IDLE, AppState.RECORDING)
        
        self.lbl_status.config(text=f"System State: {state.name}")
        self.lbl_calib_status.config(
            text="Status: Calibrated" if is_calibrated else "Status: Not Calibrated",
            fg="#0a0" if is_calibrated else "#a00"
        )
        
        self.btn_calib.config(state="normal" if (not is_recording and hardware_ok) else "disabled")
        
        if is_recording:
            self.btn_rec.config(text="STOP RECORDING", bg="#ff5555", fg="white", state="normal")
        else:
            can_record = is_calibrated and hardware_ok
            self.btn_rec.config(
                text="START RECORDING", 
                bg="#55ff55" if can_record else "#f0f0f0",
                state="normal" if can_record else "disabled"
            )

    def on_closing(self):
        if self.manager.is_recording:
            messagebox.showwarning("Warning", "Please stop recording before closing.")
            return
        
        self.manager.shutdown()
        self.destroy()

    def _build_ui(self):
        container = tk.Frame(self, padx=30, pady=30)
        container.pack(fill="both", expand=True)

        tk.Label(container, text="GAZE CAPTURE", font=("Helvetica", 14, "bold")).pack(pady=10)
        
        self.lbl_calib_status = tk.Label(container, text="Status: Checking...", fg="#666", font=("Helvetica", 10))
        self.lbl_calib_status.pack(pady=15)

        self.btn_calib = tk.Button(container, text="Run Calibration", command=self.on_calibrate)
        self.btn_calib.pack(fill="x", pady=5)

        self.btn_rec = tk.Button(container, text="START RECORDING", font=("Helvetica", 10, "bold"),
                                command=self.on_record_toggle)
        self.btn_rec.pack(fill="x", pady=25)

        self.lbl_status = tk.Label(self, text="Initializing...", relief=tk.SUNKEN, anchor="w", padx=10)
        self.lbl_status.pack(side="bottom", fill="x")