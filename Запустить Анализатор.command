#!/bin/bash
# Запуск Анализатора учебных планов на macOS в 1 клик
cd "$(dirname "$0")"

echo "============================================================"
echo " Запуск Анализатора учебных планов..."
echo "============================================================"

if [ -f ".venv/bin/python" ]; then
    PYTHON_EXEC=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_EXEC="python3"
else
    echo "Ошибка: Python не найден в системе."
    echo "Установите зависимости командой: uv pip install -e ."
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

"$PYTHON_EXEC" run_desktop.py
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "Приложение завершилось с кодом ошибки $EXIT_CODE."
    read -p "Нажмите Enter для выхода..."
fi
