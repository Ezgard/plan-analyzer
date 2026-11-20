"""
Комплексные тесты для библиотеки plan_analyzer:
- парсинг пакета планов
- извлечение пар 'дисциплина-кафедра'
- детекция прямых коллизий
- семантическое подобие и скрытые коллизии
- модификация и сохранение шахтинских файлов
"""
import os
import zipfile
import tempfile
import pytest

from plan_analyzer.analyzer import PlanAnalyzer
from plan_analyzer.similarity import DisciplineSimilarityEngine, clean_for_matching
from plan_analyzer.plx_editor import PLXFileContainer
from plan_analyzer.service import PlanService
from plan_analyzer.models import ChangeRequest


# Демонстрационный XML план 1 (Кафедра 42: Кафедра фундаментальной и прикладной информатики)
DEMO_PLAN_1 = """<?xml version="1.0" encoding="utf-8"?>
<Документ>
    <Титул 
        Код="09.03.03" 
        Имя="Прикладная информатика" 
        Профиль="Искусственный интеллект" 
        УровеньОбразования="бакалавриат" 
        ФормаОбучения="очная" 
        ГодНачалаПодготовки="2025" />
    <СтрокиПлана>
        <Строка Код="101" ТипОбъекта="2" НовИдДисциплины="Б1.О.01" Дисциплина="История России" Кафедра="42" КафедраНазвание="Кафедра фундаментальной и прикладной информатики">
            <Сем Ном="1" Лек="16" Пр="32" СРС="60" ЗЕТ="3" Экз="1" />
        </Строка>
        <Строка Код="102" ТипОбъекта="2" НовИдДисциплины="Б1.О.02" Дисциплина="Высшая математика" Кафедра="42" КафедраНазвание="Кафедра фундаментальной и прикладной информатики">
            <Сем Ном="1" Лек="32" Пр="32" СРС="80" ЗЕТ="4" Экз="1" />
        </Строка>
        <Строка Код="103" ТипОбъекта="2" НовИдДисциплины="Б1.О.03" Дисциплина="Юридические вопросы" Кафедра="10" КафедраНазвание="Кафедра юриспруденции">
            <Сем Ном="2" Лек="16" Пр="16" СРС="40" ЗЕТ="2" Зач="1" />
        </Строка>
    </СтрокиПлана>
</Документ>
"""

# Демонстрационный XML план 2 (Коллизия: Высшая математика читается Кафедрой 15, а Юридические проблемы - Кафедрой 20)
DEMO_PLAN_2 = """<?xml version="1.0" encoding="utf-8"?>
<Документ>
    <Титул 
        Код="01.03.02" 
        Имя="Прикладная математика и информатика" 
        Профиль="Математическое моделирование" 
        УровеньОбразования="бакалавриат" 
        ФормаОбучения="очная" 
        ГодНачалаПодготовки="2025" />
    <СтрокиПлана>
        <Строка Код="201" ТипОбъекта="2" НовИдДисциплины="Б1.О.01" Дисциплина="История России" Кафедра="42" КафедраНазвание="Кафедра фундаментальной и прикладной информатики">
            <Сем Ном="1" Лек="16" Пр="32" СРС="60" ЗЕТ="3" Экз="1" />
        </Строка>
        <Строка Код="202" ТипОбъекта="2" НовИдДисциплины="Б1.О.02" Дисциплина="Высшая математика" Кафедра="15" КафедраНазвание="Кафедра высшей математики">
            <Сем Ном="1" Лек="32" Пр="32" СРС="80" ЗЕТ="4" Экз="1" />
        </Строка>
        <Строка Код="203" ТипОбъекта="2" НовИдДисциплины="Б1.О.03" Дисциплина="Юридические проблемы" Кафедра="20" КафедраНазвание="Кафедра государственного права">
            <Сем Ном="2" Лек="16" Пр="16" СРС="40" ЗЕТ="2" Зач="1" />
        </Строка>
    </СтрокиПлана>
</Документ>
"""


def test_pairs_extraction():
    """Проверка извлечения пар 'дисциплина-кафедра'."""
    analyzer = PlanAnalyzer()
    analyzer.load_plan_bytes(DEMO_PLAN_1.encode("utf-8"), filename="plan1.xml")
    analyzer.load_plan_bytes(DEMO_PLAN_2.encode("utf-8"), filename="plan2.xml")

    pairs = analyzer.get_all_pairs()
    assert len(pairs) > 0

    # История России читается на Кафедре 42 в 2 планах
    hist_pairs = [p for p in pairs if p.discipline_title == "История России"]
    assert len(hist_pairs) == 1
    assert hist_pairs[0].plans_count == 2
    assert hist_pairs[0].dept_code == "42"


def test_conflict_detection():
    """Проверка обнаружения коллизии: Высшая математика привязана к разным кафедрам."""
    analyzer = PlanAnalyzer()
    analyzer.load_plan_bytes(DEMO_PLAN_1.encode("utf-8"), filename="plan1.xml")
    analyzer.load_plan_bytes(DEMO_PLAN_2.encode("utf-8"), filename="plan2.xml")

    conflicts = analyzer.find_conflicts()
    assert len(conflicts) == 1

    c = conflicts[0]
    assert c.discipline_title == "Высшая математика"
    assert len(c.departments) == 2
    assert any("42" in code for code in c.department_codes)
    assert any("15" in code for code in c.department_codes)


def test_similarity_and_hidden_conflict():
    """Проверка поиска подобия (Юридические вопросы vs Юридические проблемы) и скрытой коллизии."""
    analyzer = PlanAnalyzer()
    analyzer.load_plan_bytes(DEMO_PLAN_1.encode("utf-8"), filename="plan1.xml")
    analyzer.load_plan_bytes(DEMO_PLAN_2.encode("utf-8"), filename="plan2.xml")

    engine = DisciplineSimilarityEngine()
    sims = engine.compute_similarity_pairs(
        analyzer.occurrences_by_discipline,
        min_score=0.70,
        use_embeddings=True,
    )

    # Должна быть найдена пара "Юридические вопросы" <-> "Юридические проблемы"
    law_pair = None
    for s in sims:
        titles = {s.discipline_a, s.discipline_b}
        if "Юридические вопросы" in titles and "Юридические проблемы" in titles:
            law_pair = s
            break

    assert law_pair is not None
    assert law_pair.combined_score >= 0.70
    # Кафедры разные (Кафедра юриспруденции vs Кафедра государственного права) -> скрытая коллизия
    assert law_pair.is_hidden_conflict is True


def test_plx_editor_and_backup():
    """Проверка модификации XML/PLX и сохранения бэкапа."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        plan_path = os.path.join(tmp_dir, "test_plan.xml")
        with open(plan_path, "w", encoding="utf-8") as f:
            f.write(DEMO_PLAN_1)

        container = PLXFileContainer(plan_path)
        changes = container.modify_discipline(
            discipline_title="Высшая математика",
            new_dept_code="99",
            new_dept_name="Кафедра математического анализа",
            new_discipline_title="Математический анализ",
        )

        assert len(changes) == 1
        assert changes[0].new_dept_code == "99"
        assert changes[0].new_title == "Математический анализ"

        # Сохранение с бэкапом
        saved = container.save(backup=True)
        assert os.path.exists(saved)
        assert os.path.exists(plan_path + ".bak")

        # Перечитываем и проверяем
        reloaded = PLXFileContainer(saved)
        found = False
        for elem in reloaded.root.iter():
            if elem.get("Дисциплина") == "Математический анализ" and elem.get("Кафедра") == "99":
                found = True
                break
        assert found is True


def test_service_stage_and_apply():
    """Проверка полного цикла сервиса: стейджинг изменений, diff и применение."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        p1 = os.path.join(tmp_dir, "plan1.xml")
        p2 = os.path.join(tmp_dir, "plan2.xml")
        with open(p1, "w", encoding="utf-8") as f:
            f.write(DEMO_PLAN_1)
        with open(p2, "w", encoding="utf-8") as f:
            f.write(DEMO_PLAN_2)

        service = PlanService()
        service.load_from_paths([p1, p2])

        # Коллизия по Высшей математике
        conflicts = service.get_conflicts()
        assert len(conflicts) == 1

        # Закрепляем Высшую математику во всех планах за Кафедрой 15
        diffs = service.stage_change(
            ChangeRequest(
                action_type="change_dept",
                discipline_title="Высшая математика",
                target_dept_code="15",
                target_dept_name="Кафедра высшей математики",
            )
        )
        assert len(diffs) >= 1

        # Применяем в отдельную выходную директорию
        out_dir = os.path.join(tmp_dir, "output")
        resp = service.apply_changes(backup=False, output_dir=out_dir)

        assert resp.success is True
        assert resp.modified_files_count >= 1
        assert os.path.exists(os.path.join(out_dir, "plan1.xml"))

        # Проверяем, что в выходном файле план1 кафедра изменилась на 15
        out_container = PLXFileContainer(os.path.join(out_dir, "plan1.xml"))
        for elem in out_container.root.iter():
            if elem.get("Дисциплина") == "Высшая математика":
                assert elem.get("Кафедра") == "15"


def test_year_and_course_filters():
    """Проверка фильтрации по году набора и курсу обучения."""
    analyzer = PlanAnalyzer()
    analyzer.load_plan_bytes(DEMO_PLAN_1.encode("utf-8"), filename="plan1.xml") # 2025 год

    # Создаем план 2024 года с 3 семестром (2 курс)
    plan_2024 = DEMO_PLAN_2.replace('ГодНачалаПодготовки="2025"', 'ГодНачалаПодготовки="2024"')
    analyzer.load_plan_bytes(plan_2024.encode("utf-8"), filename="plan2.xml")

    # 1. Проверяем доступные годы
    years = analyzer.get_available_years()
    assert "2024" in years and "2025" in years

    # 2. Фильтр пар по 2025 году
    pairs_2025 = analyzer.get_all_pairs(start_year="2025")
    assert all(all(o.start_year == "2025" for o in p.occurrences) for p in pairs_2025)

    # 3. Фильтр пар по 2024 году
    pairs_2024 = analyzer.get_all_pairs(start_year="2024")
    assert all(all(o.start_year == "2024" for o in p.occurrences) for p in pairs_2024)

    # 4. Фильтр по курсу (курс 1 = сем. 1-2)
    pairs_c1 = analyzer.get_all_pairs(course=1)
    assert len(pairs_c1) > 0
    assert all(all((o.semester + 1) // 2 == 1 for o in p.occurrences) for p in pairs_c1)


def test_academic_year_calculation_and_filter():
    """Проверка расчета конкретного учебного года и фильтрации по нему."""
    from plan_analyzer.analyzer import calculate_academic_year

    # Проверка формулы
    assert calculate_academic_year("2025", 1) == "2025/2026"
    assert calculate_academic_year("2025", 2) == "2025/2026"
    assert calculate_academic_year("2025", 3) == "2026/2027"
    assert calculate_academic_year("2025", 4) == "2026/2027"
    assert calculate_academic_year("2024", 3) == "2025/2026"

    analyzer = PlanAnalyzer()
    analyzer.load_plan_bytes(DEMO_PLAN_1.encode("utf-8"), filename="plan1.xml")  # 2025, сем. 1 -> 2025/2026
    plan_2024 = DEMO_PLAN_2.replace('ГодНачалаПодготовки="2025"', 'ГодНачалаПодготовки="2024"')
    analyzer.load_plan_bytes(plan_2024.encode("utf-8"), filename="plan2.xml")

    # Доступные учебные годы
    ay_list = analyzer.get_available_academic_years()
    assert "2025/2026" in ay_list

    # Фильтр по конкретному учебному году
    pairs_ay = analyzer.get_all_pairs(academic_year="2025/2026")
    assert len(pairs_ay) > 0
    for p in pairs_ay:
        for o in p.occurrences:
            assert o.academic_year == "2025/2026"


