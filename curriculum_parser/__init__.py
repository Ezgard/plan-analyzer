"""
Curriculum Parser — автономный модуль синтаксического анализа и валидации
учебных планов ОПОП (Шахты / ГосИнсп / XML / PLX / ZIP).

Предоставляет как процедурный API (parse_curriculum_plan, parse_curriculum, parse_plx),
так и объектно-ориентированный парсер (PLXParser, CurriculumParser).
"""

__version__ = "0.1.0"

from .exceptions import (
    CurriculumParsingError,
    PLXParsingError,
    SecurityValidationError,
    EmptyPlanError,
)

from .models import (
    CompetencyItem,
    ReattestationItem,
    DisciplineItem,
    CurriculumModule,
    IUPProfile,
    CurriculumPlanData,
    ScheduleDayItem,
    ScheduleWeekItem,
    ScheduleBudgetItem,
    ScheduleSessionItem,
    ScheduleCourseItem,
    CurriculumScheduleData,
)

from .utils import (
    safe_int,
    safe_float,
    format_credit_val,
    calculate_absolute_semester,
    parse_semesters_from_text,
    normalize_competency_code,
    extract_competency_codes_from_string,
    decode_raw_bytes,
    validate_xml_security,
)

from .parser import (
    PLXParser,
    CurriculumParser,
    parse_curriculum_plan,
    parse_curriculum,
    parse_plx,
    parse_curriculum_schedule,
    dict_to_curriculum_plan,
    ACTIVITY_SYMBOLS,
    DAY_NAMES_RU,
    MONTH_NAMES_RU,
)

__all__ = [
    "__version__",
    # Main parse functions
    "parse_curriculum_plan",
    "parse_curriculum",
    "parse_plx",
    "parse_curriculum_schedule",
    "dict_to_curriculum_plan",
    # Parsers
    "PLXParser",
    "CurriculumParser",
    # Models
    "CurriculumPlanData",
    "DisciplineItem",
    "CompetencyItem",
    "IUPProfile",
    "CurriculumModule",
    "ReattestationItem",
    "ScheduleDayItem",
    "ScheduleWeekItem",
    "ScheduleBudgetItem",
    "ScheduleSessionItem",
    "ScheduleCourseItem",
    "CurriculumScheduleData",
    # Constants
    "ACTIVITY_SYMBOLS",
    "DAY_NAMES_RU",
    "MONTH_NAMES_RU",
    # Exceptions
    "CurriculumParsingError",
    "PLXParsingError",
    "SecurityValidationError",
    "EmptyPlanError",
    # Utils
    "safe_int",
    "safe_float",
    "format_credit_val",
    "calculate_absolute_semester",
    "parse_semesters_from_text",
    "normalize_competency_code",
    "extract_competency_codes_from_string",
    "decode_raw_bytes",
    "validate_xml_security",
]
