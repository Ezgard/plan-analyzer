# Curriculum Parser (`curriculum_parser`)

Автономный переносимый Python-пакет для синтаксического анализа, валидации и нормализации учебных планов основных профессиональных образовательных программ (ОПОП) высшего образования Российской Федерации.

Поддерживает форматы:
- **Шахтинские файлы PLX / XML (MMIS / ГосИнсп / Лаборатория ММИС)** — XML DiffGram схем `dsMMISDB.xsd` (в кодировках UTF-16LE, UTF-16BE, UTF-8, CP1251, а также упакованные в `.zip` / `.plx` архивы);
- **Стандартный и упрощенный XML учебного плана**;
- **Индивидуальные учебные планы (ИУП)** — с автоматическим распознаванием переаттестаций, закрытых дисциплин и активных дисциплин студента.

---

## Ключевые особенности

1. **Полная автономность и 0 runtime-зависимостей**:
   Пакет написан исключительно на стандартной библиотеке Python 3.9+ (`xml.etree.ElementTree`, `zipfile`, `gzip`, `io`, `re`, `functools`, `dataclasses`, `collections`, `json`). Для запуска в продакшене не требуются никакие внешние библиотеки.
2. **Встроенная защита от XXE и инъекций**:
   Автоматическая валидация безопасности XML на этапе разбора (`validate_xml_security`), блокирующая атаки XML External Entity (XXE), DTD-инъекции и разыменование внешних сущностей.
3. **Двойная совместимость моделей (Object & Dict-like)**:
   Все структуры данных (`CurriculumPlanData`, `DisciplineItem`, `CompetencyItem` и др.) представляют собой строгие `dataclass`-модели, одновременно реализующие методы словарей (`__getitem__`, `get`, `keys()`, `values()`, `items()`, `to_dict()`, `to_json()`). Это гарантирует 100% обратную совместимость с кодом, ожидающим как типизированные объекты, так и стандартные словари `dict`.
4. **Нормализация шифров компетенций**:
   Автоматическая замена нестандартных символов тире (`–`, `—`, `−`), неразрывных пробелов (`\xa0`) и форматирование к каноническому виду (`УК-5`, `ОПК-1`, `ПК-4.1`) с кэшированием через `functools.lru_cache`.
5. **Корректный расчет сквозных семестров**:
   В планах MMIS часы раскладываются по курсу и семестру на курсе (1 — осенний, 2 — весенний). Парсер автоматически вычисляет абсолютный сквозной семестр (1..12+).

---

## Установка

### Вариант 1: Установка в режиме разработки (pip)
```bash
pip install -e modules/curriculum_parser
```

### Вариант 2: Прямое копирование в сторонний проект
Поскольку пакет полностью изолирован и не имеет зависимостей от внешних библиотек, вы можете просто скопировать директорию `modules/curriculum_parser` в ваш проект (например, в директорию `my_project/curriculum_parser/`) и использовать стандартный импорт:
```python
from curriculum_parser import parse_curriculum_plan, PLXParser
```

---

## Быстрый старт

### Процедурный API (`parse_curriculum_plan`)

```python
from curriculum_parser import parse_curriculum_plan

# Чтение из файла (поддерживаются .plx, .xml, .zip)
with open("plan.plx", "rb") as f:
    content = f.read()

# Парсинг в типизированный объект CurriculumPlanData
plan = parse_curriculum_plan(content, filename="plan.plx")

# Доступ к полям через атрибуты:
print(f"Направление: {plan.direction_code} — {plan.direction_title}")
print(f"Профиль: {plan.profile_title}")
print(f"Уровень: {plan.edu_level}, Форма: {plan.study_form}, Год: {plan.start_year}")
print(f"Всего дисциплин: {len(plan.disciplines)}")

# Доступ к полям через синтаксис словаря (обратная совместимость):
print(f"Направление (dict-like): {plan['direction_code']}")

# Поиск дисциплины по коду или названию
math = plan.find_discipline("Математический анализ")
if math:
    print(f"Найдена: {math.title}, ЗЕТ: {math.total_ze}, Семестр: {math.semester}")

# Фильтрация дисциплин по семестру и блокам
first_sem = plan.filter_by_semester(1)
base_block = plan.filter_by_block("Б1.О")
```

### Получение стандартного словаря (`dict`)

Если вашему коду требуется строго стандартный словарь `dict`:

```python
# Способ 1: через параметр as_dict=True
plan_dict = parse_curriculum_plan(content, filename="plan.plx", as_dict=True)

# Способ 2: вызов метода to_dict() у модели
plan_model = parse_curriculum_plan(content, filename="plan.plx")
plan_dict = plan_model.to_dict()

# Способ 3: экспорт в форматированный JSON
plan_json = plan_model.to_json(indent=2)
```

### Объектно-ориентированный API (`PLXParser` / `CurriculumParser`)

```python
from curriculum_parser import PLXParser

# Генерация демонстрационного XML для тестирования
demo_xml = PLXParser.generate_demo_plx_xml()

# Парсинг содержимого в словарь
result_dict = PLXParser.parse_plx_content(demo_xml, "demo.plx")

# Парсинг в строго типизированную модель
result_model = PLXParser.parse(demo_xml, "demo.plx")
```

---

## Структуры данных и модели

### `CurriculumPlanData`
Корневая структура распарсенного учебного плана:
- `filename: str` — имя исходного файла;
- `direction_code: str` — шифр направления подготовки (например, `09.03.03`);
- `direction_title: str` — наименование направления (например, `Прикладная информатика`);
- `profile_title: str` — наименование профиля/направленности ОПОП;
- `edu_level: str` — уровень образования (`бакалавриат`, `магистратура`, `специалитет`);
- `study_form: str` — форма обучения (`очная`, `заочная`, `очно-заочная`);
- `start_year: int` — год начала подготовки (например, `2025`);
- `is_iup: bool` — признак индивидуального плана студента;
- `iup_profile: IUPProfile` — метаданные ИУП (студент, группа, переаттестации);
- `disciplines: List[DisciplineItem]` — полный перечень всех элементов плана;
- `pure_disciplines: List[DisciplineItem]` — теоретические дисциплины (Б1);
- `practices: List[DisciplineItem]` — практики (Б2);
- `gia: List[DisciplineItem]` — государственная итоговая аттестация (Б3);
- `facultatives: List[DisciplineItem]` — факультативные дисциплины (ФТД);
- `iup_closed_disciplines: List[DisciplineItem]` — дисциплины, зачтенные при переаттестации;
- `iup_active_disciplines: List[DisciplineItem]` — дисциплины, подлежащие изучению;
- `modules: List[CurriculumModule]` — иерархические блоки и модули плана;
- `modules_map: Dict[str, Any]` — исходная карта связей модулей.

Методы:
- `to_dict() -> Dict[str, Any]` — сериализация в чистый словарь;
- `to_json(indent: int = 2) -> str` — сериализация в JSON;
- `find_discipline(code_or_title: str) -> Optional[DisciplineItem]` — поиск;
- `filter_by_semester(semester: int) -> List[DisciplineItem]` — фильтрация по семестру;
- `filter_by_block(block_prefix: str) -> List[DisciplineItem]` — фильтрация по префиксу блока (`Б1.О`, `Б2`, `ФТД`).

### `DisciplineItem`
Элемент учебного плана (дисциплина, практика или ГИА):
- `code: str` — шифр дисциплины (например, `Б1.О.01`);
- `title: str` — наименование дисциплины;
- `block: str` — блок (`Блок 1`, `Блок 2`, `Блок 3`);
- `dept_name: str` — наименование кафедры;
- `dept_code: str` — идентификатор кафедры;
- `semester: int` — основной семестр изучения;
- `semesters: List[int]` — список семестров изучения;
- `total_ze: int` — трудоемкость в зачетных единицах (ЗЕТ);
- `total_hours: int` — общий объем часов;
- `lectures: int` — лекционные часы;
- `seminars: int` — практические и лабораторные занятия;
- `contact_hours: int` — контактная работа;
- `self_hours: int` — самостоятельная работа студента (СРС);
- `control_hours: int` — часы контроля;
- `exam_type: str` — форма промежуточной аттестации (`экзамен`, `зачет`, `дифзачет`);
- `competencies: List[CompetencyItem]` — закрепленные компетенции и индикаторы;
- `item_type: str` — тип элемента (`discipline`, `practice`, `gia`, `facultative`);
- `module_title: str` — название родительского модуля/блока;
- `iup_status: str` — статус в ИУП (`standard`, `active_study`, `fully_closed`, `partially_closed`);
- `reattestations: List[ReattestationItem]` — данные о переаттестациях.

---

## Обработка исключений

Пакет предоставляет строгую иерархию исключений:

```
CurriculumParsingError (базовое исключение)
└── PLXParsingError (ошибки синтаксиса/чтения XML и PLX)
    ├── SecurityValidationError (обнаружение XXE или DTD атак)
    └── EmptyPlanError (пустой файл или отсутствие полезных данных)
```

Пример безопасной обработки:

```python
from curriculum_parser import (
    parse_curriculum_plan,
    CurriculumParsingError,
    SecurityValidationError,
    EmptyPlanError
)

try:
    plan = parse_curriculum_plan(raw_bytes, "unknown.plx")
except SecurityValidationError:
    print("Внимание! Обнаружена попытка внедрения XXE!")
except EmptyPlanError:
    print("Передан пустой файл плана.")
except CurriculumParsingError as err:
    print(f"Ошибка синтаксического анализа: {err}")
```

---

## Тестирование

Набор тестов полностью автономен и не требует базы данных или сетевого подключения.

Запуск тестов:
```bash
pytest modules/curriculum_parser/tests
```
