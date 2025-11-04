import asyncio
import logging
from functools import partial
from pathlib import Path
from tkinter import messagebox, simpledialog, Toplevel, Canvas
from typing import Callable, Optional
import datetime
import json

import tkinter as tk
from screeninfo import get_monitors

from gaze_capture.app.bridge import AsyncioTkinterBridge
from gaze_capture.app.manager import PipelineManager
from gaze_capture.app.state import AppState
from gaze_capture.app.tracker import TrackerController, DummyTrackerController
from gaze_capture.config import settings

logger = logging.getLogger(__name__)


class GazeCaptureApp(tk.Tk):
    """
    The main application window and view controller.

    This class is responsible for building the UI, managing the application's
    state, and orchestrating the core components (TrackerController,
    PipelineManager) in response to user actions.
    """

    def __init__(self, bridge: AsyncioTkinterBridge, is_dummy_mode: bool = False):
        super().__init__()
        self.title("Gaze Capture")
        self.geometry("350x650")

        self.bridge = bridge
        self.pipeline_manager = PipelineManager(use_dummy_source=is_dummy_mode)
        if is_dummy_mode:
            self.tracker_controller = DummyTrackerController(bridge)
        else:
            self.tracker_controller = TrackerController(bridge)

        # --- Application State ---
        self.app_state: AppState = AppState.INITIALIZING
        self.participant_id: Optional[str] = None
        self.participant_dir: Optional[Path] = None
        self.is_calibrated: bool = False

        self.csv_sink_enabled = tk.BooleanVar(value=("csv" in settings.pipeline.enabled_sinks))
        self.http_sink_enabled = tk.BooleanVar(value=("http" in settings.pipeline.enabled_sinks))
        self.screenrec_enabled = tk.BooleanVar(value=settings.pipeline.enable_screen_recording)

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Defer initialization until after the main window is set up and running.
        self.after(100, self.initialize_app)
    
    @property
    def calibration_json_path(self) -> Optional[Path]:
        """Returns the path to the calibration result JSON file for the current participant."""
        if not self.participant_dir:
            return None
        return self.participant_dir / f"calibration_result.json"
    
    def initialize_app(self):
        """Kicks off the async initialization process."""
        self.set_state(AppState.INITIALIZING)
        self.run_coro_from_ui(self._initialize_tracker_and_set_state)
    
    async def _initialize_tracker_and_set_state(self):
        """Wrapper to initialize controller and handle UI state changes."""
        success = await self.tracker_controller.initialize()
        if success:
            self.set_state(AppState.IDLE)
        else:
            self.set_state(AppState.NO_TRACKER)
            await self.run_on_main_thread(
                messagebox.showerror, "Error", "No Tobii eye tracker found. Please check connection."
            )

    def _build_ui(self):
        # Participant Context
        participant_frame = tk.LabelFrame(self, text="1. Participant", padx=10, pady=10)
        participant_frame.pack(padx=10, pady=10, fill="x")
        self.participant_label = tk.Label(participant_frame, text="Current: None")
        self.participant_label.pack(pady=5)
        self.set_participant_button = tk.Button(
            participant_frame, 
            text="Set / Change Participant", 
            command=partial(self.run_coro_from_ui, self.prompt_and_set_participant)
        )
        self.set_participant_button.pack(pady=5, fill="x")

        # Calibration
        calib_frame = tk.LabelFrame(self, text="2. Calibration", padx=10, pady=10)
        calib_frame.pack(padx=10, pady=10, fill="x")
        self.start_calib_button = tk.Button(calib_frame, text="Start New Calibration", command=partial(self.run_coro_from_ui, self.start_calibration))
        self.start_calib_button.pack(pady=5, fill="x")
        self.check_calib_button = tk.Button(calib_frame, text="Check Calibration", command=partial(self.run_coro_from_ui, self.check_calibration))
        self.check_calib_button.pack(pady=5, fill="x")

        # Data Sinks Configuration
        sink_frame = tk.LabelFrame(self, text="3. Data Sinks", padx=10, pady=10)
        sink_frame.pack(padx=10, pady=10, fill="x")
        tk.Checkbutton(sink_frame, text="Save to CSV File", variable=self.csv_sink_enabled).pack(anchor="w")
        tk.Checkbutton(sink_frame, text="Send via HTTP", variable=self.http_sink_enabled).pack(anchor="w")

        # Screen Recording
        screenrec_frame = tk.LabelFrame(self, text="4. Screen Recording", padx=10, pady=10)
        screenrec_frame.pack(padx=10, pady=10, fill="x")
        tk.Checkbutton(
            screenrec_frame,
            text="Enable Screen Recording",
            variable=self.screenrec_enabled
        ).pack(anchor="w")

        # Recording
        record_frame = tk.LabelFrame(self, text="5. Recording", padx=10, pady=10)
        record_frame.pack(padx=10, pady=10, fill="x")
        self.record_button = tk.Button(record_frame, text="Start Recording", command=partial(self.run_coro_from_ui, self.start_recording))
        self.record_button.pack(pady=5, fill="x")
        self.stop_button = tk.Button(record_frame, text="Stop Recording", command=partial(self.run_coro_from_ui, self.stop_recording))
        self.stop_button.pack(pady=5, fill="x")

        # Status Bar
        self.status_label = tk.Label(self, text="Initializing...", relief=tk.SUNKEN, anchor="w", padx=5)
        self.status_label.pack(side="bottom", fill="x")

    def run_coro_from_ui(self, coro_func: Callable, *args, **kwargs):
        """Helper to safely run an async method from a UI event."""
        self.bridge.run_coro_threadsafe(coro_func(*args, **kwargs))

    async def run_on_main_thread(self, func: Callable, *args, **kwargs):
        """
        Executes a synchronous function on the main Tkinter thread and allows
        an async coroutine (on a background thread) to await its completion.
        This is the essential bridge for thread-safe UI updates.
        """
        future = self.bridge.loop.create_future()
        self.after(0, lambda: self._execute_ui_task(future, func, *args, **kwargs))
        return await future

    def _execute_ui_task(self, future, func, *args, **kwargs):
        """A helper that runs in the main thread to resolve the asyncio future."""
        try:
            result = func(*args, **kwargs)
            self.bridge.loop.call_soon_threadsafe(future.set_result, result)
        except Exception as e:
            self.bridge.loop.call_soon_threadsafe(future.set_exception, e)

    async def prompt_and_set_participant(self):
        """Prompts user for Participant ID and then loads their context."""
        pid = await self.run_on_main_thread(
            simpledialog.askstring, "Participant ID", "Enter participant ID:"
        )
        if not pid or not pid.strip():
            return

        self.participant_id = pid.strip()
        self.participant_dir = settings.data_dir / self.participant_id
        self.participant_dir.mkdir(parents=True, exist_ok=True)
        self.participant_label.config(text=f"Current: {self.participant_id}")
        logger.info(f"Participant context set to ID: {self.participant_id}")

        # Automatically try to load existing calibration
        await self._load_calibration_if_exists()
        self.set_state(AppState.IDLE)

    async def _load_calibration_if_exists(self):
        """Checks for a calibration file and applies it if found."""
        # Note: This assumes your naming convention is calibration_{pid}.bin
        calib_file = self.participant_dir / "calibration.bin"
        if not calib_file.exists():
            logger.info(f"No existing calibration found for {self.participant_id}.")
            self.is_calibrated = False
            return

        logger.info(f"Found existing calibration file: {calib_file}. Applying...")
        try:
            with calib_file.open("rb") as f:
                data = f.read()
            await self.tracker_controller.apply_calibration_data(data)
            self.is_calibrated = True
            await self.run_on_main_thread(
                messagebox.showinfo, "Calibration Loaded", f"Successfully loaded existing calibration for '{self.participant_id}'."
            )
        except Exception as e:
            self.is_calibrated = False
            logger.exception(f"Failed to load calibration file for {self.participant_id}.")
            await self.run_on_main_thread(
                messagebox.showerror, "Load Error", f"Failed to load calibration file: {e}"
            )

    def set_state(self, new_state: AppState):
        self.app_state = new_state
        logger.info(f"Application state changing to {new_state.name}")
        
        # Default all action buttons to disabled
        action_buttons = [self.start_calib_button, self.check_calib_button, self.record_button, self.stop_button]
        for btn in action_buttons:
            btn.config(state="disabled")

        status_text = ""

        if new_state == AppState.INITIALIZING:
            status_text = "Initializing... Searching for tracker..."
            self.set_participant_button.config(state="disabled") # Can't set participant until tracker is ready
        
        elif new_state == AppState.NO_TRACKER:
            status_text = "Error: No eye tracker found."
            self.set_participant_button.config(state="disabled")
        
        elif new_state == AppState.IDLE:
            self.set_participant_button.config(state="normal") # Enable setting participant
            tracker_name = self.tracker_controller.eyetracker.device_name
            status_text = f"Ready ({tracker_name})"

            if self.participant_id:
                status_text += f" - Participant: {self.participant_id}"
                # Enable actions ONLY if a participant is set
                self.start_calib_button.config(state="normal")
                if self.is_calibrated:
                    self.check_calib_button.config(state="normal")
                    self.record_button.config(state="normal")
            else:
                status_text += " - No participant set."

        elif new_state == AppState.RECORDING:
            self.set_participant_button.config(state="disabled") # No changing participant while recording
            self.status_label.config(text=f"RECORDING for participant: {self.participant_id}")
            self.stop_button.config(state="normal")
        
        elif new_state == AppState.CALIBRATING:
            self.set_participant_button.config(state="disabled")
            self.status_label.config(text=f"Calibrating for participant: {self.participant_id}...")

        self.status_label.config(text=status_text)

    def on_closing(self):
        if self.app_state == AppState.RECORDING:
            messagebox.showwarning("Recording Active", "Please stop the recording before closing.")
            return
        
        logger.info("Closing application. Shutting down resources.")
        
        # Ensure hardware resources are released correctly.
        self.tracker_controller.shutdown()
            
        self.bridge.stop()
        self.destroy()

    async def start_recording(self):
        # Check 1: Is a participant set?
        if not self.participant_id:
            await self.run_on_main_thread(messagebox.showwarning, "Error", "No participant is set. Please set a participant before recording.")
            return
            
        # Check 2: Is the system calibrated for this participant?
        if not self.is_calibrated:
            await self.run_on_main_thread(messagebox.showwarning, "Error", "A valid calibration is required to record. Please run a calibration.")
            return
            
        # Check 3: Is it already running?
        if self.pipeline_manager.is_running:
            return
            
        # Check 4: Is at least one data sink enabled?
        enabled_sinks = [s for s, v in [("csv", self.csv_sink_enabled), ("http", self.http_sink_enabled)] if v.get()]
        if not enabled_sinks:
            await self.run_on_main_thread(messagebox.showwarning, "Recording", "Please select at least one data sink.")
            return

        # If all checks pass, proceed.
        self.set_state(AppState.RECORDING)
        await self.pipeline_manager.start(
            tracker=self.tracker_controller.eyetracker, 
            participant_dir=self.participant_dir, 
            enabled_sinks=enabled_sinks,
            enable_screen_recording=self.screenrec_enabled.get()
        )
        await self.run_on_main_thread(messagebox.showinfo, "Recording", f"Recording started for participant {self.participant_id}.")

    async def stop_recording(self):
        if not self.pipeline_manager.is_running:
            return
        
        await self.pipeline_manager.stop()
        self.set_state(AppState.IDLE)
        messagebox.showinfo("Recording", "Recording stopped.")

    # --- Calibration Methods ---

    def _handle_calibration_result(self, result):
        """Synchronous handler that updates state and triggers the async save."""
        if result and result.status == 'calibration_status_success':
            self.is_calibrated = True
            # Fire-and-forget the save operation. It runs in the background.
            self.run_coro_from_ui(self._save_calibration_files, result)
            messagebox.showinfo("Calibration", "Calibration successful! Saving data...")
        else:
            self.is_calibrated = False
            status = result.status if result else "Unknown error"
            messagebox.showwarning("Calibration", f"Calibration failed with status: {status}")

    async def start_calibration(self):        
        # UI update must be on the main thread
        await self.run_on_main_thread(self.set_state, AppState.CALIBRATING)

        try:
            # Hardware command (runs in background)
            await self.tracker_controller.enter_calibration_mode()            
            await self._run_calibration_window()

        except Exception as e:
            logger.exception("Calibration failed.")
            await self.run_on_main_thread(messagebox.showerror, "Calibration Error", f"An error occurred: {e}")
        finally:
            # Final hardware and UI cleanup
            await self.tracker_controller.leave_calibration_mode()
            await self.run_on_main_thread(self.set_state, AppState.IDLE)

    async def _save_calibration_files(self, result):
        """Saves the binary and JSON calibration data by requesting it from the controller."""
        if not self.participant_dir: 
            logger.error("Attempted to save calibration without a participant directory.")
            return

        try:
            # 1. Save the binary data (this is unchanged)
            bin_data = await self.tracker_controller.retrieve_calibration_data()
            if bin_data:
                out_path_bin = self.participant_dir / f"calibration.bin"
                with out_path_bin.open("wb") as f:
                    f.write(bin_data)
                logger.info(f"Saved binary calibration to {out_path_bin}")

            # 2. Get the clean dictionary from the controller and save it as JSON
            # Note: get_calibration_result_as_dict is a SYNCHRONOUS method
            result_dict = self.tracker_controller.get_calibration_result_as_dict(result)
            
            # Add timestamp here, as this is a concern of the data-saving layer
            result_dict["timestamp"] = datetime.datetime.now().isoformat()
            
            with self.calibration_json_path.open("w") as f:
                json.dump(result_dict, f, indent=2)
            logger.info(f"Saved detailed JSON calibration result to {self.calibration_json_path}")

        except Exception as e:
            logger.exception("Failed to save calibration files.")
            await self.run_on_main_thread(
                messagebox.showerror, "Save Error", f"Could not save calibration files: {e}"
            )

    async def _run_calibration_window(self):
        """
        Creates the calibration window and runs the entire visual flow.
        All UI calls are explicitly run on the main thread.
        """
        # Create the UI window on the main thread
        calib_win, canvas = await self.run_on_main_thread(self._create_calibration_ui)
        
        try:
            # Show intro text (UI)
            await self.run_on_main_thread(self._update_canvas_text, canvas, "Look at the white dots...")
            
            # Wait (background)
            await asyncio.sleep(3)

            # --- Main calibration loop ---
            for nx, ny in settings.calibration.points_to_calibrate:
                # Draw dot (UI)
                await self.run_on_main_thread(self._update_canvas_dot, canvas, nx, ny)
                # Wait for user to focus (background)
                await asyncio.sleep(2)
                # Collect data (hardware, background)
                await self.tracker_controller.collect_calibration_data(nx, ny)
                # Brief pause (background)
                await asyncio.sleep(0.5)

            # --- Finalize ---
            # Show "Calculating..." message (UI)
            await self.run_on_main_thread(self._update_canvas_text, canvas, "Calculating calibration...")
            # Compute results (hardware, background)
            result = await self.tracker_controller.compute_and_apply_calibration()
            
            # Show final result (UI)
            await self.run_on_main_thread(self._handle_calibration_result, result)

        finally:
            # Always destroy the window, even if an error occurs (UI)
            await self.run_on_main_thread(calib_win.destroy)

    # --- Synchronous UI Helpers ---

    def _create_calibration_ui(self):
        """Creates and returns the fullscreen Toplevel window and canvas."""
        w, h = get_monitors()[0].width, get_monitors()[0].height
        calib_win = Toplevel(self)
        calib_win.attributes("-fullscreen", True)
        calib_win.attributes("-topmost", True)
        calib_win.configure(bg="black")
        calib_win.focus_force()
        canvas = Canvas(calib_win, width=w, height=h, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        calib_win.update_idletasks()
        return calib_win, canvas

    def _update_canvas_text(self, canvas, text):
        """Clears the canvas and displays text."""
        canvas.delete("all")

        canvas.create_text(canvas.winfo_width()/2, canvas.winfo_height()/2, text=text, 
                           font=("Helvetica", 24), fill="white")
        canvas.update()

    def _update_canvas_dot(self, canvas, nx, ny):
        """Clears the canvas and draws a calibration dot."""
        canvas.delete("all")
        dot_radius = 15
        x, y = int(nx * canvas.winfo_width()), int(ny * canvas.winfo_height())
        canvas.create_oval(x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius, fill="white")
        canvas.update()

    async def check_calibration(self):
        """Loads calibration data and schedules the check window to be displayed."""
        if not self.participant_id:
            await self.run_on_main_thread(messagebox.showwarning, "Check Calibration", "No participant is set.")
            return

        if not self.calibration_json_path or not self.calibration_json_path.exists():
            await self.run_on_main_thread(
                messagebox.showwarning, "Check Calibration", f"No calibration JSON found for {self.participant_id}."
            )
            return

        try:
            # Load the data asynchronously
            def load_json():
                with self.calibration_json_path.open("r") as f:
                    return json.load(f)
            
            loop = asyncio.get_running_loop()
            calibration_data = await loop.run_in_executor(None, load_json)

            def create_and_show_window():
                try:
                    check_win, canvas = self._create_calibration_ui()
                    check_win.bind("<Escape>", lambda e: check_win.destroy())

                    self._draw_calibration_check(canvas, calibration_data)
                    canvas.create_text(
                        canvas.winfo_width() / 2, 30,
                        text="Press ESC to close",
                        font=("Helvetica", 16), fill="gray"
                    )

                except Exception as e:
                    logger.exception("Failed to create check calibration window.")
                    messagebox.showerror("UI Error", f"Could not create check window: {e}")
            
            # Schedule this function to run on the main thread and then immediately continue.
            self.after(0, create_and_show_window)

        except Exception as e:
            logger.exception("Failed to load calibration check data.")
            await self.run_on_main_thread(
                messagebox.showerror, "Check Calibration", f"Failed to load calibration data:\n{e}"
            )

    def _draw_calibration_check(self, canvas: tk.Canvas, calibration_data: dict):
        """Draws the calibration targets and gaze samples onto the given canvas."""
        # This logic is taken directly from your original, working implementation.
        w, h = canvas.winfo_width(), canvas.winfo_height()
        
        # Draw calibration target markers (+)
        marker_length = 20
        marker_thickness = 3
        for point in calibration_data.get("points", []):
            target = point.get("target", {})
            if "x" in target and "y" in target:
                tx, ty = target["x"], target["y"]
                x, y = int(tx * w), int(ty * h)
                canvas.create_line(x - marker_length, y, x + marker_length, y, fill="white", width=marker_thickness)
                canvas.create_line(x, y - marker_length, x, y + marker_length, fill="white", width=marker_thickness)

        # Draw gaze sample dots
        dot_r = 6
        for point in calibration_data.get("points", []):
            for sample in point.get("samples", []):
                # Plot both left and right eye data if available
                for eye_data in sample.values():
                    if eye_data and "x" in eye_data and "y" in eye_data:
                        gx = int(eye_data["x"] * w)
                        gy = int(eye_data["y"] * h)
                        # Use different colors for left/right eyes for better diagnostics
                        color = "cyan" if "left" in sample else "magenta"
                        canvas.create_oval(gx - dot_r, gy - dot_r, gx + dot_r, gy + dot_r, fill=color, outline="")
        canvas.update()