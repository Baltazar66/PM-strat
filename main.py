import json
import logging
from pathlib import Path

import flet as ft

from app.analysis.model_analyzer import ModelAnalyzer
from app.config import Settings, ToolConfig
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
            "safe_z_mm": settings.machine.safe_z_mm,
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
                "safe_z_mm": tool.safe_z_mm,
                "stepdown_mm": tool.stepdown_mm,
                "stock_allowance_mm": tool.stock_allowance_mm,
                "roughing_feed_mm_min": tool.roughing_feed_mm_min,
                "semi_finishing_feed_mm_min": tool.semi_finishing_feed_mm_min,
                "finishing_feed_mm_min": tool.finishing_feed_mm_min,
            }
            for tool in settings.tool_library
        ],
    }
    tool_path.parent.mkdir(parents=True, exist_ok=True)
    tool_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_strategy_view(strategies):
    text = []
    summaries = []
    for strategy in strategies:
        model_summary = strategy.parameters.get("model_summary")
        if model_summary:
            summaries.append(
                f"Модель: V={model_summary.get('volume_mm3', 0):.0f} мм³ | "
                f"BBOX={model_summary.get('bounding_box_mm', [0, 0, 0])} | "
                f"Depth={model_summary.get('max_depth_mm', 0):.1f} мм | "
                f"Faces={model_summary.get('face_count', 0)}"
            )

    if summaries:
        text.append("\n".join(summaries[:2]))

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
    model_summary_output = ft.TextField(label="Параметры модели после анализа", multiline=True, min_lines=8, max_lines=10, read_only=True, width=900)
    tool_summary_output = ft.TextField(label="Параметры выбранного инструмента", multiline=True, min_lines=6, max_lines=8, read_only=True, width=900)

    machine_name = ft.TextField(label="Название станка", value=settings.machine.name)
    machine_material = ft.TextField(label="Материал", value=settings.machine.material)
    max_spindle_rpm = ft.TextField(label="Макс. обороты шпинделя", value=str(settings.machine.max_spindle_rpm))
    safe_z = ft.TextField(label="Безопасная высота, мм", value=str(settings.machine.safe_z_mm))

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
                        ft.DataCell(ft.Text(str(tool.plunge_feed_mm_min))),
                        ft.DataCell(ft.Text(str(tool.drilling_feed_mm_min))),
                        ft.DataCell(ft.Text(str(tool.safe_z_mm))),
                        ft.DataCell(ft.Text(str(tool.stepdown_mm))),
                        ft.DataCell(ft.Text(str(tool.stock_allowance_mm))),
                        ft.DataCell(ft.Text(str(tool.roughing_feed_mm_min))),
                        ft.DataCell(ft.Text(str(tool.semi_finishing_feed_mm_min))),
                        ft.DataCell(ft.Text(str(tool.finishing_feed_mm_min))),
                    ]
                )
            )
        tool_table.rows = rows
        tool_dropdown.options = [ft.dropdown.Option(key=tool.name, text=tool.name) for tool in settings.tool_library]
        if settings.tool_library and (tool_dropdown.value is None or tool_dropdown.value not in {tool.name for tool in settings.tool_library}):
            tool_dropdown.value = settings.tool_library[0].name
        page.update()

    def compact_table_header(label: str, width: float) -> ft.DataColumn:
        return ft.DataColumn(
            label=ft.Container(
                content=ft.Text(
                    label,
                    size=10,
                    weight=ft.FontWeight.BOLD,
                    max_lines=2,
                    text_align=ft.TextAlign.CENTER,
                ),
                width=width,
                padding=ft.padding.only(left=4, right=4),
                alignment=ft.alignment.center,
            ),
            tooltip=label,
        )

    tool_table = ft.DataTable(
        columns=[
            compact_table_header("Инструмент", 90),
            compact_table_header("Тип", 70),
            compact_table_header("Ø, мм", 60),
            compact_table_header("Обороты", 80),
            compact_table_header("Резание\nм/мин", 90),
            compact_table_header("Врезание\nмм/мин", 100),
            compact_table_header("Сверление\nмм/мин", 100),
            compact_table_header("Безопасн.\nвысота", 100),
            compact_table_header("Шаг\nврезания", 85),
            compact_table_header("Припуск", 70),
            compact_table_header("Черновая\nподача", 100),
            compact_table_header("Полуфиниш\nподача", 110),
            compact_table_header("Финиш\nподача", 95),
        ],
        rows=[],
        width=1110,
        column_spacing=8,
        heading_row_height=58,
        data_row_max_height=42,
    )

    tool_dropdown = ft.Dropdown(
        label="Редактируемый инструмент",
        options=[ft.dropdown.Option(key=tool.name, text=tool.name) for tool in settings.tool_library],
        value=settings.tool_library[0].name if settings.tool_library else None,
        width=220,
    )
    tool_name_field = ft.TextField(label="Название инструмента", width=220)
    tool_type_field = ft.Dropdown(
        label="Тип инструмента",
        options=[
            ft.dropdown.Option("endmill", "Фреза"),
            ft.dropdown.Option("drill", "Сверло"),
        ],
        width=180,
    )
    tool_diameter = ft.TextField(label="Диаметр, мм", width=140)
    tool_rpm = ft.TextField(label="Обороты", width=140)
    tool_cutting_speed = ft.TextField(label="Скорость резания, м/мин", width=190)
    tool_plunge_feed = ft.TextField(label="Подача врезания, мм/мин", width=190)
    tool_drilling_feed = ft.TextField(label="Подача сверления, мм/мин", width=190)
    tool_safe_z = ft.TextField(label="Безопасная высота, мм", width=150)
    tool_stepdown = ft.TextField(label="Шаг врезания, мм", width=150)
    tool_allowance = ft.TextField(label="Припуск, мм", width=140)
    tool_rough_feed = ft.TextField(label="Черновая подача, мм/мин", width=180)
    tool_semi_feed = ft.TextField(label="Полуфинишная подача, мм/мин", width=200)
    tool_finish_feed = ft.TextField(label="Финишная подача, мм/мин", width=180)

    def load_selected_tool_into_form():
        tool = next((item for item in settings.tool_library if item.name == tool_dropdown.value), None)
        if tool is None:
            return
        tool_name_field.value = tool.name
        tool_type_field.value = tool.tool_type
        tool_diameter.value = str(tool.diameter_mm)
        tool_rpm.value = str(tool.max_rpm)
        tool_cutting_speed.value = str(tool.cutting_speed_m_min)
        tool_plunge_feed.value = str(tool.plunge_feed_mm_min)
        tool_drilling_feed.value = str(tool.drilling_feed_mm_min)
        tool_safe_z.value = str(tool.safe_z_mm)
        tool_stepdown.value = str(tool.stepdown_mm)
        tool_allowance.value = str(tool.stock_allowance_mm)
        tool_rough_feed.value = str(tool.roughing_feed_mm_min if tool.roughing_feed_mm_min is not None else "")
        tool_semi_feed.value = str(tool.semi_finishing_feed_mm_min if tool.semi_finishing_feed_mm_min is not None else "")
        tool_finish_feed.value = str(tool.finishing_feed_mm_min if tool.finishing_feed_mm_min is not None else "")

        tool_summary_output.value = (
            f"Инструмент: {tool.name}\n"
            f"Тип: {tool.tool_type}\n"
            f"Ø: {tool.diameter_mm} мм | Обороты: {tool.max_rpm}\n"
            f"Скорость резания: {tool.cutting_speed_m_min} м/мин | Подача врезания: {tool.plunge_feed_mm_min} мм/мин | Подача сверления: {tool.drilling_feed_mm_min} мм/мин\n"
            f"Безопасная высота: {tool.safe_z_mm} мм | Шаг врезания: {tool.stepdown_mm} мм | Припуск: {tool.stock_allowance_mm} мм\n"
            f"Черновая: {tool.roughing_feed_mm_min} мм/мин | Полуфинишная: {tool.semi_finishing_feed_mm_min} мм/мин | Финишная: {tool.finishing_feed_mm_min} мм/мин"
        )
        page.update()

    def apply_tool_changes(e):
        tool = next((item for item in settings.tool_library if item.name == tool_dropdown.value), None)
        if tool is None:
            return

        tool.name = (tool_name_field.value or tool.name).strip() or tool.name
        tool.tool_type = (tool_type_field.value or tool.tool_type).strip() or tool.tool_type
        tool.diameter_mm = float(tool_diameter.value or tool.diameter_mm)
        tool.max_rpm = int(tool_rpm.value or tool.max_rpm)
        tool.cutting_speed_m_min = float(tool_cutting_speed.value or tool.cutting_speed_m_min)
        tool.plunge_feed_mm_min = float(tool_plunge_feed.value or tool.plunge_feed_mm_min)
        tool.drilling_feed_mm_min = float(tool_drilling_feed.value or tool.drilling_feed_mm_min)
        tool.safe_z_mm = float(tool_safe_z.value or tool.safe_z_mm)
        tool.stepdown_mm = float(tool_stepdown.value or tool.stepdown_mm)
        tool.stock_allowance_mm = float(tool_allowance.value or tool.stock_allowance_mm)
        tool.roughing_feed_mm_min = float(tool_rough_feed.value) if tool_rough_feed.value not in (None, "") else None
        tool.semi_finishing_feed_mm_min = float(tool_semi_feed.value) if tool_semi_feed.value not in (None, "") else None
        tool.finishing_feed_mm_min = float(tool_finish_feed.value) if tool_finish_feed.value not in (None, "") else None

        if tool.name != tool_dropdown.value:
            tool_dropdown.value = tool.name
        save_tool_library_to_disk()
        refresh_tool_table()
        load_selected_tool_into_form()
        page.update()

    def add_new_tool(e):
        new_name = f"Новый_{len(settings.tool_library) + 1}"
        new_tool = ToolConfig(
            name=new_name,
            tool_type="endmill",
            diameter_mm=6.0,
            flute_length_mm=25.0,
            max_rpm=15000,
            cutting_speed_m_min=180.0,
            plunge_feed_mm_min=180.0,
            drilling_feed_mm_min=220.0,
            feed_per_tooth=0.06,
            material=settings.machine.material,
            max_depth_mm=18.0,
            safe_z_mm=settings.machine.safe_z_mm,
            stepdown_mm=2.5,
            stock_allowance_mm=0.3,
            roughing_feed_mm_min=1500.0,
            semi_finishing_feed_mm_min=1200.0,
            finishing_feed_mm_min=900.0,
        )
        settings.tool_library.append(new_tool)
        save_tool_library_to_disk()
        refresh_tool_table()
        tool_dropdown.value = new_tool.name
        load_selected_tool_into_form()
        page.update()

    def delete_selected_tool(e):
        if not settings.tool_library:
            return
        selected_name = tool_dropdown.value
        settings.tool_library = [tool for tool in settings.tool_library if tool.name != selected_name]
        save_tool_library_to_disk()
        refresh_tool_table()
        if settings.tool_library:
            tool_dropdown.value = settings.tool_library[0].name
            load_selected_tool_into_form()
        page.update()

    refresh_tool_table()
    tool_dropdown.on_change = lambda e: load_selected_tool_into_form()
    load_selected_tool_into_form()

    def update_machine_settings_from_form():
        settings.machine.name = machine_name.value.strip() or "Default_3Axis"
        settings.machine.material = machine_material.value.strip() or "aluminium"
        settings.machine.max_spindle_rpm = int(max_spindle_rpm.value or 18000)
        settings.machine.safe_z_mm = float(safe_z.value or 5.0)

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

        model_summary_output.value = (
            f"Модель: {analysis.model_path}\n"
            f"Объём: {analysis.volume_mm3:.0f} мм³\n"
            f"Габариты: {analysis.bounding_box_mm}\n"
            f"Макс. глубина: {analysis.max_depth_mm:.1f} мм\n"
            f"Площадь: {analysis.surface_area_mm2:.0f} мм²\n"
            f"Лиц: {analysis.face_count} | Вершин: {analysis.vertices_count}\n"
            f"Зоны: {', '.join(analysis.machining_zones) if analysis.machining_zones else 'не определены'}"
        )
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

    def panel(title: str, *controls) -> ft.Card:
        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    controls=[ft.Text(title, size=18, weight=ft.FontWeight.BOLD), *list(controls)],
                    spacing=12,
                ),
                padding=16,
                border_radius=12,
                border=ft.border.all(1, ft.colors.OUTLINE_VARIANT),
                bgcolor=ft.colors.WHITE,
            ),
            margin=ft.margin.only(bottom=8),
        )

    content = ft.Column(
        controls=[
            ft.Text("PowerMill Strategy Generator", size=26, weight=ft.FontWeight.BOLD),
            panel(
                "Модель и запуск",
                ft.Row([model_path_field, ft.ElevatedButton("Выбрать модель", on_click=choose_model)], alignment=ft.MainAxisAlignment.START),
                ft.Row([
                    ft.ElevatedButton("Проверить PowerMill", on_click=lambda _: connect_to_powermill()),
                    ft.ElevatedButton("Использовать активную модель", on_click=lambda _: (connect_to_powermill(), analyze_and_generate(None))),
                    ft.ElevatedButton("Анализировать и сформировать стратегии", on_click=analyze_and_generate),
                    ft.ElevatedButton("Сохранить базу инструментов", on_click=lambda _: (update_machine_settings_from_form(), save_tool_library_to_disk(), page.update())),
                ], wrap=True),
                project_status,
            ),
            panel(
                "Настройки станка",
                ft.Row([machine_name, machine_material]),
                ft.Row([max_spindle_rpm, safe_z]),
            ),
            panel(
                "Доступные инструменты",
                ft.Container(
                    content=ft.Column(
                        controls=[tool_table],
                        scroll=ft.ScrollMode.AUTO,
                        height=300,
                    ),
                    width=1120,
                    padding=ft.padding.only(top=4),
                ),
            ),
            panel(
                "Настройки выбранного инструмента",
                ft.Row([tool_dropdown]),
                ft.Row([tool_name_field, tool_type_field]),
                ft.Row([tool_diameter, tool_rpm]),
                ft.Row([tool_cutting_speed, tool_plunge_feed, tool_drilling_feed]),
                ft.Row([tool_safe_z, tool_stepdown, tool_allowance]),
                ft.Row([tool_rough_feed, tool_semi_feed, tool_finish_feed]),
                ft.Row([
                    ft.ElevatedButton("Сохранить параметры инструмента", on_click=apply_tool_changes),
                    ft.OutlinedButton("Добавить инструмент", on_click=add_new_tool),
                    ft.OutlinedButton("Удалить инструмент", on_click=delete_selected_tool),
                ]),
                tool_summary_output,
            ),
            panel(
                "Результаты анализа и стратегии",
                model_summary_output,
                strategy_output,
            ),
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
    )

    page.add(ft.Container(content=content, padding=10, expand=True))

    connect_to_powermill()


if __name__ == "__main__":
    ft.app(target=main)
