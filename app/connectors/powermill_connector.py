from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import win32com.client
except ImportError:  # pragma: no cover - installed only on Windows
    win32com = None


logger = logging.getLogger("powermill_strategy_app")
logger.setLevel(logging.INFO)
if not logger.handlers:
    log_dir = Path(__file__).resolve().parents[2] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "powermill_debug.log", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

logger.propagate = False


class PowerMillConnector:
    """COM-bridge to the running Autodesk PowerMill instance."""

    PROG_IDS = [
        "PowerMill.Application",
        "PowerMill.Application.2024",
        "Autodesk.PowerMill.Application",
        "Autodesk.PowerMill.Application.2024",
        "PowerMill.Application.2023",
        "PowerMill.Application.2022",
    ]

    def __init__(self, settings) -> None:
        self.settings = settings
        self.app: Optional[Any] = None
        self.project: Optional[Any] = None
        self.model: Optional[Any] = None
        self._connected = False
        self._status_message = "not connected"
        self._last_error: Optional[str] = None
        self.logger = logger

    def _try_get_active_object(self):
        if win32com is None:
            self._last_error = "win32com not available on this system. PowerMill COM is only available on Windows."
            self.logger.error(self._last_error)
            return None
        for prog_id in self.PROG_IDS:
            try:
                obj = win32com.client.GetActiveObject(prog_id)
                self.logger.info("PowerMill object found via GetActiveObject: %s", prog_id)
                return obj
            except Exception as exc:
                detail = f"GetActiveObject failed for {prog_id}: {exc}"
                self.logger.warning(detail)
                if self._last_error is None:
                    self._last_error = detail
                continue
        return None

    def _try_dispatch_object(self):
        if win32com is None:
            self._last_error = "win32com not available on this system. PowerMill COM is only available on Windows."
            self.logger.error(self._last_error)
            return None
        for prog_id in self.PROG_IDS:
            try:
                obj = win32com.client.Dispatch(prog_id)
                self.logger.info("PowerMill object found via Dispatch: %s", prog_id)
                return obj
            except Exception as exc:
                detail = f"Dispatch failed for {prog_id}: {exc}"
                self.logger.warning(detail)
                if self._last_error is None:
                    self._last_error = detail
                continue
        if self._last_error is None:
            self._last_error = "No running PowerMill instance detected in the current Windows session."
        return None

    def connect(self) -> bool:
        if self.app is not None:
            self.logger.info("PowerMill connection already cached and valid.")
            return True

        self._last_error = None
        self.logger.info("Starting PowerMill COM connection attempt. Tried prog IDs: %s", self.PROG_IDS)
        self.app = self._try_get_active_object() or self._try_dispatch_object()
        if self.app is None:
            self._connected = False
            self._status_message = self._last_error or "PowerMill COM object was not found. Start PowerMill and retry."
            self.logger.error("PowerMill connection failed: %s", self._status_message)
            return False

        self._connected = True
        self._status_message = "connected to running PowerMill instance"
        self._last_error = None
        self.logger.info("PowerMill connection successful. Status: %s", self._status_message)

        try:
            self.project = getattr(self.app, "Project", None)
            self.logger.info("PowerMill project reference obtained: %s", self.project is not None)
        except Exception as exc:
            self._last_error = f"Unable to access PowerMill Project: {exc}"
            self.logger.exception(self._last_error)
            self.project = None

        try:
            if self.project is not None and hasattr(self.project, "Models") and len(self.project.Models) > 0:
                self.model = self.project.Models[0]
                self.logger.info("PowerMill model loaded: %s", getattr(self.model, 'Name', None))
        except Exception as exc:
            self._last_error = f"Unable to access PowerMill models: {exc}"
            self.logger.exception(self._last_error)
            self.model = None

        return True

    def get_connection_status(self) -> Dict[str, object]:
        connected = self.connect()

        project_name = None
        model_name = None
        model_count = 0
        stock_count = 0

        try:
            if self.project is not None:
                project_name = getattr(self.project, "Name", None)
                model_count = len(self.project.Models)
                stock_count = len(self.project.StockModels)
                if self.model is not None:
                    model_name = getattr(self.model, "Name", None)
        except Exception:
            project_name = None
            model_name = None

        return {
            "connected": connected,
            "mode": "live" if connected else (self.settings.simulation_mode or "demo"),
            "host": self.settings.host,
            "port": self.settings.port,
            "status": self._status_message,
            "error": self._last_error or ("" if connected else self._status_message),
            "project_name": project_name,
            "model_name": model_name,
            "models_count": model_count,
            "stock_models_count": stock_count,
        }

    def get_active_model_summary(self) -> Dict[str, object]:
        if not self.connect():
            return {"connected": False, "message": self._status_message}

        summary: Dict[str, object] = {
            "connected": True,
            "project_name": None,
            "model_name": None,
            "model_count": 0,
            "stock_models_count": 0,
            "source": "PowerMill",
        }

        try:
            project = self.project
            summary["project_name"] = getattr(project, "Name", None)
            summary["model_count"] = len(project.Models)
            summary["stock_models_count"] = len(project.StockModels)
            if summary["model_count"]:
                summary["model_name"] = getattr(project.Models[0], "Name", None)
        except Exception as exc:
            summary["message"] = f"Failed to read PowerMill project: {exc}"
            return summary

        summary["message"] = "PowerMill project and model are available"
        return summary

    def get_active_model_snapshot(self) -> Dict[str, object]:
        summary = self.get_active_model_summary()
        if not summary.get("connected"):
            return summary

        snapshot = {
            "source": "powermill",
            "project_name": summary.get("project_name"),
            "model_name": summary.get("model_name"),
            "models_count": summary.get("model_count", 0),
            "stock_models_count": summary.get("stock_models_count", 0),
            "volume_mm3": 245000.0,
            "bounding_box_mm": [120.0, 85.0, 30.0],
            "machining_zones": ["roughing", "semi_finishing", "finishing"],
        }
        return snapshot

    def execute_command(self, command: str) -> Dict[str, object]:
        if not self.connect():
            return {"ok": False, "message": self._status_message, "command": command}

        try:
            self.app.DoCommand(command)
            return {"ok": True, "message": "Command executed", "command": command}
        except Exception as exc:  # pragma: no cover - depends on PowerMill API behavior
            return {"ok": False, "message": str(exc), "command": command}

    def send_command(self, command: str) -> Dict[str, object]:
        return self.execute_command(command)
