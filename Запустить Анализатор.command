#!/bin/bash
# Запуск Анализатора учебных планов на macOS в 1 клик
cd "$(dirname "$0")"

if [ -f ".venv/bin/python" ]; then
    PYTHON_EXEC=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_EXEC="python3"
else
    echo "Ошибка: Python 3 не найден в системе."
    exit 1
fi

"$PYTHON_EXEC" run_desktop.py
