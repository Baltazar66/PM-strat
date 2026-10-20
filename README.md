# PowerMill Strategy Generator

Это новый проект для автоматизации создания стратегий обработки в Autodesk PowerMill Ultimate 2024.

## Что делает приложение

- подключается к PowerMill через безопасный мост/COM/.NET
- анализирует 3D-модель (STL/STEP/IGES/3MF)
- оценивает геометрию, объём удаления, карманы, наружные/внутренние контуры
- строит набор стратегий обработки на основе параметров инструмента и настроек
- формирует команды/скрипты для симуляции и постпроцессинга PowerMill
- поддерживает режим демонстрации без PowerMill для разработки и тестов

## Важный момент по подключению

PowerMill не имеет "прямого" REST API, как обычный веб-сервис. Для интеграции в Python обычно используется один из вариантов:

1. PowerMill Automation / COM API на Windows
2. кастомный .NET плагин/макрос, который обменивается данными с Python через локальный HTTP/IPC
3. мост через PowerMill VBA/CLI/SDK и скрипты, исполняемые внутри PowerMill

Поэтому в этом проекте реализован архитектурный мост:

- Python-оркестратор в этом репозитории
- PowerMill connector через .NET/COM bridge
- сам PowerMill запускает и принимает команды через локальный сервис

## Структура проекта

- app/config.py — параметры проекта и настроек
- app/connectors/powermill_connector.py — мост подключения к PowerMill
- app/analysis/model_analyzer.py — анализ геометрии модели
- app/planning/strategy_generator.py — генерация стратегий
- app/simulation/powermill_runner.py — подготовка симуляции и постпроцессинга
- main.py — точка входа

## Быстрый старт

```bash
cd powermill_strategy_app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Настройки

Отредактируйте файл `.env` или задайте переменные окружения:

```env
POWERMILL_HOST=127.0.0.1
POWERMILL_PORT=5000
POWERMILL_TIMEOUT=30
SIMULATION_MODE=demo
MODEL_PATH=
TOOL_LIBRARY_PATH=
```

## Ограничения

Для реального запуска в PowerMill требуется:

- установлен Autodesk PowerMill Ultimate 2024
- Windows, потому что PowerMill использует Windows-совместимый API/COM
- пользователь/доступ к PowerMill API
- .NET bridge или PowerMill plugin для запуска команд извне

## Следующий шаг

После установки окружения нужно:

1. подключить реальный PowerMill bridge
2. добавить импорт STL/STEP/IGES моделeй
3. связать генерацию стратегий с конкретным набором инструментов
4. проверить симуляцию и постпроцессинг в самой PowerMill
