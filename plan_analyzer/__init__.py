"""
Библиотека анализа учебных планов, реестра пар 'дисциплина-кафедра', коллизий и семантического подобия.
"""

from plan_analyzer.models import (
    PlanMetadata,
    DisciplineOccurrence,
    DisciplineDeptPair,
    DepartmentConflict,
    DisciplineSimilarityPair,
    ChangeRequest,
    PlannedFileChange,
    ApplyChangesResponse,
)
from plan_analyzer.analyzer import PlanAnalyzer, normalize_discipline_title
from plan_analyzer.similarity import DisciplineSimilarityEngine, clean_for_matching
from plan_analyzer.plx_editor import PLXFileContainer
from plan_analyzer.service import PlanService

__all__ = [
    "PlanAnalyzer",
    "PlanService",
    "DisciplineSimilarityEngine",
    "PLXFileContainer",
    "PlanMetadata",
    "DisciplineOccurrence",
    "DisciplineDeptPair",
    "DepartmentConflict",
    "DisciplineSimilarityPair",
    "ChangeRequest",
    "PlannedFileChange",
    "ApplyChangesResponse",
    "normalize_discipline_title",
    "clean_for_matching",
]
