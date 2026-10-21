from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Toolpath:
    category: str
    tool_name: str
    strategy_name: str
    waypoints: List[List[float]] = field(default_factory=list)
    feed_rate: float = 0.0
    stepdown_mm: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)


class ToolpathGenerator:
    def __init__(self, settings) -> None:
        self.settings = settings

    def _build_waypoints(self, analysis, strategy, index: int) -> List[List[float]]:
        bounding_box = getattr(analysis, "bounding_box_mm", [120.0, 85.0, 30.0]) or [120.0, 85.0, 30.0]
        max_depth = float(getattr(analysis, "max_depth_mm", max(bounding_box) if bounding_box else 15.0) or 15.0)
        stepdown = float(strategy.parameters.get("stepdown_mm", 2.5))
        safe_z = float(strategy.parameters.get("safe_z_mm", self.settings.machine.safe_z_mm or 5.0))
        x_len, y_len, z_len = bounding_box

        start_z = safe_z
        if strategy.category == "roughing":
            z_values = [start_z, max(1.0, max_depth * 0.65), max_depth]
        elif strategy.category == "semi_finishing":
            z_values = [start_z, max(1.0, max_depth * 0.45), max_depth * 0.8]
        else:
            z_values = [start_z, max_depth * 0.2, max_depth * 0.5]

        points: List[List[float]] = []
        for level in range(3):
            z = min(max(z_values[level], 0.0), max_depth)
            x0 = 0.0
            y0 = 0.0
            x1 = max(1.0, x_len)
            y1 = max(1.0, y_len)
            points.append([x0, y0, z])
            points.append([x1, y0, z])
            points.append([x1, y1, z])
            points.append([x0, y1, z])

        if stepdown > 0:
            points = [
                [x, y, min(max(z + (index * stepdown), 0.0), max_depth)]
                for x, y, z in points
            ]

        return points

    def generate(self, analysis, strategies) -> List[Toolpath]:
        toolpaths: List[Toolpath] = []
        for index, strategy in enumerate(strategies):
            if strategy.category not in {"roughing", "semi_finishing", "finishing", "drilling"}:
                continue
            stepdown = float(strategy.parameters.get("stepdown_mm", 2.5))
            safe_z = float(strategy.parameters.get("safe_z_mm", self.settings.machine.safe_z_mm or 5.0))
            path = Toolpath(
                category=strategy.category,
                tool_name=strategy.tool_name,
                strategy_name=strategy.name,
                waypoints=self._build_waypoints(analysis, strategy, index),
                feed_rate=float(strategy.feed_rate),
                stepdown_mm=stepdown,
                parameters={
                    "model_summary": strategy.parameters.get("model_summary"),
                    "selected_tool_name": strategy.parameters.get("selected_tool_name"),
                    "safe_z_mm": safe_z,
                },
            )
            toolpaths.append(path)
        return toolpaths
