"""
Тесты строгой изоляции и автономности модуля curriculum_parser:
- Проверка AST: 0 импортов из 'backend' или внешних частей монорепозитория;
- Проверка AST: только стандартная библиотека Python (stdlib) и внутрипакетные импорты;
- Проверка выполнения в изолированном процессе Python.
"""
import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path


class TestPackageIsolation(unittest.TestCase):

    def setUp(self):
        self.pkg_dir = Path(__file__).resolve().parent.parent
        self.py_files = [
            f for f in self.pkg_dir.glob("*.py")
            if f.is_file() and not f.name.startswith(".")
        ]

    def test_all_expected_python_files_exist(self):
        file_names = {f.name for f in self.py_files}
        expected = {"__init__.py", "parser.py", "models.py", "exceptions.py", "utils.py"}
        for exp in expected:
            self.assertIn(exp, file_names, f"Файл {exp} должен существовать в пакете curriculum_parser")

    def test_ast_zero_backend_imports(self):
        """Проверяет через абстрактное синтаксическое дерево (AST) отсутствие импортов из 'backend'."""
        for py_path in self.py_files:
            with open(py_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(
                            alias.name.startswith("backend"),
                            f"Запрещенный импорт '{alias.name}' в файле {py_path.name}:{node.lineno}"
                        )
                elif isinstance(node, ast.ImportFrom):
                    mod_name = node.module or ""
                    self.assertFalse(
                        mod_name.startswith("backend"),
                        f"Запрещенный импорт из '{mod_name}' в файле {py_path.name}:{node.lineno}"
                    )

    def test_ast_pure_stdlib_and_internal_imports(self):
        """Проверяет, что все импорты относятся к стандартной библиотеке Python или локальному пакету."""
        # Разрешенные модули stdlib и локальные модули
        stdlib_and_internal = {
            "ast", "collections", "dataclasses", "datetime", "functools", "glob",
            "gzip", "io", "json", "os", "pathlib", "re", "sys",
            "typing", "unittest", "xml", "zipfile",
            "curriculum_parser", "modules"
        }

        for py_path in self.py_files:
            with open(py_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_path))

            for node in ast.walk(tree):
                # Относительные импорты (from . import ...) всегда разрешены
                if isinstance(node, ast.ImportFrom) and node.level > 0:
                    continue

                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_mod = alias.name.split(".")[0]
                        self.assertIn(
                            root_mod,
                            stdlib_and_internal,
                            f"Обнаружен сторонний не-stdlib импорт '{alias.name}' в {py_path.name}:{node.lineno}"
                        )
                elif isinstance(node, ast.ImportFrom):
                    mod_name = node.module or ""
                    root_mod = mod_name.split(".")[0]
                    self.assertIn(
                        root_mod,
                        stdlib_and_internal,
                        f"Обнаружен сторонний не-stdlib импорт '{mod_name}' в {py_path.name}:{node.lineno}"
                    )

    def test_isolated_subprocess_import(self):
        """Проверяет успешный импорт пакета в изолированном дочернем процессе Python."""
        code = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import curriculum_parser\n"
            "assert curriculum_parser.__version__ == '0.1.0'\n"
            "from curriculum_parser import parse_curriculum_plan, PLXParser\n"
            "xml = PLXParser.generate_demo_plx_xml()\n"
            "plan = parse_curriculum_plan(xml, 'test.plx')\n"
            "assert plan.direction_code == '09.03.03'\n"
            "assert plan['direction_code'] == '09.03.03'\n"
            "print('ISOLATED_OK')\n"
        )
        res = subprocess.run(
            [sys.executable, "-c", code, str(self.pkg_dir.parent)],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0, f"Ошибка в изолированном процессе: {res.stderr}")
        self.assertIn("ISOLATED_OK", res.stdout)


if __name__ == "__main__":
    unittest.main()
