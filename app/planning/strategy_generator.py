from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Strategy:
    name: str
    category: str
    feed_rate: float
    spindle_rpm: int
    tool_name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


class StrategyGenerator:
    def __init__(self, settings) -> None:
        self.settings = settings

    def _pick_tool(self, preferred_type: str):
        tools = self.settings.tool_library
        for tool in tools:
            if tool.tool_type == preferred_type:
                return tool
        for tool in tools:
            if tool.tool_type in {"endmill", "drill"}:
                return tool
        return tools[0]

    def build_strategies(self, analysis) -> List[Strategy]:
        endmill = self._pick_tool("endmill")
        drill = self._pick_tool("drill")

        roughing_feed = max(900.0, min(endmill.feed_rate_mm_min * 1.8, 3000.0))
        semi_feed = max(700.0, min(endmill.feed_rate_mm_min * 1.3, 2200.0))
        finishing_feed = max(500.0, min(endmill.feed_rate_mm_min * 0.9, 1800.0))

        strategies = [
            Strategy(
                name="Roughing_Adaptive",
                category="roughing",
                feed_rate=round(roughing_feed, 1),
                spindle_rpm=endmill.max_rpm,
                tool_name=endmill.name,
                description="Локальная черновая обработка: удаление основного объёма по карманам и зонам с запасом материала.",
                parameters={
                    "stepdown_mm": self.settings.machine.stepdown_mm,
                    "stock_allowance_mm": self.settings.machine.stock_allowance_mm,
                    "safe_z_mm": self.settings.machine.safe_z_mm,
                },
            ),
            Strategy(
                name="SemiFinishing_Parallel",
                category="semi_finishing",
                feed_rate=round(semi_feed, 1),
                spindle_rpm=endmill.max_rpm,
                tool_name=endmill.name,
                description="Полуфинишная обработка локальными проходами по стенкам и поверхностям.",
                parameters={
                    "stepdown_mm": self.settings.machine.stepdown_mm / 2,
                    "stock_allowance_mm": 0.15,
                },
            ),
            Strategy(
                name="Finishing_Contour",
                category="finishing",
                feed_rate=round(finishing_feed, 1),
                spindle_rpm=endmill.max_rpm,
                tool_name=endmill.name,
                description="Финишная контурная стратегия с точным снятием оставшегося припуска.",
                parameters={
                    "toolpath": "contour",
                    "allowance_mm": 0.05,
                },
            ),
        ]

        if any(feature.feature_type == "hole" for feature in analysis.features):
            strategies.append(
                Strategy(
                    name="Drilling_Sequence",
                    category="drilling",
                    feed_rate=float(drill.drilling_feed_mm_min),
                    spindle_rpm=drill.max_rpm,
                    tool_name=drill.name,
                    description="Сверление по отверстиям и посадочным зонам с учётом параметров подачи и врезания для текущего станка.",
                    parameters={
                        "drill_diameter_mm": drill.diameter_mm,
                        "pecking_enabled": True,
                        "feed_mm_min": drill.drilling_feed_mm_min,
                    },
                )
            )

        return strategies
