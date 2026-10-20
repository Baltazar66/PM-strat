from pathlib import Path

from app.analysis.model_analyzer import ModelAnalyzer
from app.config import Settings
from app.connectors.powermill_connector import PowerMillConnector


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


def test_settings_loads_default_tools():
    settings = Settings()
    assert len(settings.tool_library) >= 3
    assert any(tool.tool_type == "endmill" for tool in settings.tool_library)
    assert any(tool.tool_type == "drill" for tool in settings.tool_library)


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
