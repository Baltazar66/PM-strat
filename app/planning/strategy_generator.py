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
        tools = self.settings.tool_library or []
        for tool in tools:
            if tool.tool_type == preferred_type:
                return tool
        for tool in tools:
            if tool.tool_type in {"endmill", "drill"}:
                return tool
        if tools:
            return tools[0]
        raise ValueError("No tools available in the current project tool library")

    def _build_model_summary(self, analysis) -> Dict[str, object]:
        bounding_box = list(getattr(analysis, "bounding_box_mm", [120.0, 85.0, 30.0]) or [120.0, 85.0, 30.0])
        max_depth = float(getattr(analysis, "max_depth_mm", max(bounding_box) if bounding_box else 15.0))
        volume = float(getattr(analysis, "volume_mm3", 0.0) or 0.0)
        surface_area = float(getattr(analysis, "surface_area_mm2", max(volume / 3.0, 1.0)) or 1.0)
        faces = int(getattr(analysis, "face_count", 0) or 0)
        vertices = int(getattr(analysis, "vertices_count", 0) or 0)

        return {
            "volume_mm3": volume,
            "bounding_box_mm": [float(v) for v in bounding_box],
            "surface_area_mm2": surface_area,
            "max_depth_mm": max_depth,
            "face_count": faces,
            "vertices_count": vertices,
            "machining_zones": list(getattr(analysis, "machining_zones", []) or []),
            "feature_count": len(getattr(analysis, "features", []) or []),
        }

    def _scale_by_model(self, analysis, base_value: float, scale: float = 1.0) -> float:
        volume = max(float(getattr(analysis, "volume_mm3", 0.0) or 0.0), 1.0)
        max_depth = max(float(getattr(analysis, "max_depth_mm", 15.0) or 15.0), 1.0)
        model_factor = (volume / 80000.0) ** 0.5
        depth_factor = max(0.6, min(1.8, max_depth / 20.0))
        return max(1.0, base_value * model_factor * depth_factor * scale)

    def _select_tool_for_operation(self, analysis, operation: str):
        bbox = getattr(analysis, "bounding_box_mm", [120.0, 85.0, 30.0]) or [120.0, 85.0, 30.0]
        max_depth = float(getattr(analysis, "max_depth_mm", max(bbox) if bbox else 15.0))
        candidate_tools = list(self.settings.tool_library or [])
        if not candidate_tools:
            raise ValueError("No tools available in the current project tool library")

        def score(tool):
            tool_type = tool.tool_type.lower()
            if operation == "drilling":
                if tool_type != "drill":
                    return -9999
                depth_match = max(0.0, tool.max_depth_mm - max_depth)
                diameter_penalty = abs(tool.diameter_mm - min(max(3.0, max(bbox) / 6.0), 12.0)) * 12.0
                return 2000.0 - depth_match * 2.0 - diameter_penalty

            if tool_type != "endmill":
                return -9999
            if operation == "roughing":
                target_diameter = min(max(3.0, max(bbox) / 4.0), 8.0)
                diameter_penalty = abs(tool.diameter_mm - target_diameter) * 18.0
                depth_match = max(0.0, min(tool.max_depth_mm, max_depth) - max_depth * 0.5)
                return 600.0 - diameter_penalty + depth_match * 0.5

            if operation == "semi_finishing":
                target_diameter = min(max(2.5, max(bbox) / 6.0), 8.0)
                diameter_penalty = abs(tool.diameter_mm - target_diameter) * 20.0
                depth_match = max(0.0, min(tool.max_depth_mm, max_depth) - max_depth * 0.45)
                return 520.0 - diameter_penalty + depth_match * 0.6

            target_diameter = min(max(2.0, max(bbox) / 8.0), 6.0)
            diameter_penalty = abs(tool.diameter_mm - target_diameter) * 22.0
            depth_match = max(0.0, min(tool.max_depth_mm, max_depth) - max_depth * 0.4)
            return 500.0 - diameter_penalty + depth_match * 0.5

        ranked = sorted(candidate_tools, key=score, reverse=True)
        return ranked[0]

    def build_strategies(self, analysis) -> List[Strategy]:
        roughing_tool = self._select_tool_for_operation(analysis, "roughing")
        semi_tool = self._select_tool_for_operation(analysis, "semi_finishing")
        finishing_tool = self._select_tool_for_operation(analysis, "finishing")
        drilling_tool = self._select_tool_for_operation(analysis, "drilling") if any(feature.feature_type in {"hole", "drill"} for feature in (getattr(analysis, "features", []) or [])) else None
        model_summary = self._build_model_summary(analysis)

        rough_stepdown = roughing_tool.get_operation_stepdown("roughing", 2.5)
        semi_stepdown = semi_tool.get_operation_stepdown("semi_finishing", 2.5)
        finishing_allowance = finishing_tool.get_operation_allowance("finishing", 0.3)
        rough_stock_allowance = roughing_tool.get_operation_allowance("roughing", 0.3)
        rough_safe_z = roughing_tool.safe_z_mm if roughing_tool.safe_z_mm and roughing_tool.safe_z_mm > 0 else self.settings.machine.safe_z_mm

        roughing_feed = self._scale_by_model(analysis, roughing_tool.get_operation_feed("roughing", max(900.0, roughing_tool.feed_rate_mm_min * 1.8)), 0.9)
        semi_feed = self._scale_by_model(analysis, semi_tool.get_operation_feed("semi_finishing", max(700.0, semi_tool.feed_rate_mm_min * 1.3)), 0.8)
        finishing_feed = self._scale_by_model(analysis, finishing_tool.get_operation_feed("finishing", max(500.0, finishing_tool.feed_rate_mm_min * 0.9)), 0.7)

        strategies = [
            Strategy(
                name="Roughing_Adaptive",
                category="roughing",
                feed_rate=round(roughing_feed, 1),
                spindle_rpm=roughing_tool.max_rpm,
                tool_name=roughing_tool.name,
                description=f"Локальная черновая обработка по карманам и стенкам для модели объёмом {model_summary['volume_mm3']:.0f} мм³ с глубиной до {model_summary['max_depth_mm']:.1f} мм. Используется доступный инструмент {roughing_tool.name}.",
                parameters={
                    "stepdown_mm": round(rough_stepdown, 2),
                    "stock_allowance_mm": round(rough_stock_allowance, 3),
                    "safe_z_mm": round(rough_safe_z, 2),
                    "model_summary": model_summary,
                    "selected_tool_name": roughing_tool.name,
                    "target_zones": ["roughing"],
                },
            ),
            Strategy(
                name="SemiFinishing_Parallel",
                category="semi_finishing",
                feed_rate=round(semi_feed, 1),
                spindle_rpm=semi_tool.max_rpm,
                tool_name=semi_tool.name,
                description=f"Полуфинишная обработка локальными проходами по поверхности модели с габаритом {model_summary['bounding_box_mm']} мм. Используется доступный инструмент {semi_tool.name}.",
                parameters={
                    "stepdown_mm": round(semi_stepdown, 2),
                    "stock_allowance_mm": round(semi_tool.get_operation_allowance("semi_finishing", 0.15), 3),
                    "safe_z_mm": round(semi_tool.safe_z_mm if semi_tool.safe_z_mm and semi_tool.safe_z_mm > 0 else self.settings.machine.safe_z_mm, 2),
                    "model_summary": model_summary,
                    "selected_tool_name": semi_tool.name,
                    "target_zones": ["semi_finishing"],
                },
            ),
            Strategy(
                name="Finishing_Contour",
                category="finishing",
                feed_rate=round(finishing_feed, 1),
                spindle_rpm=finishing_tool.max_rpm,
                tool_name=finishing_tool.name,
                description=f"Финишная контурная стратегия по оставшемуся припуску. Используется доступный инструмент {finishing_tool.name}.",
                parameters={
                    "toolpath": "contour",
                    "allowance_mm": round(finishing_allowance, 3),
                    "safe_z_mm": round(finishing_tool.safe_z_mm if finishing_tool.safe_z_mm and finishing_tool.safe_z_mm > 0 else self.settings.machine.safe_z_mm, 2),
                    "model_summary": model_summary,
                    "selected_tool_name": finishing_tool.name,
                    "target_zones": ["finishing"],
                },
            ),
        ]

        if drilling_tool is not None:
            strategies.append(
                Strategy(
                    name="Drilling_Sequence",
                    category="drilling",
                    feed_rate=float(drilling_tool.drilling_feed_mm_min),
                    spindle_rpm=drilling_tool.max_rpm,
                    tool_name=drilling_tool.name,
                    description=f"Сверление по отверстиям и посадочным зонам с учётом доступного инструмента {drilling_tool.name}.",
                    parameters={
                        "drill_diameter_mm": drilling_tool.diameter_mm,
                        "pecking_enabled": True,
                        "feed_mm_min": drilling_tool.drilling_feed_mm_min,
                        "model_summary": model_summary,
                        "selected_tool_name": drilling_tool.name,
                        "safe_z_mm": round(drilling_tool.safe_z_mm if drilling_tool.safe_z_mm and drilling_tool.safe_z_mm > 0 else self.settings.machine.safe_z_mm, 2),
                    },
                )
            )

        return strategies
