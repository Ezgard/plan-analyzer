#!/bin/bash
# Скрипт быстрой публикации репозитория на GitHub
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_DIR"

echo "============================================================"
echo " Публикация Анализатора учебных планов на GitHub"
echo "============================================================"

# Проверяем инициализацию git
if [ ! -d ".git" ]; then
    echo "Инициализация локального Git-репозитория..."
    git init
    git branch -M main
fi

# Проверяем наличие удаленного репозитория origin
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")

if [ -z "$REMOTE_URL" ]; then
    if [ -n "$1" ]; then
        REMOTE_URL="$1"
        git remote add origin "$REMOTE_URL"
        echo "Установлен remote origin: $REMOTE_URL"
    else
        echo ""
        echo "Внимание: удаленный репозиторий GitHub еще не подключен."
        echo "Создайте новый пустой репозиторий на https://github.com/new"
        echo "и введите его адрес (например, https://github.com/username/curriculum-plan-analyzer.git):"
        read -r -p "URL репозитория GitHub: " INPUT_URL
        if [ -z "$INPUT_URL" ]; then
            echo "URL не указан. Завершение работы."
            exit 1
        fi
        git remote add origin "$INPUT_URL"
        REMOTE_URL="$INPUT_URL"
    fi
else
    echo "Текущий remote origin: $REMOTE_URL"
fi

# Проверяем статус и коммитим незакоммиченные файлы
if [ -n "$(git status --porcelain)" ]; then
    echo "Фиксация изменений..."
    git add .
    git commit -m "feat: обновление Анализатора учебных планов и десктопного режима"
fi

echo "Отправка ветки main на GitHub..."
git push -u origin main

echo ""
echo "============================================================"
echo "Репозиторий успешно отправлен на GitHub!"
echo "URL: $REMOTE_URL"
echo "============================================================"
