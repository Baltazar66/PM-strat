from pathlib import Path

from app.analysis.model_analyzer import Feature, ModelAnalysis, ModelAnalyzer
from app.config import Settings, ToolConfig
from app.connectors.powermill_connector import PowerMillConnector
from app.planning.strategy_generator import StrategyGenerator
from app.planning.toolpath_generator import ToolpathGenerator


def test_connection_status_exposes_error_details(monkeypatch):
    class DummySettings:
        simulation_mode = "demo"
        host = "127.0.0.1"
        port = 5000

    monkeypatch.setattr("app.connectors.powermill_connector.win32com", None)
    connector = PowerMillConnector(DummySettings())

    status = connector.get_connection_status()

    assert "connected" in status
    assert "error" in status
    assert isinstance(status["error"], str)


def test_connection_initializes_com_thread(monkeypatch):
    class DummySettings:
        simulation_mode = "demo"
        host = "127.0.0.1"
        port = 5000

    calls = {"co_init": 0, "co_uninit": 0, "order": []}

    class DummyModel:
        Name = "Сборка1"

    class DummyProject:
        Models = [DummyModel()]
        StockModels = []

    class DummyApp:
        Project = DummyProject()

    class DummyWin32Com:
        class client:
            @staticmethod
            def GetActiveObject(prog_id):
                assert prog_id == "PowerMill.Application"
                return DummyApp()

    class DummyPythonCom:
        @staticmethod
        def CoInitialize():
            calls["co_init"] += 1
            calls["order"].append("init")

        @staticmethod
        def CoUninitialize():
            calls["co_uninit"] += 1
            calls["order"].append("uninit")

    monkeypatch.setattr("app.connectors.powermill_connector.win32com", DummyWin32Com())
    monkeypatch.setattr("app.connectors.powermill_connector.pythoncom", DummyPythonCom())

    connector = PowerMillConnector(DummySettings())
    assert connector.connect() is True
    assert connector.project is not None
    assert connector.model is not None
    assert connector.model.Name == "Сборка1"
    assert calls["co_init"] >= 1
    assert calls["co_uninit"] >= 1
    assert calls["order"].index("uninit") > calls["order"].index("init")


def test_settings_loads_default_tools():
    settings = Settings()
    assert len(settings.tool_library) >= 3
    assert any(tool.tool_type == "endmill" for tool in settings.tool_library)
    assert any(tool.tool_type == "drill" for tool in settings.tool_library)


def test_strategy_generator_uses_model_geometry():
    settings = Settings()
    analysis = ModelAnalysis(
        model_path="demo.stl",
        volume_mm3=200000.0,
        bounding_box_mm=[150.0, 90.0, 35.0],
        features=[
            Feature(name="Pocket_01", feature_type="pocket", area_mm2=15000.0, depth_mm=18.0, complexity=0.7),
            Feature(name="Wall_01", feature_type="wall", area_mm2=20000.0, depth_mm=22.0, complexity=0.6),
        ],
        machining_zones=["roughing", "semi_finishing", "finishing"],
        surface_area_mm2=48000.0,
        max_depth_mm=25.0,
        face_count=200,
        vertices_count=400,
        feature_points=[[0.0, 0.0, 0.0], [150.0, 90.0, 35.0]],
    )

    strategies = StrategyGenerator(settings).build_strategies(analysis)

    assert len(strategies) >= 3
    assert all("model_summary" in strategy.parameters for strategy in strategies)
    assert any(strategy.category == "roughing" for strategy in strategies)
    assert any(strategy.category == "finishing" for strategy in strategies)
    assert all(strategy.parameters["model_summary"]["volume_mm3"] > 0 for strategy in strategies)


def test_strategy_generator_chooses_only_from_available_tools():
    settings = Settings()
    settings.tool_library = [
        ToolConfig(name="EM_10", tool_type="endmill", diameter_mm=10.0, flute_length_mm=40.0, max_rpm=12000, cutting_speed_m_min=180.0, plunge_feed_mm_min=180.0, drilling_feed_mm_min=220.0, feed_per_tooth=0.06, material="aluminium", max_depth_mm=30.0),
        ToolConfig(name="EM_6", tool_type="endmill", diameter_mm=6.0, flute_length_mm=25.0, max_rpm=16000, cutting_speed_m_min=180.0, plunge_feed_mm_min=180.0, drilling_feed_mm_min=220.0, feed_per_tooth=0.06, material="aluminium", max_depth_mm=18.0),
        ToolConfig(name="DR_5", tool_type="drill", diameter_mm=5.0, flute_length_mm=40.0, max_rpm=12000, cutting_speed_m_min=90.0, plunge_feed_mm_min=120.0, drilling_feed_mm_min=260.0, feed_per_tooth=0.08, material="aluminium", max_depth_mm=35.0),
    ]

    analysis = ModelAnalysis(
        model_path="small_block.stl",
        volume_mm3=18000.0,
        bounding_box_mm=[18.0, 18.0, 8.0],
        features=[Feature(name="Pocket_01", feature_type="pocket", area_mm2=2000.0, depth_mm=8.0, complexity=0.6)],
        machining_zones=["semi_finishing", "finishing"],
        surface_area_mm2=1500.0,
        max_depth_mm=8.0,
        face_count=30,
        vertices_count=60,
        feature_points=[[0.0, 0.0, 0.0], [10.0, 10.0, 8.0]],
    )

    strategies = StrategyGenerator(settings).build_strategies(analysis)
    roughing = next(s for s in strategies if s.category == "roughing")
    finishing = next(s for s in strategies if s.category == "finishing")

    assert roughing.tool_name == "EM_6"
    assert finishing.tool_name == "EM_6"


def test_toolpath_generator_builds_operations_from_analysis():
    settings = Settings()
    settings.tool_library = [
        ToolConfig(name="EM_6", tool_type="endmill", diameter_mm=6.0, flute_length_mm=25.0, max_rpm=16000, cutting_speed_m_min=180.0, plunge_feed_mm_min=180.0, drilling_feed_mm_min=220.0, feed_per_tooth=0.06, material="aluminium", max_depth_mm=18.0),
        ToolConfig(name="DR_5", tool_type="drill", diameter_mm=5.0, flute_length_mm=40.0, max_rpm=12000, cutting_speed_m_min=90.0, plunge_feed_mm_min=120.0, drilling_feed_mm_min=260.0, feed_per_tooth=0.08, material="aluminium", max_depth_mm=35.0),
    ]

    analysis = ModelAnalysis(
        model_path="sample.step",
        volume_mm3=50000.0,
        bounding_box_mm=[80.0, 60.0, 25.0],
        features=[Feature(name="Pocket_01", feature_type="pocket", area_mm2=4000.0, depth_mm=20.0, complexity=0.8)],
        machining_zones=["roughing", "semi_finishing", "finishing"],
        surface_area_mm2=7000.0,
        max_depth_mm=22.0,
        face_count=120,
        vertices_count=240,
        feature_points=[[0.0, 0.0, 0.0], [80.0, 60.0, 25.0]],
    )
    strategies = StrategyGenerator(settings).build_strategies(analysis)

    toolpaths = ToolpathGenerator(settings).generate(analysis, strategies)

    assert len(toolpaths) >= 3
    assert all(path.category in {"roughing", "semi_finishing", "finishing"} for path in toolpaths)
    assert all(path.waypoints for path in toolpaths)


def test_toolpath_generator_uses_selected_tool_safe_z_and_stepdown():
    settings = Settings()
    settings.tool_library = [
        ToolConfig(
            name="EM_12",
            tool_type="endmill",
            diameter_mm=12.0,
            flute_length_mm=40.0,
            max_rpm=12000,
            cutting_speed_m_min=180.0,
            plunge_feed_mm_min=180.0,
            drilling_feed_mm_min=220.0,
            feed_per_tooth=0.06,
            material="aluminium",
            max_depth_mm=28.0,
            safe_z_mm=12.0,
            stepdown_mm=4.0,
            stock_allowance_mm=0.5,
            roughing_feed_mm_min=1600.0,
            semi_finishing_feed_mm_min=1200.0,
            finishing_feed_mm_min=900.0,
        )
    ]

    analysis = ModelAnalysis(
        model_path="sample_block.step",
        volume_mm3=60000.0,
        bounding_box_mm=[70.0, 50.0, 18.0],
        features=[Feature(name="Pocket_01", feature_type="pocket", area_mm2=3000.0, depth_mm=18.0, complexity=0.75)],
        machining_zones=["roughing", "semi_finishing", "finishing"],
        surface_area_mm2=6000.0,
        max_depth_mm=18.0,
        face_count=80,
        vertices_count=160,
        feature_points=[[0.0, 0.0, 0.0], [70.0, 50.0, 18.0]],
    )

    roughing = next(s for s in StrategyGenerator(settings).build_strategies(analysis) if s.category == "roughing")
    toolpaths = ToolpathGenerator(settings).generate(analysis, [roughing])

    assert len(toolpaths) == 1
    assert toolpaths[0].waypoints[0][2] == roughing.parameters["safe_z_mm"]
    assert toolpaths[0].stepdown_mm == roughing.parameters["stepdown_mm"]


def test_model_analyzer_reads_step_like_coordinates(tmp_path):
    step_path = tmp_path / "sample.step"
    step_path.write_text(
        """
        ISO-10303-21;
        HEADER;
        ENDSEC;
        DATA;
        #1 = CARTESIAN_POINT('',(0.0,0.0,0.0));
        #2 = CARTESIAN_POINT('',(50.0,40.0,20.0));
        #3 = CARTESIAN_POINT('',(10.0,5.0,12.0));
        ENDSEC;
        END-ISO-10303-21;
        """,
        encoding="utf-8",
    )

    analyzer = ModelAnalyzer(str(step_path))
    analysis = analyzer.analyze()

    assert analysis.model_path == str(step_path)
    assert analysis.volume_mm3 > 0
    assert len(analysis.bounding_box_mm) == 3
    assert len(analysis.features) >= 3
    assert analysis.machining_zones


def test_model_analyzer_extracts_real_mesh_geometry(tmp_path):
    stl_path = tmp_path / "cube.stl"
    stl_path.write_text(
        """solid cube
        facet normal 0 0 -1
          outer loop
            vertex 0 0 0
            vertex 10 0 0
            vertex 0 10 0
          endloop
        endfacet
        facet normal 0 0 -1
          outer loop
            vertex 0 10 0
            vertex 10 0 0
            vertex 10 10 0
          endloop
        endfacet
        facet normal 0 0 1
          outer loop
            vertex 0 0 10
            vertex 0 10 10
            vertex 10 0 10
          endloop
        endfacet
        facet normal 0 0 1
          outer loop
            vertex 0 10 10
            vertex 10 10 10
            vertex 10 0 10
          endloop
        endfacet
        facet normal -1 0 0
          outer loop
            vertex 0 0 0
            vertex 0 10 0
            vertex 0 0 10
          endloop
        endfacet
        facet normal -1 0 0
          outer loop
            vertex 0 10 0
            vertex 0 10 10
            vertex 0 0 10
          endloop
        endfacet
        facet normal 1 0 0
          outer loop
            vertex 10 0 0
            vertex 10 0 10
            vertex 10 10 0
          endloop
        endfacet
        facet normal 1 0 0
          outer loop
            vertex 10 10 0
            vertex 10 0 10
            vertex 10 10 10
          endloop
        endfacet
        facet normal 0 -1 0
          outer loop
            vertex 0 0 0
            vertex 10 0 0
            vertex 0 0 10
          endloop
        endfacet
        facet normal 0 -1 0
          outer loop
            vertex 10 0 0
            vertex 10 0 10
            vertex 0 0 10
          endloop
        endfacet
        facet normal 0 1 0
          outer loop
            vertex 0 10 0
            vertex 0 10 10
            vertex 10 10 0
          endloop
        endfacet
        facet normal 0 1 0
          outer loop
            vertex 0 10 10
            vertex 10 10 10
            vertex 10 10 0
          endloop
        endfacet
        endsolid cube
        """,
        encoding="utf-8",
    )

    analysis = ModelAnalyzer(str(stl_path)).analyze()

    assert analysis.model_path == str(stl_path)
    assert analysis.volume_mm3 > 900
    assert analysis.volume_mm3 < 1100
    assert analysis.bounding_box_mm == [10.0, 10.0, 10.0]
    assert analysis.surface_area_mm2 > 0
    assert analysis.face_count >= 6
    assert analysis.vertices_count >= 8
    assert len(analysis.feature_points) >= 2
