import logging
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Callable, Any

from .calibration import CalibrationWindow 
from ..core.manager import SessionManager
from ..core.state import AppState

logger = logging.getLogger(__name__)

class GazeCaptureApp(tk.Tk):
    """
    Thin UI Layer (Presenter).
    Responsibility: User input and visual state feedback.
    Logic: Delegated entirely to SessionManager via run_task().
    """
    def __init__(self, manager: SessionManager):
        super().__init__()
        self.manager = manager
        
        self.title(f"Gaze Capture v{manager.settings.__version__}")
        self.geometry("350x550")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # FIX: Use a lambda to call run_task. This ensures the coroutine is actually started.
        self.after(100, lambda: self.manager.run_task(self._initialize_system()))

    # --- UI Thread Helper ---
    def run_on_ui(self, func: Callable, *args: Any):
        """Schedules a function to run on the Tkinter main thread."""
        self.after(0, lambda: func(*args))

    # --- Sync UI Event Handlers (Run on Main Thread) ---

    def on_set_participant(self):
        """Triggered by button. Dialogs must run on Main Thread."""
        pid = simpledialog.askstring("Participant", "Enter Participant ID:")
        if pid:
            # Send the logic to the background thread
            self.manager.run_task(self._async_set_participant(pid))

    def on_calibrate(self):
        """Triggered by button."""
        self.manager.run_task(self._async_calibrate_flow())

    def on_record_toggle(self):
        """Triggered by button."""
        self.manager.run_task(self._async_record_flow())

    # --- Async Logic Flows (Run on Background Bridge Thread) ---

    async def _initialize_system(self):
        """Initial connection sequence."""
        self.run_on_ui(self.set_ui_state, AppState.INITIALIZING)
        
        success = await self.manager.controller.connect(self.manager.settings.display_area)
        
        if success:
            self.run_on_ui(self.set_ui_state, AppState.IDLE)
            self.run_on_ui(messagebox.showinfo, "Connected", f"Tracker: {self.manager.tracker_name}")
        else:
            self.run_on_ui(self.set_ui_state, AppState.NO_TRACKER)
            self.run_on_ui(messagebox.showerror, "Error", "No eye tracker found.")

    async def _async_set_participant(self, pid: str):
        """Logic for setting participant and loading calibration."""
        is_calibrated = await self.manager.set_participant(pid)
        
        # Logic to update UI label
        def update_label():
            status = "Calibrated" if is_calibrated else "Not Calibrated"
            self.lbl_part.config(text=f"ID: {pid}\n({status})")
            self.set_ui_state(AppState.IDLE)
            
        self.run_on_ui(update_label)

    async def _async_calibrate_flow(self):
        """Orchestrates the calibration UI and hardware."""
        self.run_on_ui(self.set_ui_state, AppState.CALIBRATING)
        
        # Instantiate the View (Tkinter part happens inside view.open)
        view = CalibrationWindow(self, self.manager.controller.screen_width, self.manager.controller.screen_height)
        
        # Manager handles the loop (Background thread)
        success = await self.manager.run_calibration(view)
        
        if success:
            self.run_on_ui(messagebox.showinfo, "Success", "Calibration saved.")
        
        self.run_on_ui(self.set_ui_state, AppState.IDLE)

    async def _async_record_flow(self):
        """Logic for start/stop recording."""
        if not self.manager.is_recording:
            success = await self.manager.start_recording()
            if success:
                self.run_on_ui(self.set_ui_state, AppState.RECORDING)
            else:
                self.run_on_ui(messagebox.showwarning, "Warning", "Check settings/calibration.")
        else:
            await self.manager.stop_recording()
            self.run_on_ui(self.set_ui_state, AppState.IDLE)
            self.run_on_ui(messagebox.showinfo, "Info", "Recording saved.")

    # --- UI Polish & Lifecycle ---

    def set_ui_state(self, state: AppState):
        """Updates button availability based on Manager state."""
        has_part = self.manager.participant_id is not None
        is_calibrated = self.manager.is_calibrated
        is_recording = self.manager.is_recording

        self.lbl_status.config(text=f"System State: {state.name}")
        
        self.btn_part.config(state="disabled" if is_recording else "normal")
        self.btn_calib.config(state="normal" if (has_part and not is_recording) else "disabled")
        
        if is_recording:
            self.btn_rec.config(text="STOP RECORDING", bg="#ff5555", fg="white")
        else:
            can_record = has_part and is_calibrated
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
        
        self.lbl_part = tk.Label(container, text="No Participant Set", fg="#666", font=("Helvetica", 10))
        self.lbl_part.pack(pady=15)

        self.btn_part = tk.Button(container, text="1. Set Participant", command=self.on_set_participant)
        self.btn_part.pack(fill="x", pady=5)

        self.btn_calib = tk.Button(container, text="2. Run Calibration", command=self.on_calibrate)
        self.btn_calib.pack(fill="x", pady=5)

        self.btn_rec = tk.Button(container, text="START RECORDING", font=("Helvetica", 10, "bold"),
                                command=self.on_record_toggle)
        self.btn_rec.pack(fill="x", pady=25)

        self.lbl_status = tk.Label(self, text="Initializing...", relief=tk.SUNKEN, anchor="w", padx=10)
        self.lbl_status.pack(side="bottom", fill="x")