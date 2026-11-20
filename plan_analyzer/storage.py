"""
Модуль постоянного хранения справочников преподавателей, отраслей и привязок к дисциплинам.
Поддерживает ручное управление, загрузку из Excel (.xlsx) и CSV, а также экспорт в Excel.
"""
import os
import io
import csv
import json
import uuid
from typing import Dict, List, Optional, Tuple, Any
import openpyxl

from plan_analyzer.models import Teacher, Industry, DisciplineProfile


def generate_short_id() -> str:
    """Генерирует короткий уникальный ID."""
    return uuid.uuid4().hex[:8]


class RegistryStorage:
    """Хранилище справочников преподавателей, отраслей и связей с дисциплинами."""

    def __init__(self, storage_path: str = "data/registry_store.json"):
        self.storage_path = storage_path
        self.teachers: Dict[str, Teacher] = {}
        self.industries: Dict[str, Industry] = {}
        self.discipline_bindings: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        """Загрузка данных из JSON-файла."""
        if not os.path.exists(self.storage_path):
            self._init_defaults()
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for t_id, t_dict in data.get("teachers", {}).items():
                self.teachers[t_id] = Teacher(**t_dict)

            for i_id, i_dict in data.get("industries", {}).items():
                self.industries[i_id] = Industry(**i_dict)

            self.discipline_bindings = data.get("discipline_bindings", {})
        except Exception:
            self._init_defaults()

    def _init_defaults(self):
        """Инициализация базовыми отраслями по умолчанию."""
        default_industries = [
            "Информационные технологии",
            "Математика и механика",
            "Юриспруденция",
            "Экономика и управление",
            "Гуманитарные науки",
            "Естественные науки",
            "Инженерия и технологии",
            "Физическая культура и спорт",
        ]
        for ind_name in default_industries:
            iid = generate_short_id()
            self.industries[iid] = Industry(id=iid, name=ind_name)
        self.save()

    def save(self):
        """Сохранение состояния на диск."""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        data = {
            "teachers": {t_id: t.model_dump() for t_id, t in self.teachers.items()},
            "industries": {i_id: ind.model_dump() for i_id, ind in self.industries.items()},
            "discipline_bindings": self.discipline_bindings,
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # --- Преподаватели ---

    def get_teachers(self) -> List[Teacher]:
        """Возвращает отсортированный список всех преподавателей."""
        return sorted(list(self.teachers.values()), key=lambda t: t.name)

    def add_teacher(self, name: str, department: str = "", position: str = "") -> Teacher:
        """Добавляет нового преподавателя."""
        name = name.strip()
        # Проверяем, существует ли уже
        for t in self.teachers.values():
            if t.name.lower() == name.lower():
                return t

        tid = generate_short_id()
        teacher = Teacher(id=tid, name=name, department=department.strip(), position=position.strip())
        self.teachers[tid] = teacher
        self.save()
        return teacher

    def delete_teacher(self, teacher_id: str) -> bool:
        """Удаляет преподавателя и очищает привязки к нему."""
        if teacher_id not in self.teachers:
            return False

        del self.teachers[teacher_id]
        # Очищаем привязки
        for binding in self.discipline_bindings.values():
            t_ids = binding.get("teacher_ids", [])
            if teacher_id in t_ids:
                binding["teacher_ids"] = [tid for tid in t_ids if tid != teacher_id]

        self.save()
        return True

    # --- Отрасли ---

    def get_industries(self) -> List[Industry]:
        """Возвращает отсортированный список всех отраслей."""
        return sorted(list(self.industries.values()), key=lambda i: i.name)

    def add_industry(self, name: str, description: str = "") -> Industry:
        """Добавляет новую отрасль."""
        name = name.strip()
        for ind in self.industries.values():
            if ind.name.lower() == name.lower():
                return ind

        iid = generate_short_id()
        industry = Industry(id=iid, name=name, description=description.strip())
        self.industries[iid] = industry
        self.save()
        return industry

    def delete_industry(self, industry_id: str) -> bool:
        """Удаляет отрасль."""
        if industry_id not in self.industries:
            return False

        ind_name = self.industries[industry_id].name
        del self.industries[industry_id]

        for binding in self.discipline_bindings.values():
            if binding.get("industry") == ind_name:
                binding["industry"] = None

        self.save()
        return True

    # --- Привязки дисциплин ---

    def get_discipline_binding(self, discipline_title: str) -> Tuple[Optional[str], List[Teacher]]:
        """Возвращает (отрасль, список_преподавателей) для дисциплины."""
        binding = self.discipline_bindings.get(discipline_title, {})
        industry = binding.get("industry")
        teacher_ids = binding.get("teacher_ids", [])
        teachers = [self.teachers[tid] for tid in teacher_ids if tid in self.teachers]
        return industry, teachers

    def set_discipline_binding(
        self,
        discipline_title: str,
        industry: Optional[str] = None,
        teacher_ids: Optional[List[str]] = None,
    ):
        """Устанавливает отрасль и список преподавателей для дисциплины."""
        if discipline_title not in self.discipline_bindings:
            self.discipline_bindings[discipline_title] = {}

        if industry is not None:
            self.discipline_bindings[discipline_title]["industry"] = industry.strip() if industry else None

        if teacher_ids is not None:
            # Оставляем только существующие ID
            valid_ids = [tid for tid in teacher_ids if tid in self.teachers]
            self.discipline_bindings[discipline_title]["teacher_ids"] = valid_ids

        self.save()

    # --- Импорт из файлов (Excel / CSV) ---

    def import_teachers_file(self, content: bytes, filename: str) -> int:
        """Импортирует преподавателей из файла .xlsx или .csv."""
        rows = self._read_table_file(content, filename)
        if not rows:
            return 0

        # Поиск индексов колонок
        headers = [str(cell).strip().lower() for cell in rows[0]]
        name_col = -1
        dept_col = -1
        pos_col = -1

        for idx, h in enumerate(headers):
            if any(k in h for k in ("фио", "преподавател", "имя", "работник", "сотрудник")):
                name_col = idx
            elif any(k in h for k in ("кафедр", "подразделен")):
                dept_col = idx
            elif any(k in h for k in ("должност", "звание", "степен")):
                pos_col = idx

        if name_col == -1:
            name_col = 0  # Если не найдено, берем первый столбец

        count = 0
        for r in rows[1:]:
            if name_col < len(r) and r[name_col]:
                name = str(r[name_col]).strip()
                if not name:
                    continue
                dept = str(r[dept_col]).strip() if dept_col != -1 and dept_col < len(r) and r[dept_col] else ""
                pos = str(r[pos_col]).strip() if pos_col != -1 and pos_col < len(r) and r[pos_col] else ""
                self.add_teacher(name, dept, pos)
                count += 1

        self.save()
        return count

    def import_industries_file(self, content: bytes, filename: str) -> int:
        """Импортирует отрасли из файла .xlsx или .csv."""
        rows = self._read_table_file(content, filename)
        if not rows:
            return 0

        headers = [str(cell).strip().lower() for cell in rows[0]]
        ind_col = -1
        desc_col = -1

        for idx, h in enumerate(headers):
            if any(k in h for k in ("отрасл", "наименован", "назван", "сфер", "направлен")):
                ind_col = idx
            elif any(k in h for k in ("описан", "примечан", "коммент")):
                desc_col = idx

        if ind_col == -1:
            ind_col = 0

        count = 0
        for r in rows[1:]:
            if ind_col < len(r) and r[ind_col]:
                name = str(r[ind_col]).strip()
                if not name:
                    continue
                desc = str(r[desc_col]).strip() if desc_col != -1 and desc_col < len(r) and r[desc_col] else ""
                self.add_industry(name, desc)
                count += 1

        self.save()
        return count

    def import_bindings_file(self, content: bytes, filename: str) -> int:
        """
        Импортирует связки Дисциплина - Отрасль - Преподаватели из файла.
        Колонки: 'Дисциплина', 'Отрасль', 'Преподаватели'.
        """
        rows = self._read_table_file(content, filename)
        if not rows:
            return 0

        headers = [str(cell).strip().lower() for cell in rows[0]]
        disc_col = -1
        ind_col = -1
        teach_col = -1

        for idx, h in enumerate(headers):
            if any(k in h for k in ("дисциплин", "предмет", "курс")):
                disc_col = idx
            elif any(k in h for k in ("отрасл", "сфер")):
                ind_col = idx
            elif any(k in h for k in ("преподават", "лектор", "фио")):
                teach_col = idx

        if disc_col == -1:
            disc_col = 0

        count = 0
        for r in rows[1:]:
            if disc_col < len(r) and r[disc_col]:
                disc_title = str(r[disc_col]).strip()
                if not disc_title:
                    continue

                ind_name = str(r[ind_col]).strip() if ind_col != -1 and ind_col < len(r) and r[ind_col] else None
                if ind_name:
                    self.add_industry(ind_name)

                teacher_ids = []
                if teach_col != -1 and teach_col < len(r) and r[teach_col]:
                    raw_teachers = str(r[teach_col])
                    # Разделение по запятой, точке с запятой или переносу
                    names = [n.strip() for n in raw_teachers.replace(";", ",").replace("\n", ",").split(",") if n.strip()]
                    for n in names:
                        t = self.add_teacher(n)
                        teacher_ids.append(t.id)

                self.set_discipline_binding(disc_title, industry=ind_name, teacher_ids=teacher_ids)
                count += 1

        self.save()
        return count

    @staticmethod
    def _read_table_file(content: bytes, filename: str) -> List[List[Any]]:
        """Универсальное чтение .xlsx и .csv в список строк."""
        filename_lower = filename.lower()
        if filename_lower.endswith(".xlsx"):
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            sheet = wb.active
            rows = []
            for row in sheet.iter_rows(values_only=True):
                if any(cell is not None for cell in row):
                    rows.append(list(row))
            return rows
        else:
            # CSV: автоопределение кодировки и диалекта
            text = ""
            for enc in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
                try:
                    text = content.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue

            delimiter = ";" if ";" in text[:500] else ","
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            return [row for row in reader if any(cell.strip() for cell in row)]

    def export_to_excel(
        self,
        discipline_profiles: List[DisciplineProfile],
        semester_audits: Optional[List[Any]] = None,
    ) -> bytes:
        """Экспортирует весь реестр дисциплин со связями в Excel-файл (.xlsx)."""
        wb = openpyxl.Workbook()

        # Лист 1: Дисциплины
        ws_disc = wb.active
        ws_disc.title = "Реестр дисциплин"
        disc_headers = [
            "Дисциплина",
            "Отрасль",
            "Преподаватели",
            "Кафедры",
            "Коллизия кафедр",
            "Формы контроля",
            "Коллизия форм контроля",
            "Количество планов",
            "Учебные годы",
            "Семестры",
            "Трудоемкость (ЗЕТ)",
            "Объем часов",
            "Суммарно ЗЕТ (все планы)",
            "Суммарно часов (все планы)",
        ]
        ws_disc.append(disc_headers)

        for p in discipline_profiles:
            teachers_str = ", ".join(t.name for t in p.teachers) if p.teachers else ""
            depts_str = ", ".join(p.departments)
            sems_str = ", ".join(str(s) for s in sorted(p.semesters))
            ay_str = ", ".join(p.academic_years) if p.academic_years else "—"
            ctrl_str = ", ".join(p.exam_types) if p.exam_types else "не указана"
            ws_disc.append([
                p.title,
                p.industry or "Не указана",
                teachers_str,
                depts_str,
                "ДА (РАСХОЖДЕНИЕ)" if p.has_conflict else "Нет",
                ctrl_str,
                "ДА (РАСХОЖДЕНИЕ)" if p.has_control_conflict else "Нет",
                p.plans_count,
                ay_str,
                sems_str,
                p.ze_display or p.total_ze,
                p.hours_display or p.total_hours,
                p.sum_ze,
                p.sum_hours,
            ])

        # Лист 2: Аудит семестров (ФГОС)
        if semester_audits:
            ws_audit = wb.create_sheet(title="Аудит семестров (ФГОС)")
            ws_audit.append([
                "Файл плана",
                "Шифр",
                "Направление",
                "Семестр",
                "Курс",
                "Учебный год",
                "Экзаменов",
                "Зачетов",
                "Диф. зачетов",
                "Курсовых",
                "Статус нагрузки",
                "Нарушения нормативов",
            ])
            for a in semester_audits:
                status_str = "ПРЕВЫШЕН ЛИМИТ" if a.is_overloaded else "В норме"
                viol_str = "; ".join(a.violations) if a.violations else "Нет"
                ws_audit.append([
                    a.plan_name,
                    a.direction_code,
                    a.direction_title,
                    a.semester,
                    a.course,
                    a.academic_year,
                    a.exams_count,
                    a.pass_count,
                    a.diff_pass_count,
                    a.course_works_count,
                    status_str,
                    viol_str,
                ])

        # Лист 2: Преподаватели
        ws_teach = wb.create_sheet(title="Преподаватели")
        ws_teach.append(["ФИО преподавателя", "Кафедра", "Должность", "Количество дисциплин"])
        for t in self.get_teachers():
            # Считаем количество дисциплин
            assigned_count = sum(
                1 for b in self.discipline_bindings.values()
                if t.id in b.get("teacher_ids", [])
            )
            ws_teach.append([t.name, t.department, t.position, assigned_count])

        # Лист 3: Отрасли
        ws_ind = wb.create_sheet(title="Отрасли")
        ws_ind.append(["Наименование отрасли", "Количество дисциплин"])
        for ind in self.get_industries():
            count = sum(
                1 for b in self.discipline_bindings.values()
                if b.get("industry") == ind.name
            )
            ws_ind.append([ind.name, count])

        # Автонастройка ширины колонок
        for sheet in (ws_disc, ws_teach, ws_ind):
            for col in sheet.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                sheet.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)

        out_buf = io.BytesIO()
        wb.save(out_buf)
        return out_buf.getvalue()
