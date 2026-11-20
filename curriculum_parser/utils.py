"""
Вспомогательные утилиты для парсинга учебных планов:
- Безопасное приведение типов (safe_int, safe_float)
- Расчет сквозных семестров (calculate_absolute_semester)
- Извлечение семестров из текста (parse_semesters_from_text)
- Мемоизированная нормализация шифров компетенций (normalize_competency_code)
- Извлечение компетенций из строки (extract_competency_codes_from_string)
- Распаковка zip и автоматическое определение кодировок (decode_raw_bytes)
- Валидация безопасности XML и защита от XXE атак (validate_xml_security)

Полностью автономный модуль без зависимостей от внешних библиотек или БД.
"""
import functools
import gzip
import io
import re
import zipfile
from typing import Any, List, Union

try:
    from .exceptions import PLXParsingError, SecurityValidationError, EmptyPlanError
except (ImportError, ValueError):
    from curriculum_parser.exceptions import (  # type: ignore
        PLXParsingError, SecurityValidationError, EmptyPlanError
    )


def safe_int(value: Any, default: int = 0) -> int:
    """
    Безопасное преобразование значения в целое число без исключений.
    Корректно обрабатывает None, пустые строки, числа с плавающей точкой,
    а также строки с разделителем-запятой (например '3,0' -> 3).
    """
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    val_str = str(value).strip().replace(",", ".")
    if not val_str:
        return default
    try:
        return int(float(val_str))
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Безопасное преобразование значения в число с плавающей точкой.
    Корректно обрабатывает None, пустые строки и запятые в качестве десятичного разделителя.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    val_str = str(value).strip().replace(",", ".")
    if not val_str:
        return default
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return default


def format_credit_val(value: Any, default: Union[int, float] = 0) -> Union[int, float]:
    """
    Форматирует число кредитов/ЗЕТ:
    если целое число (3.0, 4.0), возвращает int (3, 4),
    если дробное (1.5, 2.5), возвращает округленный float (1.5, 2.5).
    """
    f = safe_float(value, default=float(default))
    if f <= 0:
        return default
    if f.is_integer():
        return int(f)
    return round(f, 2)


def calculate_absolute_semester(sem_val: Any, kurs_val: Any = None, default: int = 1) -> int:
    """
    Вычисляет сквозной (абсолютный) номер семестра (1..12+).
    В планах MMIS (Шахты) в таблицах часов поле 'Семестр' хранит номер семестра
    на текущем курсе (1 - осенний, 2 - весенний), а номер курса лежит в поле 'Курс' (1..6).
    Если семестр > 2, он уже является сквозным абсолютным.
    Если курс >= 1 и семестр в (1, 2), сквозной семестр = (kurs - 1) * 2 + sem.
    Если указан только курс без семестра на курсе, сквозной семестр = (kurs - 1) * 2 + 1.
    """
    s = safe_int(sem_val, default=0)
    k = safe_int(kurs_val, default=0)

    # Если уже указан сквозной семестр старше 2 (например 3, 4, 5, 6, 7, 8)
    if s > 2:
        return s

    # Если указан курс и семестр на курсе (1 или 2)
    if k >= 1 and s in (1, 2):
        return (k - 1) * 2 + s

    # Если указан только курс без семестра на курсе
    if k >= 1 and s == 0:
        return (k - 1) * 2 + 1

    # Если указан только семестр без курса (1 или 2)
    if s > 0:
        return s

    return default


def parse_semesters_from_text(val: Any) -> List[int]:
    """Извлекает номера семестров из строковых атрибутов (например '3', '3, 4', '3 4', '1-2')."""
    if not val:
        return []
    numbers = [int(n) for n in re.findall(r"\b\d+\b", str(val))]
    return [n for n in numbers if 1 <= n <= 16]


_RE_DASH = re.compile(r"\s*[\u2010\u2011\u2012\u2013\u2014\u2015\u2212-]\s*")
_RE_SPACES = re.compile(r"\s+")
_RE_COMP_SPLIT = re.compile(r"[,;\n\r]+")
_RE_SUB_PARTS = re.compile(r"(?<=\d)\s+(?=[А-ЯЁA-Z])")


@functools.lru_cache(maxsize=8192)
def normalize_competency_code(val: Any) -> str:
    """
    Нормализует шифр компетенции или индикатора.
    Устраняет длинные тире, неразрывные пробелы и лишние пробелы вокруг дефиса:
    'ПК – 1' -> 'ПК-1', 'ПК - 4.1' -> 'ПК-4.1', 'УК - 5' -> 'УК-5'.
    Мемоизирован для максимального быстродействия.
    """
    if not val:
        return ""
    s = str(val).strip().replace("\xa0", " ")
    s = _RE_DASH.sub("-", s)
    s = _RE_SPACES.sub(" ", s).strip(". ")
    return s


def extract_competency_codes_from_string(text: str) -> List[str]:
    """
    Извлекает и нормализует шифры компетенций из строкового поля (например 'УК – 1; ОПК - 2' или 'УК-1 УК-2').
    """
    if not text:
        return []
    result = []
    primary_parts = [p.strip() for p in _RE_COMP_SPLIT.split(str(text)) if p.strip()]
    for part in primary_parts:
        sub_parts = _RE_SUB_PARTS.split(part)
        for sp in sub_parts:
            code = normalize_competency_code(sp)
            if code and any(ch.isalpha() for ch in code):
                result.append(code)
    return result


def decode_raw_bytes(raw_content: bytes) -> str:
    """
    Распаковывает zip при необходимости и определяет кодировку XML.
    Поддерживает: ZIP .plx, BOM (UTF-8, UTF-16LE, UTF-16BE), UTF-8, UTF-16LE, CP1251.
    """
    if not raw_content:
        return ""

    # 1. Проверка на zip-архив (Шахтинские .plx часто пакуются в zip)
    if raw_content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw_content)) as z:
                for name in z.namelist():
                    if name.lower().endswith((".xml", ".plx")):
                        return decode_raw_bytes(z.read(name))
                if z.namelist():
                    return decode_raw_bytes(z.read(z.namelist()[0]))
        except (zipfile.BadZipFile, KeyError, io.UnsupportedOperation) as e:
            raise PLXParsingError(f"Ошибка чтения архива PLX: {e}") from e

    # 1.1. Проверка на gzip-сжатие
    if raw_content.startswith(b"\x1f\x8b"):
        try:
            return decode_raw_bytes(gzip.decompress(raw_content))
        except Exception as e:
            raise PLXParsingError(f"Ошибка распаковки gzip-содержимого: {e}") from e

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


def validate_xml_security(xml_text: str) -> None:
    """
    Проверяет XML на XXE (XML External Entity) инъекции и DTD эксплойты.
    Бросает SecurityValidationError в случае обнаружения опасных конструкций.
    """
    upper_xml = xml_text.upper()
    if "<!ENTITY" in upper_xml or ("<!DOCTYPE" in upper_xml and any(w in upper_xml for w in ("SYSTEM", "PUBLIC"))):
        raise SecurityValidationError("Загрузка внешних XML-сущностей (XXE) заблокирована политикой безопасности.")
