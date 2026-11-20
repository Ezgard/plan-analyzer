"""
Модуль парсинга учебных планов формата PLX (Шахты / ГосИнсп / XML / ZIP).
Поддерживает форматы:
1. Шахтинский XML DiffGram (dsMMISDB.xsd) в кодировках UTF-16LE, UTF-8, zip-архивы .plx
2. Упрощенный XML учебного плана
Извлекает метаданные ОПОП, список дисциплин, часы по видам работ, формы контроля и компетенции с индикаторами.
"""
import functools
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter
from datetime import date, timedelta
from typing import Dict, List, Any, Union, Optional, Tuple

try:
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
    from .exceptions import (
        CurriculumParsingError,
        PLXParsingError,
        SecurityValidationError,
        EmptyPlanError,
    )
    from .models import (
        CurriculumPlanData,
        DisciplineItem,
        CompetencyItem,
        IUPProfile,
        CurriculumModule,
        ReattestationItem,
        ScheduleDayItem,
        ScheduleWeekItem,
        ScheduleBudgetItem,
        ScheduleSessionItem,
        ScheduleCourseItem,
        CurriculumScheduleData,
    )
except (ImportError, ValueError):
    from curriculum_parser.utils import (  # type: ignore
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
    from curriculum_parser.exceptions import (  # type: ignore
        CurriculumParsingError,
        PLXParsingError,
        SecurityValidationError,
        EmptyPlanError,
    )
    from curriculum_parser.models import (  # type: ignore
        CurriculumPlanData,
        DisciplineItem,
        CompetencyItem,
        IUPProfile,
        CurriculumModule,
        ReattestationItem,
        ScheduleDayItem,
        ScheduleWeekItem,
        ScheduleBudgetItem,
        ScheduleSessionItem,
        ScheduleCourseItem,
        CurriculumScheduleData,
    )



# Общероссийский справочник условных обозначений КУГ (ФГОС ВО / Лаборатория ММИС)
ACTIVITY_SYMBOLS = {
    "1": {
        "code": "Т",
        "name": "Теоретическое обучение",
        "description": "Аудиторные занятия и самостоятельная работа",
        "color": "#e0f2fe",
        "text_color": "#0369a1",
        "badge_class": "bg-sky-100 text-sky-800 border-sky-200"
    },
    "3": {
        "code": "Э",
        "name": "Экзаменационная сессия",
        "description": "Промежуточная аттестация (экзамены, зачеты)",
        "color": "#fef08a",
        "text_color": "#854d0e",
        "badge_class": "bg-amber-100 text-amber-900 border-amber-300"
    },
    "4": {
        "code": "У",
        "name": "Учебная практика",
        "description": "Учебная практика (ознакомительная, проектная)",
        "color": "#bbf7d0",
        "text_color": "#166534",
        "badge_class": "bg-emerald-100 text-emerald-800 border-emerald-300"
    },
    "5": {
        "code": "П",
        "name": "Производственная практика",
        "description": "Производственная и профессиональная практика",
        "color": "#86efac",
        "text_color": "#14532d",
        "badge_class": "bg-green-200 text-green-900 border-green-400"
    },
    "6": {
        "code": "Пд",
        "name": "Преддипломная практика",
        "description": "Преддипломная практика для выполнения ВКР",
        "color": "#a7f3d0",
        "text_color": "#065f46",
        "badge_class": "bg-teal-100 text-teal-800 border-teal-300"
    },
    "7": {
        "code": "Д",
        "name": "Защита ВКР",
        "description": "Подготовка к процедуре защиты и защита выпускной квалификационной работы",
        "color": "#fbcfe8",
        "text_color": "#9d174d",
        "badge_class": "bg-pink-100 text-pink-800 border-pink-300"
    },
    "11": {
        "code": "Г",
        "name": "Государственный экзамен",
        "description": "Подготовка к сдаче и сдача государственного экзамена",
        "color": "#f472b6",
        "text_color": "#831843",
        "badge_class": "bg-fuchsia-200 text-fuchsia-900 border-fuchsia-400"
    },
    "12": {
        "code": "К",
        "name": "Каникулы",
        "description": "Зимние и летние каникулы",
        "color": "#e2e8f0",
        "text_color": "#334155",
        "badge_class": "bg-slate-200 text-slate-800 border-slate-300"
    },
    "13": {
        "code": "-",
        "name": "Не используется",
        "description": "Период за пределами нормативного срока освоения программы",
        "color": "#f8fafc",
        "text_color": "#94a3b8",
        "badge_class": "bg-slate-50 text-slate-400 border-slate-200"
    },
    "15": {
        "code": "*",
        "name": "Нерабочие праздничные дни",
        "description": "Нерабочие праздничные дни (не включая воскресенья)",
        "color": "#fecaca",
        "text_color": "#991b1b",
        "badge_class": "bg-rose-100 text-rose-800 border-rose-300"
    },
    "49": {
        "code": "ПА",
        "name": "Повторная аттестация",
        "description": "Повторная, вторая повторная промежуточная аттестация",
        "color": "#fed7aa",
        "text_color": "#9a3412",
        "badge_class": "bg-orange-100 text-orange-800 border-orange-300"
    }
}

DAY_NAMES_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]

MONTH_NAMES_RU = [
    "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
    "Январь", "Февраль", "Март", "Апрель",
    "Май", "Июнь", "Июль", "Август"
]

# Государственные нерабочие праздничные дни РФ (ст. 112 ТК РФ)
FIXED_HOLIDAYS_RU = {
    (1, 1): "Новый год",
    (1, 2): "Новогодние каникулы",
    (1, 3): "Новогодние каникулы",
    (1, 4): "Новогодние каникулы",
    (1, 5): "Новогодние каникулы",
    (1, 6): "Новогодние каникулы",
    (1, 7): "Рождество Христово",
    (1, 8): "Новогодние каникулы",
    (2, 23): "День защитника Отечества",
    (3, 8): "Международный женский день",
    (5, 1): "Праздник Весны и Труда",
    (5, 9): "День Победы",
    (6, 12): "День России",
    (11, 4): "День народного единства",
}


class PLXParser:
    """Универсальный парсер файлов учебных планов .plx и .xml."""

    @staticmethod
    def decode_raw_bytes(raw_content: bytes) -> str:
        """Распаковывает zip при необходимости и определяет кодировку XML."""
        if not raw_content:
            return ""

        # 1. Проверка на zip-архив (Шахтинские .plx иногда пакуются в zip)
        if raw_content.startswith(b"PK\x03\x04"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw_content)) as z:
                    for name in z.namelist():
                        if name.lower().endswith((".xml", ".plx")):
                            return PLXParser.decode_raw_bytes(z.read(name))
                    if z.namelist():
                        return PLXParser.decode_raw_bytes(z.read(z.namelist()[0]))
            except (zipfile.BadZipFile, KeyError, io.UnsupportedOperation) as e:
                raise PLXParsingError(f"Ошибка чтения архива PLX: {e}") from e

        # 2. Определение по BOM
        if raw_content.startswith(b"\xff\xfe"):
            return raw_content.decode("utf-16le", errors="replace")
        if raw_content.startswith(b"\xfe\xff"):
            return raw_content.decode("utf-16be", errors="replace")
        if raw_content.startswith(b"\xef\xbb\xbf"):
            return raw_content.decode("utf-8-sig", errors="replace")

        # 3. Перебор стандартных кодировок
        for enc in ("utf-8", "utf-16le", "cp1251"):
            try:
                return raw_content.decode(enc)
            except Exception:
                continue

        return raw_content.decode("utf-8", errors="replace")

    @classmethod
    def parse_plx_content(cls, content_input: Union[bytes, str], filename: str = "plan.plx") -> Dict[str, Any]:
        """
        Главная точка входа: парсит содержимое (bytes, str XML или путь к файлу).
        Автоматически определяет формат (Шахты MMIS DiffGram vs обычный XML).
        """
        if isinstance(content_input, str):
            # Поддержка прямой передачи пути к файлу
            if "<" not in content_input and len(content_input) < 4096:
                try:
                    import os
                    if os.path.isfile(content_input):
                        if filename == "plan.plx":
                            filename = os.path.basename(content_input)
                        with open(content_input, "rb") as f:
                            content_input = f.read()
                except (OSError, ValueError):
                    pass

        if isinstance(content_input, bytes):
            xml_text = cls.decode_raw_bytes(content_input)
        else:
            xml_text = content_input or ""

        # Убираем BOM и лишние пробелы, если остались в начале строки
        xml_text = xml_text.lstrip("\ufeff").strip()
        if not xml_text:
            raise EmptyPlanError("Файл учебного плана пуст или не содержит данных.")

        # Защита от XML External Entity (XXE) атак
        validate_xml_security(xml_text)

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            try:
                root = ET.fromstring(xml_text.encode("utf-8", errors="replace"))
            except ET.ParseError as pe:
                raise PLXParsingError(f"Ошибка синтаксического разбора XML в файле {filename}: {pe}") from pe

        # Проверяем наличие шахтинской схемы dsMMISDB
        mmis_rows = [e for e in root.iter() if e.tag.endswith("ПланыСтроки")]
        if mmis_rows:
            return cls._parse_mmis_diffgram(root, filename)
        else:
            return cls._parse_standard_xml(root, filename)

    @classmethod
    def _parse_schedule_from_elems(
        cls,
        elems_by_tag: Dict[str, List[ET.Element]],
        start_year: int,
        study_years: int = 4
    ) -> Optional[Dict[str, Any]]:
        """
        Парсинг календарного учебного графика (КУГ) из проиндексированных элементов.
        Автоматически восстанавливает компрессию недель (1 часть vs 6 частей Пн-Сб),
        рассчитывает бюджет времени и проецирует недели на реальные даты учебного года.
        """
        def get_elems_by_names(names: Union[str, list, tuple, set]) -> List[ET.Element]:
            target = [names] if isinstance(names, str) else list(names)
            res = []
            for n in target:
                matched = elems_by_tag.get(n)
                if matched:
                    res.extend(matched)
            return res

        # 1. Поиск ячеек графика (ПланыГрафикиЯчейки)
        cell_elems = get_elems_by_names(["ПланыГрафикиЯчейки", "ГрафикиЯчейки"])
        if not cell_elems:
            cell_elems = [e for tag, elist in elems_by_tag.items() if "график" in tag.lower() and "ячейк" in tag.lower() for e in elist]

        if not cell_elems:
            return None

        # 2. Семестры графика (ПланыГрафикиСеместры)
        sem_elems = get_elems_by_names(["ПланыГрафикиСеместры", "ГрафикиСеместры"])
        semesters_data = []
        for s in sem_elems:
            semesters_data.append({
                "course": safe_int(s.get("Курс"), default=1),
                "semester_on_course": safe_int(s.get("Семестр"), default=1),
                "start_date": (s.get("ДатаНачала") or "")[:10],
                "end_date": (s.get("ДатаОкончания") or "")[:10],
                "is_leap": (s.get("Високосный") or "false").lower() == "true",
                "long_first_week": (s.get("ДлиннаяПерваяНеделя") or "false").lower() == "true",
                "long_last_week": (s.get("ДлиннаяПоследняяНеделя") or "false").lower() == "true",
            })

        # 2.1 Сессии / заезды заочной и очно-заочной формы (Заезды, ГрафикиЗаезды)
        zaezd_elems = get_elems_by_names(["Заезды", "ГрафикиЗаезды"])
        sessions_by_course: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for z in zaezd_elems:
            c_num = safe_int(z.get("Курс"), default=1)
            s_num = safe_int(z.get("Сессия"), default=1)
            dur = safe_int(z.get("Продолжительность"), default=0)
            d_start = (z.get("ДатаНачала") or "")[:10]
            raw_name = (z.get("Название") or "").strip()
            sem_val = safe_int(z.get("Семестр"), default=None) if z.get("Семестр") else None

            if dur > 0 and d_start and d_start != "0001-01-01":
                try:
                    dt_s = date.fromisoformat(d_start)
                    dt_e = dt_s + timedelta(days=dur - 1)
                    d_end = dt_e.isoformat()
                except ValueError:
                    d_end = d_start

                if not raw_name:
                    if s_num == 1:
                        s_name = "Установочная сессия"
                    elif s_num == 2:
                        s_name = "Зимняя экзаменационная сессия"
                    elif s_num == 3:
                        s_name = "Летняя экзаменационная сессия"
                    else:
                        s_name = f"Сессия {s_num}"
                else:
                    s_name = raw_name

                sessions_by_course[c_num].append({
                    "course": c_num,
                    "session_num": s_num,
                    "name": s_name,
                    "start_date": d_start,
                    "end_date": d_end,
                    "duration_days": dur,
                    "semester": sem_val
                })

        for c_num in sessions_by_course:
            sessions_by_course[c_num].sort(key=lambda x: x["start_date"])

        # 3. Восстановление календарной сетки по ячейкам
        raw_grid: Dict[int, Dict[int, Dict[int, Dict[str, Any]]]] = defaultdict(lambda: defaultdict(dict))
        budget_counter: Dict[int, Counter] = defaultdict(Counter)

        for c in cell_elems:
            course = safe_int(c.get("Курс"), default=1)
            week_in_sem = safe_int(c.get("НомерНедели"), default=1)
            w_first = safe_int(c.get("НомерПервойНедели"), default=1)
            day = safe_int(c.get("НомерЧастиНедели"), default=1)
            act_code = str(c.get("КодВидаДеятельности") or "1")
            parts_in_week = safe_int(c.get("КоличествоЧастейВНеделе"), default=1)
            date_str = (c.get("DateElementGYP") or "")[:10]

            # Корректный расчет сквозного номера недели в учебном году
            abs_week = (w_first + week_in_sem - 1) if w_first > 0 else week_in_sem

            if parts_in_week == 1:
                # Вся неделя однородна - разворачиваем на 6 дней (Пн-Сб)
                budget_counter[course][act_code] += 1.0
                base_dt = None
                if date_str:
                    try:
                        base_dt = date.fromisoformat(date_str)
                    except ValueError:
                        pass

                for d in range(1, 7):
                    day_dt_str = (base_dt + timedelta(days=d - 1)).isoformat() if base_dt else date_str
                    raw_grid[course][abs_week][d] = {
                        "act_code": act_code,
                        "date": day_dt_str,
                        "is_split": False
                    }
            else:
                # Поденная запись дня недели
                weight = 1.0 / parts_in_week if parts_in_week > 0 else (1.0 / 6.0)
                budget_counter[course][act_code] += weight
                raw_grid[course][abs_week][day] = {
                    "act_code": act_code,
                    "date": date_str,
                    "is_split": True
                }

        # 4. Формирование структуры по курсам
        courses_output: Dict[int, Dict[str, Any]] = {}
        warnings: List[str] = []

        for course in sorted(raw_grid.keys()):
            # Пропускаем неактивные курсы (например 5, 6, 7 где все заполнено '-')
            active_acts = set(budget_counter[course].keys()) - {"13"}
            if not active_acts:
                continue

            course_start_year = start_year + (course - 1)
            academic_year_str = f"{course_start_year}/{course_start_year + 1}"

            # Расчет календарных дат учебного года
            # Если в неделе 1 есть известная дата из КУГ, берем понедельник этой недели;
            # иначе - понедельник недели 1 сентября.
            known_first_date = None
            if 1 in raw_grid[course]:
                first_days = sorted(raw_grid[course][1].keys())
                if first_days:
                    fd = first_days[0]
                    fd_str = raw_grid[course][1][fd].get("date")
                    if fd_str and len(fd_str) >= 10:
                        try:
                            known_first_date = date.fromisoformat(fd_str) - timedelta(days=fd - 1)
                        except ValueError:
                            pass

            if known_first_date:
                start_monday = known_first_date
            else:
                sept_first = date(course_start_year, 9, 1)
                if sept_first.weekday() == 6:  # Воскресенье
                    start_monday = sept_first + timedelta(days=1)
                else:
                    start_monday = sept_first - timedelta(days=sept_first.weekday())

            max_week = max(raw_grid[course].keys()) if raw_grid[course] else 52
            total_weeks_count = max_week

            weeks_list = []
            for w in range(1, total_weeks_count + 1):
                days_dict = raw_grid[course].get(w, {})
                days_data = []

                # Ищем базовый понедельник для текущей недели:
                # Если в этой неделе есть хотя бы один день с известной датой, привязываемся к нему
                w_monday = None
                for d_k in sorted(days_dict.keys()):
                    k_d_str = days_dict[d_k].get("date")
                    if k_d_str and len(k_d_str) >= 10:
                        try:
                            w_monday = date.fromisoformat(k_d_str) - timedelta(days=d_k - 1)
                            break
                        except ValueError:
                            pass
                if not w_monday:
                    w_monday = start_monday + timedelta(weeks=(w - 1))

                week_codes = [days_dict[d]["act_code"] for d in days_dict]

                for d in range(1, 7):
                    day_cal_date = w_monday + timedelta(days=(d - 1))
                    day_info = days_dict.get(d)
                    if day_info:
                        act_code = day_info["act_code"]
                        d_date = day_info.get("date") or day_cal_date.isoformat()
                    else:
                        if "13" in week_codes:
                            act_code = "13"
                        elif day_cal_date.month == 9 and w > 40:
                            act_code = "13"
                        else:
                            act_code = "1"  # по умолчанию теория
                        d_date = day_cal_date.isoformat()

                    meta = ACTIVITY_SYMBOLS.get(act_code, {
                        "code": act_code,
                        "name": f"Вид {act_code}",
                        "color": "#f1f5f9",
                        "badge_class": "bg-slate-100 text-slate-800"
                    })

                    # Идентификация точного названия государственного праздника РФ
                    name_text = meta["name"]
                    if act_code == "15":
                        h_title = "Нерабочий праздничный день"
                        if d_date and len(d_date) >= 10:
                            try:
                                m_idx = int(d_date[5:7])
                                day_idx_num = int(d_date[8:10])
                                if (m_idx, day_idx_num) in FIXED_HOLIDAYS_RU:
                                    h_title = f"Праздник: {FIXED_HOLIDAYS_RU[(m_idx, day_idx_num)]}"
                            except (ValueError, IndexError):
                                pass
                        name_text = h_title

                    # Попадание дня в сессию (заезд заочников)
                    matched_session = ""
                    for sess in sessions_by_course.get(course, []):
                        if sess["start_date"] <= d_date <= sess["end_date"]:
                            matched_session = sess["name"]
                            break

                    days_data.append({
                        "day_num": d,
                        "day_name": DAY_NAMES_RU[d - 1],
                        "act_code": act_code,
                        "symbol": meta["code"],
                        "name": name_text,
                        "date": d_date,
                        "color": meta["color"],
                        "badge_class": meta["badge_class"],
                        "session_name": matched_session
                    })

                # Корректное определение доминирующего символа недели:
                acts_list = [d["act_code"] for d in days_data]
                active_acts = [a for a in acts_list if a not in ("13", "15")]
                non_dash_acts = [a for a in acts_list if a != "13"]

                if active_acts:
                    # Преобладающий вид учебной деятельности (Т, Э, У, П, К, Д, Г, ПА)
                    dom_code = Counter(active_acts).most_common(1)[0][0]
                elif non_dash_acts:
                    # Неделя целиком состоит из праздничных дней
                    dom_code = Counter(non_dash_acts).most_common(1)[0][0]
                elif acts_list:
                    # Неделя целиком состоит из прочерков '-' (код 13, обучение завершено)
                    dom_code = Counter(acts_list).most_common(1)[0][0]
                else:
                    dom_code = "1"

                is_uniform = (len(set(acts_list)) <= 1)
                dom_meta = ACTIVITY_SYMBOLS.get(dom_code, {
                    "code": dom_code,
                    "name": "Смешанная неделя",
                    "color": "#f8fafc"
                })

                # Точные даты начала и конца недели
                w_start_str = days_data[0]["date"] if days_data else w_monday.isoformat()
                w_end_str = days_data[-1]["date"] if days_data else (w_monday + timedelta(days=5)).isoformat()
                active_days = [d for d in days_data if d["act_code"] != "13"]
                if active_days and days_data[-1]["act_code"] == "13":
                    w_end_str = active_days[-1]["date"]

                weeks_list.append({
                    "week_num": w,
                    "is_uniform": is_uniform,
                    "dom_symbol": dom_meta["code"],
                    "dom_color": dom_meta["color"],
                    "name": dom_meta["name"],
                    "days": days_data,
                    "start_date": w_start_str,
                    "end_date": w_end_str,
                })

            # Бюджет времени курса
            total_budget_weeks = sum(budget_counter[course].values())
            budget_items = []
            for act_code, w_val in budget_counter[course].most_common():
                meta = ACTIVITY_SYMBOLS.get(act_code, {
                    "code": act_code,
                    "name": f"Неизвестно ({act_code})",
                    "color": "#f1f5f9",
                    "badge_class": "bg-slate-100 text-slate-700"
                })
                budget_items.append({
                    "act_code": act_code,
                    "symbol": meta["code"],
                    "name": meta["name"],
                    "weeks": round(w_val, 2),
                    "days": round(w_val * 6.0),
                    "percent": round((w_val / total_budget_weeks * 100), 1) if total_budget_weeks else 0,
                    "badge_class": meta.get("badge_class", "")
                })

            is_balanced = (51.5 <= total_budget_weeks <= 53.5)
            if not is_balanced:
                warnings.append(f"Курс {course}: отклонение от 52 недель (фактически {round(total_budget_weeks, 2)} нед.)")

            courses_output[course] = {
                "course_num": course,
                "weeks_count": len(weeks_list),
                "academic_year": academic_year_str,
                "calendar_year_start": course_start_year,
                "total_weeks": round(total_budget_weeks, 2),
                "weeks": weeks_list,
                "budget": budget_items,
                "sessions": sessions_by_course.get(course, []),
                "is_balanced": is_balanced,
                "notes": ""
            }

        return {
            "courses": courses_output,
            "semesters": semesters_data,
            "legend": ACTIVITY_SYMBOLS,
            "study_years_count": len(courses_output) or study_years,
            "warnings": warnings
        }

    @classmethod
    def _parse_mmis_diffgram(cls, root: ET.Element, filename: str) -> Dict[str, Any]:
        """Парсинг полноценного Шахтинского плана (DataSet MMIS)."""
        def get_local_tag(elem: ET.Element) -> str:
            t = elem.tag
            return t.split("}", 1)[1] if "}" in t else (t.split(":", 1)[1] if ":" in t else t)

        # Быстрая однократная индексация элементов по локальному тегу (O(N) вместо O(K*N))
        elems_by_tag: Dict[str, List[ET.Element]] = defaultdict(list)
        for e in root.iter():
            elems_by_tag[get_local_tag(e)].append(e)

        def get_elems_by_names(names: Union[str, set, list, tuple]) -> List[ET.Element]:
            target = [names] if isinstance(names, str) else list(names)
            res = []
            for n in target:
                matched = elems_by_tag.get(n)
                if matched:
                    res.extend(matched)
            return res

        # 1. Справочник кафедр: Код -> Название
        depts: Dict[str, str] = {}
        for e in get_elems_by_names(["Кафедры", "ПланыКафедры"]):
            code = e.get("Код")
            name = e.get("Название")
            if code and name:
                depts[code] = name.strip()

        # 2. Компетенции и индикаторы (извлекаем из Компетенции и ПланыКомпетенции без дублирования)
        comp_map: Dict[str, Dict[str, Any]] = {}
        comps_by_cipher: Dict[str, Dict[str, Any]] = {}

        for e in get_elems_by_names(["Компетенции", "ПланыКомпетенции"]):
            cid = e.get("Код")
            cipher = normalize_competency_code(e.get("ШифрКомпетенции") or e.get("Шифр") or e.get("Индекс"))
            name = (e.get("Наименование") or e.get("Название") or e.get("Содержание") or "").strip()
            parent_id = e.get("КодРодителя") or e.get("КодРодительскойКомпетенции")

            if cid and str(cid) not in comp_map:
                comp_data = {
                    "cipher": cipher,
                    "name": name,
                    "parent_id": str(parent_id) if parent_id is not None else None
                }
                comp_map[str(cid)] = comp_data
                if cipher and "." not in cipher and cipher not in comps_by_cipher:
                    comps_by_cipher[cipher] = comp_data

        comp_by_row: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for cd in get_elems_by_names(["ПланыКомпетенцииДисциплины", "КомпетенцииДисциплины", "ПланыСтрокиКомпетенции"]):
            c_code = cd.get("КодКомпетенции")
            if not c_code or str(c_code) not in comp_map:
                continue

            c_info = comp_map[str(c_code)]
            p_id = c_info.get("parent_id")
            parent = None

            # 1. Поиск родителя по ID
            if p_id and str(p_id) in comp_map:
                parent = comp_map[str(p_id)]
            # 2. Поиск родителя по шифру до точки (например 'УК-1.1' -> 'УК-1')
            elif "." in c_info["cipher"]:
                parent_cipher = c_info["cipher"].rsplit(".", 1)[0]
                parent = comps_by_cipher.get(parent_cipher)

            if parent:
                parent_ciph = parent["cipher"]
                parent_name = parent["name"] or f"Компетенция {parent_ciph}"
                ind_ciph = c_info["cipher"]
                ind_name = c_info["name"] or f"Формирует знания, умения и навыки в соответствии с индикатором {ind_ciph} компетенции {parent_ciph}"
                item = {
                    "code": parent_ciph,
                    "name": parent_name,
                    "indicator_code": ind_ciph,
                    "indicator_name": ind_name
                }
            else:
                code = c_info["cipher"]
                name = c_info["name"] or f"Компетенция {code}"
                ind_code = f"И{code}.1" if (not code.startswith("И") and "." not in code) else code
                ind_name = c_info["name"] or f"Анализирует задачи и применяет методы в рамках компетенции {code}"
                item = {
                    "code": code,
                    "name": name,
                    "indicator_code": ind_code,
                    "indicator_name": ind_name
                }

            # Регистрируем для всех возможных идентификаторов строки
            for r_key in (cd.get("КодСтроки"), cd.get("КодОбъекта"), cd.get("КодДисциплины")):
                if r_key:
                    comp_by_row[str(r_key)].append(item)

        # 3. Распределение часов и форм контроля по объектам
        # В Шахтах: основная современная таблица — ПланыНовыеЧасы / НовыеЧасы.
        # ПланыЧасы / Часы — устаревшая таблица. Нельзя их объединять, чтобы не дублировать часы!
        new_hours = get_elems_by_names(["ПланыНовыеЧасы", "НовыеЧасы"])
        if new_hours:
            hour_elements = new_hours
        else:
            old_hours = get_elems_by_names(["ПланыЧасы", "Часы"])
            hour_elements = old_hours if old_hours else get_elems_by_names(["ПланыЧасыСессии", "ЧасыСессии"])

        hours_by_row: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        for h in hour_elements:
            obj_code = h.get("КодОбъекта") or h.get("КодСтроки") or h.get("КодДисциплины")
            if obj_code:
                hours_by_row[str(obj_code)].append(h.attrib)

        # 4. Метаданные ОПОП и Титула
        all_oop = {e.get("Код"): e.attrib for e in get_elems_by_names(["ООП", "ПланыООП"])}
        plan_elem = get_elems_by_names(["Планы", "План"])
        plan_attrib = plan_elem[0].attrib if plan_elem else {}

        main_oop_id = plan_attrib.get("КодООП")
        main_oop = all_oop.get(main_oop_id, {})
        if not main_oop and all_oop:
            for cid, oop in all_oop.items():
                if not oop.get("КодРодительскогоООП"):
                    main_oop = oop
                    break

        direction_code = main_oop.get("Шифр") or (plan_attrib.get("Титул", "").split("\n")[0].split(" ")[0] if plan_attrib.get("Титул") else "") or "40.04.01"
        direction_title = main_oop.get("Название") or "Юриспруденция"

        # Профиль: активный ООП или профили плана / вторая строка Титула
        active_oop_id = plan_attrib.get("КодАктивногоООП")
        active_oop = all_oop.get(active_oop_id, {})
        title_lines = [line.strip() for line in (plan_attrib.get("Титул") or "").splitlines() if line.strip()]
        if len(title_lines) > 1 and len(title_lines[1]) > len(active_oop.get("Название") or ""):
            profile_title = title_lines[1]
        else:
            profile_title = active_oop.get("Название") or main_oop.get("Название") or ""

        # Уровень образования: автоопределение по ОКСО / шифру направления или коду
        if ".03." in direction_code:
            edu_level = "бакалавриат"
        elif ".04." in direction_code:
            edu_level = "магистратура"
        elif ".05." in direction_code:
            edu_level = "специалитет"
        elif ".06." in direction_code or ".07." in direction_code or ".08." in direction_code:
            edu_level = "аспирантура"
        else:
            lvl_code = plan_attrib.get("КодУровняОбразования") or main_oop.get("Квалификация") or "3"
            edu_levels = {
                "1": "бакалавриат",
                "2": "бакалавриат",
                "3": "магистратура",
                "4": "специалитет",
                "7": "аспирантура"
            }
            edu_level = edu_levels.get(str(lvl_code), "магистратура")

        # Форма обучения
        sf_code = plan_attrib.get("КодФормыОбучения") or "1"
        study_forms = {"1": "очная", "2": "заочная", "3": "очно-заочная"}
        study_form = study_forms.get(str(sf_code), "очная")

        start_year = safe_int(plan_attrib.get("ГодНачалаПодготовки"), default=2026)
        qualification = plan_attrib.get("Квалификация") or main_oop.get("Квалификация") or ""
        try:
            study_years = safe_int(float((plan_attrib.get("СрокОбучения") or "4").replace(",", ".")), default=4)
        except Exception:
            study_years = 4

        # 4.1 Метаданные ИУП (Индивидуальный учебный план)
        doc_candidates = get_elems_by_names(["Документ", "Document"])
        doc_attrib = doc_candidates[0].attrib if doc_candidates else (root.attrib if get_local_tag(root) == "Документ" else {})

        indiv_flag = plan_attrib.get("Индивидуальный") or doc_attrib.get("Индивидуальный") or "0"
        student_fio = (plan_attrib.get("ФИО") or plan_attrib.get("ФамилияСтуд") or "").strip().strip('""')
        group_name_iup = (plan_attrib.get("GroupNameIUP") or "").strip()
        base_plan_filename = doc_attrib.get("PrevName") or ""
        start_course = safe_int(plan_attrib.get("КурсНачалаОбуч"), default=1)
        start_semester = safe_int(plan_attrib.get("СеместрНачалаОбуч"), default=1)
        is_iup = (str(indiv_flag).strip() not in ("0", "false", "") or bool(student_fio))

        # 4.2 Таблица переаттестаций и перезачетов (ПереаттестацияДетали)
        reattest_elems = get_elems_by_names(["ПереаттестацияДетали", "Переаттестация"])
        reattest_by_row: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        all_reattestations: List[Dict[str, Any]] = []

        grade_map = {"5": "отлично", "4": "хорошо", "3": "удовлетворительно", "6": "зачтено"}

        for r in reattest_elems:
            row_id = r.get("КодСтроки")
            c_id = r.get("Код")
            w_code = safe_int(r.get("КодВидаРабот"))
            orig_course = safe_int(r.get("ИсходныйКурс") or r.get("Курс"), default=1)
            orig_sem = safe_int(r.get("ИсходныйСеместр") or r.get("Семестр"), default=1)
            qty_was = safe_float(r.get("КоличествоБыло"), default=0.0)
            qty_done = safe_float(r.get("КоличествоИзучено"), default=0.0)
            t_type_code = safe_int(r.get("ТипЗачета"), default=1)
            t_type = "переаттестация" if t_type_code == 3 else "перезачет"
            grade_raw = r.get("Оценка")
            grade_str = grade_map.get(str(grade_raw)) or (str(grade_raw) if grade_raw else "")

            rec = {
                "id": c_id,
                "row_id": str(row_id) if row_id else "",
                "work_type_code": w_code,
                "original_course": orig_course,
                "original_semester": orig_sem,
                "amount_was": qty_was,
                "amount_studied": qty_done,
                "attestation_type": t_type,
                "attestation_type_code": t_type_code,
                "grade": grade_str,
                "grade_code": grade_raw
            }
            all_reattestations.append(rec)
            if row_id:
                reattest_by_row[str(row_id)].append(rec)

        # 5. Дисциплины, практики, ГИА и модули (ПланыСтроки)
        all_rows = get_elems_by_names(["ПланыСтроки", "Строки"])
        parent_ids = set(r.get("КодРодителя") for r in all_rows if r.get("КодРодителя"))

        # Карта модулей учебного плана (ТипОбъекта="1" / "5" или контейнеры-родители)
        modules_map = {}
        for row in all_rows:
            r_id = row.get("Код")
            r_name = row.get("Дисциплина")
            r_code = row.get("ДисциплинаКод") or ""
            r_tip = row.get("ТипОбъекта") or "2"
            if r_name and (r_tip in ("1", "5") or r_id in parent_ids):
                modules_map[str(r_id)] = {
                    "id": str(r_id),
                    "title": r_name.strip(),
                    "code": r_code.strip(),
                    "is_module": r_tip == "1",
                    "is_elective_group": r_tip == "5"
                }

        disciplines = []
        for row in all_rows:
            disc_id = row.get("Код")
            name = row.get("Дисциплина")
            code = row.get("ДисциплинаКод") or ""
            tip_obj = row.get("ТипОбъекта") or "2"

            # Исключаем пустые строки, строки со скрытием в РПД и сами заголовки модулей
            if not name or row.get("СкрытьВРПД") == "true":
                continue
            if tip_obj in ("1", "5") or disc_id in parent_ids:
                continue

            dept_id = row.get("КодКафедры")
            dept_name = depts.get(dept_id, "Общеуниверситетская кафедра")

            # Определение принадлежности к родительскому модулю
            parent_id = row.get("КодРодителя")
            parent_module_title = ""
            parent_module_code = ""
            if parent_id and str(parent_id) in modules_map:
                parent_module_title = modules_map[str(parent_id)]["title"]
                parent_module_code = modules_map[str(parent_id)]["code"]

            # Корректная классификация блока дисциплины
            if "Б1.О" in code:
                block = "обязательной части"
            elif "Б1.В" in code:
                block = "части, формируемой участниками образовательных отношений"
            elif "Б2.О" in code:
                block = "обязательной части (практика)"
            elif "Б2.В" in code:
                block = "части, формируемой участниками образовательных отношений (практика)"
            elif "Б3" in code:
                block = "государственной итоговой аттестации"
            elif "ФТД" in code:
                block = "факультативных дисциплин"
            elif "Б4" in code:
                block = "элективных дисциплин по физической культуре и спорту"
            else:
                block = "обязательной части"

            # Точная классификация типа объекта (item_type)
            name_lower = name.lower()
            if "Б2" in code or tip_obj == "3" or "практик" in name_lower or "практика" in block.lower():
                item_type = "practice"
                is_practice = True
                is_gia = False
                is_facultative = False
            elif ("Б3" in code or "государственной итоговой аттестации" in block.lower() or ("аттестац" in name_lower and "Б1" not in code)) or (tip_obj == "4" and "Б1" not in code and "курсов" not in name_lower):
                item_type = "gia"
                is_practice = False
                is_gia = True
                is_facultative = False
            elif "ФТД" in code or tip_obj == "6" or "факультатив" in block.lower():
                item_type = "facultative"
                is_practice = False
                is_gia = False
                is_facultative = True
            else:
                item_type = "discipline"
                is_practice = False
                is_gia = False
                is_facultative = False

            h_list = hours_by_row.get(str(disc_id), [])
            if not h_list and row.get("КодСтроки"):
                h_list = hours_by_row.get(str(row.get("КодСтроки")), [])

            row_kurs = safe_int(row.get("Курс"), default=0)

            # Собираем все сквозные (абсолютные) семестры дисциплины (1..12+)
            semesters_found = set()

            # а) Из записей часов (в Шахтах поле 'Семестр' = 1 или 2 на курсе, 'Курс' = 1..6)
            for h in h_list:
                h_sem = safe_int(h.get("Семестр"), default=0)
                h_kurs = safe_int(h.get("Курс"), default=0) or row_kurs
                if h_sem > 0 or h_kurs > 0:
                    abs_s = calculate_absolute_semester(h_sem, h_kurs)
                    if 1 <= abs_s <= 16:
                        semesters_found.add(abs_s)

            # б) Из атрибутов самой строки ПланыСтроки (Семестр, Сем)
            row_sem = safe_int(row.get("Семестр") or row.get("Сем"), default=0)
            if row_sem > 0:
                abs_s = calculate_absolute_semester(row_sem, row_kurs)
                if 1 <= abs_s <= 16:
                    semesters_found.add(abs_s)

            # в) Из форм контроля в строке (Экзамен, Зачет, КП, КР)
            control_fields = [
                "Экзамен", "Зачет", "ЗачетСОценкой", "ДифЗачет", "КП", "КР",
                "СемЭкз", "СемЗач", "СеместрЭкзамена", "СеместрЗачета"
            ]
            for c_field in control_fields:
                val = row.get(c_field)
                if val:
                    for s in parse_semesters_from_text(val):
                        abs_s = calculate_absolute_semester(s, row_kurs)
                        if 1 <= abs_s <= 16:
                            semesters_found.add(abs_s)

            # г) Если семестр так и не найден, но указан курс - берем начальный семестр курса
            if not semesters_found and row_kurs > 0:
                semesters_found.add((row_kurs - 1) * 2 + 1)

            semesters = sorted(list(semesters_found))
            semester = semesters[0] if semesters else (calculate_absolute_semester(1, row_kurs) if row_kurs else 1)
            semesters_str = ", ".join(str(s) for s in semesters) if semesters else str(semester)

            # Объемные часы занятий (КодТипаЧасов == '1' - плановые часы, или fallback на все часы)
            h_volume = [h for h in h_list if h.get("КодТипаЧасов", "1") == "1"]
            if not h_volume and h_list:
                h_volume = h_list

            lec = lab = prac = self_h = control_h = total_h = 0
            for h in h_volume:
                w_code = h.get("КодВидаРаботы")
                qty_val = h.get("Количество")
                if not qty_val or qty_val == "0":
                    continue
                qty_int = safe_int(safe_float(qty_val))
                if not qty_int:
                    continue
                if w_code == "101":
                    lec += qty_int
                elif w_code == "102":
                    lab += qty_int
                elif w_code in ("103", "104"):
                    prac += qty_int
                elif w_code == "107":
                    self_h += qty_int
                elif w_code == "108":
                    control_h += qty_int
                elif w_code == "1000":
                    total_h += qty_int

            # 1. Попытка взять официальный утвержденный ЗЕТ из строки ПланыСтроки
            ze_from_row = None
            ze_attr_names = [
                "ЗЕТэкспертное", "ЗЕТ_Экспертное", "ЗетЭкспертное", "ЗЕТ_экспертное",
                "ЗЕТфакт", "ЗЕТ_Факт", "ЗетФакт", "ЗЕТ_факт",
                "ЗЕТплан", "ЗЕТ_План", "ЗетПлан", "ЗЕТ_план",
                "ЗЕТ", "ЗЕ", "ВсегоЗЕТ",
                "ТрудоемкостьКредитов", "Кредитов", "Кредиты",
                "БазоваяЧастьЗЕТ", "ВариативнаяЧастьЗЕТ"
            ]
            for attr in ze_attr_names:
                val = row.get(attr)
                if val is not None and str(val).strip():
                    val_float = safe_float(val)
                    if val_float > 0:
                        ze_from_row = format_credit_val(val_float)
                        break

            # 2. Кредиты (ЗЕТ) из записей часов ПланыНовыеЧасы:
            # В Шахтах КодВидаРаботы: 50 - ЗЕТ факт/общий, 51 - ЗЕТ экспертное, 52 - ЗЕТ план
            ze_candidates = [h for h in h_list if h.get("КодВидаРаботы") in ("50", "51", "52")]
            ze_50 = [h for h in ze_candidates if h.get("КодВидаРаботы") == "50"]
            if ze_50:
                ze_candidates = ze_50
            ze_type1 = [h for h in ze_candidates if h.get("КодТипаЧасов") == "1"]
            ze_to_sum = ze_type1 if ze_type1 else ze_candidates

            # ВАЖНО: В ПланыНовыеЧасы часто присутствуют строки с Семестр="0" или без Семестра
            # (это итоги за курс или всю дисциплину) и строки с Семестр="1", "2" (семестровые).
            # Складывать их вместе нельзя, иначе ЗЕТ удваивается!
            has_explicit_sem = any(safe_int(h.get("Семестр"), default=0) > 0 for h in ze_to_sum)
            if has_explicit_sem:
                ze_to_sum = [h for h in ze_to_sum if safe_int(h.get("Семестр"), default=0) > 0]
            else:
                has_kurs = any(safe_int(h.get("Курс"), default=0) > 0 for h in ze_to_sum)
                if has_kurs:
                    ze_to_sum = [h for h in ze_to_sum if safe_int(h.get("Курс"), default=0) > 0]

            seen_ze_sem = set()
            ze_float_sum = 0.0
            for h in ze_to_sum:
                sem_key = (h.get("Курс"), h.get("Семестр"))
                if sem_key in seen_ze_sem and None not in sem_key:
                    continue
                seen_ze_sem.add(sem_key)
                ze_float_sum += safe_float(h.get("Количество", 0))

            ze_from_hours = format_credit_val(ze_float_sum) if ze_float_sum > 0 else 0

            # Приоритет ЗЕТ:
            # Если в строке ПланыСтроки указан официальный ЗЕТ — отдаем ему приоритет!
            if ze_from_row and ze_from_row > 0:
                ze = ze_from_row
            elif ze_from_hours and ze_from_hours > 0:
                ze = ze_from_hours
            else:
                ze = 0

            # Общие часы (total_h) из атрибутов строки, если вид работы 1000 не был указан
            tot_attr_names = ["ЧасовПоПлану", "ЧасовПоЗЕТ", "ВсегоЧасов", "Часов"]
            for attr in tot_attr_names:
                val = row.get(attr)
                if val is not None and str(val).strip():
                    val_int = safe_int(val)
                    if val_int > 0:
                        total_h = val_int
                        break

            if not total_h or total_h <= 0:
                calc_tot = lec + prac + lab + self_h + control_h
                total_h = calc_tot if calc_tot > 0 else (int(round(ze * 36)) if ze > 0 else 108)

            # Если ЗЕТ не определен, но часы известны — рассчитываем по академической норме (1 ЗЕТ = 36 ч)
            if not ze or ze <= 0:
                if total_h > 0:
                    ze = format_credit_val(round(total_h / 36.0, 1))
                else:
                    ze = 3

            exam_map = {
                "1": "экзамен",
                "2": "зачет",
                "3": "диф. зачет",
                "4": "курсовой проект",
                "5": "курсовая работа"
            }
            exam_forms = []
            semester_controls: Dict[int, List[str]] = {}
            session_controls: List[Dict[str, Any]] = []
            seen_sess_ctrl = set()

            for h in h_list:
                v = h.get("КодВидаРаботы")
                if v in exam_map:
                    c_name = exam_map[v]
                    exam_forms.append(c_name)
                    h_k = safe_int(h.get("Курс"), default=row_kurs)
                    h_s = safe_int(h.get("Семестр"), default=0)
                    h_sess = safe_int(h.get("Сессия"), default=0)

                    if h_s > 0 and h_k > 0:
                        abs_s = calculate_absolute_semester(h_s, h_k)
                        semester_controls.setdefault(abs_s, [])
                        if c_name not in semester_controls[abs_s]:
                            semester_controls[abs_s].append(c_name)
                    elif h_s > 0:
                        semester_controls.setdefault(h_s, [])
                        if c_name not in semester_controls[h_s]:
                            semester_controls[h_s].append(c_name)

                    if h_sess > 0 and h_k > 0:
                        key_sc = (h_k, h_sess, c_name)
                        if key_sc not in seen_sess_ctrl:
                            seen_sess_ctrl.add(key_sc)
                            session_controls.append({
                                "course": h_k,
                                "session_num": h_sess,
                                "control": c_name
                            })

            if row.get("Экзамен") or row.get("СемЭкз") or row.get("СеместрЭкзамена"):
                exam_forms.append("экзамен")
            if row.get("ЗачетСОценкой") or row.get("ДифЗачет"):
                exam_forms.append("диф. зачет")
            if row.get("Зачет") or row.get("СемЗач") or row.get("СеместрЗачета"):
                exam_forms.append("зачет")
            if row.get("КП"):
                exam_forms.append("курсовой проект")
            if row.get("КР"):
                exam_forms.append("курсовая работа")

            if not exam_forms:
                if tip_obj == "4":
                    exam_forms = ["курсовая работа"]
                elif tip_obj == "3":
                    exam_forms = ["диф. зачет"]
                else:
                    exam_forms = ["зачет"]

            exam_type = ", ".join(dict.fromkeys(exam_forms))
            cand_keys = [str(k) for k in [disc_id, row.get("Код"), row.get("КодСтроки"), row.get("КодОбъекта"), row.get("КодДисциплины")] if k]
            comps_raw = []
            for k in cand_keys:
                if k in comp_by_row:
                    comps_raw.extend(comp_by_row[k])

            # Если связей в таблицах нет, проверяем строковые атрибуты самой строки плана
            if not comps_raw:
                raw_comp_str = row.get("Компетенции") or row.get("КомпетенцииКоды") or row.get("ШифрыКомпетенций") or ""
                if raw_comp_str:
                    for ciph in extract_competency_codes_from_string(raw_comp_str):
                        if ciph in comps_by_cipher:
                            c_item = comps_by_cipher[ciph]
                            comps_raw.append({
                                "code": ciph,
                                "name": c_item["name"] or f"Компетенция {ciph}",
                                "indicator_code": f"И{ciph}.1" if not ciph.startswith("И") and "." not in ciph else ciph,
                                "indicator_name": c_item["name"] or f"Формирует знания и умения в рамках компетенции {ciph}"
                            })
                        else:
                            comps_raw.append({
                                "code": ciph,
                                "name": f"Компетенция {ciph}",
                                "indicator_code": f"И{ciph}.1" if not ciph.startswith("И") and "." not in ciph else ciph,
                                "indicator_name": f"Формирует знания и умения в рамках компетенции {ciph}"
                            })

            # Дедупликация компетенций с сохранением порядка
            seen_comps = set()
            comps = []
            for c in comps_raw:
                c_key = (c.get("code"), c.get("indicator_code"))
                if c_key not in seen_comps:
                    seen_comps.add(c_key)
                    comps.append(c)

            # ИУП-статус дисциплины и переаттестации
            row_reatts = []
            for k in cand_keys:
                if k in reattest_by_row:
                    row_reatts.extend(reattest_by_row[k])

            reattested_zet = sum(r["amount_studied"] for r in row_reatts if r["work_type_code"] == 50)
            has_reatt_hours = any(
                h.get("Переаттестовано") == "true" or (h.get("Курс") == "0" and h.get("Семестр") == "0")
                for h in h_list
            )

            if not is_iup:
                iup_status = "standard"
            elif (total_h == 0 or not semesters) and (row_reatts or has_reatt_hours or reattested_zet > 0):
                iup_status = "fully_closed"
            elif (row_reatts or has_reatt_hours or reattested_zet > 0) and total_h > 0:
                iup_status = "partially_closed"
            else:
                iup_status = "active_study"

            disciplines.append({
                "row_code": str(disc_id or ""),
                "code": code,
                "title": name,
                "block": block,
                "dept_name": dept_name,
                "dept_code": dept_id,
                "semester": semester,
                "semesters": semesters or [semester],
                "semesters_str": semesters_str,
                "total_ze": ze,
                "total_hours": total_h,
                "lectures": lec,
                "seminars": prac + lab,
                "contact_hours": lec + prac + lab,
                "self_hours": self_h,
                "control_hours": control_h,
                "exam_type": exam_type,
                "semester_controls": semester_controls,
                "session_controls": session_controls,
                "competencies": comps,
                "obj_type": tip_obj,
                "item_type": item_type,
                "is_practice": is_practice,
                "is_gia": is_gia,
                "is_facultative": is_facultative,
                "module_title": parent_module_title,
                "parent_module_code": parent_module_code,
                "is_iup_closed": (iup_status == "fully_closed"),
                "iup_status": iup_status,
                "reattestations": row_reatts,
                "reattested_zet": reattested_zet
            })

        modules_structured = []
        for m_id, m_info in modules_map.items():
            m_items = [
                d for d in disciplines
                if (d.get("module_title") and d["module_title"] == m_info["title"]) or
                   (d.get("parent_module_code") and d["parent_module_code"] == m_info["code"])
            ]
            modules_structured.append({
                "id": m_id,
                "title": m_info["title"],
                "code": m_info["code"],
                "is_module": m_info["is_module"],
                "is_elective_group": m_info["is_elective_group"],
                "items_count": len(m_items),
                "total_ze": sum(d.get("total_ze", 0) for d in m_items),
                "items": m_items
            })

        schedule_data = cls._parse_schedule_from_elems(elems_by_tag, start_year, study_years)

        return {
            "filename": filename,
            "direction_code": direction_code,
            "direction_title": direction_title,
            "profile_title": profile_title,
            "edu_level": edu_level,
            "study_form": study_form,
            "start_year": start_year,
            "study_years": study_years,
            "qualification": qualification,
            "schedule": schedule_data,
            "is_iup": is_iup,
            "iup_profile": {
                "is_iup": is_iup,
                "student_fio": student_fio,
                "group_name": group_name_iup,
                "base_plan_filename": base_plan_filename,
                "start_course": start_course,
                "start_semester": start_semester,
                "total_reattestations": len(all_reattestations),
                "reattestations": all_reattestations
            },
            "disciplines": disciplines,
            "pure_disciplines": [d for d in disciplines if d.get("item_type") == "discipline"],
            "practices": [d for d in disciplines if d.get("item_type") == "practice"],
            "gia": [d for d in disciplines if d.get("item_type") == "gia"],
            "facultatives": [d for d in disciplines if d.get("item_type") == "facultative"],
            "iup_closed_disciplines": [d for d in disciplines if d.get("iup_status") == "fully_closed"],
            "iup_active_disciplines": [d for d in disciplines if d.get("iup_status") != "fully_closed"],
            "modules": modules_structured
        }

    @classmethod
    def _parse_standard_xml(cls, root: ET.Element, filename: str) -> Dict[str, Any]:
        """Парсинг стандартного упрощенного XML учебного плана."""
        title_elem = root.find(".//Титул")
        if title_elem is None:
            title_elem = root.find(".//План")
        if title_elem is None:
            title_elem = root

        direction_code = (
            title_elem.get("Код") or
            title_elem.get("СпециальностьКод") or
            "09.03.03"
        )
        direction_title = (
            title_elem.get("Имя") or
            title_elem.get("СпециальностьНаименование") or
            "Прикладная информатика"
        )
        profile_title = (
            title_elem.get("Профиль") or
            title_elem.get("Специализация") or
            "Информационные технологии в гуманитарной сфере"
        )
        edu_level = title_elem.get("УровеньОбразования") or "бакалавриат"
        study_form = title_elem.get("ФормаОбучения") or "очная"
        start_year = safe_int(title_elem.get("ГодНачалаПодготовки"), default=2025)

        plan_data = {
            "filename": filename,
            "direction_code": direction_code,
            "direction_title": direction_title,
            "profile_title": profile_title,
            "edu_level": edu_level,
            "study_form": study_form,
            "start_year": start_year,
            "disciplines": []
        }

        rows = root.findall(".//СтрокиПлана/Строка") or root.findall(".//Строка") or root.findall(".//Дисциплина")

        # Карта модулей учебного плана
        parent_ids = set(r.get("КодРодителя") for r in rows if r.get("КодРодителя"))
        modules_map = {}
        for row in rows:
            r_id = row.get("Код") or row.get("НовИдДисциплины") or row.get("ИдетификаторДисциплины")
            r_name = row.get("Дисциплина") or row.get("Наименование")
            r_code = row.get("НовИдДисциплины") or row.get("ИдетификаторДисциплины") or ""
            r_tip = row.get("ТипОбъекта") or "2"
            if r_name and (r_tip in ("1", "5") or (r_id and r_id in parent_ids)):
                modules_map[str(r_id)] = {
                    "id": str(r_id),
                    "title": r_name.strip(),
                    "code": r_code.strip(),
                    "is_module": r_tip == "1",
                    "is_elective_group": r_tip == "5"
                }

        for row in rows:
            name = (
                row.get("Дисциплина") or
                row.get("Наименование") or
                row.get("НовИдДисциплины")
            )
            if not name:
                continue

            tip_obj = row.get("ТипОбъекта") or "2"
            r_id = row.get("Код") or row.get("НовИдДисциплины") or row.get("ИдетификаторДисциплины")
            if tip_obj in ("1", "5") or (r_id and r_id in parent_ids):
                continue

            code = row.get("НовИдДисциплины") or row.get("ИдетификаторДисциплины") or ""
            parent_id = row.get("КодРодителя")
            parent_module_title = ""
            parent_module_code = ""
            if parent_id and str(parent_id) in modules_map:
                parent_module_title = modules_map[str(parent_id)]["title"]
                parent_module_code = modules_map[str(parent_id)]["code"]

            # Точная классификация типа объекта (item_type)
            name_lower = name.lower()
            code_upper = code.upper()
            if "Б2" in code_upper or tip_obj == "3" or "практик" in name_lower:
                item_type = "practice"
                is_practice = True
                is_gia = False
                is_facultative = False
            elif "Б3" in code_upper or tip_obj == "4" or "аттестац" in name_lower or "вкр" in name_lower or "диплом" in name_lower:
                item_type = "gia"
                is_practice = False
                is_gia = True
                is_facultative = False
            elif "ФТД" in code_upper or tip_obj == "6" or "факульт" in name_lower:
                item_type = "facultative"
                is_practice = False
                is_gia = False
                is_facultative = True
            else:
                item_type = "discipline"
                is_practice = False
                is_gia = False
                is_facultative = False

            if "Б1.О" in code:
                block = "обязательной части"
            elif "Б1.В" in code:
                block = "части, формируемой участниками образовательных отношений"
            elif "Б2.О" in code:
                block = "обязательной части (практика)"
            elif "Б2.В" in code:
                block = "части, формируемой участниками образовательных отношений (практика)"
            elif "Б3" in code:
                block = "государственной итоговой аттестации"
            elif "ФТД" in code:
                block = "факультативных дисциплин"
            elif "Б4" in code:
                block = "элективных дисциплин по физической культуре и спорту"
            else:
                block = "обязательной части"

            dept_name = row.get("КафедраНазвание") or f"Кафедра {row.get('Кафедра', '')}".strip()
            row_kurs = safe_int(row.get("Курс"), default=0)

            sem_elems = row.findall(".//Сем")
            semesters_found = []
            lec = 0
            prac = 0
            lab = 0
            self_h = 0
            control_h = 0
            ze = 0
            total_h = 0
            exam_forms = []
            semester_controls: Dict[int, List[str]] = {}

            if sem_elems:
                ze_float = 0.0
                for sem_elem in sem_elems:
                    sem_num = safe_int(sem_elem.get("Ном") or sem_elem.get("Семестр"), default=0)
                    sem_kurs = safe_int(sem_elem.get("Курс") or row_kurs, default=0)
                    abs_s = calculate_absolute_semester(sem_num, sem_kurs)
                    if 1 <= abs_s <= 16:
                        semesters_found.append(abs_s)

                    lec += safe_int(safe_float(sem_elem.get("Лек") or sem_elem.get("Лекции")), default=0)
                    lab += safe_int(safe_float(sem_elem.get("Лаб") or sem_elem.get("Лабораторные")), default=0)
                    prac += safe_int(safe_float(sem_elem.get("Пр") or sem_elem.get("Практические")), default=0)
                    self_h += safe_int(safe_float(sem_elem.get("СРС") or sem_elem.get("СамостоятельнаяРабота")), default=0)
                    control_h += safe_int(safe_float(sem_elem.get("Контроль") or sem_elem.get("ЧасыКонтроль")), default=0)

                    # Извлечение ЗЕТ из семестровых атрибутов
                    s_ze = (
                        sem_elem.get("ЗЕТ") or
                        sem_elem.get("Кредиты") or
                        sem_elem.get("Кредитов") or
                        sem_elem.get("ЗЕ") or
                        sem_elem.get("ТрудоемкостьКредитов") or
                        sem_elem.get("Трудоемкость")
                    )
                    if s_ze is not None and str(s_ze).strip():
                        ze_float += safe_float(s_ze)

                    total_h += safe_int(safe_float(sem_elem.get("Всего") or sem_elem.get("Часов")), default=0)

                    s_ctrls = []
                    if sem_elem.get("Экз") or sem_elem.get("Экзамен"):
                        s_ctrls.append("экзамен")
                    if sem_elem.get("ДифЗач") or sem_elem.get("ЗачетСОценкой"):
                        s_ctrls.append("диф. зачет")
                    if sem_elem.get("Зач") or sem_elem.get("Зачет"):
                        s_ctrls.append("зачет")
                    if sem_elem.get("КП"):
                        s_ctrls.append("курсовой проект")
                    if sem_elem.get("КР"):
                        s_ctrls.append("курсовая работа")

                    for sc in s_ctrls:
                        exam_forms.append(sc)
                    if s_ctrls and abs_s > 0:
                        semester_controls.setdefault(abs_s, []).extend(s_ctrls)

                if ze_float > 0:
                    ze = format_credit_val(ze_float)

            # Атрибуты строки row (Семестр, Сем)
            row_sem = safe_int(row.get("Семестр") or row.get("Сем") or row.get("Ном"), default=0)
            if row_sem > 0:
                abs_s = calculate_absolute_semester(row_sem, row_kurs)
                if 1 <= abs_s <= 16:
                    semesters_found.append(abs_s)

            # Формы контроля в строке
            control_fields = [
                "Экзамен", "Зачет", "ЗачетСОценкой", "ДифЗачет", "КП", "КР",
                "СемЭкз", "СемЗач", "СеместрЭкзамена", "СеместрЗачета"
            ]
            for c_field in control_fields:
                val = row.get(c_field)
                if val:
                    ctrl_name = None
                    if "экз" in c_field.lower():
                        ctrl_name = "экзамен"
                    elif "диф" in c_field.lower() or "оценк" in c_field.lower():
                        ctrl_name = "диф. зачет"
                    elif "зач" in c_field.lower():
                        ctrl_name = "зачет"
                    elif "кп" in c_field.lower():
                        ctrl_name = "курсовой проект"
                    elif "кр" in c_field.lower():
                        ctrl_name = "курсовая работа"

                    parsed_s = parse_semesters_from_text(val)
                    for s in parsed_s:
                        abs_s = calculate_absolute_semester(s, row_kurs)
                        if 1 <= abs_s <= 16:
                            semesters_found.append(abs_s)
                            if ctrl_name:
                                semester_controls.setdefault(abs_s, []).append(ctrl_name)
                    if ctrl_name:
                        exam_forms.append(ctrl_name)

            # Если семестр так и не найден, но указан курс - берем начальный семестр курса
            if not semesters_found and row_kurs > 0:
                semesters_found.append((row_kurs - 1) * 2 + 1)

            semesters = sorted(list(set(semesters_found)))
            semester = semesters[0] if semesters else (calculate_absolute_semester(1, row_kurs) if row_kurs else 1)
            semesters_str = ", ".join(str(s) for s in semesters) if semesters else str(semester)

            # Если ЗЕТ не был найден в семестровых записях, ищем в атрибутах самой строки
            if not ze or ze <= 0:
                ze_attr_names = [
                    "ЗЕТ", "ЗЕТэкспертное", "ЗЕТфакт", "ЗЕТплан",
                    "Кредиты", "Кредитов", "ТрудоемкостьКредитов",
                    "ВсегоЗЕТ", "ЗЕ"
                ]
                for attr in ze_attr_names:
                    val = row.get(attr)
                    if val is not None and str(val).strip():
                        val_float = safe_float(val)
                        if val_float > 0:
                            ze = format_credit_val(val_float)
                            break

            contact_h = lec + prac + lab
            if not total_h or total_h <= 0:
                tot_attr_names = ["ЧасовПоПлану", "ВсегоЧасов", "ЧасовПоЗЕТ", "Часов"]
                for attr in tot_attr_names:
                    val = row.get(attr)
                    if val is not None and str(val).strip():
                        val_int = safe_int(val)
                        if val_int > 0:
                            total_h = val_int
                            break

            if not total_h or total_h <= 0:
                calc_total = contact_h + self_h + control_h
                total_h = calc_total if calc_total > 0 else (int(round(ze * 36)) if ze > 0 else 108)

            # Если ЗЕТ не определен, но известны часы — рассчитываем по академической норме (1 ЗЕТ = 36 ч)
            if not ze or ze <= 0:
                if total_h > 0:
                    ze = format_credit_val(round(total_h / 36.0, 1))
                else:
                    ze = 3

            if not exam_forms:
                exam_forms = ["зачет"]
            exam_type = ", ".join(dict.fromkeys(exam_forms))

            competencies = []
            comp_elems = row.findall(".//Компетенции/Компетенция") or row.findall(".//Компетенция")
            for c in comp_elems:
                raw_c = c.get("Код") or c.get("Индекс") or c.get("Шифр") or "УК-1"
                c_code = normalize_competency_code(raw_c)
                c_name = (c.get("Наименование") or c.get("Название") or f"Компетенция {c_code}").strip()
                ind_code = c.get("Индикатор") or (f"И{c_code}.1" if not c_code.startswith("И") and "." not in c_code else c_code)
                ind_name = c.get("ИндикаторНаименование") or f"Формирует знания, умения и навыки в рамках компетенции {c_code}"
                competencies.append({
                    "code": c_code,
                    "name": c_name,
                    "indicator_code": ind_code,
                    "indicator_name": ind_name
                })

            if not competencies:
                raw_comp_str = row.get("Компетенции") or row.get("КомпетенцииКоды") or row.get("ШифрыКомпетенций") or ""
                if raw_comp_str:
                    for ciph in extract_competency_codes_from_string(raw_comp_str):
                        competencies.append({
                            "code": ciph,
                            "name": f"Компетенция {ciph}",
                            "indicator_code": f"И{ciph}.1" if not ciph.startswith("И") and "." not in ciph else ciph,
                            "indicator_name": f"Формирует знания, умения и навыки в рамках компетенции {ciph}"
                        })

            seen_c = set()
            dedup_competencies = []
            for c in competencies:
                c_key = (c.get("code"), c.get("indicator_code"))
                if c_key not in seen_c:
                    seen_c.add(c_key)
                    dedup_competencies.append(c)
            competencies = dedup_competencies

            plan_data["disciplines"].append({
                "row_code": str(row.get("Код", "")),
                "code": code,
                "title": name,
                "block": block,
                "dept_name": dept_name,
                "dept_code": row.get("Кафедра", ""),
                "semester": semester,
                "semesters": semesters or [semester],
                "semesters_str": semesters_str,
                "total_ze": ze,
                "total_hours": total_h,
                "lectures": lec,
                "seminars": prac + lab,
                "contact_hours": contact_h,
                "self_hours": self_h,
                "control_hours": control_h,
                "exam_type": exam_type,
                "semester_controls": semester_controls,
                "competencies": competencies,
                "obj_type": tip_obj,
                "item_type": item_type,
                "is_practice": is_practice,
                "is_gia": is_gia,
                "is_facultative": is_facultative,
                "module_title": parent_module_title,
                "parent_module_code": parent_module_code
            })

        # Структурированное разделение сущностей для раздельного отображения
        plan_data["pure_disciplines"] = [d for d in plan_data["disciplines"] if d["item_type"] == "discipline"]
        plan_data["practices"] = [d for d in plan_data["disciplines"] if d["item_type"] == "practice"]
        plan_data["gia"] = [d for d in plan_data["disciplines"] if d["item_type"] == "gia"]
        plan_data["facultatives"] = [d for d in plan_data["disciplines"] if d["item_type"] == "facultative"]

        # Иерархические модули плана
        modules_structured = []
        for m_id, m_info in modules_map.items():
            m_items = [
                d for d in plan_data["disciplines"]
                if (d.get("module_title") and d["module_title"] == m_info["title"]) or
                   (d.get("parent_module_code") and d["parent_module_code"] == m_info["code"])
            ]
            modules_structured.append({
                "id": m_id,
                "title": m_info["title"],
                "code": m_info["code"],
                "is_module": m_info["is_module"],
                "is_elective_group": m_info["is_elective_group"],
                "items_count": len(m_items),
                "total_ze": sum(d.get("total_ze", 0) for d in m_items),
                "items": m_items
            })
        plan_data["modules"] = modules_structured
        plan_data["modules_map"] = modules_map

        plan_data["is_iup"] = False
        plan_data["iup_profile"] = {
            "is_iup": False,
            "student_fio": "",
            "group_name": "",
            "base_plan_filename": "",
            "start_course": 1,
            "start_semester": 1,
            "total_reattestations": 0,
            "reattestations": []
        }
        plan_data["iup_closed_disciplines"] = []
        plan_data["iup_active_disciplines"] = plan_data["disciplines"]

        # Индексация тегов для извлечения графика, если он присутствует
        elems_by_tag: Dict[str, List[ET.Element]] = defaultdict(list)
        for e in root.iter():
            tag = e.tag.split("}", 1)[1] if "}" in e.tag else (e.tag.split(":", 1)[1] if ":" in e.tag else e.tag)
            elems_by_tag[tag].append(e)

        plan_data["study_years"] = safe_int(plan_data.get("study_years", 4), default=4)
        plan_data["qualification"] = str(plan_data.get("qualification", ""))
        plan_data["schedule"] = cls._parse_schedule_from_elems(
            elems_by_tag,
            plan_data.get("start_year", 2025),
            plan_data.get("study_years", 4)
        )

        return plan_data

    @staticmethod
    def generate_demo_plx_xml() -> str:
        """Создает валидный пример XML в шахтинском стиле для тестирования парсера."""
        return """<?xml version="1.0" encoding="utf-8"?>
<Документ>
    <Титул 
        Код="09.03.03" 
        Имя="Прикладная информатика" 
        Профиль="Искусственный интеллект и анализ данных" 
        УровеньОбразования="бакалавриат" 
        ФормаОбучения="очная" 
        ГодНачалаПодготовки="2025" />
    <СтрокиПлана>
        <!-- Модуль-контейнер -->
        <Строка Код="100" ТипОбъекта="1" НовИдДисциплины="Б1.О.М01" Дисциплина="Модуль искусственного интеллекта и программной инженерии" />

        <Строка Код="101" КодРодителя="100" ТипОбъекта="2" НовИдДисциплины="Б1.О.01" Дисциплина="История России" Кафедра="42" КафедраНазвание="Кафедра фундаментальной и прикладной информатики">
            <Сем Ном="1" Лек="16" Пр="32" СРС="60" ЗЕТ="3" Экз="1" />
            <Компетенции>
                <Компетенция Код="УК-5" Наименование="Способен воспринимать межкультурное разнообразие общества" />
            </Компетенции>
        </Строка>
        <Строка Код="102" КодРодителя="100" ТипОбъекта="2" НовИдДисциплины="Б1.О.05" Дисциплина="Высшая математика и линейная алгебра" Кафедра="42" КафедраНазвание="Кафедра фундаментальной и прикладной информатики">
            <Сем Ном="1" Лек="32" Пр="32" СРС="80" ЗЕТ="4" Экз="1" />
            <Компетенции>
                <Компетенция Код="ОПК-1" Наименование="Способен применять естественнонаучные и общеинженерные знания" />
            </Компетенции>
        </Строка>
        <Строка Код="103" КодРодителя="100" ТипОбъекта="2" НовИдДисциплины="Б1.О.12" Дисциплина="Алгоритмы и структуры данных" Кафедра="42" КафедраНазвание="Кафедра фундаментальной и прикладной информатики">
            <Сем Ном="2" Лек="24" Пр="48" СРС="72" ЗЕТ="4" Экз="1" />
            <Компетенции>
                <Компетенция Код="ОПК-2" Наименование="Способен разрабатывать алгоритмы и программы" />
            </Компетенции>
        </Строка>
        <Строка Код="104" КодРодителя="100" ТипОбъекта="2" НовИдДисциплины="Б1.В.03" Дисциплина="Машинное обучение и анализ больших данных" Кафедра="42" КафедраНазвание="Кафедра фундаментальной и прикладной информатики">
            <Сем Ном="4" Лек="18" Пр="36" СРС="90" ЗЕТ="4" Экз="1" />
            <Компетенции>
                <Компетенция Код="ПК-1" Наименование="Способен проектировать и внедрять модели машинного обучения" />
            </Компетенции>
        </Строка>

        <!-- Практика (Б2) -->
        <Строка Код="201" ТипОбъекта="3" НовИдДисциплины="Б2.О.01(У)" Дисциплина="Учебная технологическая (проектно-технологическая) практика" Кафедра="42" КафедраНазвание="Кафедра фундаментальной и прикладной информатики">
            <Сем Ном="4" Лек="0" Пр="72" СРС="144" ЗЕТ="6" Зач="1" />
            <Компетенции>
                <Компетенция Код="ОПК-2" Наименование="Способен разрабатывать алгоритмы и программы" />
                <Компетенция Код="ПК-1" Наименование="Способен проектировать и внедрять модели машинного обучения" />
            </Компетенции>
        </Строка>

        <!-- ГИА (Б3) -->
        <Строка Код="301" ТипОбъекта="4" НовИдДисциплины="Б3.01(Д)" Дисциплина="Выполнение и защита выпускной квалификационной работы" Кафедра="42" КафедраНазвание="Кафедра фундаментальной и прикладной информатики">
            <Сем Ном="8" Лек="0" Пр="0" СРС="216" ЗЕТ="6" Экз="1" />
            <Компетенции>
                <Компетенция Код="УК-5" Наименование="Способен воспринимать межкультурное разнообразие общества" />
                <Компетенция Код="ОПК-1" Наименование="Способен применять естественнонаучные знания" />
                <Компетенция Код="ПК-1" Наименование="Способен проектировать и внедрять модели машинного обучения" />
            </Компетенции>
        </Строка>
    </СтрокиПлана>
</Документ>
"""

    @classmethod
    def parse(cls, content_input: Union[bytes, str], filename: str = "plan.plx") -> CurriculumPlanData:
        """Парсит план и возвращает типизированный объект CurriculumPlanData."""
        raw_dict = cls.parse_plx_content(content_input, filename)
        return dict_to_curriculum_plan(raw_dict)


def dict_to_curriculum_plan(data: Dict[str, Any]) -> CurriculumPlanData:
    """
    Преобразует сырой словарь распарсенного плана в типизированный объект CurriculumPlanData.
    Обеспечивает валидацию и приведение вложенных структур (дисциплины, компетенции,
    модули, профиль ИУП) к моделям с сохранением dict-like доступа.
    """
    disciplines: List[DisciplineItem] = []
    for d in data.get("disciplines", []):
        if isinstance(d, DisciplineItem):
            disciplines.append(d)
            continue

        comps = [
            c if isinstance(c, CompetencyItem) else CompetencyItem(
                code=str(c.get("code", "")),
                name=str(c.get("name", "")),
                indicator_code=str(c.get("indicator_code", "")),
                indicator_name=str(c.get("indicator_name", ""))
            )
            for c in d.get("competencies", [])
        ]

        reatts = [
            r if isinstance(r, ReattestationItem) else ReattestationItem(
                id=r.get("id"),
                row_id=str(r.get("row_id", "")),
                work_type_code=safe_int(r.get("work_type_code", 0)),
                original_course=safe_int(r.get("original_course", 0)),
                original_semester=safe_int(r.get("original_semester", 0)),
                amount_was=safe_float(r.get("amount_was", 0.0)),
                amount_studied=safe_float(r.get("amount_studied", 0.0)),
                attestation_type=str(r.get("attestation_type", "")),
                attestation_type_code=safe_int(r.get("attestation_type_code", 0)),
                grade=str(r.get("grade", "")),
                grade_code=r.get("grade_code")
            )
            for r in d.get("reattestations", [])
        ]

        item = DisciplineItem(
            row_code=str(d.get("row_code", "")),
            code=str(d.get("code", "")),
            title=str(d.get("title", "")),
            block=str(d.get("block", "")),
            dept_name=str(d.get("dept_name", "")),
            dept_code=str(d.get("dept_code", "")),
            semester=safe_int(d.get("semester", 1)),
            semesters=d.get("semesters", [safe_int(d.get("semester", 1))]),
            semesters_str=str(d.get("semesters_str", "")),
            total_ze=format_credit_val(d.get("total_ze", 0)),
            total_hours=safe_int(d.get("total_hours", 0)),
            lectures=safe_int(d.get("lectures", 0)),
            seminars=safe_int(d.get("seminars", 0)),
            contact_hours=safe_int(d.get("contact_hours", 0)),
            self_hours=safe_int(d.get("self_hours", 0)),
            control_hours=safe_int(d.get("control_hours", 0)),
            exam_type=str(d.get("exam_type", "зачет")),
            semester_controls=d.get("semester_controls", {}),
            session_controls=d.get("session_controls", []),
            competencies=comps,
            obj_type=str(d.get("obj_type", "2")),
            item_type=str(d.get("item_type", "discipline")),
            is_practice=bool(d.get("is_practice", False)),
            is_gia=bool(d.get("is_gia", False)),
            is_facultative=bool(d.get("is_facultative", False)),
            module_title=str(d.get("module_title", "")),
            parent_module_code=str(d.get("parent_module_code", "")),
            is_iup_closed=bool(d.get("is_iup_closed", False)),
            iup_status=str(d.get("iup_status", "standard")),
            reattestations=reatts,
            reattested_zet=safe_float(d.get("reattested_zet", 0.0))
        )
        disciplines.append(item)

    raw_iup = data.get("iup_profile") or {}
    if isinstance(raw_iup, IUPProfile):
        iup_profile = raw_iup
    else:
        iup_reatts = [
            r if isinstance(r, ReattestationItem) else ReattestationItem(
                id=r.get("id"),
                row_id=str(r.get("row_id", "")),
                work_type_code=safe_int(r.get("work_type_code", 0)),
                original_course=safe_int(r.get("original_course", 0)),
                original_semester=safe_int(r.get("original_semester", 0)),
                amount_was=safe_float(r.get("amount_was", 0.0)),
                amount_studied=safe_float(r.get("amount_studied", 0.0)),
                attestation_type=str(r.get("attestation_type", "")),
                attestation_type_code=safe_int(r.get("attestation_type_code", 0)),
                grade=str(r.get("grade", "")),
                grade_code=r.get("grade_code")
            )
            for r in raw_iup.get("reattestations", [])
        ]
        iup_profile = IUPProfile(
            is_iup=bool(raw_iup.get("is_iup", data.get("is_iup", False))),
            student_fio=str(raw_iup.get("student_fio", "")),
            group_name=str(raw_iup.get("group_name", "")),
            base_plan_filename=str(raw_iup.get("base_plan_filename", "")),
            start_course=safe_int(raw_iup.get("start_course", 1)),
            start_semester=safe_int(raw_iup.get("start_semester", 1)),
            total_reattestations=safe_int(raw_iup.get("total_reattestations", len(iup_reatts))),
            reattestations=iup_reatts
        )

    modules: List[CurriculumModule] = []
    for m in data.get("modules", []):
        if isinstance(m, CurriculumModule):
            modules.append(m)
            continue
        m_items: List[DisciplineItem] = []
        for it in m.get("items", []):
            if isinstance(it, DisciplineItem):
                m_items.append(it)
            elif isinstance(it, dict):
                matched = next(
                    (d for d in disciplines if d.code == it.get("code") and d.title == it.get("title")),
                    None
                )
                if matched:
                    m_items.append(matched)
        modules.append(CurriculumModule(
            id=str(m.get("id", "")),
            title=str(m.get("title", "")),
            code=str(m.get("code", "")),
            is_module=bool(m.get("is_module", False)),
            is_elective_group=bool(m.get("is_elective_group", False)),
            items_count=safe_int(m.get("items_count", len(m_items))),
            total_ze=format_credit_val(m.get("total_ze", sum(it.total_ze for it in m_items))),
            items=m_items
        ))

    pure = [d for d in disciplines if d.item_type == "discipline"]
    practices = [d for d in disciplines if d.item_type == "practice"]
    gia = [d for d in disciplines if d.item_type == "gia"]
    facultatives = [d for d in disciplines if d.item_type == "facultative"]
    closed = [d for d in disciplines if d.iup_status == "fully_closed"]
    active = [d for d in disciplines if d.iup_status != "fully_closed"]

    # Десериализация графика учебного процесса (КУГ)
    schedule_data = None
    raw_sch = data.get("schedule")
    if raw_sch:
        if isinstance(raw_sch, CurriculumScheduleData):
            schedule_data = raw_sch
        elif isinstance(raw_sch, dict):
            courses_dict: Dict[int, ScheduleCourseItem] = {}
            for c_num, c_val in raw_sch.get("courses", {}).items():
                if isinstance(c_val, ScheduleCourseItem):
                    courses_dict[int(c_num)] = c_val
                elif isinstance(c_val, dict):
                    weeks_items = []
                    for w in c_val.get("weeks", []):
                        days_items = [
                            ScheduleDayItem(**d) if isinstance(d, dict) else d
                            for d in w.get("days", [])
                        ]
                        weeks_items.append(ScheduleWeekItem(
                            week_num=w["week_num"],
                            is_uniform=bool(w.get("is_uniform", True)),
                            dom_symbol=str(w.get("dom_symbol", "Т")),
                            dom_color=str(w.get("dom_color", "#e0f2fe")),
                            days=days_items,
                            start_date=str(w.get("start_date", "")),
                            end_date=str(w.get("end_date", "")),
                        ))
                    budget_items = [
                        ScheduleBudgetItem(**b) if isinstance(b, dict) else b
                        for b in c_val.get("budget", [])
                    ]
                    sessions_items = [
                        ScheduleSessionItem(**s) if isinstance(s, dict) else s
                        for s in c_val.get("sessions", [])
                    ]
                    courses_dict[int(c_num)] = ScheduleCourseItem(
                        course_num=int(c_num),
                        weeks_count=safe_int(c_val.get("weeks_count", len(weeks_items))),
                        academic_year=str(c_val.get("academic_year", "")),
                        calendar_year_start=safe_int(c_val.get("calendar_year_start", 0)),
                        total_weeks=safe_float(c_val.get("total_weeks", 52.0)),
                        weeks=weeks_items,
                        budget=budget_items,
                        sessions=sessions_items,
                        is_balanced=bool(c_val.get("is_balanced", True)),
                        notes=str(c_val.get("notes", ""))
                    )
            schedule_data = CurriculumScheduleData(
                courses=courses_dict,
                semesters=raw_sch.get("semesters", []),
                legend=raw_sch.get("legend", ACTIVITY_SYMBOLS),
                study_years_count=safe_int(raw_sch.get("study_years_count", len(courses_dict))),
                warnings=raw_sch.get("warnings", [])
            )

    return CurriculumPlanData(
        filename=str(data.get("filename", "")),
        direction_code=str(data.get("direction_code", "")),
        direction_title=str(data.get("direction_title", "")),
        profile_title=str(data.get("profile_title", "")),
        edu_level=str(data.get("edu_level", "")),
        study_form=str(data.get("study_form", "")),
        start_year=safe_int(data.get("start_year", 2025)),
        study_years=safe_int(data.get("study_years", 4)),
        qualification=str(data.get("qualification", "")),
        is_iup=bool(data.get("is_iup", False)),
        iup_profile=iup_profile,
        disciplines=disciplines,
        pure_disciplines=pure,
        practices=practices,
        gia=gia,
        facultatives=facultatives,
        iup_closed_disciplines=closed,
        iup_active_disciplines=active,
        modules=modules,
        modules_map=data.get("modules_map", {}),
        schedule=schedule_data
    )


def parse_curriculum_plan(
    content_input: Union[bytes, str],
    filename: str = "plan.plx",
    as_dict: bool = False
) -> Union[CurriculumPlanData, Dict[str, Any]]:
    """
    Главная публичная функция парсинга учебного плана (PLX, XML, ZIP).

    :param content_input: байты файла или строка XML
    :param filename: имя исходного файла для определения формата и метаданных
    :param as_dict: если True, возвращает стандартный словарь вместо CurriculumPlanData
    :return: типизированный объект CurriculumPlanData (с поддержкой dict-интерфейса) или dict
    """
    raw_dict = PLXParser.parse_plx_content(content_input, filename)
    if as_dict:
        return raw_dict
    return dict_to_curriculum_plan(raw_dict)


parse_curriculum = parse_curriculum_plan
parse_plx = parse_curriculum_plan
CurriculumParser = PLXParser


def parse_curriculum_schedule(
    content_input: Union[bytes, str],
    filename: str = "plan.plx"
) -> Optional[CurriculumScheduleData]:
    """Извлекает и возвращает только календарный учебный график плана."""
    plan = parse_curriculum_plan(content_input, filename)
    return plan.schedule

