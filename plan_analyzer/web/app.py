"""
FastAPI приложение для локального веб-интерфейса анализа планов и разрешения коллизий.
"""
import os
import sys
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from plan_analyzer.service import PlanService
from plan_analyzer.models import (
    ChangeRequest,
    CreateTeacherPayload,
    CreateIndustryPayload,
    DisciplineBindingPayload,
)

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = os.path.join(sys._MEIPASS, "plan_analyzer", "web")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Анализатор учебных планов и коллизий кафедр")

# Статические файлы и шаблоны
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

service = PlanService()


# --- Pydantic DTOs ---

class DirectoryLoadRequest(BaseModel):
    directory_path: str
    append: bool = True


class DeletePlanPayload(BaseModel):
    file_path: str


class ApplyChangesPayload(BaseModel):
    backup: bool = True
    output_dir: Optional[str] = None


# --- Web Routes ---

@app.get("/", response_class=HTMLResponse)
async def index_view(request: Request):
    """Главная страница интерфейса."""
    return templates.TemplateResponse(request=request, name="index.html")


# --- API Routes ---

@app.get("/api/status")
async def get_status():
    """Текущий статус загруженных данных."""
    plans = service.get_plans()
    conflicts = service.get_conflicts()
    pairs = service.get_pairs()
    staged = service.get_staged_requests()
    ctrl_conflicts = service.get_control_conflicts()
    sem_audits = service.get_semester_control_audits()
    overloaded_count = sum(1 for a in sem_audits if a.is_overloaded)
    return {
        "plans_count": len(plans),
        "disciplines_count": len(service.analyzer.occurrences_by_discipline),
        "pairs_count": len(pairs),
        "conflicts_count": len(conflicts),
        "control_conflicts_count": len(ctrl_conflicts),
        "overloaded_semesters_count": overloaded_count,
        "staged_count": len(staged),
    }


@app.post("/api/load-directory")
async def load_directory(req: DirectoryLoadRequest):
    """Загрузка планов из локальной директории на сервере."""
    if not os.path.isdir(req.directory_path):
        raise HTTPException(status_code=400, detail=f"Директория не найдена: {req.directory_path}")
    loaded = service.load_from_directory(req.directory_path, append=req.append)
    return {
        "success": True,
        "loaded_count": len(loaded),
        "total_plans": len(service.get_plans()),
        "plans": [p.model_dump() for p in service.get_plans()],
    }


@app.post("/api/load-demo-plans")
async def load_demo_plans():
    """Загрузка демонстрационных планов из папки demo_plans в один клик."""
    loaded = service.load_demo_plans(append=True)
    return {
        "success": True,
        "loaded_count": len(loaded),
        "total_plans": len(service.get_plans()),
        "plans": [p.model_dump() for p in service.get_plans()],
    }


@app.post("/api/upload-files")
async def upload_files(files: List[UploadFile] = File(...), append: bool = True):
    """Загрузка файлов планов через браузер (с поддержкой последовательного добавления)."""
    file_tuples = []
    for f in files:
        content = await f.read()
        file_tuples.append((f.filename, content))
    loaded = service.load_from_uploads(file_tuples, append=append)
    return {
        "success": True,
        "loaded_count": len(loaded),
        "total_plans": len(service.get_plans()),
        "plans": [p.model_dump() for p in service.get_plans()],
    }


@app.post("/api/clear-plans")
async def clear_plans():
    """Полная очистка всех загруженных планов."""
    service.clear_plans()
    return {"success": True, "plans_count": 0}


@app.post("/api/delete-plan")
async def delete_plan_post(payload: DeletePlanPayload):
    """Удаление конкретного плана через POST (защита от спецсимволов и слэшей в URL)."""
    success = service.remove_plan(payload.file_path)
    return {"success": success, "plans_count": len(service.get_plans())}


@app.delete("/api/plans/{file_path:path}")
async def delete_plan(file_path: str):
    """Удаление конкретного плана из анализа."""
    success = service.remove_plan(file_path)
    return {"success": success, "plans_count": len(service.get_plans())}


@app.get("/api/plans")
async def get_plans():
    """Список всех загруженных планов."""
    return [p.model_dump() for p in service.get_plans()]


@app.get("/api/filter-options")
async def get_filter_options():
    """Доступные опции фильтрации (годы набора, учебные годы и курсы обучения)."""
    return {
        "years": service.get_available_years(),
        "academic_years": service.get_available_academic_years(),
        "courses": service.get_available_courses(),
    }


@app.get("/api/pairs")
async def get_pairs(
    search: Optional[str] = None,
    dept: Optional[str] = None,
    year: Optional[str] = None,
    course: Optional[int] = None,
    academic_year: Optional[str] = None,
):
    """Список пар 'Дисциплина - Кафедра' с фильтрацией по кафедре, году набора, курсу и учебному году."""
    pairs = service.get_pairs(
        search=search,
        dept_filter=dept,
        year_filter=year,
        course_filter=course,
        academic_year_filter=academic_year,
    )
    return [p.model_dump() for p in pairs]


@app.get("/api/conflicts")
async def get_conflicts(
    search: Optional[str] = None,
    year: Optional[str] = None,
    course: Optional[int] = None,
    academic_year: Optional[str] = None,
):
    """Список коллизий закрепления кафедр с фильтрацией по году набора, курсу и учебному году."""
    conflicts = service.get_conflicts(
        search=search,
        year_filter=year,
        course_filter=course,
        academic_year_filter=academic_year,
    )
    return [c.model_dump() for c in conflicts]


@app.get("/api/control-conflicts")
async def get_control_conflicts(
    search: Optional[str] = None,
    year: Optional[str] = None,
    course: Optional[int] = None,
    academic_year: Optional[str] = None,
):
    """Список коллизий форм промежуточного контроля (экзамен/зачет) между планами."""
    conflicts = service.get_control_conflicts(
        search=search,
        year_filter=year,
        course_filter=course,
        academic_year_filter=academic_year,
    )
    return [c.model_dump() for c in conflicts]


@app.get("/api/control-audit")
async def get_control_audit(
    max_exams: int = 5,
    max_passes: int = 6,
    max_course_works: int = 2,
    overloaded_only: bool = False,
    search: Optional[str] = None,
    year: Optional[str] = None,
    course: Optional[int] = None,
    academic_year: Optional[str] = None,
):
    """Результаты нормативного аудита нагрузки в семестрах планов (лимиты экзаменов, зачетов, курсовых)."""
    audits = service.get_semester_control_audits(
        max_exams=max_exams,
        max_passes=max_passes,
        max_course_works=max_course_works,
        overloaded_only=overloaded_only,
        search=search,
        year_filter=year,
        course_filter=course,
        academic_year_filter=academic_year,
    )
    return [a.model_dump() for a in audits]


@app.get("/api/control-summary")
async def get_control_summary(
    max_exams: int = 5,
    max_passes: int = 6,
    max_course_works: int = 2,
    year: Optional[str] = None,
    course: Optional[int] = None,
    academic_year: Optional[str] = None,
):
    """Сводка по коллизиям контроля и перегруженным семестрам."""
    summary = service.get_control_audit_summary(
        max_exams=max_exams,
        max_passes=max_passes,
        max_course_works=max_course_works,
        year_filter=year,
        course_filter=course,
        academic_year_filter=academic_year,
    )
    return summary.model_dump()


@app.get("/api/similarities")
async def get_similarities(
    min_score: float = 0.75,
    use_embeddings: bool = True,
    hidden_only: bool = False
):
    """Пары схожих дисциплин (опечатки + семантические аналоги)."""
    sims = service.get_similarities(
        min_score=min_score,
        use_embeddings=use_embeddings,
        hidden_only=hidden_only,
    )
    return [s.model_dump() for s in sims]


@app.get("/api/departments")
async def get_departments():
    """Справочник кафедр."""
    return service.get_departments_catalog()


@app.get("/api/disciplines")
async def get_disciplines(
    search: Optional[str] = None,
    industry: Optional[str] = None,
    teacher: Optional[str] = None,
    dept: Optional[str] = None,
    year: Optional[str] = None,
    course: Optional[str] = None,
    academic_year: Optional[str] = None,
    conflict_only: bool = False,
):
    """Каталог дисциплин как центральных единиц анализа."""
    course_int = None
    if course is not None and str(course).strip().isdigit():
        course_int = int(str(course).strip())

    profiles = service.get_discipline_profiles(
        search=search,
        industry=industry,
        teacher_id=teacher,
        dept=dept,
        year=year,
        course=course_int,
        academic_year=academic_year,
        conflict_only=conflict_only,
    )
    return [p.model_dump() for p in profiles]


@app.post("/api/disciplines/bind")
async def bind_discipline(payload: DisciplineBindingPayload):
    """Привязка отрасли и преподавателей к дисциплине."""
    service.bind_discipline(
        discipline_title=payload.discipline_title,
        industry=payload.industry,
        teacher_ids=payload.teacher_ids,
    )
    return {"success": True}


# --- Управление преподавателями ---

@app.get("/api/teachers")
async def get_teachers():
    """Список всех преподавателей."""
    return [t.model_dump() for t in service.get_teachers()]


@app.post("/api/teachers")
async def create_teacher(payload: CreateTeacherPayload):
    """Ручное добавление преподавателя."""
    t = service.add_teacher(name=payload.name, department=payload.department, position=payload.position)
    return t.model_dump()


@app.delete("/api/teachers/{teacher_id}")
async def delete_teacher(teacher_id: str):
    """Удаление преподавателя."""
    success = service.delete_teacher(teacher_id)
    return {"success": success}


@app.post("/api/teachers/upload")
async def upload_teachers(file: UploadFile = File(...)):
    """Загрузка преподавателей из файла (.xlsx или .csv)."""
    content = await file.read()
    count = service.import_teachers_file(content, filename=file.filename)
    return {"success": True, "imported_count": count}


# --- Управление отраслями ---

@app.get("/api/industries")
async def get_industries():
    """Список всех отраслей."""
    return [i.model_dump() for i in service.get_industries()]


@app.post("/api/industries")
async def create_industry(payload: CreateIndustryPayload):
    """Ручное добавление отрасли."""
    ind = service.add_industry(name=payload.name, description=payload.description)
    return ind.model_dump()


@app.delete("/api/industries/{industry_id}")
async def delete_industry(industry_id: str):
    """Удаление отрасли."""
    success = service.delete_industry(industry_id)
    return {"success": success}


@app.post("/api/industries/upload")
async def upload_industries(file: UploadFile = File(...)):
    """Загрузка отраслей из файла (.xlsx или .csv)."""
    content = await file.read()
    count = service.import_industries_file(content, filename=file.filename)
    return {"success": True, "imported_count": count}


@app.post("/api/bindings/upload")
async def upload_bindings(file: UploadFile = File(...)):
    """Загрузка файла связок 'Дисциплина - Отрасль - Преподаватели'."""
    content = await file.read()
    count = service.import_bindings_file(content, filename=file.filename)
    return {"success": True, "imported_count": count}


@app.get("/api/export/excel")
async def export_excel():
    """Экспорт полного реестра дисциплин, преподавателей и отраслей в Excel (.xlsx)."""
    excel_bytes = service.export_excel()
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="disciplines_registry.xlsx"'},
    )


# --- Staging & Diff API ---

@app.get("/api/staged")
async def get_staged():
    """Просмотр запланированных изменений (diff preview)."""
    diffs = service.preview_staged_changes()
    requests = service.get_staged_requests()
    return {
        "requests": [r.model_dump() for r in requests],
        "diffs": [d.model_dump() for d in diffs],
    }


@app.post("/api/stage-change")
async def stage_change(req: ChangeRequest):
    """Добавление изменения в корзину."""
    diffs = service.stage_change(req)
    return {
        "success": True,
        "total_staged": len(service.staged_changes),
        "diffs": [d.model_dump() for d in diffs],
    }


@app.delete("/api/staged/{index}")
async def remove_staged(index: int):
    """Удаление одного запланированного изменения из корзины."""
    diffs = service.remove_staged_change(index)
    return {
        "success": True,
        "total_staged": len(service.staged_changes),
        "diffs": [d.model_dump() for d in diffs],
    }


@app.delete("/api/staged")
async def clear_staged():
    """Полная очистка корзины изменений."""
    service.clear_staged_changes()
    return {"success": True}


@app.post("/api/apply-changes")
async def apply_changes(payload: ApplyChangesPayload):
    """Применение изменений к файлам планов."""
    resp = service.apply_changes(backup=payload.backup, output_dir=payload.output_dir)
    return resp.model_dump()
