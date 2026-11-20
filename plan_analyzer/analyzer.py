"""
Аналитический модуль для извлечения пар 'дисциплина-кафедра' и выявления коллизий.
"""
import os
import glob
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional, Set, Any

from curriculum_parser import parse_curriculum_plan, CurriculumPlanData
from plan_analyzer.models import (
    PlanMetadata,
    DisciplineOccurrence,
    DisciplineDeptPair,
    DepartmentConflict,
    ControlFormConflict,
    SemesterAuditResult,
)


def normalize_discipline_title(title: str) -> str:
    """Нормализует строку названия дисциплины (лишние пробелы, регистр)."""
    if not title:
        return ""
    # Очистка неразрывных пробелов и множественных пробелов
    clean = " ".join(title.replace("\xa0", " ").strip().split())
    return clean


def calculate_academic_year(start_year: str, semester: int) -> str:
    """
    Вычисляет конкретный учебный год (напр., '2025/2026')
    на основе года начала подготовки (набора) и номера семестра.
    """
    try:
        sy = int(str(start_year).strip())
        course = (semester + 1) // 2 if semester > 0 else 1
        ay_start = sy + course - 1
        return f"{ay_start}/{ay_start + 1}"
    except (ValueError, TypeError):
        return ""


class PlanAnalyzer:
    """Анализатор пакета учебных планов."""

    def __init__(self):
        self.plans: Dict[str, CurriculumPlanData] = {}
        self.plan_metadata: Dict[str, PlanMetadata] = {}
        self.occurrences_by_discipline: Dict[str, List[DisciplineOccurrence]] = defaultdict(list)
        self.raw_files_bytes: Dict[str, bytes] = {}

    def load_files(self, file_paths: List[str]) -> List[PlanMetadata]:
        """Загружает список файлов планов с диска."""
        results = []
        for path in file_paths:
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                content = f.read()
            meta = self.load_plan_bytes(content, filename=os.path.basename(path), file_path=path)
            if meta:
                results.append(meta)
        return results

    def load_directory(self, dir_path: str, recursive: bool = True) -> List[PlanMetadata]:
        """Ищет и загружает все plx и xml файлы из директории."""
        if not os.path.isdir(dir_path):
            raise FileNotFoundError(f"Каталог не найден: {dir_path}")

        pattern = os.path.join(dir_path, "**/*" if recursive else "*")
        found_files = []
        for ext in (".plx", ".xml"):
            found_files.extend(glob.glob(f"{pattern}{ext}", recursive=recursive))

        return self.load_files(sorted(list(set(found_files))))

    def remove_plan(self, file_path: str) -> bool:
        """
        Удаляет план и все его дисциплины из анализатора.
        Поддерживает поиск по точному пути, нормализованному пути, абсолютному пути или имени файла.
        """
        target_key = None
        # 1. Прямой поиск по ключу
        if file_path in self.plans:
            target_key = file_path
        else:
            # 2. Гибкий поиск: нормализованный, абсолютный путь или базовое имя файла
            norm_target = os.path.normpath(file_path)
            abs_target = os.path.abspath(file_path)
            base_target = os.path.basename(file_path)

            for key in list(self.plans.keys()):
                if (
                    os.path.normpath(key) == norm_target
                    or os.path.abspath(key) == abs_target
                    or key.endswith(norm_target)
                    or norm_target.endswith(key)
                    or os.path.basename(key) == base_target
                ):
                    target_key = key
                    break

        if not target_key:
            return False

        del self.plans[target_key]
        self.raw_files_bytes.pop(target_key, None)
        self.plan_metadata.pop(target_key, None)

        # Удаляем вхождения из occurrences_by_discipline
        titles_to_delete = []
        for title, occurrences in self.occurrences_by_discipline.items():
            self.occurrences_by_discipline[title] = [
                occ for occ in occurrences
                if occ.plan_file != target_key and os.path.basename(occ.plan_file) != os.path.basename(target_key)
            ]
            if not self.occurrences_by_discipline[title]:
                titles_to_delete.append(title)

        for title in titles_to_delete:
            del self.occurrences_by_discipline[title]

        return True

    def load_plan_bytes(
        self,
        content: bytes,
        filename: str,
        file_path: Optional[str] = None
    ) -> Optional[PlanMetadata]:
        """Парсит и регистрирует один учебный план."""
        effective_path = file_path or filename
        try:
            plan = parse_curriculum_plan(content, filename=filename)
        except Exception:
            # Если файл не является валидным планом или поврежден
            return None

        # Если план с таким путем уже был загружен, сначала очищаем его предыдущее состояние
        if effective_path in self.plans:
            self.remove_plan(effective_path)

        self.plans[effective_path] = plan
        self.raw_files_bytes[effective_path] = content

        meta = PlanMetadata(
            file_path=effective_path,
            file_name=filename,
            direction_code=plan.direction_code,
            direction_title=plan.direction_title,
            profile_title=plan.profile_title,
            edu_level=plan.edu_level,
            study_form=plan.study_form,
            start_year=str(plan.start_year),
            faculty=str(getattr(plan, "faculty", "") or getattr(plan, "qualification", "")),
            total_disciplines=len(plan.disciplines),
        )
        self.plan_metadata[effective_path] = meta

        # Регистрируем вхождения дисциплин
        for d in plan.disciplines:
            norm_title = normalize_discipline_title(d.title)
            if not norm_title:
                continue

            dept_name = (d.dept_name or "").strip() or "Не указана"
            dept_code = str(d.dept_code or "").strip()
            c_num = (d.semester + 1) // 2 if d.semester > 0 else 1
            ay_str = calculate_academic_year(str(plan.start_year), d.semester)

            raw_exam = (getattr(d, "exam_type", "") or "").strip().lower()
            ctrl_forms = [f.strip().lower() for f in raw_exam.split(",") if f.strip()]
            if not ctrl_forms and raw_exam:
                ctrl_forms = [raw_exam]
            sem_ctrls = getattr(d, "semester_controls", {}) or {}

            occ = DisciplineOccurrence(
                plan_file=effective_path,
                plan_name=filename,
                direction_code=plan.direction_code,
                direction_title=plan.direction_title,
                profile_title=plan.profile_title,
                start_year=str(plan.start_year),
                dept_code=dept_code,
                dept_name=dept_name,
                semester=d.semester,
                semesters_str=d.semesters_str,
                academic_year=ay_str,
                course=c_num,
                total_ze=d.total_ze,
                total_hours=d.total_hours,
                row_code=getattr(d, "row_code", "") or "",
                exam_type=raw_exam,
                control_forms=ctrl_forms,
                semester_controls=sem_ctrls,
            )
            self.occurrences_by_discipline[norm_title].append(occ)

        return meta

    def get_available_years(self) -> List[str]:
        """Возвращает отсортированный список уникальных годов набора/начала подготовки."""
        years = {meta.start_year.strip() for meta in self.plan_metadata.values() if meta.start_year}
        return sorted([y for y in years if y and y != "0"])

    def get_available_academic_years(self) -> List[str]:
        """Возвращает отсортированный список обнаруженных конкретных учебных годов (напр., ['2025/2026'])."""
        ay_set = set()
        for occurrences in self.occurrences_by_discipline.values():
            for occ in occurrences:
                if occ.academic_year:
                    ay_set.add(occ.academic_year)
        return sorted(list(ay_set))

    def get_available_courses(self) -> List[int]:
        """Возвращает список обнаруженных курсов обучения (1-6)."""
        courses = set()
        for occurrences in self.occurrences_by_discipline.values():
            for occ in occurrences:
                if occ.semester > 0:
                    courses.add((occ.semester + 1) // 2)
        return sorted(list(courses)) if courses else [1, 2, 3, 4]

    def _matches_filters(
        self,
        occ: DisciplineOccurrence,
        start_year: Optional[str] = None,
        course: Optional[int] = None,
        academic_year: Optional[str] = None,
    ) -> bool:
        """Проверяет соответствие вхождения фильтрам по году набора, курсу и конкретному учебному году."""
        if start_year and str(start_year).strip() != "":
            if occ.start_year.strip() != str(start_year).strip():
                return False
        if course is not None and course > 0:
            occ_course = occ.course if occ.course > 0 else ((occ.semester + 1) // 2 if occ.semester > 0 else 1)
            if occ_course != course:
                return False
        if academic_year and str(academic_year).strip() != "":
            if occ.academic_year != str(academic_year).strip():
                return False
        return True

    def get_all_pairs(
        self,
        start_year: Optional[str] = None,
        course: Optional[int] = None,
        academic_year: Optional[str] = None,
    ) -> List[DisciplineDeptPair]:
        """
        Возвращает список всех уникальных пар 'Дисциплина — Кафедра'.
        Поддерживает фильтрацию по году начала подготовки, курсу и конкретному учебному году.
        """
        pairs_dict: Dict[Tuple[str, str, str], List[DisciplineOccurrence]] = defaultdict(list)

        for disc_title, occurrences in self.occurrences_by_discipline.items():
            for occ in occurrences:
                if not self._matches_filters(occ, start_year=start_year, course=course, academic_year=academic_year):
                    continue
                key = (disc_title, occ.dept_name, occ.dept_code)
                pairs_dict[key].append(occ)

        result: List[DisciplineDeptPair] = []
        for (disc_title, dept_name, dept_code), occurrences in pairs_dict.items():
            unique_plans = {occ.plan_file for occ in occurrences}
            result.append(
                DisciplineDeptPair(
                    discipline_title=disc_title,
                    dept_name=dept_name,
                    dept_code=dept_code,
                    plans_count=len(unique_plans),
                    occurrences=occurrences,
                )
            )

        # Сортировка по алфавиту дисциплины, затем кафедры
        result.sort(key=lambda p: (p.discipline_title.lower(), p.dept_name.lower()))
        return result

    def find_conflicts(
        self,
        start_year: Optional[str] = None,
        course: Optional[int] = None,
        academic_year: Optional[str] = None,
    ) -> List[DepartmentConflict]:
        """
        Ищет коллизии: ситуации, когда одна и та же дисциплина закреплена
        за разными кафедрами в разных планах (с учетом фильтрации по году/курсу/учебному году).
        """
        conflicts: List[DepartmentConflict] = []

        for disc_title, occurrences in self.occurrences_by_discipline.items():
            # Фильтруем вхождения
            filtered_occs = [
                occ for occ in occurrences
                if self._matches_filters(occ, start_year=start_year, course=course, academic_year=academic_year)
            ]
            if not filtered_occs:
                continue

            # Группируем вхождения по кафедре
            by_dept: Dict[str, List[DisciplineOccurrence]] = defaultdict(list)
            dept_codes_map: Dict[str, str] = {}

            for occ in filtered_occs:
                dept_label = occ.dept_name
                if occ.dept_code and occ.dept_code != "0":
                    dept_label = f"{occ.dept_name} (№ {occ.dept_code})"
                by_dept[dept_label].append(occ)
                dept_codes_map[dept_label] = occ.dept_code

            # Коллизия возникает, если кафедр больше одной
            if len(by_dept) > 1:
                # Определяем рекомендованную кафедру (наибольшее число планов)
                dept_counts = {
                    d_name: len({occ.plan_file for occ in occs})
                    for d_name, occs in by_dept.items()
                }
                suggested_dept = max(dept_counts.items(), key=lambda item: item[1])[0]

                conflicts.append(
                    DepartmentConflict(
                        discipline_title=disc_title,
                        departments=list(by_dept.keys()),
                        department_codes=[dept_codes_map[d] for d in by_dept.keys()],
                        total_occurrences=len(filtered_occs),
                        by_department=dict(by_dept),
                        suggested_target_dept=suggested_dept,
                    )
                )

        # Сортируем: сначала те, у которых больше всего коллизий/вхождений
        conflicts.sort(key=lambda c: (-len(c.departments), -c.total_occurrences, c.discipline_title))
        return conflicts

    def get_departments_summary(self) -> List[Dict[str, Any]]:
        """Возвращает сводку по всем кафедрам: количество читаемых дисциплин и планов."""
        dept_stats = defaultdict(lambda: {"codes": set(), "disciplines": set(), "plans": set()})

        for disc_title, occurrences in self.occurrences_by_discipline.items():
            for occ in occurrences:
                stats = dept_stats[occ.dept_name]
                if occ.dept_code:
                    stats["codes"].add(occ.dept_code)
                stats["disciplines"].add(disc_title)
                stats["plans"].add(occ.plan_file)

        summary = []
        for dept_name, stats in dept_stats.items():
            summary.append({
                "dept_name": dept_name,
                "dept_codes": sorted(list(stats["codes"])),
                "disciplines_count": len(stats["disciplines"]),
                "plans_count": len(stats["plans"]),
            })

        summary.sort(key=lambda s: -s["disciplines_count"])
        return summary

    def find_control_conflicts(
        self,
        start_year: Optional[str] = None,
        course: Optional[int] = None,
        academic_year: Optional[str] = None,
    ) -> List[ControlFormConflict]:
        """
        Находит коллизии форм контроля: дисциплины, по которым в разных планах установлены
        различные формы промежуточной аттестации (например, в одном плане Экзамен, в другом Зачет).
        """
        conflicts: List[ControlFormConflict] = []

        for disc_title, occurrences in self.occurrences_by_discipline.items():
            filtered_occs = [
                occ for occ in occurrences
                if self._matches_filters(occ, start_year=start_year, course=course, academic_year=academic_year)
            ]
            if len(filtered_occs) < 2:
                continue

            by_form = defaultdict(list)
            for occ in filtered_occs:
                form_key = (occ.exam_type or "не указана").strip().lower()
                by_form[form_key].append(occ)

            if len(by_form) > 1:
                # Рекомендованная форма контроля (по большинству планов)
                form_counts = {
                    form: len({occ.plan_file for occ in occs})
                    for form, occs in by_form.items()
                }
                suggested_form = max(form_counts.items(), key=lambda item: item[1])[0]

                conflicts.append(
                    ControlFormConflict(
                        discipline_title=disc_title,
                        forms=sorted(list(by_form.keys())),
                        total_occurrences=len(filtered_occs),
                        by_form=dict(by_form),
                        suggested_form=suggested_form,
                    )
                )

        conflicts.sort(key=lambda c: (-len(c.forms), -c.total_occurrences, c.discipline_title))
        return conflicts

    def audit_semester_controls(
        self,
        max_exams: int = 5,
        max_passes: int = 6,
        max_course_works: int = 2,
        start_year: Optional[str] = None,
        course: Optional[int] = None,
        academic_year: Optional[str] = None,
    ) -> List[SemesterAuditResult]:
        """
        Выполняет нормативный аудит семестров по всем планам.
        Проверяет лимиты ФГОС и локальных актов:
        - не более max_exams экзаменов в сессию (по умолч. 5)
        - не более max_passes зачетов в семестр (по умолч. 6)
        - не более max_course_works курсовых работ/проектов в семестр (по умолч. 2)
        """
        results: List[SemesterAuditResult] = []

        # Карта названий дисциплин для детального отображения
        title_by_occ_key = {}
        for title, occurrences in self.occurrences_by_discipline.items():
            for o in occurrences:
                title_by_occ_key[id(o)] = title
                if o.row_code:
                    title_by_occ_key[(o.plan_file, o.row_code)] = title

        # Группировка вхождений по плану и семестру
        plan_semester_occs = defaultdict(list)
        for disc_title, occurrences in self.occurrences_by_discipline.items():
            for occ in occurrences:
                if not self._matches_filters(occ, start_year=start_year, course=course, academic_year=academic_year):
                    continue
                # Дисциплина может читаться в конкретном семестре
                plan_semester_occs[(occ.plan_file, occ.semester)].append(occ)

        for (p_file, sem_num), occs in plan_semester_occs.items():
            if not occs:
                continue
            sample = occs[0]
            c_num = sample.course if sample.course > 0 else ((sem_num + 1) // 2 if sem_num > 0 else 1)
            ay_str = sample.academic_year

            exams_discs = []
            pass_discs = []
            diff_pass_discs = []
            cw_discs = []

            for occ in occs:
                # Получаем формы контроля для текущего семестра
                forms = []
                if occ.semester_controls and sem_num in occ.semester_controls:
                    forms = occ.semester_controls[sem_num]
                elif occ.control_forms:
                    forms = occ.control_forms
                elif occ.exam_type:
                    forms = [occ.exam_type]

                for f in forms:
                    f_low = f.lower()
                    if "экз" in f_low:
                        exams_discs.append(occ)
                    elif "диф" in f_low:
                        diff_pass_discs.append(occ)
                    elif "зач" in f_low:
                        pass_discs.append(occ)
                    if "курсов" in f_low or "кп" in f_low or "кр" in f_low:
                        cw_discs.append(occ)

            e_count = len(exams_discs)
            p_count = len(pass_discs)
            dp_count = len(diff_pass_discs)
            cw_count = len(cw_discs)

            violations = []
            if e_count > max_exams:
                violations.append(f"Превышен лимит экзаменов: {e_count} (норма: не более {max_exams})")
            if (p_count + dp_count) > max_passes:
                violations.append(f"Превышен лимит зачетов: {p_count + dp_count} (норма: не более {max_passes})")
            if cw_count > max_course_works:
                violations.append(f"Превышен лимит курсовых работ/проектов: {cw_count} (норма: не более {max_course_works})")

            def get_titles(occs_list):
                seen = set()
                res = []
                for o in occs_list:
                    t = title_by_occ_key.get((o.plan_file, o.row_code), title_by_occ_key.get(id(o), ""))
                    if t and t not in seen:
                        seen.add(t)
                        res.append(t)
                return res

            disc_by_ctrl = {
                "экзамены": get_titles(exams_discs),
                "зачеты": get_titles(pass_discs),
                "диф_зачеты": get_titles(diff_pass_discs),
                "курсовые": get_titles(cw_discs),
            }

            results.append(
                SemesterAuditResult(
                    plan_file=sample.plan_file,
                    plan_name=sample.plan_name,
                    direction_code=sample.direction_code,
                    direction_title=sample.direction_title,
                    semester=sem_num,
                    course=c_num,
                    academic_year=ay_str,
                    exams_count=e_count,
                    pass_count=p_count,
                    diff_pass_count=dp_count,
                    course_works_count=cw_count,
                    is_overloaded=len(violations) > 0,
                    violations=violations,
                    disciplines_by_control=disc_by_ctrl,
                )
            )

        results.sort(key=lambda r: (not r.is_overloaded, r.plan_name, r.semester))
        return results
