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
    surface_area_mm2: float = 0.0
    max_depth_mm: float = 15.0
    face_count: int = 0
    vertices_count: int = 0
    feature_points: List[List[float]] = field(default_factory=list)


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

    def _read_mesh_metrics(self, model_path: str):
        suffix = Path(model_path).suffix.lower()
        default = {
            "volume_mm3": 245000.0,
            "bounding_box_mm": [120.0, 85.0, 30.0],
            "surface_area_mm2": 42000.0,
            "max_depth_mm": 15.0,
            "face_count": 0,
            "vertices_count": 0,
            "feature_points": [[0.0, 0.0, 0.0], [10.0, 10.0, 10.0]],
        }

        try:
            if suffix in {".stl", ".obj", ".off", ".ply", ".3mf"}:
                try:
                    import trimesh

                    mesh = trimesh.load(model_path, force="scene", process=False)
                    if mesh is None:
                        return default
                    if isinstance(mesh, trimesh.Scene):
                        mesh = mesh.to_geometry() if hasattr(mesh, "to_geometry") else mesh.dump(concatenate=True)
                    if mesh is None:
                        return default

                    volume_value = float(abs(getattr(mesh, "volume", 0.0) or 0.0))
                    bounds = mesh.bounds
                    extent = [float(v) for v in (bounds[1] - bounds[0])] if bounds.size else [1.0, 1.0, 1.0]
                    feature_points = []
                    if hasattr(mesh, "vertices") and len(mesh.vertices):
                        sample = mesh.vertices[: min(8, len(mesh.vertices))]
                        feature_points = [[float(x), float(y), float(z)] for x, y, z in sample]
                    if not feature_points:
                        feature_points = [[0.0, 0.0, 0.0], [max(1.0, extent[0]), max(1.0, extent[1]), max(1.0, extent[2])]]

                    return {
                        "volume_mm3": volume_value,
                        "bounding_box_mm": [float(v) for v in extent],
                        "surface_area_mm2": float(mesh.area),
                        "max_depth_mm": max(extent) if extent else 15.0,
                        "face_count": int(len(mesh.faces)) if hasattr(mesh, "faces") else 0,
                        "vertices_count": int(len(mesh.vertices)) if hasattr(mesh, "vertices") else 0,
                        "feature_points": feature_points,
                    }
                except Exception:
                    pass

            if suffix in {".stl", ".obj", ".off", ".ply"}:
                text = Path(model_path).read_text(encoding="utf-8", errors="ignore")
                vertex_matches = re.findall(r"vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", text, flags=re.IGNORECASE)
                if vertex_matches:
                    points = [(float(x), float(y), float(z)) for x, y, z in vertex_matches]
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    zs = [p[2] for p in points]
                    dx = max(xs) - min(xs) if xs else 1.0
                    dy = max(ys) - min(ys) if ys else 1.0
                    dz = max(zs) - min(zs) if zs else 1.0
                    extent = [dx, dy, dz]
                    volume = max(dx * dy * dz, 1.0)
                    surface_area = max(2.0 * (dx * dy + dy * dz + dz * dx), 1.0)
                    return {
                        "volume_mm3": volume,
                        "bounding_box_mm": [max(float(v), 1.0) for v in extent],
                        "surface_area_mm2": surface_area,
                        "max_depth_mm": max(extent) if extent else 15.0,
                        "face_count": max(len(vertex_matches) // 3, 1),
                        "vertices_count": len(points),
                        "feature_points": [[float(x), float(y), float(z)] for x, y, z in points[:8]],
                    }
        except Exception:
            pass

        return default

    def _read_geometry(self) -> tuple[float, List[float], float, float, int, int, List[List[float]]]:
        model_path = self.model_path
        if not model_path or not Path(model_path).exists():
            return (245000.0, [120.0, 85.0, 30.0], 42000.0, 15.0, 128, 256, [[0.0, 0.0, 0.0], [120.0, 85.0, 30.0]])

        suffix = Path(model_path).suffix.lower()
        try:
            if suffix in {".step", ".stp", ".iges", ".igs"}:
                text = Path(model_path).read_text(encoding="utf-8", errors="ignore")
                bounds = self._extract_step_bounds(text)
                if bounds is not None:
                    length, width, height = bounds
                    volume = max(length * width * height, 1.0)
                    surface_area = max(length * width, 1.0)
                    return (volume, [float(v) for v in bounds], surface_area, max(bounds), 0, 0, [[0.0, 0.0, 0.0], [float(length), float(width), float(height)]])

            metrics = self._read_mesh_metrics(model_path)
            return (
                float(metrics["volume_mm3"]),
                [float(v) for v in metrics["bounding_box_mm"]],
                float(metrics["surface_area_mm2"]),
                float(metrics["max_depth_mm"]),
                int(metrics["face_count"]),
                int(metrics["vertices_count"]),
                [[float(v) for v in point] for point in metrics["feature_points"]],
            )
        except Exception:
            pass

        return (245000.0, [120.0, 85.0, 30.0], 42000.0, 15.0, 128, 256, [[0.0, 0.0, 0.0], [120.0, 85.0, 30.0]])

    def analyze(self) -> ModelAnalysis:
        if self.powermill_snapshot:
            snapshot = self.powermill_snapshot
            volume_mm3 = float(snapshot.get("volume_mm3", 245000.0))
            bounding_box_mm = [float(v) for v in snapshot.get("bounding_box_mm", [120.0, 85.0, 30.0])]
            surface_area_mm2 = float(snapshot.get("surface_area_mm2", 42000.0))
            max_depth_mm = float(snapshot.get("max_depth_mm", 15.0))
            face_count = int(snapshot.get("face_count", 128))
            vertices_count = int(snapshot.get("vertices_count", 256))
            feature_points = snapshot.get("feature_points", [[0.0, 0.0, 0.0], [120.0, 85.0, 30.0]])
            model_path = snapshot.get("model_name") or self.model_path or "PowerMill_active_model"
        else:
            volume_mm3, bounding_box_mm, surface_area_mm2, max_depth_mm, face_count, vertices_count, feature_points = self._read_geometry()
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
            surface_area_mm2=surface_area_mm2,
            max_depth_mm=max_depth_mm,
            face_count=face_count,
            vertices_count=vertices_count,
            feature_points=[[float(v) for v in point] for point in feature_points],
        )
