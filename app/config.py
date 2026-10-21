import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ToolConfig:
    name: str
    tool_type: str
    diameter_mm: float
    flute_length_mm: float
    max_rpm: int
    cutting_speed_m_min: float = 180.0
    plunge_feed_mm_min: float = 180.0
    drilling_feed_mm_min: float = 240.0
    feed_per_tooth: float = 0.06
    material: str = "aluminium"
    max_depth_mm: float = 20.0
    safe_z_mm: float = 5.0
    stepdown_mm: float = 2.5
    stock_allowance_mm: float = 0.3
    roughing_feed_mm_min: Optional[float] = None
    semi_finishing_feed_mm_min: Optional[float] = None
    finishing_feed_mm_min: Optional[float] = None

    @property
    def feed_rate_mm_min(self) -> float:
        return max(1.0, self.max_rpm * self.feed_per_tooth * 2)

    def get_operation_feed(self, operation: str, fallback: float) -> float:
        if operation == "roughing" and self.roughing_feed_mm_min is not None:
            return float(self.roughing_feed_mm_min)
        if operation == "semi_finishing" and self.semi_finishing_feed_mm_min is not None:
            return float(self.semi_finishing_feed_mm_min)
        if operation == "finishing" and self.finishing_feed_mm_min is not None:
            return float(self.finishing_feed_mm_min)
        return float(fallback)

    def get_operation_stepdown(self, operation: str, fallback: float) -> float:
        if operation == "roughing":
            return float(self.stepdown_mm if self.stepdown_mm and self.stepdown_mm > 0 else fallback)
        if operation == "semi_finishing":
            return float((self.stepdown_mm / 2.0) if self.stepdown_mm and self.stepdown_mm > 0 else fallback / 2.0)
        if operation == "finishing":
            return float(min(self.stepdown_mm or fallback, max(0.5, (self.stepdown_mm or fallback) / 3.0)))
        return float(fallback)

    def get_operation_allowance(self, operation: str, fallback: float) -> float:
        if operation == "roughing":
            return float(self.stock_allowance_mm if self.stock_allowance_mm and self.stock_allowance_mm > 0 else fallback)
        if operation == "semi_finishing":
            return float(0.15 if self.stock_allowance_mm <= 0 else min(self.stock_allowance_mm, 0.15))
        if operation == "finishing":
            return float(max(0.05, min(self.stock_allowance_mm or fallback, 0.25)))
        return float(fallback)


@dataclass
class MachineSettings:
    name: str = "Default_3Axis"
    material: str = "aluminium"
    max_spindle_rpm: int = 18000
    safe_z_mm: float = 5.0
    stepdown_mm: float = 2.5
    stock_allowance_mm: float = 0.3


@dataclass
class StrategySettings:
    simulation_mode: str = "auto"
    host: str = "127.0.0.1"
    port: int = 5000
    timeout_seconds: int = 30
    model_path: Optional[str] = None
    tool_library: List[ToolConfig] = field(default_factory=list)
    machine: MachineSettings = field(default_factory=MachineSettings)


class Settings:
    def __init__(self) -> None:
        self.simulation_mode = os.getenv("SIMULATION_MODE", "auto")
        self.host = os.getenv("POWERMILL_HOST", "127.0.0.1")
        self.port = int(os.getenv("POWERMILL_PORT", "5000"))
        self.timeout_seconds = int(os.getenv("POWERMILL_TIMEOUT", "30"))
        self.model_path = os.getenv("MODEL_PATH")
        self.tool_library_path = os.getenv("TOOL_LIBRARY_PATH")
        self.machine = self._build_machine_settings()
        self.tool_library = self._load_tool_library()

    def _build_machine_settings(self) -> MachineSettings:
        return MachineSettings(
            name=os.getenv("MACHINE_NAME", "Default_3Axis"),
            material=os.getenv("MATERIAL_TYPE", "aluminium"),
            max_spindle_rpm=int(os.getenv("MAX_SPINDLE_RPM", "18000")),
            safe_z_mm=float(os.getenv("SAFE_Z_MM", "5.0")),
            stepdown_mm=float(os.getenv("DEFAULT_STEPDOWN_MM", "2.5")),
            stock_allowance_mm=float(os.getenv("DEFAULT_STOCK_ALLOWANCE_MM", "0.3")),
        )

    def _load_tool_library(self) -> List[ToolConfig]:
        default_file = Path(__file__).resolve().parent / "data" / "tool_library.json"
        file_path = Path(self.tool_library_path) if self.tool_library_path else default_file

        if not file_path.exists():
            return self._default_tools()

        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            machine = payload.get("machine", {})
            self.machine = MachineSettings(
                name=machine.get("name", self.machine.name),
                material=machine.get("material", self.machine.material),
                max_spindle_rpm=int(machine.get("max_spindle_rpm", self.machine.max_spindle_rpm)),
                safe_z_mm=float(machine.get("safe_z_mm", self.machine.safe_z_mm)),
                stepdown_mm=float(machine.get("stepdown_mm", getattr(self.machine, "stepdown_mm", 2.5))),
                stock_allowance_mm=float(machine.get("stock_allowance_mm", getattr(self.machine, "stock_allowance_mm", 0.3))),
            )

            tools_data = payload.get("tools", [])
            if not tools_data:
                return self._default_tools()

            return [
                ToolConfig(
                    name=item["name"],
                    tool_type=item.get("tool_type", "endmill"),
                    diameter_mm=float(item.get("diameter_mm", 6.0)),
                    flute_length_mm=float(item.get("flute_length_mm", 25.0)),
                    max_rpm=int(item.get("max_rpm", self.machine.max_spindle_rpm)),
                    cutting_speed_m_min=float(item.get("cutting_speed_m_min", 180.0)),
                    plunge_feed_mm_min=float(item.get("plunge_feed_mm_min", 180.0)),
                    drilling_feed_mm_min=float(item.get("drilling_feed_mm_min", 220.0)),
                    feed_per_tooth=float(item.get("feed_per_tooth", 0.06)),
                    material=item.get("material", self.machine.material),
                    max_depth_mm=float(item.get("max_depth_mm", 10.0)),
                    safe_z_mm=float(item.get("safe_z_mm", self.machine.safe_z_mm)),
                    stepdown_mm=float(item.get("stepdown_mm", getattr(self.machine, "stepdown_mm", 2.5))),
                    stock_allowance_mm=float(item.get("stock_allowance_mm", getattr(self.machine, "stock_allowance_mm", 0.3))),
                    roughing_feed_mm_min=(float(item["roughing_feed_mm_min"]) if "roughing_feed_mm_min" in item and item["roughing_feed_mm_min"] is not None else None),
                    semi_finishing_feed_mm_min=(float(item["semi_finishing_feed_mm_min"]) if "semi_finishing_feed_mm_min" in item and item["semi_finishing_feed_mm_min"] is not None else None),
                    finishing_feed_mm_min=(float(item["finishing_feed_mm_min"]) if "finishing_feed_mm_min" in item and item["finishing_feed_mm_min"] is not None else None),
                )
                for item in tools_data
            ]
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            return self._default_tools()

    def _default_tools(self) -> List[ToolConfig]:
        return [
            ToolConfig(
                name="EM_6",
                tool_type="endmill",
                diameter_mm=6.0,
                flute_length_mm=25.0,
                max_rpm=16000,
                cutting_speed_m_min=180.0,
                plunge_feed_mm_min=180.0,
                drilling_feed_mm_min=220.0,
                feed_per_tooth=0.06,
                material="aluminium",
                max_depth_mm=16.0,
                safe_z_mm=5.0,
                stepdown_mm=2.5,
                stock_allowance_mm=0.3,
                roughing_feed_mm_min=1800.0,
                semi_finishing_feed_mm_min=1400.0,
                finishing_feed_mm_min=900.0,
            ),
            ToolConfig(
                name="EM_8",
                tool_type="endmill",
                diameter_mm=8.0,
                flute_length_mm=30.0,
                max_rpm=14000,
                cutting_speed_m_min=170.0,
                plunge_feed_mm_min=160.0,
                drilling_feed_mm_min=200.0,
                feed_per_tooth=0.06,
                material="aluminium",
                max_depth_mm=20.0,
                safe_z_mm=5.0,
                stepdown_mm=3.0,
                stock_allowance_mm=0.25,
                roughing_feed_mm_min=1700.0,
                semi_finishing_feed_mm_min=1200.0,
                finishing_feed_mm_min=800.0,
            ),
            ToolConfig(
                name="DR_5",
                tool_type="drill",
                diameter_mm=5.0,
                flute_length_mm=40.0,
                max_rpm=12000,
                cutting_speed_m_min=90.0,
                plunge_feed_mm_min=120.0,
                drilling_feed_mm_min=260.0,
                feed_per_tooth=0.08,
                material="aluminium",
                max_depth_mm=35.0,
                safe_z_mm=5.0,
                stepdown_mm=1.2,
                stock_allowance_mm=0.05,
                roughing_feed_mm_min=1200.0,
                semi_finishing_feed_mm_min=900.0,
                finishing_feed_mm_min=650.0,
            ),
        ]


settings = Settings()
