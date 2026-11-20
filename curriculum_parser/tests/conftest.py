"""
Настройка путей поиска модулей для автономных тестов curriculum_parser.
"""
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
pkg_dir = current_dir.parent
modules_dir = pkg_dir.parent

for p in (str(modules_dir), str(pkg_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)
