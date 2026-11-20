"""
Модели данных для структурированного представления учебных планов ОПОП.
Поддерживают как строгий типизированный объектный доступ через атрибуты,
так и словарный доступ (dict-like: __getitem__, get, keys, values, items, to_dict)
для 100% обратной совместимости с существующим кодом.
"""
from dataclasses import dataclass, field, asdict
import json
from typing import List, Dict, Any, Optional, Iterator, Union


@dataclass
class CompetencyItem:
    """Элемент компетенции и соответствующего индикатора достижения."""
    code: str
    name: str
    indicator_code: str
    indicator_name: str

    def to_dict(self) -> Dict[str, Any]:
        """Преобразует объект в стандартный словарь."""
        return {
            "code": self.code,
            "name": self.name,
            "indicator_code": self.indicator_code,
            "indicator_name": self.indicator_name,
        }

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return ("code", "name", "indicator_code", "indicator_name")

    def values(self):
        return (self.code, self.name, self.indicator_code, self.indicator_name)

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())


@dataclass
class ReattestationItem:
    """Запись о перезачете или переаттестации дисциплины в ИУП."""
    id: Optional[str]
    row_id: str
    work_type_code: int
    original_course: int
    original_semester: int
    amount_was: float
    amount_studied: float
    attestation_type: str
    attestation_type_code: int
    grade: str
    grade_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Преобразует запись переаттестации в стандартный словарь."""
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


@dataclass
class DisciplineItem:
    """Дисциплина, практика, ГИА или факультатив учебного плана."""
    code: str
    title: str
    block: str
    dept_name: str
    dept_code: str
    semester: int
    row_code: str = ""
    semesters: List[int] = field(default_factory=list)
    semesters_str: str = ""
    total_ze: Union[int, float] = 0
    total_hours: int = 0
    lectures: int = 0
    seminars: int = 0
    contact_hours: int = 0
    self_hours: int = 0
    control_hours: int = 0
    exam_type: str = "зачет"
    semester_controls: Dict[int, List[str]] = field(default_factory=dict)
    session_controls: List[Dict[str, Any]] = field(default_factory=list)
    competencies: List[CompetencyItem] = field(default_factory=list)
    obj_type: str = "2"
    item_type: str = "discipline"
    is_practice: bool = False
    is_gia: bool = False
    is_facultative: bool = False
    module_title: str = ""
    parent_module_code: str = ""
    is_iup_closed: bool = False
    iup_status: str = "standard"
    reattestations: List[ReattestationItem] = field(default_factory=list)
    reattested_zet: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Преобразует дисциплину в стандартный словарь."""
        d = asdict(self)
        d["competencies"] = [c.to_dict() if isinstance(c, CompetencyItem) else c for c in self.competencies]
        d["reattestations"] = [r.to_dict() if isinstance(r, ReattestationItem) else r for r in self.reattestations]
        return d

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


@dataclass
class CurriculumModule:
    """Структурный блок или модуль учебного плана."""
    id: str
    title: str
    code: str
    is_module: bool = False
    is_elective_group: bool = False
    items_count: int = 0
    total_ze: Union[int, float] = 0
    items: List[DisciplineItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Преобразует модуль в стандартный словарь."""
        return {
            "id": self.id,
            "title": self.title,
            "code": self.code,
            "is_module": self.is_module,
            "is_elective_group": self.is_elective_group,
            "items_count": self.items_count,
            "total_ze": self.total_ze,
            "items": [it.to_dict() if isinstance(it, DisciplineItem) else it for it in self.items]
        }

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


@dataclass
class IUPProfile:
    """Профиль индивидуального учебного плана студента."""
    is_iup: bool = False
    student_fio: str = ""
    group_name: str = ""
    base_plan_filename: str = ""
    start_course: int = 1
    start_semester: int = 1
    total_reattestations: int = 0
    reattestations: List[ReattestationItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Преобразует профиль ИУП в стандартный словарь."""
        return {
            "is_iup": self.is_iup,
            "student_fio": self.student_fio,
            "group_name": self.group_name,
            "base_plan_filename": self.base_plan_filename,
            "start_course": self.start_course,
            "start_semester": self.start_semester,
            "total_reattestations": self.total_reattestations,
            "reattestations": [r.to_dict() if isinstance(r, ReattestationItem) else r for r in self.reattestations]
        }

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


@dataclass
class ScheduleDayItem:
    """Один учебный день недели в календарном графике (Пн-Сб)."""
    day_num: int
    day_name: str
    act_code: str
    symbol: str
    name: str
    date: str = ""
    color: str = "#e0f2fe"
    badge_class: str = ""
    session_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


@dataclass
class ScheduleWeekItem:
    """Неделя календарного учебного графика (1..52+)."""
    week_num: int
    is_uniform: bool
    dom_symbol: str
    dom_color: str
    days: List[ScheduleDayItem] = field(default_factory=list)
    start_date: str = ""
    end_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "week_num": self.week_num,
            "is_uniform": self.is_uniform,
            "dom_symbol": self.dom_symbol,
            "dom_color": self.dom_color,
            "days": [d.to_dict() if isinstance(d, ScheduleDayItem) else d for d in self.days],
            "start_date": self.start_date,
            "end_date": self.end_date,
        }

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


@dataclass
class ScheduleBudgetItem:
    """Статья бюджета времени (вид деятельности, недели, дни)."""
    act_code: str
    symbol: str
    name: str
    weeks: float
    days: int
    percent: float
    badge_class: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


@dataclass
class ScheduleSessionItem:
    """Сессия (заезд) заочной или очно-заочной формы обучения."""
    course: int
    session_num: int
    name: str
    start_date: str
    end_date: str
    duration_days: int
    semester: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


@dataclass
class ScheduleCourseItem:
    """Календарный учебный график одного курса."""
    course_num: int
    weeks_count: int
    academic_year: str = ""
    calendar_year_start: int = 0
    total_weeks: float = 52.0
    weeks: List[ScheduleWeekItem] = field(default_factory=list)
    budget: List[ScheduleBudgetItem] = field(default_factory=list)
    sessions: List[ScheduleSessionItem] = field(default_factory=list)
    is_balanced: bool = True
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "course_num": self.course_num,
            "weeks_count": self.weeks_count,
            "academic_year": self.academic_year,
            "calendar_year_start": self.calendar_year_start,
            "total_weeks": self.total_weeks,
            "weeks": [w.to_dict() if isinstance(w, ScheduleWeekItem) else w for w in self.weeks],
            "budget": [b.to_dict() if isinstance(b, ScheduleBudgetItem) else b for b in self.budget],
            "sessions": [s.to_dict() if isinstance(s, ScheduleSessionItem) else s for s in self.sessions],
            "is_balanced": self.is_balanced,
            "notes": self.notes,
        }

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


@dataclass
class CurriculumScheduleData:
    """Полный календарный учебный график (КУГ) учебного плана по всем курсам."""
    courses: Dict[int, ScheduleCourseItem] = field(default_factory=dict)
    semesters: List[Dict[str, Any]] = field(default_factory=list)
    legend: Dict[str, Any] = field(default_factory=dict)
    study_years_count: int = 4
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "courses": {
                c: (item.to_dict() if isinstance(item, ScheduleCourseItem) else item)
                for c, item in self.courses.items()
            },
            "semesters": self.semesters,
            "legend": self.legend,
            "study_years_count": self.study_years_count,
            "warnings": self.warnings,
        }

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())


@dataclass
class CurriculumPlanData:
    """
    Полные структурированные данные учебного плана ОПОП.
    Поддерживает:
    - строгий типизированный доступ через атрибуты (plan.direction_code, plan.disciplines)
    - доступ как к словарю (plan["direction_code"], plan.get("disciplines"))
    - экспорт в стандартный словарь plan.to_dict() и JSON plan.to_json()
    - фильтрацию дисциплин по семестрам, блокам и поиск
    """
    filename: str
    direction_code: str
    direction_title: str
    profile_title: str
    edu_level: str
    study_form: str
    start_year: int
    study_years: int = 4
    qualification: str = ""
    is_iup: bool = False
    iup_profile: IUPProfile = field(default_factory=IUPProfile)
    disciplines: List[DisciplineItem] = field(default_factory=list)
    pure_disciplines: List[DisciplineItem] = field(default_factory=list)
    practices: List[DisciplineItem] = field(default_factory=list)
    gia: List[DisciplineItem] = field(default_factory=list)
    facultatives: List[DisciplineItem] = field(default_factory=list)
    iup_closed_disciplines: List[DisciplineItem] = field(default_factory=list)
    iup_active_disciplines: List[DisciplineItem] = field(default_factory=list)
    modules: List[CurriculumModule] = field(default_factory=list)
    modules_map: Dict[str, Any] = field(default_factory=dict)
    schedule: Optional[CurriculumScheduleData] = None

    def to_dict(self) -> Dict[str, Any]:
        """Преобразует структуру в полностью десериализованный стандартный Python-словарь."""
        return {
            "filename": self.filename,
            "direction_code": self.direction_code,
            "direction_title": self.direction_title,
            "profile_title": self.profile_title,
            "edu_level": self.edu_level,
            "study_form": self.study_form,
            "start_year": self.start_year,
            "study_years": self.study_years,
            "qualification": self.qualification,
            "is_iup": self.is_iup,
            "iup_profile": self.iup_profile.to_dict() if isinstance(self.iup_profile, IUPProfile) else self.iup_profile,
            "disciplines": [d.to_dict() if isinstance(d, DisciplineItem) else d for d in self.disciplines],
            "pure_disciplines": [d.to_dict() if isinstance(d, DisciplineItem) else d for d in self.pure_disciplines],
            "practices": [d.to_dict() if isinstance(d, DisciplineItem) else d for d in self.practices],
            "gia": [d.to_dict() if isinstance(d, DisciplineItem) else d for d in self.gia],
            "facultatives": [d.to_dict() if isinstance(d, DisciplineItem) else d for d in self.facultatives],
            "iup_closed_disciplines": [d.to_dict() if isinstance(d, DisciplineItem) else d for d in self.iup_closed_disciplines],
            "iup_active_disciplines": [d.to_dict() if isinstance(d, DisciplineItem) else d for d in self.iup_active_disciplines],
            "modules": [m.to_dict() if isinstance(m, CurriculumModule) else m for m in self.modules],
            "modules_map": self.modules_map,
            "schedule": self.schedule.to_dict() if isinstance(self.schedule, CurriculumScheduleData) else self.schedule,
        }

    def to_json(self, indent: int = 2, ensure_ascii: bool = False) -> str:
        """Сериализует учебный план в форматированную строку JSON."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=ensure_ascii)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()

    def items(self):
        return self.to_dict().items()

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def find_discipline(self, code_or_title: str) -> Optional[DisciplineItem]:
        """Поиск дисциплины по точному шифру или фрагменту названия."""
        target = code_or_title.strip().lower()
        for d in self.disciplines:
            if d.code.strip().lower() == target or target in d.title.lower():
                return d
        return None

    def filter_by_semester(self, semester: int) -> List[DisciplineItem]:
        """Возвращает все дисциплины, изучаемые в указанном семестре."""
        return [d for d in self.disciplines if semester in d.semesters or d.semester == semester]

    def filter_by_block(self, block_prefix: str) -> List[DisciplineItem]:
        """Возвращает дисциплины определенного блока (например 'Б1.О', 'Б2', 'ФТД')."""
        prefix = block_prefix.strip().upper()
        return [d for d in self.disciplines if d.code.upper().startswith(prefix)]

    @property
    def has_schedule(self) -> bool:
        """Проверяет, содержит ли план данные календарного учебного графика."""
        return self.schedule is not None and bool(self.schedule.courses)

    def get_course_for_academic_year(self, academic_year_start: int) -> Optional[int]:
        """
        Возвращает номер курса (1..N), на котором обучаются студенты
        в указанном учебном году (например, academic_year_start=2025 для года 2025/2026).
        Если в этот учебный год набор еще не состоялся или программа завершена, возвращает None.
        """
        if not self.start_year or academic_year_start < self.start_year:
            return None
        course = academic_year_start - self.start_year + 1
        max_course = max(self.schedule.courses.keys()) if (self.schedule and self.schedule.courses) else self.study_years
        if 1 <= course <= max_course:
            return course
        return None

    def get_schedule_for_academic_year(self, academic_year_start: int) -> Optional[ScheduleCourseItem]:
        """Возвращает график курса для указанного учебного года."""
        course = self.get_course_for_academic_year(academic_year_start)
        if course and self.schedule and course in self.schedule.courses:
            return self.schedule.courses[course]
        return None
