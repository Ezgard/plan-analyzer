"""
Тесты для комплексного анализа форм контроля учебных планов:
- Межплановые коллизии форм контроля по одинаковым дисциплинам (экзамен vs зачет)
- Нормативный аудит семестровой нагрузки (лимиты экзаменов, зачетов, курсовых в сессию)
- Интеграция с профилем дисциплины и REST API
"""
import pytest
from plan_analyzer.analyzer import PlanAnalyzer
from plan_analyzer.service import PlanService
from fastapi.testclient import TestClient
from plan_analyzer.web.app import app


DEMO_PLAN_EXAM = """<?xml version="1.0" encoding="utf-8"?>
<Документ>
    <Титул Код="09.03.03" Имя="Прикладная информатика" ГодНачалаПодготовки="2025" />
    <СтрокиПлана>
        <Строка НовИдДисциплины="Б1.О.01" Дисциплина="История России" Кафедра="42" КафедраНазвание="Кафедра информатики">
            <Сем Ном="1" Лек="16" Пр="32" СРС="60" ЗЕТ="3" Экз="1" />
        </Строка>
        <Строка НовИдДисциплины="Б1.О.02" Дисциплина="Высшая математика" Кафедра="42" КафедраНазвание="Кафедра информатики">
            <Сем Ном="1" Лек="32" Пр="32" СРС="80" ЗЕТ="4" Экз="1" />
        </Строка>
    </СтрокиПлана>
</Документ>
"""

DEMO_PLAN_PASS = """<?xml version="1.0" encoding="utf-8"?>
<Документ>
    <Титул Код="01.03.02" Имя="Прикладная математика" ГодНачалаПодготовки="2025" />
    <СтрокиПлана>
        <!-- По Истории России здесь ЗАЧЕТ вместо Экзамена -> Коллизия форм контроля! -->
        <Строка НовИдДисциплины="Б1.О.01" Дисциплина="История России" Кафедра="42" КафедраНазвание="Кафедра информатики">
            <Сем Ном="1" Лек="16" Пр="32" СРС="60" ЗЕТ="3" Зач="1" />
        </Строка>
        <!-- По Высшей математике здесь Экзамен -> Совпадает -->
        <Строка НовИдДисциплины="Б1.О.02" Дисциплина="Высшая математика" Кафедра="42" КафедраНазвание="Кафедра информатики">
            <Сем Ном="1" Лек="32" Пр="32" СРС="80" ЗЕТ="4" Экз="1" />
        </Строка>
    </СтрокиПлана>
</Документ>
"""

# План с перегрузкой семестра 1 (6 экзаменов при норме не более 5)
DEMO_PLAN_OVERLOADED = """<?xml version="1.0" encoding="utf-8"?>
<Документ>
    <Титул Код="10.05.01" Имя="Компьютерная безопасность" ГодНачалаПодготовки="2025" />
    <СтрокиПлана>
        <Строка Дисциплина="Дисциплина 1"><Сем Ном="1" Экз="1" /></Строка>
        <Строка Дисциплина="Дисциплина 2"><Сем Ном="1" Экз="1" /></Строка>
        <Строка Дисциплина="Дисциплина 3"><Сем Ном="1" Экз="1" /></Строка>
        <Строка Дисциплина="Дисциплина 4"><Сем Ном="1" Экз="1" /></Строка>
        <Строка Дисциплина="Дисциплина 5"><Сем Ном="1" Экз="1" /></Строка>
        <Строка Дисциплина="Дисциплина 6"><Сем Ном="1" Экз="1" /></Строка>
        <Строка Дисциплина="Дисциплина 7"><Сем Ном="1" КР="1" /></Строка>
        <Строка Дисциплина="Дисциплина 8"><Сем Ном="1" КП="1" /></Строка>
        <Строка Дисциплина="Дисциплина 9"><Сем Ном="1" КР="1" /></Строка>
    </СтрокиПлана>
</Документ>
"""


def test_control_form_conflicts_detection():
    """Проверка обнаружения расхождений форм контроля между планами."""
    analyzer = PlanAnalyzer()
    analyzer.load_plan_bytes(DEMO_PLAN_EXAM.encode("utf-8"), filename="plan_exam.xml")
    analyzer.load_plan_bytes(DEMO_PLAN_PASS.encode("utf-8"), filename="plan_pass.xml")

    conflicts = analyzer.find_control_conflicts()
    titles = {c.discipline_title: c for c in conflicts}

    # По Истории России должна быть коллизия: экзамен vs зачет
    assert "История России" in titles
    hist_conf = titles["История России"]
    assert len(hist_conf.forms) >= 2
    assert "экзамен" in hist_conf.forms
    assert "зачет" in hist_conf.forms

    # По Высшей математике коллизии быть не должно (в обоих планах экзамен)
    assert "Высшая математика" not in titles


def test_semester_control_audit():
    """Проверка аудита семестровой нагрузки (лимиты экзаменов и курсовых)."""
    analyzer = PlanAnalyzer()
    analyzer.load_plan_bytes(DEMO_PLAN_OVERLOADED.encode("utf-8"), filename="overloaded.xml")

    # Аудит с лимитами: не более 5 экзаменов, не более 2 курсовых
    audits = analyzer.audit_semester_controls(max_exams=5, max_passes=6, max_course_works=2)
    assert len(audits) >= 1

    sem1 = next(a for a in audits if a.semester == 1)
    assert sem1.exams_count == 6
    assert sem1.course_works_count == 3
    assert sem1.is_overloaded is True
    assert any("экзамен" in v.lower() for v in sem1.violations)
    assert any("курсов" in v.lower() for v in sem1.violations)


def test_service_control_audit_integration():
    """Проверка интеграции анализа форм контроля в PlanService."""
    service = PlanService()
    service.analyzer.load_plan_bytes(DEMO_PLAN_EXAM.encode("utf-8"), filename="plan_exam.xml")
    service.analyzer.load_plan_bytes(DEMO_PLAN_PASS.encode("utf-8"), filename="plan_pass.xml")

    # Проверяем флаг в каталоге дисциплин
    profiles = {p.title: p for p in service.get_discipline_profiles()}
    assert profiles["История России"].has_control_conflict is True
    assert "экзамен" in profiles["История России"].exam_types
    assert "зачет" in profiles["История России"].exam_types

    assert profiles["Высшая математика"].has_control_conflict is False

    # Получение коллизий через сервис
    conflicts = service.get_control_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].discipline_title == "История России"


def test_control_audit_api():
    """Проверка эндпоинтов REST API для форм контроля."""
    client = TestClient(app)
    client.post("/api/clear-plans")

    files = [
        ("files", ("plan1.xml", DEMO_PLAN_EXAM.encode("utf-8"), "text/xml")),
        ("files", ("plan2.xml", DEMO_PLAN_PASS.encode("utf-8"), "text/xml")),
    ]
    client.post("/api/upload-files?append=true", files=files)

    res_conf = client.get("/api/control-conflicts")
    assert res_conf.status_code == 200
    conf_data = res_conf.json()
    assert len(conf_data) == 1
    assert conf_data[0]["discipline_title"] == "История России"

    res_audit = client.get("/api/control-audit")
    assert res_audit.status_code == 200
    audit_data = res_audit.json()
    assert isinstance(audit_data, list)

    res_summary = client.get("/api/control-summary")
    assert res_summary.status_code == 200
    summary = res_summary.json()
    assert summary["conflicts_count"] == 1
