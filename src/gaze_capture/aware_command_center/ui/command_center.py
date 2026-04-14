import tkinter as tk
from tkinter import messagebox
import asyncio
import logging
from typing import Callable, Any

from .theme import Theme
from .widgets import HoldButton
from ..orchestrator import ExperimentOrchestrator
from ..services import ServiceState
from ...configs import DisplayAreaSettings
from ...ui import CalibrationWindow
from ...core.state import AppState

logger = logging.getLogger(__name__)

class CommandCenterUI(tk.Tk):
    def __init__(self, orchestrator: ExperimentOrchestrator, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.orchestrator = orchestrator
        self.loop = loop
        
        self.title("Gaze Capture Command Center")
        self.geometry("800x1100")
        self.configure(bg=Theme.BG_WINDOW, padx=20, pady=20)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self._service_indicators: dict[str, tk.Canvas] = {}
        self._service_timers: dict[str, tk.Label] = {}
        self._service_starts: dict[str, tk.Button] = {}
        self._service_stops: dict[str, HoldButton] = {}

        self._sync_buttons: dict[str, tk.Button] = {}
        self._sync_labels: dict[str, tk.Label] = {}

        self._build_ui()

        # Start hardware connection in the background
        def _on_init_done(success):
            if not success:
                logger.warning("Hardware connection failed on startup.")
            self._populate_initial_data()
                
        self._run_async(self.orchestrator.initialize(), _on_init_done)

        self._poll_ui_state()

    def _run_async(self, coro, callback: Callable[[Any], None] = None):
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        
        def _handle_completion(fut):
            try:
                result = fut.result() # This will raise an exception if the task crashed
                if callback:
                    self.after(0, lambda: callback(result))
            except Exception as e:
                logger.error(f"Async task failed: {e}", exc_info=True)
                if callback:
                    self.after(0, lambda: callback(False))

        future.add_done_callback(_handle_completion)

    def _create_card(self, parent, title: str) -> tk.Frame:
        card = tk.Frame(parent, bg=Theme.BG_CARD, padx=15, pady=15)
        card.pack(fill="x", pady=10)
        tk.Label(card, text=title, font=Theme.FONT_H2, bg=Theme.BG_CARD, fg=Theme.TEXT_MAIN, anchor="w").pack(fill="x")
        return card

    def _build_ui(self):
        tk.Label(self, text="Experiment Command Center", font=Theme.FONT_H1, bg=Theme.BG_WINDOW, fg=Theme.TEXT_MAIN).pack(anchor="w")
        self.lbl_path = tk.Label(self, text=f"Root: {self.orchestrator.experiment_root}", font=Theme.FONT_MONO, bg=Theme.BG_WINDOW, fg=Theme.TEXT_MUTED)
        self.lbl_path.pack(anchor="w", pady=(0, 10))

        # 1. Setup Card
        card1 = self._create_card(self, "1. Session Setup")
        row1 = tk.Frame(card1, bg=Theme.BG_CARD)
        row1.pack(fill="x")
        
        tk.Label(row1, text="Participant ID:", bg=Theme.BG_CARD, fg=Theme.TEXT_MAIN).pack(side="left")
        self.ent_pid = tk.Entry(row1, bg=Theme.BG_INPUT, fg=Theme.TEXT_MAIN, insertbackground=Theme.TEXT_MAIN, bd=0, width=15)
        self.ent_pid.pack(side="left", padx=10)
        
        tk.Label(row1, text="Scenario ID:", bg=Theme.BG_CARD, fg=Theme.TEXT_MAIN).pack(side="left", padx=(20, 0))
        self.ent_sid = tk.Entry(row1, bg=Theme.BG_INPUT, fg=Theme.TEXT_MAIN, insertbackground=Theme.TEXT_MAIN, bd=0, width=15)
        self.ent_sid.pack(side="left", padx=10)
        
        tk.Button(row1, text="Apply IDs", bg=Theme.ACCENT, fg=Theme.TEXT_MAIN, bd=0, command=self.on_set_ids).pack(side="left", padx=20)

        # 2. Hardware Config Card
        card2 = self._create_card(self, "2. Eye Tracker Configuration")
        geom_frame = tk.Frame(card2, bg=Theme.BG_CARD)
        geom_frame.pack(fill="x", pady=5)
        
        fields = [("Res W:", "width_px"), ("Res H:", "height_px"), 
                  ("Dim W:", "width_mm"), ("Dim H:", "height_mm"),
                  ("Off V:", "vertical_offset_mm"), ("Off H:", "horizontal_offset_mm"),
                  ("Off D:", "depth_offset_mm")]
        
        self._geom_entries = {}
        
        for i, (label, key) in enumerate(fields):
            tk.Label(geom_frame, text=label, bg=Theme.BG_CARD, fg=Theme.TEXT_MAIN).grid(row=i//4, column=(i%4)*2, sticky="e", padx=5, pady=5)
            ent = tk.Entry(geom_frame, bg=Theme.BG_INPUT, fg=Theme.TEXT_MAIN, bd=0, width=8)
            ent.grid(row=i//4, column=(i%4)*2 + 1, padx=5, pady=5)
            self._geom_entries[key] = ent
            
        tk.Button(geom_frame, text="Update Config", bg=Theme.BG_INPUT, fg=Theme.TEXT_MAIN, bd=0, command=self.on_update_config).grid(row=0, column=8, rowspan=2, padx=20)
        
        calib_frame = tk.Frame(card2, bg=Theme.BG_CARD)
        calib_frame.pack(fill="x", pady=10)
        tk.Button(calib_frame, text="Calibrate Tracker", bg=Theme.ACCENT, fg=Theme.TEXT_MAIN, bd=0, width=20, command=self.on_calibrate).pack(side="left")
        tk.Button(calib_frame, text="View Results", bg=Theme.BG_INPUT, fg=Theme.TEXT_MAIN, bd=0, width=15, command=self.on_view_results).pack(side="left", padx=10)

        self.btn_find_tracker = tk.Button(calib_frame, text="Find Tracker", bg=Theme.WARNING, fg="black", bd=0, width=15, command=self.on_find_tracker)
        self.btn_find_tracker.pack(side="left", padx=10)

        # 3. External Equipment & Data Card
        card_ext = self._create_card(self, "3. External Equipment & Data")
        row_ext = tk.Frame(card_ext, bg=Theme.BG_CARD)
        row_ext.pack(fill="x", pady=5)

        # A. LOGGING SECTION (GoPro & Biometrics)
        for label in self.orchestrator.settings.external_equiment_to_sync:
            col = tk.Frame(row_ext, bg=Theme.BG_CARD)
            col.pack(side="left", expand=True, fill="both", padx=5)
            
            btn = tk.Button(
                col, text=f"Log {label} Start", 
                bg=Theme.BG_INPUT, fg=Theme.TEXT_MAIN, 
                bd=0, height=1, font=Theme.FONT_BODY,
                state="disabled",
                command=lambda l=label: self.on_log_external_time(l)
            )
            btn.pack(fill="x")
            self._sync_buttons[label] = btn
            
            lbl = tk.Label(col, text="HH:MM:SS", font=Theme.FONT_TINY, bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED)
            lbl.pack(pady=(5, 0))
            self._sync_labels[label] = lbl

        # B. VERTICAL SEPARATOR
        # We use a 2px wide frame with a slightly darker background to create a visual divider
        separator = tk.Frame(row_ext, bg=Theme.BG_WINDOW, width=2)
        separator.pack(side="left", fill="y", padx=20)

        # C. FETCH SECTION (Polaris DB)
        col_polaris = tk.Frame(row_ext, bg=Theme.BG_CARD)
        col_polaris.pack(side="left", expand=True, fill="both", padx=5)

        self.btn_fetch_polaris_events = tk.Button(
            col_polaris, text="Fetch Polaris Events", 
            bg=Theme.BG_INPUT, fg=Theme.TEXT_MAIN, 
            bd=0, height=1, font=Theme.FONT_BODY,
            state="disabled", 
            command=self.on_fetch_polaris_db
        )
        self.btn_fetch_polaris_events.pack(fill="x")

        self.lbl_polaris_filename = tk.Label(
            col_polaris, text="N/A", 
            font=Theme.FONT_TINY, bg=Theme.BG_CARD, 
            fg=Theme.TEXT_MUTED, wraplength=180
        )
        self.lbl_polaris_filename.pack(pady=(5, 0))

        # 4. Services Card
        card3 = self._create_card(self, "4. Services Control")
        srv_frame = tk.Frame(card3, bg=Theme.BG_CARD)
        srv_frame.pack(fill="x")
        
        for name in self.orchestrator.services.keys():
            row = tk.Frame(srv_frame, bg=Theme.BG_CARD)
            row.pack(fill="x", pady=5)
            
            ind = tk.Canvas(row, width=16, height=16, bg=Theme.BG_CARD, highlightthickness=0)
            ind.create_oval(2, 2, 14, 14, fill=Theme.DISABLED, tags="dot")
            ind.pack(side="left", padx=5)
            self._service_indicators[name] = ind
            
            tk.Label(row, text=name.capitalize().ljust(15), font=Theme.FONT_MONO, bg=Theme.BG_CARD, fg=Theme.TEXT_MAIN, width=15, anchor="w").pack(side="left")
            
            timer = tk.Label(row, text="00:00", font=Theme.FONT_MONO, bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED, width=8)
            timer.pack(side="left", padx=10)
            self._service_timers[name] = timer
            
            start_btn = tk.Button(row, text="Start", bg=Theme.SUCCESS, fg="black", bd=0, width=10,
                                  command=lambda n=name: self._run_async(self.orchestrator.start_service(n)))
            start_btn.pack(side="left", padx=5)
            self._service_starts[name] = start_btn
            
            stop_btn = HoldButton(row, text="Stop", width=100, height=25, bg_color=Theme.BG_INPUT,
                                  command=lambda n=name: self._run_async(self.orchestrator.stop_service(n)))
            stop_btn.pack(side="left", padx=5)
            self._service_stops[name] = stop_btn

        global_frame = tk.Frame(card3, bg=Theme.BG_CARD)
        global_frame.pack(fill="x", pady=15)
        tk.Button(global_frame, text="START ALL", bg=Theme.SUCCESS, fg="black", bd=0, font=Theme.FONT_H2, 
                  command=lambda: self._run_async(self.orchestrator.start_all())).pack(side="left", fill="x", expand=True, padx=5)
        HoldButton(global_frame, text="HOLD TO STOP ALL", height=35, bg_color=Theme.BG_INPUT, fill_color=Theme.DANGER, 
                   command=lambda: self._run_async(self.orchestrator.stop_all())).pack(side="left", fill="x", expand=True, padx=5)

        # 6. Finalize Card
        card5 = self._create_card(self, "6. Post-Session Actions")
        btn_frame = tk.Frame(card5, bg=Theme.BG_CARD)
        btn_frame.pack(fill="x", pady=(0, 10))
        
        self.btn_mark_success = tk.Button(btn_frame, text="MARK AS SUCCESS", bg=Theme.SUCCESS, fg="black", bd=0, font=Theme.FONT_H2, height=2,
                                          command=lambda: self.on_mark_session(True))
        self.btn_mark_success.pack(side="left", fill="x", expand=True, padx=5)
        
        self.btn_mark_aborted = tk.Button(btn_frame, text="MARK AS ABORTED", bg=Theme.DANGER, fg="white", bd=0, font=Theme.FONT_H2, height=2,
                                          command=lambda: self.on_mark_session(False))
        self.btn_mark_aborted.pack(side="left", fill="x", expand=True, padx=5)

        # --- NEW: Notes Box ---
        notes_frame = tk.Frame(card5, bg=Theme.BG_CARD)
        notes_frame.pack(fill="x")
        tk.Label(notes_frame, text="Session Notes (Optional):", bg=Theme.BG_CARD, fg=Theme.TEXT_MUTED, font=Theme.FONT_BODY).pack(anchor="w")
        self.txt_notes = tk.Text(notes_frame, bg=Theme.BG_INPUT, fg=Theme.TEXT_MAIN, insertbackground=Theme.TEXT_MAIN, bd=0, height=3, font=Theme.FONT_BODY)
        self.txt_notes.pack(fill="x", pady=5)


    # --- Actions & Logic ---

    def _populate_initial_data(self):
        cfg = self.orchestrator.settings.display_area
        for key, ent in self._geom_entries.items():
            ent.delete(0, tk.END) # Clear it first to prevent appending
            ent.insert(0, str(getattr(cfg, key)))
    
    def on_find_tracker(self):
        self.btn_find_tracker.config(text="Searching...", state="disabled")
        
        def _on_done(success):
            self.btn_find_tracker.config(text="Find Tracker", state="normal")
            if success:
                messagebox.showinfo("Hardware", "Eye tracker connected successfully.")
            else:
                messagebox.showwarning("Hardware", "No eye tracker found. Check USB connection.")
                
        self._run_async(self.orchestrator.initialize(), _on_done)

    def on_log_external_time(self, label: str):
        # 2. Log the time
        dt = self.orchestrator.log_external_start(label)
        
        # 3. Update UI
        time_str = dt.astimezone().strftime("%H:%M:%S") # Show local time for the operator
        self._sync_labels[label].config(text=f"{time_str}", fg=Theme.SUCCESS)
        self._sync_buttons[label].config(bg=Theme.SUCCESS, fg="black", text=f"{label} Active")

    def on_set_ids(self):
        pid = self.ent_pid.get().strip()
        sid = self.ent_sid.get().strip()
        if not pid or not sid:
            messagebox.showerror("Error", "Both IDs are required.")
            return
        
        def _on_ids_set(calib_loaded: bool):
            msg = "IDs applied."
            if calib_loaded:
                msg += f"\nAuto-loaded cached calibration for {pid}."
            messagebox.showinfo("Setup", msg)

        # Activate Sync Buttons and turn them Yellow
        for label, btn in self._sync_buttons.items():
            btn.config(state="normal", bg=Theme.WARNING, fg="black", text=f"Log {label} Start")
            self._sync_labels[label].config(text="HH:MM:SS", fg=Theme.WARNING)
        
        self.btn_fetch_polaris_events.config(state="normal", bg=Theme.WARNING, fg="black", text="Fetch Polaris events")
        self.lbl_polaris_filename.config(text="N/A", fg=Theme.WARNING)

        self._run_async(self.orchestrator.set_experiment_ids(pid, sid), _on_ids_set)

    def on_update_config(self):
        try:
            cfg_dict = {key: float(ent.get()) for key, ent in self._geom_entries.items()}
            cfg_dict["width_px"] = int(cfg_dict["width_px"])
            cfg_dict["height_px"] = int(cfg_dict["height_px"])
            
            new_cfg = DisplayAreaSettings(**cfg_dict)

            def _on_result(success: bool):
                if success:
                    messagebox.showinfo("Config", "Hardware settings updated successfully.")
                else:
                    messagebox.showerror("Hardware Error", "Failed to apply settings. Check eye tracker connection.")

            self._run_async(self.orchestrator.update_display_settings(new_cfg), _on_result)

        except Exception as e:
            messagebox.showerror("Input Error", f"Invalid input values: {e}")

    def on_calibrate(self):
        view = CalibrationWindow(self, self.orchestrator.settings.display_area.width_px, self.orchestrator.settings.display_area.height_px)
        def _on_done(success):
            if success: messagebox.showinfo("Calibration", "Calibration Successful!")
            else: messagebox.showwarning("Calibration", "Calibration Failed or Aborted.")
            
        self._run_async(self.orchestrator.calibrate_tracker(view), _on_done)

    def on_view_results(self):
        view = CalibrationWindow(self, self.orchestrator.settings.display_area.width_px, self.orchestrator.settings.display_area.height_px)
        self._run_async(self.orchestrator.show_calibration_results(view))

    def on_fetch_polaris_db(self):
        self.btn_fetch_polaris_events.config(state="disabled", text="Connecting...")
        self.lbl_polaris_filename.config(text="Searching remote host...", fg=Theme.WARNING)

        def _on_file_downloaded(result):
            success, msg = result
            if success:
                self.btn_fetch_polaris_events.config(state="normal", bg=Theme.SUCCESS, fg="black", text="Fetched ✓")
                # Add a checkmark to the current label text
                current_name = self.lbl_polaris_filename.cget("text")
                self.lbl_polaris_filename.config(fg=Theme.SUCCESS)
                messagebox.showinfo("Success", msg)
            else:
                self.btn_fetch_polaris_events.config(state="normal", bg=Theme.WARNING, text="Retry Fetch")
                self.lbl_polaris_filename.config(text="Transfer Failed", fg=Theme.DANGER)
                messagebox.showerror("Download Failed", msg)

        def _on_file_checked(result):
            success, payload = result
            if not success:
                self.btn_fetch_polaris_events.config(state="normal", bg=Theme.WARNING, text="Fetch Polaris Events")
                self.lbl_polaris_filename.config(text="File not found", fg=Theme.DANGER)
                messagebox.showerror("Check Failed", payload)
                return

            filename = payload
            self.lbl_polaris_filename.config(text=filename, fg=Theme.WARNING)
            
            confirm = messagebox.askyesno(
                "Confirm File", 
                f"Found latest file:\n{filename}\n\nDownload and compress?"
            )
            
            if confirm:
                self.btn_fetch_polaris_events.config(state="disabled", text="Transferring...")
                self._run_async(self.orchestrator.fetch_and_zip_remote_file(filename), _on_file_downloaded)
            else:
                self.btn_fetch_polaris_events.config(state="normal", bg=Theme.WARNING, text="Fetch Polaris Events")
                self.lbl_polaris_filename.config(text="N/A", fg=Theme.WARNING)

        self._run_async(self.orchestrator.get_latest_remote_filename(), _on_file_checked)

    def on_mark_session(self, success: bool):
        # 1. Grab notes from the text box
        notes = self.txt_notes.get("1.0", tk.END).strip()
        
        is_ok, msg = self.orchestrator.mark_session(is_success=success, notes=notes)
        
        if is_ok:
            if success:
                self.ent_pid.delete(0, tk.END)
                self.ent_sid.delete(0, tk.END)

                # Reset buttons
                for label, btn in self._sync_buttons.items():
                    btn.config(state="disabled", bg=Theme.BG_INPUT, fg=Theme.TEXT_MAIN, text=f"Log {label} Start")
                    self._sync_labels[label].config(text="N/A", fg=Theme.TEXT_MUTED)

                self.btn_fetch_polaris_events.config(state="disabled", bg=Theme.BG_INPUT, fg=Theme.TEXT_MAIN, text="Fetch Polaris DB")
                self.lbl_polaris_filename.config(text="N/A", fg=Theme.TEXT_MUTED)
            else:
                # Activate Sync Buttons and turn them Yellow
                for label, btn in self._sync_buttons.items():
                    btn.config(state="normal", bg=Theme.WARNING, fg="black", text=f"Log {label} Start")
                    self._sync_labels[label].config(text="HH:MM:SS", fg=Theme.WARNING)
                
                self.btn_fetch_polaris_events.config(state="normal", bg=Theme.WARNING, fg="black", text="Fetch Polaris events")
                self.lbl_polaris_filename.config(text="N/A", fg=Theme.WARNING)
            
            self.txt_notes.delete("1.0", tk.END)
            


            messagebox.showinfo("Session Marked", msg)
        else:
            messagebox.showwarning("Warning", msg)

    # --- Polling Loop ---

    def _poll_ui_state(self):
        states = self.orchestrator.get_service_states()
        durations = self.orchestrator.get_service_durations()
        is_recording = False

        for name, state in states.items():
            ind = self._service_indicators[name]
            timer = self._service_timers[name]
            
            if state == ServiceState.UNAVAILABLE:
                color, text_color = Theme.DISABLED, Theme.TEXT_MUTED
            elif state == ServiceState.READY:
                color, text_color = Theme.SUCCESS, Theme.TEXT_MAIN
            elif state == ServiceState.RECORDING:
                color, text_color = Theme.DANGER, Theme.DANGER
                is_recording = True
            else:
                color, text_color = Theme.DISABLED, Theme.TEXT_MUTED

            ind.itemconfig("dot", fill=color)
            timer.config(text=durations.get(name, "00:00"), fg=text_color)
            
            if state == ServiceState.UNAVAILABLE:
                self._service_starts[name].config(state="disabled")
                self._service_stops[name].set_state("disabled")
            elif state == ServiceState.READY:
                self._service_starts[name].config(state="normal")
                self._service_stops[name].set_state("disabled")
            elif state == ServiceState.RECORDING:
                self._service_starts[name].config(state="disabled")
                self._service_stops[name].set_state("normal")

        hw_state = self.orchestrator.gaze_manager.current_state
        
        if hw_state is AppState.NO_TRACKER:
            self.btn_find_tracker.pack(side="left", padx=10)
        else:
            self.btn_find_tracker.pack_forget()

        # Dynamic Lockout for "Mark As" buttons
        has_session = self.orchestrator.session_id is not None
        can_mark = has_session and not is_recording
        mark_state = "normal" if can_mark else "disabled"
        
        self.btn_mark_success.config(state=mark_state)
        self.btn_mark_aborted.config(state=mark_state)

        self.after(200, self._poll_ui_state)

    def on_closing(self):
        def _on_shutdown_done(_):
            self.destroy()

        self._run_async(self.orchestrator.shutdown(), _on_shutdown_done)