import asyncio
import json
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

from .services import BaseService, ServiceState
from ..core.manager import EyeTrackingManager
from ..configs import AppSettings, DisplayAreaSettings
from ..core.protocols import CalibrationView

logger = logging.getLogger(__name__)

class ExperimentOrchestrator:
    """
    Command Center Backend.
    Manages metadata, file operations, and coordinates all Services.
    """
    def __init__(self, settings: AppSettings, gaze_manager: EyeTrackingManager, services: list[BaseService]):
        self.settings = settings
        self.gaze_manager = gaze_manager
        
        self.session_id: str | None = None
        self.participant_id: str | None = None
        self.scenario_id: str | None = None

        self.services: dict[str, BaseService] = {s.name: s for s in services}
        self.external_start_times: dict[str, list[datetime]] = defaultdict(list)
        
        self.experiment_root: Path = self.settings.data_dir
        self.experiment_root.mkdir(parents=True, exist_ok=True)
        
        self._load_or_create_display_settings()

    @property
    def session_dir(self) -> Path | None:
        return (self.experiment_root / self.session_id) if self.session_id else None
    
    @property
    def run_id(self) -> str:
        return f"{self.participant_id}_april_{self.scenario_id}"

    def _load_or_create_display_settings(self):
        """Synchronously loads settings from disk, or creates the file if missing."""
        display_json = self.experiment_root / "display_settings.json"
        
        if display_json.exists():
            try:
                with open(display_json, "r") as f:
                    data = json.load(f)
                    self.settings.display_area = DisplayAreaSettings(**data)
                logger.info("Loaded display settings from disk.")
            except Exception as e:
                logger.error(f"Failed to load display settings (using defaults): {e}")
        else:
            with open(display_json, "w") as f:
                f.write(self.settings.display_area.model_dump_json(indent=2))
            logger.info("Created default display settings file.")

    async def initialize(self) -> bool:
        """Called at app startup ONLY to connect hardware using pre-loaded settings."""
        return await self.gaze_manager.connect(self.settings.display_area)
    
    def create_session_folder(self, pid: str, sid: str) -> None:
        self.participant_id = pid
        self.scenario_id = sid
        self.session_id = f"{self.run_id}__{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create folder structure
        self.session_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "ET").mkdir(parents=True, exist_ok=True)
        (self.session_dir / "simulator").mkdir(parents=True, exist_ok=True)
        (self.session_dir / "taskRecognition").mkdir(parents=True, exist_ok=True)
        (self.session_dir / "videoRecordings").mkdir(parents=True, exist_ok=True)
        (self.session_dir / "metadata").mkdir(parents=True, exist_ok=True)

    async def set_experiment_ids(self, pid: str, sid: str) -> None:
        self.create_session_folder(pid, sid)

        cache_dir = self.experiment_root / ".calibrations" / pid
        if cache_dir.exists():
            success = await self.gaze_manager.load_calibration(cache_dir)
            
            # Force GazeService to re-evaluate its state now that it has calibration
            if success:
                logger.info(f"Auto-loading cached calibration for {pid}")
                self.services["gaze"].refresh_state()

            return success
            
        return False

    # --- Hardware & Calibration Bridges ---

    async def update_display_settings(self, new_settings: DisplayAreaSettings) -> bool:
        self.settings.display_area = new_settings
        display_json = self.experiment_root / "display_settings.json"
        
        with open(display_json, "w") as f:
            f.write(new_settings.model_dump_json(indent=2))
        
        return await self.gaze_manager.controller.apply_display_settings(new_settings)

    async def calibrate_tracker(self, view: CalibrationView) -> bool:
        if not self.participant_id:
            logger.warning("Cannot calibrate: No participant ID set.")
            return False
        cache_dir = self.experiment_root / ".calibrations" / self.participant_id
        cache_dir.mkdir(parents=True, exist_ok=True)
        return await self.gaze_manager.run_calibration(cache_dir, view)

    async def show_calibration_results(self, view: CalibrationView) -> bool:
        if not self.participant_id:
            return False
        cache_dir = self.experiment_root / ".calibrations" / self.participant_id
        return await self.gaze_manager.controller.show_calibration_results(cache_dir, view)

    # --- UI Status Getters ---

    def get_service_states(self) -> dict[str, ServiceState]:
        return {name: svc.current_state for name, svc in self.services.items()}

    def get_service_durations(self) -> dict[str, str]:
        return {name: svc.get_duration_str() for name, svc in self.services.items()}
    
    # --- Copy polaris .db file ---

    async def get_latest_remote_filename(self) -> tuple[bool, str]:
        """Queries the remote host for the newest file with a 5-second timeout."""
        try:
            ssh_opts = "-o ConnectTimeout=5 -o StrictHostKeyChecking=no"

            # The regex:
            # ^events-           Starts with 'events-'
            # [0-9]{4}-[0-9]{2}-[0-9]{2}  Date (YYYY-MM-DD)
            # T                  The 'T' separator
            # [0-9]{2}:[0-9]{2}:[0-9]{2}  Time (HH:MM:SS)
            # \.db$              Ends exactly in '.db'
            regex = r"^events-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.db$"
            
            # Get last edited file that matches regex
            find_cmd = f"ls -t '{self.settings.orion_polaris_db_dir}' | grep -E '{regex}' | head -n 1"
            
            proc = await asyncio.create_subprocess_shell(
                f"ssh {ssh_opts} {self.settings.orion_host} \"{find_cmd}\"",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 10 second absolute timeout for the whole operation
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            
            if proc.returncode != 0:
                # Note: grep returns exit code 1 if no matches are found, 
                # we should handle that as "No files" rather than "SSH Error"
                if proc.returncode == 1:
                    return False, "No .db files found."
                
                err = stderr.decode('utf-8').strip()
                return False, f"Remote check failed: {err}"
                
            filename = stdout.decode('utf-8').strip()
            if not filename:
                return False, "No .db files found."
                
            return True, filename
            
        except asyncio.TimeoutError:
            return False, "Connection to simulator timed out."
        except Exception as e:
            return False, str(e)

    async def fetch_and_zip_remote_file(self, filename: str) -> tuple[bool, str]:
        """Downloads the specific file via SCP and zips it locally."""
        if not self.session_dir:
            return False, "No active session."

        try:
            sim_dir = self.session_dir / "simulator"
            temp_dest = sim_dir / filename
            final_zip = sim_dir / f"simdata__{filename}.zip"

            # 1. Transfer via SCP
            scp_opts = "-o ConnectTimeout=5 -o StrictHostKeyChecking=no"
            scp_cmd = f"scp -q {scp_opts} '{self.settings.orion_host}:{self.settings.orion_polaris_db_dir}/{filename}' '{temp_dest}'"
            
            proc_scp = await asyncio.create_subprocess_shell(scp_cmd)
            # 5 minute timeout for a 1GB file over local network is usually safe
            await asyncio.wait_for(proc_scp.wait(), timeout=300.0) 
            
            if proc_scp.returncode != 0:
                return False, "File transfer failed or was interrupted."

            # 2. Compress locally
            zip_cmd = f"zip -j -q '{final_zip}' '{temp_dest}'"
            proc_zip = await asyncio.create_subprocess_shell(zip_cmd)
            await proc_zip.wait()
            
            if proc_zip.returncode != 0:
                return False, "Local ZIP compression failed."

            # 3. Cleanup
            if temp_dest.exists():
                temp_dest.unlink()

            return True, f"Successfully saved as {final_zip.name}"

        except asyncio.TimeoutError:
            return False, "Operation timed out. The file might be too large or connection dropped."
        except Exception as e:
            logger.error(f"Error fetching file: {e}", exc_info=True)
            return False, f"Unexpected error: {e}"
        
    def log_external_start(self, label: str) -> datetime:
        """Captures current UTC time for an external device."""
        now = datetime.now(timezone.utc)
        self.external_start_times[label].append(now)
        return now

    # --- Service Orchestration ---

    async def start_service(self, target_name: str) -> bool:
        if self.session_dir is None:
            logger.warning("Missing participant or scenario IDs.")
            return False

        if target_name not in self.services:
            return False

        return await self.services[target_name].start(self.session_id)

    async def stop_service(self, target_name: str) -> None:
        if target_name in self.services:
            await self.services[target_name].stop()

    async def start_all(self) -> bool:
        started_services = []
        for name in self.services:
            success = await self.start_service(name)
            if success:
                started_services.append(name)
            else:
                logger.error(f"Failed to start '{name}'. Rolling back other services...")
                for started in started_services:
                    await self.stop_service(started)
                return False
        return True

    async def stop_all(self):
        for name in self.services:
            await self.stop_service(name)

    def _correct_folder_structure(self):
        # Update filenames
        grouped_files: dict[str, list[Path]] = defaultdict(list)

        # Pass 1: Collect and group files by (parent_directory, X_part)
        for filepath in self.session_dir.rglob("*"):
            if filepath.is_file():
                # Skip metadata folder
                rel_parts = filepath.relative_to(self.session_dir).parts
                if rel_parts and rel_parts[0] == "metadata":
                    continue

                x_part = filepath.stem.split("__")[0]
                
                grouped_files[x_part].append(filepath)

        # Pass 2: Rename files with sequential suffixes if needed
        for x_part, files in grouped_files.items():
            # Sort the files so earlier timestamps get _1, later get _2, etc.
            files.sort()
            
            for i, filepath in enumerate(files, start=1):
                # Add a number suffix only if there's more than one file in the group
                num_suffix = f"_{i}" if len(files) > 1 else ""
                
                new_filename = f"{self.run_id}_{x_part}{num_suffix}{filepath.suffix}"
                new_filepath = filepath.with_name(new_filename)
                
                try:
                    filepath.rename(new_filepath)
                except Exception as e:
                    logger.error(f"Failed to rename file {filepath.name} to {new_filename}: {e}")
        
        # Update folder name
        new_path = self.experiment_root / self.run_id
        counter = 1
        while new_path.exists():
            new_path = self.experiment_root / f"{self.run_id}_v{counter}"
            counter += 1
        self.session_dir.rename(new_path)

    # --- Utilities & File Handlers ---

    def mark_session(self, is_success: bool, notes: str = "") -> tuple[bool, str]:
        """Safely marks session. Returns (Success, Message)."""
        if not self.session_id or not self.session_dir:
            return False, "No active session to mark."

        if any(svc.current_state == ServiceState.RECORDING for svc in self.services.values()):
            return False, "Cannot mark session while services are actively recording. Stop them first."
        
        metadata_dir = self.session_dir / "metadata"

        meta = {
            "success": is_success,
            "participant": self.participant_id,
            "scenario": self.scenario_id,
            "notes": notes,
            "end_timestamp": datetime.now(timezone.utc).isoformat(),
            "external_sync": {
                label: [dt.isoformat() for dt in dts]
                for label, dts in self.external_start_times.items()
            }
        }
        with open(metadata_dir / "session_meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        
        # Copy calibration
        if self.gaze_manager.controller.last_calibration_path is not None:
            shutil.copytree(self.gaze_manager.controller.last_calibration_path, metadata_dir/"calibration", dirs_exist_ok=True)

        # Save display settings
        if self.gaze_manager.controller.last_display_settings is not None:
            with open(metadata_dir/"display_settings.json", "w") as f:
                f.write(self.gaze_manager.controller.last_display_settings.model_dump_json(indent=2))

        try:
            if is_success:
                self._correct_folder_structure()
                self.session_id, self.participant_id, self.scenario_id = None, None, None
            else:
                new_path = self.session_dir.with_name(f"{self.session_dir.name}_aborted")
                self.session_dir.rename(new_path)
                self.create_session_folder(self.participant_id, self.scenario_id)
                
            self.external_start_times = defaultdict(list)
            return True, "Session marked successfully."
        except Exception as e:
            logger.error(f"Failed to rename session directory: {e}")
            return False, f"Failed to rename directory: {e}"

    async def shutdown(self):
        """Called when the UI closes to safely kill all tasks."""
        await self.stop_all() # Ensure recordings are stopped
        
        await asyncio.gather(*(svc.shutdown() for svc in self.services.values()))
        
        self.gaze_manager.shutdown()