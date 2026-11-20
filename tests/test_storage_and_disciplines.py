"""
Тесты функционала 'Дисциплина как единица анализа',
справочников преподавателей, отраслей и импорта/экспорта.
"""
import io
import os
import tempfile
import openpyxl
import pytest
from fastapi.testclient import TestClient

from plan_analyzer.models import DisciplineProfile, Teacher, Industry
from plan_analyzer.storage import RegistryStorage
from plan_analyzer.service import PlanService
from plan_analyzer.web.app import app
from tests.test_plan_analyzer import DEMO_PLAN_1, DEMO_PLAN_2


def test_storage_teachers_and_industries():
    """Проверка ручного управления преподавателями и отраслями."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        store_path = os.path.join(tmp_dir, "test_store.json")
        storage = RegistryStorage(storage_path=store_path)

        # 1. Добавление преподавателя
        t1 = storage.add_teacher("Иванов Иван Иванович", "Кафедра ВМ", "Доцент")
        assert t1.id is not None
        assert t1.name == "Иванов Иван Иванович"
        assert len(storage.get_teachers()) == 1

        # 2. Добавление отрасли
        ind = storage.add_industry("Информационная безопасность", "Защита данных")
        assert ind.name == "Информационная безопасность"
        assert any(i.name == "Информационная безопасность" for i in storage.get_industries())

        # 3. Привязка к дисциплине
        storage.set_discipline_binding("Криптография", industry="Информационная безопасность", teacher_ids=[t1.id])
        assigned_ind, assigned_teachers = storage.get_discipline_binding("Криптография")
        assert assigned_ind == "Информационная безопасность"
        assert len(assigned_teachers) == 1
        assert assigned_teachers[0].name == "Иванов Иван Иванович"

        # 4. Проверка персистентности (перезагрузка из файла)
        reloaded = RegistryStorage(storage_path=store_path)
        assert len(reloaded.get_teachers()) == 1
        r_ind, r_teachers = reloaded.get_discipline_binding("Криптография")
        assert r_ind == "Информационная безопасность"
        assert len(r_teachers) == 1

        # 5. Удаление преподавателя
        storage.delete_teacher(t1.id)
        assert len(storage.get_teachers()) == 0
        _, after_del_teachers = storage.get_discipline_binding("Криптография")
        assert len(after_del_teachers) == 0


def test_import_and_export_excel():
    """Проверка импорта преподавателей из Excel и экспорта реестра."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        store_path = os.path.join(tmp_dir, "test_store.json")
        storage = RegistryStorage(storage_path=store_path)

        # Создаем тестовый Excel файл преподавателей
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["ФИО", "Кафедра", "Должность"])
        ws.append(["Петров Петр Петрович", "Кафедра ИТ", "Профессор"])
        ws.append(["Сидорова Анна Сергеевна", "Кафедра ИТ", "Старший преподаватель"])
        buf = io.BytesIO()
        wb.save(buf)

        count = storage.import_teachers_file(buf.getvalue(), "teachers.xlsx")
        assert count == 2
        assert len(storage.get_teachers()) == 2

        # Проверка экспорта в Excel
        profiles = [
            DisciplineProfile(
                title="Базы данных",
                normalized_title="базы данных",
                industry="Информационные технологии",
                teachers=storage.get_teachers(),
                departments=["Кафедра ИТ"],
                plans_count=2,
                has_conflict=False,
                total_hours=108,
                total_ze=3,
                semesters=[3],
            )
        ]
        excel_bytes = storage.export_to_excel(profiles)
        assert len(excel_bytes) > 0

        # Читаем созданный Excel и проверяем листы
        wb_out = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        assert "Реестр дисциплин" in wb_out.sheetnames
        assert "Преподаватели" in wb_out.sheetnames
        assert "Отрасли" in wb_out.sheetnames


def test_discipline_profiles_api():
    """Проверка REST API для каталога дисциплин и привязок."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        client = TestClient(app)
        client.post("/api/clear-plans")

        # 1. Загрузка плана
        files = [("files", ("plan.xml", io.BytesIO(DEMO_PLAN_1.encode("utf-8")), "text/xml"))]
        client.post("/api/upload-files?append=true", files=files)

        # 2. Получение списка дисциплин
        res = client.get("/api/disciplines")
        assert res.status_code == 200
        disciplines = res.json()
        assert len(disciplines) >= 3

        # 3. Добавление преподавателя через API
        res_t = client.post(
            "/api/teachers",
            json={"name": "Кузнецов А.А.", "department": "Кафедра ВМ", "position": "Доцент"},
        )
        assert res_t.status_code == 200
        teacher = res_t.json()

        # 4. Привязка к дисциплине 'Высшая математика'
        res_bind = client.post(
            "/api/disciplines/bind",
            json={
                "discipline_title": "Высшая математика",
                "industry": "Математика и механика",
                "teacher_ids": [teacher["id"]],
            },
        )
        assert res_bind.status_code == 200
        assert res_bind.json()["success"] is True

        # 5. Проверка, что фильтр по отрасли возвращает привязанную дисциплину
        res_filtered = client.get("/api/disciplines?industry=Математика и механика")
        assert res_filtered.status_code == 200
        filtered_discs = res_filtered.json()
        assert len(filtered_discs) == 1
        assert filtered_discs[0]["title"] == "Высшая математика"
        assert filtered_discs[0]["industry"] == "Математика и механика"
        assert len(filtered_discs[0]["teachers"]) == 1

        # 6. Проверка скачивания Excel
        res_export = client.get("/api/export/excel")
        assert res_export.status_code == 200
        assert "application/vnd.openxmlformats" in res_export.headers["content-type"]


def test_discipline_profile_credit_calculation():
    """Проверка корректности расчета ЗЕТ и часов дисциплины (не суммирование по планам в объем дисциплины)."""
    service = PlanService()
    service.load_from_directory("demo_plans")
    discs = {d.title: d for d in service.get_discipline_profiles()}

    # 'История России' читается в 2 планах (по 3 ЗЕТ каждый)
    hist = discs["История России"]
    assert hist.plans_count == 2
    assert hist.total_ze == 3  # Объем дисциплины 3 ЗЕТ, а не 6!
    assert hist.total_hours == 108  # Объем дисциплины 108 ч, а не 216!
    assert hist.ze_display == "3"
    assert hist.hours_display == "108"
    assert hist.sum_ze == 6  # Суммарная нагрузка по обоим планам
    assert hist.sum_hours == 216

    # 'Высшая математика' читается в 2 планах (по 4 ЗЕТ каждый)
    math_disc = discs["Высшая математика"]
    assert math_disc.plans_count == 2
    assert math_disc.total_ze == 4  # 4 ЗЕТ, а не 8!
    assert math_disc.total_hours == 144
    assert math_disc.ze_display == "4"
    assert math_disc.sum_ze == 8
    assert math_disc.sum_hours == 288

