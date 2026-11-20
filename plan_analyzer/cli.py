"""
Консольный интерфейс командной строки (CLI) для Plan Analyzer.
Позволяет запускать веб-интерфейс или выполнять быстрый анализ из терминала.
"""
import sys
import argparse
import webbrowser
import uvicorn

from plan_analyzer.analyzer import PlanAnalyzer
from plan_analyzer.similarity import DisciplineSimilarityEngine
from plan_analyzer.service import PlanService


def run_ui(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True, preload_dir: str = None):
    """Запуск локального веб-сервера с интерфейсом."""
    from plan_analyzer.web.app import app, service

    if preload_dir:
        print(f"Предварительная загрузка планов из: {preload_dir}")
        try:
            loaded = service.load_from_directory(preload_dir)
            print(f"Успешно загружено планов: {len(loaded)}")
        except Exception as e:
            print(f"Предупреждение: не удалось загрузить планы из {preload_dir}: {e}")

    url = f"http://{host}:{port}"
    print(f"\n=======================================================")
    print(f"  Запуск веб-интерфейса Анализатора учебных планов")
    print(f"  Адрес: {url}")
    print(f"=======================================================\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(app, host=host, port=port, log_level="info")


def run_cli_analyze(dir_path: str, min_similarity: float = 0.75):
    """Выполняет быстрый текстовый анализ в терминале."""
    print(f"\n[1/3] Сканирование директории: {dir_path} ...")
    analyzer = PlanAnalyzer()
    loaded = analyzer.load_directory(dir_path)
    print(f"Загружено планов: {len(loaded)}")

    pairs = analyzer.get_all_pairs()
    print(f"\n[2/3] Найдено уникальных пар 'Дисциплина - Кафедра': {len(pairs)}")
    for p in pairs[:10]:
        print(f"  • {p.discipline_title} -> {p.dept_name} (№{p.dept_code}) [{p.plans_count} планов]")
    if len(pairs) > 10:
        print(f"  ... и еще {len(pairs) - 10} пар")

    conflicts = analyzer.find_conflicts()
    print(f"\n[3/3] Выявлено коллизий кафедр: {len(conflicts)}")
    for c in conflicts:
        print(f"\n  [!] ДИСЦИПЛИНА С КОЛЛИЗИЕЙ: {c.discipline_title}")
        for dept_name, occs in c.by_department.items():
            print(f"      - {dept_name}: в {len(occs)} планах ({', '.join(o.plan_name for o in occs[:3])})")

    print("\nДля интерактивного разрешения коллизий и анализа подобия запустите:")
    print("  python -m plan_analyzer ui")


def main():
    parser = argparse.ArgumentParser(description="Анализатор учебных планов и коллизий кафедр")
    subparsers = parser.add_subparsers(dest="command")

    # Команда ui
    ui_parser = subparsers.add_parser("ui", help="Запустить интерактивный локальный веб-интерфейс")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Хост (по умолчанию 127.0.0.1)")
    ui_parser.add_argument("--port", type=int, default=8000, help="Порт (по умолчанию 8000)")
    ui_parser.add_argument("--dir", default=None, help="Путь к директории с планами для предзагрузки")
    ui_parser.add_argument("--no-browser", action="store_true", help="Не открывать браузер автоматически")

    # Команда analyze
    analyze_parser = subparsers.add_parser("analyze", help="Выполнить консольный анализ каталога планов")
    analyze_parser.add_argument("path", help="Путь к директории с планами (.plx, .xml)")
    analyze_parser.add_argument("--min-similarity", type=float, default=0.75, help="Минимальный порог сходства (0.5 - 1.0)")

    args = parser.parse_args()

    if args.command == "ui" or args.command is None:
        run_ui(
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8000),
            open_browser=not getattr(args, "no_browser", False),
            preload_dir=getattr(args, "dir", None),
        )
    elif args.command == "analyze":
        run_cli_analyze(args.path, min_similarity=args.min_similarity)


if __name__ == "__main__":
    main()
