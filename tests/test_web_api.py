"""
Тесты REST API веб-приложения plan_analyzer.web.app
"""
import io
import pytest
from fastapi.testclient import TestClient

from plan_analyzer.web.app import app, service
from tests.test_plan_analyzer import DEMO_PLAN_1, DEMO_PLAN_2


@pytest.fixture
def client():
    service.reset()
    return TestClient(app)


def test_index_page(client):
    """Проверка доступности главной HTML-страницы."""
    res = client.get("/")
    assert res.status_code == 200
    assert "Анализатор учебных планов" in res.text


def test_upload_and_workflow_via_api(client):
    """Полный цикл работы через API."""
    # 1. Загрузка двух файлов планов с коллизией
    files = [
        ("files", ("plan_a.xml", io.BytesIO(DEMO_PLAN_1.encode("utf-8")), "text/xml")),
        ("files", ("plan_b.xml", io.BytesIO(DEMO_PLAN_2.encode("utf-8")), "text/xml")),
    ]
    res_upload = client.post("/api/upload-files", files=files)
    assert res_upload.status_code == 200
    data_upload = res_upload.json()
    assert data_upload["success"] is True
    assert data_upload["loaded_count"] == 2

    # 2. Проверка статуса
    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    st = res_status.json()
    assert st["plans_count"] == 2
    assert st["conflicts_count"] == 1

    # 3. Реестр пар
    res_pairs = client.get("/api/pairs")
    assert res_pairs.status_code == 200
    pairs = res_pairs.json()
    assert len(pairs) > 0

    # 4. Коллизии
    res_conflicts = client.get("/api/conflicts")
    assert res_conflicts.status_code == 200
    conflicts = res_conflicts.json()
    assert len(conflicts) == 1
    assert conflicts[0]["discipline_title"] == "Высшая математика"

    # 5. Подобие
    res_sim = client.get("/api/similarities?min_score=0.7")
    assert res_sim.status_code == 200
    sims = res_sim.json()
    assert any("Юридические" in s["discipline_a"] for s in sims)

    # 6. Стейджинг разрешения коллизии
    res_stage = client.post(
        "/api/stage-change",
        json={
            "action_type": "change_dept",
            "discipline_title": "Высшая математика",
            "target_dept_code": "15",
            "target_dept_name": "Кафедра высшей математики",
        },
    )
    assert res_stage.status_code == 200
    assert res_stage.json()["success"] is True

    # 7. Просмотр Diff
    res_staged = client.get("/api/staged")
    assert res_staged.status_code == 200
    staged_data = res_staged.json()
    assert len(staged_data["diffs"]) >= 1

    # 8. Применение изменений
    res_apply = client.post(
        "/api/apply-changes",
        json={"backup": True, "output_dir": None},
    )
    assert res_apply.status_code == 200
    apply_resp = res_apply.json()
    assert apply_resp["success"] is True
    assert apply_resp["modified_files_count"] >= 1


def test_sequential_upload_and_delete(client):
    """Проверка ПОСЛЕДОВАТЕЛЬНОЙ загрузки нескольких планов и удаления."""
    # 1. Загружаем ПЕРВЫЙ план
    f1 = [("files", ("plan_first.xml", io.BytesIO(DEMO_PLAN_1.encode("utf-8")), "text/xml"))]
    res1 = client.post("/api/upload-files?append=true", files=f1)
    assert res1.status_code == 200
    assert res1.json()["total_plans"] == 1

    # 2. ПОСЛЕДОВАТЕЛЬНО загружаем ВТОРОЙ план
    f2 = [("files", ("plan_second.xml", io.BytesIO(DEMO_PLAN_2.encode("utf-8")), "text/xml"))]
    res2 = client.post("/api/upload-files?append=true", files=f2)
    assert res2.status_code == 200
    # Проверяем, что первый план НЕ стерт, а в сессии теперь ОБА плана
    assert res2.json()["total_plans"] == 2

    # 3. Проверяем статус: должно быть 2 плана и 1 коллизия
    st = client.get("/api/status").json()
    assert st["plans_count"] == 2
    assert st["conflicts_count"] == 1

    # 4. Удаляем один план через POST /api/delete-plan
    plans = client.get("/api/plans").json()
    assert len(plans) == 2
    target_path = plans[0]["file_path"]

    res_del = client.post("/api/delete-plan", json={"file_path": target_path})
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True
    assert res_del.json()["plans_count"] == 1

    # 5. Очищаем все планы
    res_clear = client.post("/api/clear-plans")
    assert res_clear.status_code == 200
    assert res_clear.json()["plans_count"] == 0


def test_load_demo_plans_and_disciplines(client):
    """Проверка загрузки демо-планов и работы каталога дисциплин с пустыми фильтрами."""
    client.post("/api/clear-plans")

    # 1. Загрузка демонстрационных планов
    res_demo = client.post("/api/load-demo-plans")
    assert res_demo.status_code == 200
    assert res_demo.json()["success"] is True
    assert res_demo.json()["loaded_count"] >= 1

    # 2. Получение каталога дисциплин
    res_disc = client.get("/api/disciplines")
    assert res_disc.status_code == 200
    disciplines = res_disc.json()
    assert len(disciplines) >= 5

    # 3. Фильтрация с пустыми строками (не должно давать 422)
    res_filter = client.get("/api/disciplines?course=&year=&search=")
    assert res_filter.status_code == 200
    assert len(res_filter.json()) == len(disciplines)

