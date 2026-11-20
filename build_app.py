#!/usr/bin/env python3
"""Скрипт автономной сборки десктопного standalone-приложения через PyInstaller."""

import os
import platform
import subprocess
import sys


def build():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sep = os.pathsep

    # Формируем флаги --add-data с учетом платформенного разделителя (macOS/Linux: :, Windows: ;)
    data_args = [
        f"--add-data={os.path.join(base_dir, 'plan_analyzer', 'web', 'templates')}{sep}{os.path.join('plan_analyzer', 'web', 'templates')}",
        f"--add-data={os.path.join(base_dir, 'plan_analyzer', 'web', 'static')}{sep}{os.path.join('plan_analyzer', 'web', 'static')}",
        f"--add-data={os.path.join(base_dir, 'demo_plans')}{sep}demo_plans",
        f"--add-data={os.path.join(base_dir, 'data')}{sep}data",
    ]

    hidden_imports = [
        "--hidden-import=uvicorn",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        "--hidden-import=webview",
        "--hidden-import=jinja2",
        "--hidden-import=openpyxl",
        "--hidden-import=pydantic",
    ]

    app_name = "PlanAnalyzer"
    entry_script = os.path.join(base_dir, "run_desktop.py")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        app_name,
        "--onedir",
        "--windowed",
        *data_args,
        *hidden_imports,
        entry_script,
    ]

    print(f"Запуск сборки десктопного приложения на платформе: {platform.system()} ({platform.machine()})...")
    print("Команда:", " ".join(cmd))

    result = subprocess.run(cmd, cwd=base_dir)
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("Сборка успешно завершена!")
        if platform.system() == "Darwin":
            print(f"Готовое macOS приложение: {os.path.join(base_dir, 'dist', f'{app_name}.app')}")
        else:
            print(f"Исполняемые файлы в каталоге: {os.path.join(base_dir, 'dist', app_name)}")
        print("=" * 60)
    else:
        print("\nОшибка при сборке через PyInstaller!", file=sys.stderr)
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
