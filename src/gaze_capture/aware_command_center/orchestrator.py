import asyncio
import json
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path

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
        
        self.experiment_root: Path = self.settings.data_dir
        self.experiment_root.mkdir(parents=True, exist_ok=True)
        
        self._load_or_create_display_settings()

    @property
    def session_dir(self) -> Path | None:
        return (self.experiment_root / self.session_id) if self.session_id else None

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

    async def set_experiment_ids(self, pid: str, sid: str) -> None:
        self.participant_id = pid
        self.scenario_id = sid
        self.session_id = f"{pid}_{sid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

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

    # --- Service Orchestration ---

    async def start_service(self, target_name: str) -> bool:
        if self.session_dir is None:
            logger.warning("Missing participant or scenario IDs.")
            return False

        if target_name not in self.services:
            return False

        self.session_dir.mkdir(parents=True, exist_ok=True)

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

    # --- Utilities & File Handlers ---

    def mark_session(self, is_success: bool, notes: str = "") -> tuple[bool, str]:
        """Safely marks session. Returns (Success, Message)."""
        if not self.session_id or not self.session_dir:
            return False, "No active session to mark."

        if any(svc.current_state == ServiceState.RECORDING for svc in self.services.values()):
            return False, "Cannot mark session while services are actively recording. Stop them first."

        meta = {
            "success": is_success,
            "participant": self.participant_id,
            "scenario": self.scenario_id,
            "notes": notes,
            "end_timestamp": datetime.now(timezone.utc).isoformat()
        }
        with open(self.session_dir / "session_meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        
        # Copy calibration
        if self.gaze_manager.controller.last_calibration_path is not None:
            shutil.copytree(self.gaze_manager.controller.last_calibration_path, self.session_dir/"calibration", dirs_exist_ok=True)

        # Save display settings
        if self.gaze_manager.controller.last_display_settings is not None:
            with open(self.session_dir/"display_settings.json", "w") as f:
                f.write(self.gaze_manager.controller.last_display_settings.model_dump_json(indent=2))

        try:
            if is_success:
                clean_name = f"{self.participant_id}_{self.scenario_id}"
                new_path = self.experiment_root / clean_name
                counter = 1
                while new_path.exists():
                    new_path = self.experiment_root / f"{clean_name}_v{counter}"
                    counter += 1
                self.session_dir.rename(new_path)
            else:
                new_path = self.session_dir.with_name(f"{self.session_dir.name}_aborted")
                self.session_dir.rename(new_path)
                
            self.session_id = None
            return True, "Session marked and directory renamed successfully."
        except Exception as e:
            logger.error(f"Failed to rename session directory: {e}")
            return False, f"Failed to rename directory: {e}"
    
    async def shutdown(self):
        """Called when the UI closes to safely kill all tasks."""
        await self.stop_all() # Ensure recordings are stopped
        
        await asyncio.gather(*(svc.shutdown() for svc in self.services.values()))
        
        self.gaze_manager.shutdown()