"""
Модели данных для модуля анализа учебных планов и разрешения коллизий кафедр.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Union
from pydantic import BaseModel


class PlanMetadata(BaseModel):
    """Метаданные отдельного учебного плана."""
    file_path: str
    file_name: str
    direction_code: str = ""
    direction_title: str = ""
    profile_title: str = ""
    edu_level: str = ""
    study_form: str = ""
    start_year: str = ""
    faculty: str = ""
    total_disciplines: int = 0


class DisciplineOccurrence(BaseModel):
    """Вхождение дисциплины в конкретный учебный план."""
    plan_file: str
    plan_name: str
    direction_code: str
    direction_title: str
    profile_title: str
    start_year: str
    dept_code: str
    dept_name: str
    semester: int
    semesters_str: str = ""
    academic_year: str = ""  # Конкретный учебный год (напр., '2025/2026')
    course: int = 1  # Номер курса (1-6)
    total_ze: Union[int, float] = 0
    total_hours: int = 0
    row_code: str = ""  # ID строки в плане (для точной модификации)
    exam_type: str = ""  # Форма промежуточной аттестации (напр., 'экзамен', 'зачет')
    control_forms: List[str] = field(default_factory=list)  # Список форм контроля
    semester_controls: Dict[int, List[str]] = field(default_factory=dict)  # Семестр -> список форм


class DisciplineDeptPair(BaseModel):
    """Пара 'Дисциплина — Кафедра' с агрегированной статистикой."""
    discipline_title: str
    dept_code: str
    dept_name: str
    plans_count: int
    occurrences: List[DisciplineOccurrence] = []


class DepartmentConflict(BaseModel):
    """Коллизия: одна дисциплина закреплена за разными кафедрами в разных планах."""
    discipline_title: str
    departments: List[str]  # Названия кафедр
    department_codes: List[str]  # Коды кафедр
    total_occurrences: int
    by_department: Dict[str, List[DisciplineOccurrence]]  # Кафедра -> список вхождений
    suggested_target_dept: Optional[str] = None  # Рекомендованная кафедра (по большинству планов)


class Teacher(BaseModel):
    """Преподаватель."""
    id: str
    name: str  # ФИО
    department: str = ""  # Кафедра
    position: str = ""  # Должность (доцент, профессор и т.д.)


class Industry(BaseModel):
    """Отрасль знаний / науки / индустрии."""
    id: str
    name: str  # Название отрасли
    description: str = ""


class DisciplineProfile(BaseModel):
    """Дисциплина как центральная единица анализа."""
    title: str
    normalized_title: str
    industry: Optional[str] = None
    teachers: List[Teacher] = []
    departments: List[str] = []
    department_codes: List[str] = []
    plans_count: int = 0
    has_conflict: bool = False
    total_hours: int = 0
    total_ze: Union[int, float] = 0
    ze_display: str = ""  # Отображение объема ЗЕТ (напр., '3', '3–4', '1.5')
    hours_display: str = ""  # Отображение объема часов (напр., '108', '108–144')
    sum_ze: Union[int, float] = 0  # Суммарная нагрузка в ЗЕТ по всем планам
    sum_hours: int = 0  # Суммарная нагрузка в часах по всем планам
    semesters: List[int] = []
    academic_years: List[str] = []  # Учебные годы реализации дисциплины (напр., ['2025/2026'])
    occurrences: List[DisciplineOccurrence] = []
    similar_disciplines: List[str] = []
    exam_types: List[str] = []  # Уникальные формы контроля по планам (напр., ['экзамен', 'зачет'])
    has_control_conflict: bool = False  # Расхождение форм контроля между планами
    control_conflict_details: str = ""  # Пояснение расхождения


class ControlFormConflict(BaseModel):
    """Коллизия форм контроля: по одной дисциплине в разных планах установлены разные формы аттестации."""
    discipline_title: str
    forms: List[str]  # Набор несовпадающих форм контроля (напр., ['экзамен', 'зачет'])
    total_occurrences: int
    by_form: Dict[str, List[DisciplineOccurrence]]  # Форма контроля -> вхождения в планы
    suggested_form: Optional[str] = None  # Рекомендованная форма (по большинству планов)


class SemesterAuditResult(BaseModel):
    """Результат нормативного аудита нагрузки в семестре по плану."""
    plan_file: str
    plan_name: str
    direction_code: str
    direction_title: str
    semester: int
    course: int
    academic_year: str
    exams_count: int = 0
    pass_count: int = 0
    diff_pass_count: int = 0
    course_works_count: int = 0
    is_overloaded: bool = False
    violations: List[str] = []
    disciplines_by_control: Dict[str, List[str]] = {}


class ControlAuditSummary(BaseModel):
    """Сводка по формам контроля и аудиту семестров."""
    conflicts_count: int = 0
    overloaded_semesters_count: int = 0
    conflicts: List[ControlFormConflict] = []
    semester_audits: List[SemesterAuditResult] = []


class DisciplineBindingPayload(BaseModel):
    """Запрос на привязку отрасли и преподавателей к дисциплине."""
    discipline_title: str
    industry: Optional[str] = None
    teacher_ids: List[str] = []


class CreateTeacherPayload(BaseModel):
    """Запрос на создание преподавателя."""
    name: str
    department: str = ""
    position: str = ""


class CreateIndustryPayload(BaseModel):
    """Запрос на создание отрасли."""
    name: str
    description: str = ""


class DisciplineSimilarityPair(BaseModel):
    """Пара семантически или лексически схожих дисциплин."""
    discipline_a: str
    discipline_b: str
    lexical_similarity: float  # 0.0 - 1.0 (RapidFuzz)
    semantic_similarity: float  # 0.0 - 1.0 (FastEmbed ONNX)
    combined_score: float  # 0.0 - 1.0
    depts_a: List[str]
    depts_b: List[str]
    is_hidden_conflict: bool  # True, если схожие дисциплины читаются разными кафедрами
    plans_count_a: int = 0
    plans_count_b: int = 0


class ChangeRequest(BaseModel):
    """Запрос на изменение в учебных планах."""
    action_type: str  # 'change_dept', 'rename_discipline', 'unify'
    discipline_title: str
    target_dept_code: Optional[str] = None
    target_dept_name: Optional[str] = None
    new_discipline_title: Optional[str] = None
    affected_plan_files: List[str] = []  # Если пустой, применяется ко всем планам, где найдена дисциплина


class PlannedFileChange(BaseModel):
    """Запланированное изменение в конкретном файле (для Diff Viewer)."""
    file_path: str
    file_name: str
    row_code: str
    original_title: str
    new_title: Optional[str] = None
    original_dept_code: str
    original_dept_name: str
    new_dept_code: Optional[str] = None
    new_dept_name: Optional[str] = None
    change_type: str  # 'Кафедра', 'Название', 'Кафедра и Название'


class ApplyChangesResponse(BaseModel):
    """Результат применения изменений."""
    success: bool
    modified_files_count: int
    total_modifications: int
    backup_created: bool
    output_directory: Optional[str] = None
    details: List[str] = []
    errors: List[str] = []
