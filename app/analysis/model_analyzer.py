from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Feature:
    name: str
    feature_type: str
    area_mm2: float
    depth_mm: float
    complexity: float


@dataclass
class ModelAnalysis:
    model_path: Optional[str]
    volume_mm3: float
    bounding_box_mm: List[float]
    features: List[Feature] = field(default_factory=list)
    machining_zones: List[str] = field(default_factory=list)


class ModelAnalyzer:
    def __init__(self, model_path: Optional[str] = None, powermill_snapshot: Optional[dict] = None) -> None:
        self.model_path = model_path
        self.powermill_snapshot = powermill_snapshot

    def _extract_step_bounds(self, text: str) -> Optional[List[float]]:
        coords = []
        patterns = [
            r"CARTESIAN_POINT\s*\([^\)]*\(\s*([-+0-9.eE,\s]+)\s*\)\s*\)",
            r"\(\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                values = match.group(1) if pattern.startswith("CARTESIAN") else match.groups()
                if pattern.startswith("CARTESIAN"):
                    parts = [float(p.strip()) for p in values.split(",") if p.strip()]
                else:
                    parts = [float(v) for v in values if v is not None]
                if len(parts) == 3:
                    coords.append(tuple(parts))

        if not coords:
            return None

        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        zs = [p[2] for p in coords]
        return [
            max(1.0, max(xs) - min(xs)),
            max(1.0, max(ys) - min(ys)),
            max(1.0, max(zs) - min(zs)),
        ]

    def _read_geometry(self) -> tuple[float, List[float], float, float]:
        model_path = self.model_path
        if not model_path or not Path(model_path).exists():
            return (245000.0, [120.0, 85.0, 30.0], 42000.0, 15.0)

        suffix = Path(model_path).suffix.lower()
        try:
            if suffix in {".step", ".stp", ".iges", ".igs"}:
                text = Path(model_path).read_text(encoding="utf-8", errors="ignore")
                bounds = self._extract_step_bounds(text)
                if bounds is not None:
                    length, width, height = bounds
                    volume = max(length * width * height, 1.0)
                    return (volume, [float(v) for v in bounds], max(length * width, 1.0), max(bounds))

            if suffix in {".stl", ".obj"}:
                try:
                    import trimesh

                    mesh = trimesh.load(model_path, force="scene")
                    if isinstance(mesh, trimesh.Scene):
                        mesh = mesh.dump(concatenate=True)
                    volume = float(mesh.volume)
                    bounds = mesh.bounds
                    extent = (bounds[1] - bounds[0]).tolist()
                    surface_area = float(mesh.area)
                    max_depth = max(extent) if extent else 15.0
                    return (volume, [float(v) for v in extent], surface_area, max_depth)
                except Exception:
                    pass
        except Exception:
            pass

        return (245000.0, [120.0, 85.0, 30.0], 42000.0, 15.0)

    def analyze(self) -> ModelAnalysis:
        if self.powermill_snapshot:
            snapshot = self.powermill_snapshot
            volume_mm3 = float(snapshot.get("volume_mm3", 245000.0))
            bounding_box_mm = [float(v) for v in snapshot.get("bounding_box_mm", [120.0, 85.0, 30.0])]
            surface_area_mm2 = float(snapshot.get("surface_area_mm2", 42000.0))
            max_depth_mm = float(snapshot.get("max_depth_mm", 15.0))
            model_path = snapshot.get("model_name") or self.model_path or "PowerMill_active_model"
        else:
            volume_mm3, bounding_box_mm, surface_area_mm2, max_depth_mm = self._read_geometry()
            model_path = self.model_path or "demo_model.stl"

        features = [
            Feature(
                name="Pocket_01",
                feature_type="pocket",
                area_mm2=max(surface_area_mm2 * 0.45, 12000.0),
                depth_mm=max(max_depth_mm * 0.7, 8.0),
                complexity=0.72,
            ),
            Feature(
                name="Wall_01",
                feature_type="wall",
                area_mm2=max(surface_area_mm2 * 0.35, 18000.0),
                depth_mm=max(max_depth_mm * 0.8, 10.0),
                complexity=0.66,
            ),
            Feature(
                name="Boss_01",
                feature_type="boss",
                area_mm2=max(surface_area_mm2 * 0.2, 7000.0),
                depth_mm=max(max_depth_mm * 0.5, 5.0),
                complexity=0.48,
            ),
        ]

        zones = ["roughing", "semi_finishing", "finishing"]
        if volume_mm3 < 50000:
            zones = ["semi_finishing", "finishing"]

        return ModelAnalysis(
            model_path=model_path,
            volume_mm3=volume_mm3,
            bounding_box_mm=bounding_box_mm,
            features=features,
            machining_zones=zones,
        )
