import json
import logging
from pathlib import Path

import flet as ft

from app.analysis.model_analyzer import ModelAnalyzer
from app.config import Settings
from app.connectors.powermill_connector import PowerMillConnector
from app.planning.strategy_generator import StrategyGenerator


settings = Settings()
logger = logging.getLogger("powermill_strategy_app")
logger.setLevel(logging.INFO)
if not logger.handlers:
    log_dir = Path(__file__).resolve().parent / "logs"
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


def save_tool_library_to_disk() -> None:
    tool_path = Path(settings.tool_library_path) if settings.tool_library_path else Path(__file__).resolve().parent / "app" / "data" / "tool_library.json"
    payload = {
        "machine": {
            "name": settings.machine.name,
            "material": settings.machine.material,
            "max_spindle_rpm": settings.machine.max_spindle_rpm,
            "cutting_speed_m_min": settings.machine.cutting_speed_m_min,
            "drilling_feed_mm_min": settings.machine.drilling_feed_mm_min,
            "plunge_feed_mm_min": settings.machine.plunge_feed_mm_min,
            "safe_z_mm": settings.machine.safe_z_mm,
            "stepdown_mm": settings.machine.stepdown_mm,
            "stock_allowance_mm": settings.machine.stock_allowance_mm,
        },
        "tools": [
            {
                "name": tool.name,
                "tool_type": tool.tool_type,
                "diameter_mm": tool.diameter_mm,
                "flute_length_mm": tool.flute_length_mm,
                "max_rpm": tool.max_rpm,
                "cutting_speed_m_min": tool.cutting_speed_m_min,
                "plunge_feed_mm_min": tool.plunge_feed_mm_min,
                "drilling_feed_mm_min": tool.drilling_feed_mm_min,
                "feed_per_tooth": tool.feed_per_tooth,
                "material": tool.material,
                "max_depth_mm": tool.max_depth_mm,
            }
            for tool in settings.tool_library
        ],
    }
    tool_path.parent.mkdir(parents=True, exist_ok=True)
    tool_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_strategy_view(strategies):
    text = []
    for index, strategy in enumerate(strategies, start=1):
        text.append(
            f"{index}. {strategy.name} [{strategy.category}]\n"
            f"   Инструмент: {strategy.tool_name}\n"
            f"   Подача: {strategy.feed_rate} мм/мин | Обороты: {strategy.spindle_rpm}\n"
            f"   {strategy.description}\n"
        )
    return "\n".join(text)


def main(page: ft.Page):
    page.title = "PowerMill Strategy Generator"
    page.window.width = 1200
    page.window.height = 860
    page.padding = 20
    page.theme_mode = ft.ThemeMode.LIGHT

    model_path_field = ft.TextField(label="Путь к модели", width=500, value=settings.model_path or "")
    project_status = ft.Text(value="Статус PowerMill: проверка...", size=13)
    strategy_output = ft.TextField(label="Сгенерированный план стратегий", multiline=True, min_lines=14, max_lines=18, read_only=True, width=900)

    machine_name = ft.TextField(label="Название станка", value=settings.machine.name)
    machine_material = ft.TextField(label="Материал", value=settings.machine.material)
    max_spindle_rpm = ft.TextField(label="Макс. обороты шпинделя", value=str(settings.machine.max_spindle_rpm))
    cutting_speed = ft.TextField(label="Скорость резания, м/мин", value=str(settings.machine.cutting_speed_m_min))
    drilling_feed = ft.TextField(label="Подача сверления, мм/мин", value=str(settings.machine.drilling_feed_mm_min))
    plunge_feed = ft.TextField(label="Подача врезания, мм/мин", value=str(settings.machine.plunge_feed_mm_min))
    safe_z = ft.TextField(label="Safe Z, мм", value=str(settings.machine.safe_z_mm))
    stepdown = ft.TextField(label="Шаг врезания, мм", value=str(settings.machine.stepdown_mm))
    stock_allowance = ft.TextField(label="Припуск, мм", value=str(settings.machine.stock_allowance_mm))

    def refresh_tool_table():
        rows = []
        for tool in settings.tool_library:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(tool.name)),
                        ft.DataCell(ft.Text(tool.tool_type)),
                        ft.DataCell(ft.Text(str(tool.diameter_mm))),
                        ft.DataCell(ft.Text(str(tool.max_rpm))),
                        ft.DataCell(ft.Text(str(tool.cutting_speed_m_min))),
                        ft.DataCell(ft.Text(str(tool.drilling_feed_mm_min))),
                        ft.DataCell(ft.Text(str(tool.plunge_feed_mm_min))),
                    ]
                )
            )
        tool_table.rows = rows
        page.update()

    tool_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Инструмент")),
            ft.DataColumn(ft.Text("Тип")),
            ft.DataColumn(ft.Text("Ø мм")),
            ft.DataColumn(ft.Text("RPM")),
            ft.DataColumn(ft.Text("Скорость")),
            ft.DataColumn(ft.Text("Подача сверл.")),
            ft.DataColumn(ft.Text("Подача врез.")),
        ],
        rows=[],
    )
    refresh_tool_table()

    def update_machine_settings_from_form():
        settings.machine.name = machine_name.value.strip() or "Default_3Axis"
        settings.machine.material = machine_material.value.strip() or "aluminium"
        settings.machine.max_spindle_rpm = int(max_spindle_rpm.value or 18000)
        settings.machine.cutting_speed_m_min = float(cutting_speed.value or 180.0)
        settings.machine.drilling_feed_mm_min = float(drilling_feed.value or 220.0)
        settings.machine.plunge_feed_mm_min = float(plunge_feed.value or 180.0)
        settings.machine.safe_z_mm = float(safe_z.value or 5.0)
        settings.machine.stepdown_mm = float(stepdown.value or 2.5)
        settings.machine.stock_allowance_mm = float(stock_allowance.value or 0.3)

    def connect_to_powermill():
        connector = PowerMillConnector(settings)
        status = connector.get_connection_status()
        model_info = connector.get_active_model_summary() if status.get("connected") else {"connected": False, "message": status.get("error") or "No live PowerMill connection"}

        logger.info("PowerMill check result: %s", status)
        if status.get("connected"):
            project_status.value = (
                f"Статус PowerMill: подключено. "
                f"Проект: {status.get('project_name') or 'неизвестен'}; "
                f"Модель: {status.get('model_name') or 'неизвестна'}"
            )
        else:
            project_status.value = (
                "Статус PowerMill: НЕ подключен. "
                f"Причина: {status.get('error') or status.get('status') or 'неизвестна'}"
            )
            logger.error("PowerMill connection failed in GUI: %s", status.get("error") or status.get("status"))

        print(f"PowerMill check -> {status}")
        page.update()
        return status

    def pick_model(e):
        picked = ft.FilePicker()
        page.overlay.append(picked)
        picked.pick_files(allow_multiple=False)

        def on_result(e):
            if picked.files and picked.files[0].path:
                model_path_field.value = picked.files[0].path
                settings.model_path = picked.files[0].path
                page.update()

        picked.on_result = on_result
        page.update()

    def analyze_and_generate(e):
        update_machine_settings_from_form()
        save_tool_library_to_disk()
        settings.model_path = model_path_field.value.strip() or None

        powermill_snapshot = None
        connector = PowerMillConnector(settings)
        if connector.get_connection_status().get("connected"):
            powermill_snapshot = connector.get_active_model_snapshot()
            project_status.value = f"Статус PowerMill: используется активная модель | {powermill_snapshot}"

        model_path = settings.model_path
        analyzer = ModelAnalyzer(model_path=model_path, powermill_snapshot=powermill_snapshot)
        analysis = analyzer.analyze()
        generator = StrategyGenerator(settings)
        strategies = generator.build_strategies(analysis)
        strategy_output.value = build_strategy_view(strategies)
        page.update()

    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)

    def choose_model(e):
        file_picker.pick_files(allow_multiple=False)

    file_picker.on_result = lambda e: (
        setattr(model_path_field, "value", file_picker.files[0].path if file_picker.files else model_path_field.value),
        setattr(settings, "model_path", file_picker.files[0].path if file_picker.files else settings.model_path),
        page.update(),
    )

    content = ft.Column(
        controls=[
            ft.Text("PowerMill Strategy Generator", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([model_path_field, ft.ElevatedButton("Выбрать модель", on_click=choose_model)]),
            ft.Row([
                ft.ElevatedButton("Проверить PowerMill", on_click=lambda _: connect_to_powermill()),
                ft.ElevatedButton("Использовать активную модель", on_click=lambda _: (connect_to_powermill(), analyze_and_generate(None))),
                ft.ElevatedButton("Анализировать и сформировать стратегии", on_click=analyze_and_generate),
                ft.ElevatedButton("Сохранить базу инструментов", on_click=lambda _: (update_machine_settings_from_form(), save_tool_library_to_disk(), page.update())),
            ]),
            project_status,
            ft.Divider(),
            ft.Text("Настройки станка", weight=ft.FontWeight.BOLD),
            ft.Row([machine_name, machine_material]),
            ft.Row([max_spindle_rpm, cutting_speed]),
            ft.Row([drilling_feed, plunge_feed]),
            ft.Row([safe_z, stepdown, stock_allowance]),
            ft.Divider(),
            ft.Text("Доступные инструменты", weight=ft.FontWeight.BOLD),
            tool_table,
            ft.Divider(),
            strategy_output,
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
    )

    page.add(ft.Container(content=content, padding=10, expand=True))

    connect_to_powermill()


if __name__ == "__main__":
    ft.app(target=main)
