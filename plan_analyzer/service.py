"""
Сервисный слой координации анализа, разрешения коллизий и модификации учебных планов.
"""
import os
import sys
import tempfile
from typing import List, Dict, Optional, Tuple, Any

from plan_analyzer.models import (
    PlanMetadata,
    DisciplineDeptPair,
    DepartmentConflict,
    DisciplineSimilarityPair,
    ChangeRequest,
    PlannedFileChange,
    ApplyChangesResponse,
    Teacher,
    Industry,
    DisciplineProfile,
    ControlFormConflict,
    SemesterAuditResult,
    ControlAuditSummary,
)
from plan_analyzer.analyzer import PlanAnalyzer
from plan_analyzer.similarity import DisciplineSimilarityEngine
from plan_analyzer.plx_editor import PLXFileContainer
from plan_analyzer.storage import RegistryStorage


class PlanService:
    """Сервис управления сессией анализа и редактирования планов."""

    def __init__(self, storage_path: str = "data/registry_store.json"):
        self.analyzer = PlanAnalyzer()
        self.similarity_engine = DisciplineSimilarityEngine()
        self.storage = RegistryStorage(storage_path=storage_path)
        self.staged_changes: List[ChangeRequest] = []
        self._cached_similarities: Optional[List[DisciplineSimilarityPair]] = None
        self._last_similarity_threshold: float = 0.75
        self.session_temp_dir = tempfile.mkdtemp(prefix="plans_session_")

    def reset(self):
        """Сбрасывает текущее состояние анализатора."""
        self.analyzer = PlanAnalyzer()
        self.staged_changes.clear()
        self._cached_similarities = None

    def clear_plans(self):
        """Очищает все загруженные планы, сохраняя сервис активным."""
        self.analyzer = PlanAnalyzer()
        self.staged_changes.clear()
        self._cached_similarities = None

    def remove_plan(self, file_path: str) -> bool:
        """Удаляет один план из анализа."""
        res = self.analyzer.remove_plan(file_path)
        if res:
            self._cached_similarities = None
        return res

    def load_from_directory(self, dir_path: str, append: bool = True) -> List[PlanMetadata]:
        """Загружает файлы из директории."""
        if not append:
            self.clear_plans()
        self._cached_similarities = None
        meta_list = self.analyzer.load_directory(dir_path)
        return meta_list

    def load_demo_plans(self, append: bool = True) -> List[PlanMetadata]:
        """Загружает демонстрационные планы из локальной папки demo_plans."""
        possible_dirs = [
            os.path.join(os.getcwd(), "demo_plans"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_plans"),
        ]
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            possible_dirs.insert(0, os.path.join(sys._MEIPASS, "demo_plans"))

        for d in possible_dirs:
            if os.path.isdir(d):
                return self.load_from_directory(d, append=append)
        return []

    def load_from_paths(self, paths: List[str], append: bool = True) -> List[PlanMetadata]:
        """Загружает файлы по списку путей."""
        if not append:
            self.clear_plans()
        self._cached_similarities = None
        meta_list = self.analyzer.load_files(paths)
        return meta_list

    def load_from_uploads(
        self,
        uploaded_files: List[Tuple[str, bytes]],
        append: bool = True
    ) -> List[PlanMetadata]:
        """Загружает файлы, переданные через форму веб-интерфейса (имя, байты)."""
        if not append:
            self.clear_plans()
        self._cached_similarities = None

        if not os.path.exists(self.session_temp_dir):
            self.session_temp_dir = tempfile.mkdtemp(prefix="plans_session_")

        loaded_meta = []
        for filename, content in uploaded_files:
            file_path = os.path.join(self.session_temp_dir, filename)
            with open(file_path, "wb") as f:
                f.write(content)
            meta = self.analyzer.load_plan_bytes(content, filename=filename, file_path=file_path)
            if meta:
                loaded_meta.append(meta)

        return loaded_meta

    def get_plans(self) -> List[PlanMetadata]:
        """Возвращает список метаданных всех загруженных планов."""
        return list(self.analyzer.plan_metadata.values())

    def get_available_years(self) -> List[str]:
        """Возвращает список доступных годов начала подготовки."""
        return self.analyzer.get_available_years()

    def get_available_academic_years(self) -> List[str]:
        """Возвращает список доступных конкретных учебных годов (напр., ['2025/2026'])."""
        return self.analyzer.get_available_academic_years()

    def get_available_courses(self) -> List[int]:
        """Возвращает список доступных курсов обучения (1-6)."""
        return self.analyzer.get_available_courses()

    def get_pairs(
        self,
        search: Optional[str] = None,
        dept_filter: Optional[str] = None,
        year_filter: Optional[str] = None,
        course_filter: Optional[int] = None,
        academic_year_filter: Optional[str] = None,
    ) -> List[DisciplineDeptPair]:
        """Возвращает список пар 'Дисциплина - Кафедра' с поддержкой поиска и фильтрации."""
        pairs = self.analyzer.get_all_pairs(
            start_year=year_filter,
            course=course_filter,
            academic_year=academic_year_filter,
        )
        if search:
            s = search.lower()
            pairs = [p for p in pairs if s in p.discipline_title.lower() or s in p.dept_name.lower()]
        if dept_filter:
            d = dept_filter.lower()
            pairs = [p for p in pairs if d in p.dept_name.lower() or d == p.dept_code]
        return pairs

    def get_conflicts(
        self,
        search: Optional[str] = None,
        year_filter: Optional[str] = None,
        course_filter: Optional[int] = None,
        academic_year_filter: Optional[str] = None,
    ) -> List[DepartmentConflict]:
        """Возвращает список коллизий закрепления кафедр."""
        conflicts = self.analyzer.find_conflicts(
            start_year=year_filter,
            course=course_filter,
            academic_year=academic_year_filter,
        )
        if search:
            s = search.lower()
            conflicts = [
                c for c in conflicts
                if s in c.discipline_title.lower() or any(s in d.lower() for d in c.departments)
            ]
        return conflicts

    def get_control_conflicts(
        self,
        search: Optional[str] = None,
        year_filter: Optional[str] = None,
        course_filter: Optional[int] = None,
        academic_year_filter: Optional[str] = None,
    ) -> List[ControlFormConflict]:
        """Возвращает коллизии форм контроля с фильтрацией."""
        conflicts = self.analyzer.find_control_conflicts(
            start_year=year_filter,
            course=course_filter,
            academic_year=academic_year_filter,
        )
        if search:
            s = search.strip().lower()
            conflicts = [
                c for c in conflicts
                if s in c.discipline_title.lower() or any(s in f.lower() for f in c.forms)
            ]
        return conflicts

    def get_semester_control_audits(
        self,
        max_exams: int = 5,
        max_passes: int = 6,
        max_course_works: int = 2,
        overloaded_only: bool = False,
        search: Optional[str] = None,
        year_filter: Optional[str] = None,
        course_filter: Optional[int] = None,
        academic_year_filter: Optional[str] = None,
    ) -> List[SemesterAuditResult]:
        """Возвращает результаты нормативного аудита нагрузки в семестрах."""
        audits = self.analyzer.audit_semester_controls(
            max_exams=max_exams,
            max_passes=max_passes,
            max_course_works=max_course_works,
            start_year=year_filter,
            course=course_filter,
            academic_year=academic_year_filter,
        )
        if overloaded_only:
            audits = [a for a in audits if a.is_overloaded]
        if search:
            s = search.strip().lower()
            audits = [
                a for a in audits
                if s in a.plan_name.lower() or s in a.direction_title.lower() or s in a.direction_code.lower()
            ]
        return audits

    def get_control_audit_summary(
        self,
        max_exams: int = 5,
        max_passes: int = 6,
        max_course_works: int = 2,
        year_filter: Optional[str] = None,
        course_filter: Optional[int] = None,
        academic_year_filter: Optional[str] = None,
    ) -> ControlAuditSummary:
        """Возвращает сводные счетчики по формам контроля и аудиту семестров."""
        conflicts = self.get_control_conflicts(
            year_filter=year_filter,
            course_filter=course_filter,
            academic_year_filter=academic_year_filter,
        )
        audits = self.get_semester_control_audits(
            max_exams=max_exams,
            max_passes=max_passes,
            max_course_works=max_course_works,
            year_filter=year_filter,
            course_filter=course_filter,
            academic_year_filter=academic_year_filter,
        )
        overloaded = sum(1 for a in audits if a.is_overloaded)
        return ControlAuditSummary(
            conflicts_count=len(conflicts),
            overloaded_semesters_count=overloaded,
            conflicts=conflicts,
            semester_audits=audits,
        )

    def get_similarities(
        self,
        min_score: float = 0.75,
        use_embeddings: bool = True,
        hidden_only: bool = False,
    ) -> List[DisciplineSimilarityPair]:
        """Вычисляет и возвращает пары похожих дисциплин."""
        if (
            self._cached_similarities is None
            or self._last_similarity_threshold != min_score
        ):
            self._cached_similarities = self.similarity_engine.compute_similarity_pairs(
                self.analyzer.occurrences_by_discipline,
                min_score=min_score,
                use_embeddings=use_embeddings,
            )
            self._last_similarity_threshold = min_score

        sims = self._cached_similarities
        if hidden_only:
            sims = [s for s in sims if s.is_hidden_conflict]
        return sims

    def get_departments_catalog(self) -> List[Dict[str, Any]]:
        """Возвращает список кафедр."""
        return self.analyzer.get_departments_summary()

    # --- Дисциплина как единица анализа ---

    def get_discipline_profiles(
        self,
        search: Optional[str] = None,
        industry: Optional[str] = None,
        teacher_id: Optional[str] = None,
        dept: Optional[str] = None,
        year: Optional[str] = None,
        course: Optional[int] = None,
        academic_year: Optional[str] = None,
        conflict_only: bool = False,
    ) -> List[DisciplineProfile]:
        """
        Формирует профили всех дисциплин как центральных единиц анализа
        с привязкой к отрасли, преподавателям, планам и кафедрам.
        """
        profiles: List[DisciplineProfile] = []

        # Карта коллизий для быстрого O(1) поиска
        conflicts = {c.discipline_title: c for c in self.analyzer.find_conflicts()}
        control_conflicts = {c.discipline_title: c for c in self.analyzer.find_control_conflicts()}

        for title, occurrences in self.analyzer.occurrences_by_discipline.items():
            # Фильтрация по году набора, курсу и конкретному учебному году на уровне вхождений
            filtered_occs = [
                occ for occ in occurrences
                if self.analyzer._matches_filters(occ, start_year=year, course=course, academic_year=academic_year)
            ]
            if not filtered_occs and occurrences:
                # Если фильтр по году набора, курсу или учебному году активен и ни одно вхождение не подошло
                if year or (course and course > 0) or (academic_year and academic_year.strip()):
                    continue

            # Получаем отрасль и преподавателей из хранилища
            assigned_ind, assigned_teachers = self.storage.get_discipline_binding(title)

            active_occs = filtered_occs or occurrences
            # Кафедры
            depts_set = {occ.dept_name for occ in active_occs if occ.dept_name}
            dept_codes_set = {occ.dept_code for occ in active_occs if occ.dept_code}
            plans_set = {occ.plan_file for occ in active_occs}
            semesters_set = {occ.semester for occ in active_occs if occ.semester > 0}
            ay_set = {occ.academic_year for occ in active_occs if occ.academic_year}

            # Расчет трудоемкости дисциплины (единицы анализа):
            # В разных планах дисциплина имеет свой нормативный объем (например 3 ЗЕТ / 108 ч).
            unique_zes = sorted(list({occ.total_ze for occ in active_occs if occ.total_ze > 0}))
            unique_hours = sorted(list({occ.total_hours for occ in active_occs if occ.total_hours > 0}))

            sum_z = sum(occ.total_ze for occ in active_occs)
            sum_h = sum(occ.total_hours for occ in active_occs)

            if len(unique_zes) == 1:
                ze_disp = str(unique_zes[0])
                canonical_ze = unique_zes[0]
            elif len(unique_zes) > 1:
                ze_disp = f"{unique_zes[0]}–{unique_zes[-1]}"
                canonical_ze = unique_zes[-1]
            else:
                ze_disp = "—"
                canonical_ze = 0

            if len(unique_hours) == 1:
                hours_disp = str(unique_hours[0])
                canonical_hours = unique_hours[0]
            elif len(unique_hours) > 1:
                hours_disp = f"{unique_hours[0]}–{unique_hours[-1]}"
                canonical_hours = unique_hours[-1]
            else:
                hours_disp = "—"
                canonical_hours = 0

            # Формы контроля
            ctrl_forms_set = set()
            for occ in active_occs:
                if occ.control_forms:
                    ctrl_forms_set.update(occ.control_forms)
                elif occ.exam_type:
                    ctrl_forms_set.add(occ.exam_type.lower())

            has_ctrl_conf = title in control_conflicts or len(ctrl_forms_set) > 1
            ctrl_details = ""
            if has_ctrl_conf:
                ctrl_details = f"Расхождение: {', '.join(sorted(list(ctrl_forms_set)))}"

            has_conf = title in conflicts or len(depts_set) > 1

            # Фильтры
            if conflict_only and not has_conf:
                continue

            if industry and industry.strip():
                if (assigned_ind or "").strip().lower() != industry.strip().lower():
                    continue

            if teacher_id and teacher_id.strip():
                if not any(t.id == teacher_id.strip() for t in assigned_teachers):
                    continue

            if dept and dept.strip():
                d_lower = dept.strip().lower()
                if not any(d_lower in d.lower() for d in depts_set) and dept.strip() not in dept_codes_set:
                    continue

            if search and search.strip():
                s = search.strip().lower()
                matches_search = (
                    s in title.lower()
                    or (assigned_ind and s in assigned_ind.lower())
                    or any(s in t.name.lower() for t in assigned_teachers)
                    or any(s in d.lower() for d in depts_set)
                )
                if not matches_search:
                    continue

            profiles.append(
                DisciplineProfile(
                    title=title,
                    normalized_title=" ".join(title.lower().split()),
                    industry=assigned_ind,
                    teachers=assigned_teachers,
                    departments=sorted(list(depts_set)),
                    department_codes=sorted(list(dept_codes_set)),
                    plans_count=len(plans_set),
                    has_conflict=has_conf,
                    total_hours=canonical_hours,
                    total_ze=canonical_ze,
                    ze_display=ze_disp,
                    hours_display=hours_disp,
                    sum_ze=sum_z,
                    sum_hours=sum_h,
                    semesters=sorted(list(semesters_set)),
                    academic_years=sorted(list(ay_set)),
                    occurrences=active_occs,
                    exam_types=sorted(list(ctrl_forms_set)),
                    has_control_conflict=has_ctrl_conf,
                    control_conflict_details=ctrl_details,
                )
            )

        # Добавляем дисциплины, которые уже есть в реестре/справочнике связок,
        # даже если они еще не загружены в виде файлов планов
        seen_titles = {p.title for p in profiles}
        for stored_title in self.storage.discipline_bindings.keys():
            if stored_title in seen_titles:
                continue
            if year or (course and course > 0) or (academic_year and academic_year.strip()) or (dept and dept.strip()) or conflict_only:
                continue

            assigned_ind, assigned_teachers = self.storage.get_discipline_binding(stored_title)
            if industry and industry.strip():
                if (assigned_ind or "").strip().lower() != industry.strip().lower():
                    continue
            if teacher_id and teacher_id.strip():
                if not any(t.id == teacher_id.strip() for t in assigned_teachers):
                    continue
            if search and search.strip():
                s = search.strip().lower()
                matches_search = (
                    s in stored_title.lower()
                    or (assigned_ind and s in assigned_ind.lower())
                    or any(s in t.name.lower() for t in assigned_teachers)
                )
                if not matches_search:
                    continue

            profiles.append(
                DisciplineProfile(
                    title=stored_title,
                    normalized_title=" ".join(stored_title.lower().split()),
                    industry=assigned_ind,
                    teachers=assigned_teachers,
                    departments=[],
                    department_codes=[],
                    plans_count=0,
                    has_conflict=False,
                    total_hours=0,
                    total_ze=0,
                    ze_display="—",
                    hours_display="—",
                    sum_ze=0,
                    sum_hours=0,
                    semesters=[],
                    academic_years=[],
                    occurrences=[],
                )
            )

        profiles.sort(key=lambda p: (not p.has_conflict, -p.plans_count, p.title.lower()))
        return profiles

    # --- Управление преподавателями и отраслями ---

    def get_teachers(self) -> List[Teacher]:
        return self.storage.get_teachers()

    def add_teacher(self, name: str, department: str = "", position: str = "") -> Teacher:
        return self.storage.add_teacher(name, department, position)

    def delete_teacher(self, teacher_id: str) -> bool:
        return self.storage.delete_teacher(teacher_id)

    def get_industries(self) -> List[Industry]:
        return self.storage.get_industries()

    def add_industry(self, name: str, description: str = "") -> Industry:
        return self.storage.add_industry(name, description)

    def delete_industry(self, industry_id: str) -> bool:
        return self.storage.delete_industry(industry_id)

    def bind_discipline(
        self,
        discipline_title: str,
        industry: Optional[str] = None,
        teacher_ids: Optional[List[str]] = None,
    ):
        """Привязывает отрасль и преподавателей к дисциплине."""
        self.storage.set_discipline_binding(discipline_title, industry=industry, teacher_ids=teacher_ids)

    def import_teachers_file(self, content: bytes, filename: str) -> int:
        return self.storage.import_teachers_file(content, filename)

    def import_industries_file(self, content: bytes, filename: str) -> int:
        return self.storage.import_industries_file(content, filename)

    def import_bindings_file(self, content: bytes, filename: str) -> int:
        return self.storage.import_bindings_file(content, filename)

    def export_excel(self) -> bytes:
        profiles = self.get_discipline_profiles()
        audits = self.get_semester_control_audits()
        return self.storage.export_to_excel(profiles, semester_audits=audits)

    # --- Staging & Diff ---

    def stage_change(self, change: ChangeRequest) -> List[PlannedFileChange]:
        """Добавляет запрос на изменение в корзину."""
        self.staged_changes.append(change)
        return self.preview_staged_changes()

    def remove_staged_change(self, index: int) -> List[PlannedFileChange]:
        """Удаляет запрос на изменение из корзины по индексу."""
        if 0 <= index < len(self.staged_changes):
            self.staged_changes.pop(index)
        return self.preview_staged_changes()

    def clear_staged_changes(self):
        """Очищает корзину изменений."""
        self.staged_changes.clear()

    def get_staged_requests(self) -> List[ChangeRequest]:
        """Возвращает текущие запросы на изменение."""
        return self.staged_changes

    def preview_staged_changes(self) -> List[PlannedFileChange]:
        """
        Генерирует предварительный просмотр всех запланированных изменений
        в файлах без сохранения на диск (diff preview).
        """
        all_diffs: List[PlannedFileChange] = []

        # Группируем запросы по дисциплине
        for req in self.staged_changes:
            occs = self.analyzer.occurrences_by_discipline.get(req.discipline_title, [])
            for occ in occs:
                # Если указаны конкретные файлы, фильтруем
                if req.affected_plan_files and occ.plan_file not in req.affected_plan_files:
                    continue

                change_types = []
                orig_dept_code = occ.dept_code
                orig_dept_name = occ.dept_name
                new_dept_code = None
                new_dept_name = None
                new_title = None

                # Проверяем смену кафедры
                if req.target_dept_code is not None and req.target_dept_code != orig_dept_code:
                    new_dept_code = req.target_dept_code
                    new_dept_name = req.target_dept_name or f"Кафедра № {req.target_dept_code}"
                    change_types.append("Кафедра")

                # Проверяем переименование
                if req.new_discipline_title and req.new_discipline_title != req.discipline_title:
                    new_title = req.new_discipline_title
                    change_types.append("Название")

                if change_types:
                    all_diffs.append(
                        PlannedFileChange(
                            file_path=occ.plan_file,
                            file_name=occ.plan_name,
                            row_code=occ.row_code,
                            original_title=occ.discipline_title if hasattr(occ, "discipline_title") else req.discipline_title,
                            new_title=new_title,
                            original_dept_code=orig_dept_code,
                            original_dept_name=orig_dept_name,
                            new_dept_code=new_dept_code,
                            new_dept_name=new_dept_name,
                            change_type=" и ".join(change_types),
                        )
                    )

        return all_diffs

    def apply_changes(
        self,
        backup: bool = True,
        output_dir: Optional[str] = None,
    ) -> ApplyChangesResponse:
        """
        Применяет все запланированные изменения физически к файлам планов на диске.
        """
        if not self.staged_changes:
            return ApplyChangesResponse(
                success=True,
                modified_files_count=0,
                total_modifications=0,
                backup_created=backup,
                output_directory=output_dir,
                details=["Нет запланированных изменений."],
            )

        # Собираем затронутые файлы
        files_to_containers: Dict[str, PLXFileContainer] = {}
        for req in self.staged_changes:
            occs = self.analyzer.occurrences_by_discipline.get(req.discipline_title, [])
            for occ in occs:
                if req.affected_plan_files and occ.plan_file not in req.affected_plan_files:
                    continue
                if occ.plan_file not in files_to_containers:
                    if os.path.exists(occ.plan_file):
                        try:
                            files_to_containers[occ.plan_file] = PLXFileContainer(occ.plan_file)
                        except Exception:
                            pass

        total_mods = 0
        details = []
        errors = []

        # Применяем изменения в XML-контейнерах
        for req in self.staged_changes:
            for file_path, container in files_to_containers.items():
                if req.affected_plan_files and file_path not in req.affected_plan_files:
                    continue
                try:
                    mods = container.modify_discipline(
                        discipline_title=req.discipline_title,
                        new_dept_code=req.target_dept_code,
                        new_dept_name=req.target_dept_name,
                        new_discipline_title=req.new_discipline_title,
                    )
                    total_mods += len(mods)
                    for m in mods:
                        details.append(
                            f"[{m.file_name}] Дисциплина '{m.original_title}': {m.change_type} -> "
                            f"{m.new_dept_name or m.new_title}"
                        )
                except Exception as e:
                    errors.append(f"Ошибка модификации в файле {file_path}: {e}")

        # Физически сохраняем измененные контейнеры
        modified_files_count = 0
        for file_path, container in files_to_containers.items():
            try:
                saved_path = container.save(backup=backup, output_dir=output_dir)
                modified_files_count += 1
            except Exception as e:
                errors.append(f"Ошибка сохранения файла {file_path}: {e}")

        # Очищаем корзину изменений и обновляем данные
        self.staged_changes.clear()
        self._cached_similarities = None

        return ApplyChangesResponse(
            success=len(errors) == 0,
            modified_files_count=modified_files_count,
            total_modifications=total_mods,
            backup_created=backup and (output_dir is None),
            output_directory=output_dir,
            details=details,
            errors=errors,
        )
