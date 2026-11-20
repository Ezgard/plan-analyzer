#!/usr/bin/env python3
"""Точка входа для десктопного запуска Анализатора учебных планов."""

import os
import sys

# Обеспечиваем доступность корневой директории в sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from plan_analyzer.desktop import main

if __name__ == "__main__":
    main()
