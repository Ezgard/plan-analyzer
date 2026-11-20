"""
Автономные тесты для модуля парсинга учебных планов curriculum_parser.
Адаптированы 14 тестов логики парсера без зависимостей от backend или БД.
"""
import unittest
import io
import os
import glob
import zipfile
from pathlib import Path

try:
    from modules.curriculum_parser import (
        PLXParser,
        PLXParsingError,
        calculate_absolute_semester,
        normalize_competency_code,
        parse_curriculum_plan,
        CurriculumPlanData,
    )
except ImportError:
    from curriculum_parser import (  # type: ignore
        PLXParser,
        PLXParsingError,
        calculate_absolute_semester,
        normalize_competency_code,
        parse_curriculum_plan,
        CurriculumPlanData,
    )


class TestCurriculumParser(unittest.TestCase):

    def test_parse_demo_plx_xml(self):
        demo_xml = PLXParser.generate_demo_plx_xml()
        parsed = PLXParser.parse_plx_content(demo_xml, "test_demo.plx")

        self.assertEqual(parsed["filename"], "test_demo.plx")
        self.assertEqual(parsed["direction_code"], "09.03.03")
        self.assertEqual(parsed["direction_title"], "Прикладная информатика")
        self.assertEqual(parsed["profile_title"], "Искусственный интеллект и анализ данных")
        self.assertEqual(parsed["edu_level"], "бакалавриат")
        self.assertEqual(parsed["study_form"], "очная")
        self.assertEqual(parsed["start_year"], 2025)

        disciplines = parsed["disciplines"]
        self.assertEqual(len(disciplines), 6)
        self.assertEqual(len(parsed["pure_disciplines"]), 4)
        self.assertEqual(len(parsed["practices"]), 1)
        self.assertEqual(len(parsed["gia"]), 1)
        self.assertEqual(len(parsed["modules"]), 1)

        history = next(d for d in disciplines if d["code"] == "Б1.О.01")
        self.assertEqual(history["title"], "История России")
        self.assertEqual(history["semester"], 1)
        self.assertEqual(history["total_ze"], 3)
        self.assertEqual(history["lectures"], 16)
        self.assertEqual(history["seminars"], 32)
        self.assertEqual(history["exam_type"], "экзамен")
        self.assertEqual(history["item_type"], "discipline")
        self.assertEqual(history["module_title"], "Модуль искусственного интеллекта и программной инженерии")
        self.assertEqual(len(history["competencies"]), 1)
        self.assertEqual(history["competencies"][0]["code"], "УК-5")

        practice = next(d for d in disciplines if d["code"] == "Б2.О.01(У)")
        self.assertEqual(practice["item_type"], "practice")
        self.assertTrue(practice["is_practice"])
        self.assertEqual(practice["total_ze"], 6)

        gia = next(d for d in disciplines if d["code"] == "Б3.01(Д)")
        self.assertEqual(gia["item_type"], "gia")
        self.assertTrue(gia["is_gia"])
        self.assertEqual(gia["semester"], 8)

    def test_parse_standard_xml_with_empty_and_corrupt_attributes(self):
        # XML с пустыми значениями и нестандартными атрибутами
        xml_data = """<?xml version="1.0" encoding="utf-8"?>
<Документ>
    <Титул Код="01.03.02" Имя="Прикладная математика" ГодНачалаПодготовки="" />
    <СтрокиПлана>
        <Строка НовИдДисциплины="Б1.О.01" Дисциплина="Математический анализ">
            <Сем Ном="" Лек="" Пр="" СРС="" ЗЕТ="" />
        </Строка>
    </СтрокиПлана>
</Документ>
"""
        parsed = PLXParser.parse_plx_content(xml_data, "corrupt_attribs.xml")
        self.assertEqual(parsed["direction_code"], "01.03.02")
        self.assertEqual(parsed["start_year"], 2025)  # default
        self.assertEqual(len(parsed["disciplines"]), 1)
        disc = parsed["disciplines"][0]
        self.assertEqual(disc["title"], "Математический анализ")
        self.assertEqual(disc["total_ze"], 3)
        self.assertEqual(disc["lectures"], 0)

    def test_parse_zip_archive(self):
        demo_xml = PLXParser.generate_demo_plx_xml().encode("utf-8")
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("plan_inside.plx", demo_xml)
        raw_zip = bio.getvalue()

        parsed = PLXParser.parse_plx_content(raw_zip, "archive_plan.plx")
        self.assertEqual(parsed["direction_code"], "09.03.03")
        self.assertGreater(len(parsed["disciplines"]), 0)

    def test_invalid_and_empty_xml(self):
        with self.assertRaises(PLXParsingError):
            PLXParser.parse_plx_content("", "empty.xml")

        with self.assertRaises(PLXParsingError):
            PLXParser.parse_plx_content(b"", "empty_bytes.xml")

        with self.assertRaises(PLXParsingError):
            PLXParser.parse_plx_content("<<<INVALID XML CONTENT>>>", "invalid.xml")

    def test_decode_boms(self):
        utf8_bom = b"\xef\xbb\xbf" + "<Doc><Титул Код='1'/></Doc>".encode("utf-8")
        decoded = PLXParser.decode_raw_bytes(utf8_bom)
        self.assertTrue("<Doc>" in decoded)

        utf16le_bom = b"\xff\xfe" + "<Doc><Титул Код='1'/></Doc>".encode("utf-16le")
        decoded_16 = PLXParser.decode_raw_bytes(utf16le_bom)
        self.assertTrue("<Doc>" in decoded_16)

    def test_calculate_absolute_semester(self):
        # 1 курс
        self.assertEqual(calculate_absolute_semester(1, 1), 1)
        self.assertEqual(calculate_absolute_semester(2, 1), 2)

        # 2 курс -> семестры 3 и 4
        self.assertEqual(calculate_absolute_semester(1, 2), 3)
        self.assertEqual(calculate_absolute_semester(2, 2), 4)

        # 3 курс -> семестры 5 и 6
        self.assertEqual(calculate_absolute_semester(1, 3), 5)
        self.assertEqual(calculate_absolute_semester(2, 3), 6)

        # 4 курс -> семестры 7 и 8
        self.assertEqual(calculate_absolute_semester(1, 4), 7)
        self.assertEqual(calculate_absolute_semester(2, 4), 8)

        # 5 курс -> семестры 9 и 10
        self.assertEqual(calculate_absolute_semester(1, 5), 9)
        self.assertEqual(calculate_absolute_semester(2, 5), 10)

        # Уже абсолютные семестры
        self.assertEqual(calculate_absolute_semester(5, 3), 5)
        self.assertEqual(calculate_absolute_semester(8, 4), 8)

        # Только курс без семестра
        self.assertEqual(calculate_absolute_semester(0, 2), 3)
        self.assertEqual(calculate_absolute_semester(0, 4), 7)

    def test_mmis_diffgram_higher_semesters(self):
        """Проверка разбора семестров 1..8 в полноценном Шахтинском плане (MMIS DiffGram)."""
        mmis_xml = """<?xml version="1.0" encoding="utf-8"?>
<dsMMISDB xmlns="http://tempuri.org/dsMMISDB.xsd">
    <Планы Код="1" КодООП="10" Титул="09.03.03 Прикладная информатика&#xA;Искусственный интеллект" ГодНачалаПодготовки="2025" КодФормыОбучения="1" КодУровняОбразования="1" />
    <ООП Код="10" Шифр="09.03.03" Название="Прикладная информатика" />
    <Кафедры Код="5" Название="Кафедра информационных систем" />

    <!-- Дисциплина 1 курса (семестр 1) -->
    <ПланыСтроки Код="101" Дисциплина="Линейная алгебра" ДисциплинаКод="Б1.О.01" КодКафедры="5" ТипОбъекта="2" />
    <!-- Дисциплина 2 курса (семестр 3) -->
    <ПланыСтроки Код="102" Дисциплина="Теория вероятностей" ДисциплинаКод="Б1.О.08" КодКафедры="5" ТипОбъекта="2" />
    <!-- Дисциплина 2 курса (семестр 4) -->
    <ПланыСтроки Код="103" Дисциплина="Базы данных" ДисциплинаКод="Б1.О.10" КодКафедры="5" ТипОбъекта="2" />
    <!-- Дисциплина 3 курса (семестр 5 и 6) -->
    <ПланыСтроки Код="104" Дисциплина="Машинное обучение" ДисциплинаКод="Б1.В.02" КодКафедры="5" ТипОбъекта="2" />
    <!-- Дисциплина 4 курса (семестр 8) -->
    <ПланыСтроки Код="105" Дисциплина="Дипломное проектирование" ДисциплинаКод="Б3.01" КодКафедры="5" ТипОбъекта="2" />

    <!-- Часы в таблице ПланыНовыеЧасы: Семестр - на курсе (1 или 2), Курс - 1..4 -->
    <ПланыНовыеЧасы КодОбъекта="101" Курс="1" Семестр="1" КодТипаЧасов="1" КодВидаРаботы="101" Количество="36" />
    <ПланыНовыеЧасы КодОбъекта="101" Курс="1" Семестр="1" КодТипаЧасов="1" КодВидаРаботы="50" Количество="3" />
    <ПланыНовыеЧасы КодОбъекта="101" Курс="1" Семестр="1" КодВидаРаботы="1" />

    <ПланыНовыеЧасы КодОбъекта="102" Курс="2" Семестр="1" КодТипаЧасов="1" КодВидаРаботы="101" Количество="36" />
    <ПланыНовыеЧасы КодОбъекта="102" Курс="2" Семестр="1" КодТипаЧасов="1" КодВидаРаботы="50" Количество="4" />
    <ПланыНовыеЧасы КодОбъекта="102" Курс="2" Семестр="1" КодВидаРаботы="1" />

    <ПланыНовыеЧасы КодОбъекта="103" Курс="2" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="101" Количество="36" />
    <ПланыНовыеЧасы КодОбъекта="103" Курс="2" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="50" Количество="4" />
    <ПланыНовыеЧасы КодОбъекта="103" Курс="2" Семестр="2" КодВидаРаботы="1" />

    <ПланыНовыеЧасы КодОбъекта="104" Курс="3" Семестр="1" КодТипаЧасов="1" КодВидаРаботы="101" Количество="36" />
    <ПланыНовыеЧасы КодОбъекта="104" Курс="3" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="101" Количество="36" />
    <ПланыНовыеЧасы КодОбъекта="104" Курс="3" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="50" Количество="5" />
    <ПланыНовыеЧасы КодОбъекта="104" Курс="3" Семестр="2" КодВидаРаботы="1" />

    <ПланыНовыеЧасы КодОбъекта="105" Курс="4" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="101" Количество="18" />
    <ПланыНовыеЧасы КодОбъекта="105" Курс="4" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="50" Количество="6" />
    <ПланыНовыеЧасы КодОбъекта="105" Курс="4" Семестр="2" КодВидаРаботы="1" />
</dsMMISDB>
"""
        parsed = PLXParser.parse_plx_content(mmis_xml, "mmis_semesters_test.plx")
        discs = {d["code"]: d for d in parsed["disciplines"]}

        self.assertEqual(len(discs), 5)
        self.assertEqual(discs["Б1.О.01"]["semester"], 1)
        self.assertEqual(discs["Б1.О.08"]["semester"], 3)
        self.assertEqual(discs["Б1.О.10"]["semester"], 4)
        self.assertEqual(discs["Б1.В.02"]["semester"], 5)
        self.assertEqual(discs["Б1.В.02"]["semesters"], [5, 6])
        self.assertEqual(discs["Б3.01"]["semester"], 8)

    def test_mmis_control_form_attributes(self):
        """Проверка извлечения семестра из атрибутов Экзамен, Зачет, Курс в ПланыСтроки."""
        mmis_xml = """<?xml version="1.0" encoding="utf-8"?>
<dsMMISDB xmlns="http://tempuri.org/dsMMISDB.xsd">
    <Планы Код="1" КодООП="10" />
    <ООП Код="10" Шифр="40.03.01" Название="Юриспруденция" />
    <ПланыСтроки Код="201" Дисциплина="Уголовное право" ДисциплинаКод="Б1.О.15" Курс="2" Экзамен="4" />
    <ПланыСтроки Код="202" Дисциплина="Гражданский процесс" ДисциплинаКод="Б1.О.18" Курс="3" Зачет="5" />
</dsMMISDB>
"""
        parsed = PLXParser.parse_plx_content(mmis_xml, "control_attribs.plx")
        discs = {d["code"]: d for d in parsed["disciplines"]}

        self.assertEqual(discs["Б1.О.15"]["semester"], 4)
        self.assertEqual(discs["Б1.О.15"]["exam_type"], "экзамен")
        self.assertEqual(discs["Б1.О.18"]["semester"], 5)
        self.assertEqual(discs["Б1.О.18"]["exam_type"], "зачет")

    def test_standard_xml_multi_semester(self):
        """Проверка стандартного XML с несколькими семестрами и семестрами старше 2."""
        xml_data = """<?xml version="1.0" encoding="utf-8"?>
<Документ>
    <Титул Код="09.03.03" Имя="Прикладная информатика" />
    <СтрокиПлана>
        <Строка НовИдДисциплины="Б1.О.05" Дисциплина="Информационные системы" Курс="2">
            <Сем Ном="3" Лек="18" Пр="36" СРС="54" ЗЕТ="3" Зач="1" />
            <Сем Ном="4" Лек="18" Пр="36" СРС="54" ЗЕТ="3" Экз="1" />
        </Строка>
        <Строка НовИдДисциплины="Б1.О.20" Дисциплина="Проектная деятельность" Курс="3" Семестр="6" Экзамен="6" />
    </СтрокиПлана>
</Документ>
"""
        parsed = PLXParser.parse_plx_content(xml_data, "multi_sem.xml")
        discs = {d["code"]: d for d in parsed["disciplines"]}

        d1 = discs["Б1.О.05"]
        self.assertEqual(d1["semester"], 3)
        self.assertEqual(d1["semesters"], [3, 4])
        self.assertEqual(d1["lectures"], 36)
        self.assertEqual(d1["seminars"], 72)
        self.assertEqual(d1["total_ze"], 6)
        self.assertIn("экзамен", d1["exam_type"])
        self.assertIn("зачет", d1["exam_type"])

        d2 = discs["Б1.О.20"]
        self.assertEqual(d2["semester"], 6)
        self.assertEqual(d2["exam_type"], "экзамен")

    def test_mmis_credits_and_hours_not_tripled(self):
        """Проверка, что в MMIS DiffGram часы и ЗЕТ не утраиваются из-за суффиксов тегов."""
        mmis_xml = """<?xml version="1.0" encoding="utf-8"?>
<dsMMISDB xmlns="http://tempuri.org/dsMMISDB.xsd">
    <Планы Код="1" КодООП="10" />
    <ООП Код="10" Шифр="40.03.01" Название="Юриспруденция" />
    <Кафедры Код="10" Название="Кафедра теории права" />

    <ПланыСтроки Код="501" Дисциплина="Философия" ДисциплинаКод="Б1.О.02" КодКафедры="10" ТипОбъекта="2" />
    <ПланыНовыеЧасы КодОбъекта="501" Курс="1" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="101" Количество="10" />
    <ПланыНовыеЧасы КодОбъекта="501" Курс="1" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="103" Количество="22" />
    <ПланыНовыеЧасы КодОбъекта="501" Курс="1" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="107" Количество="36" />
    <ПланыНовыеЧасы КодОбъекта="501" Курс="1" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="108" Количество="4" />
    <ПланыНовыеЧасы КодОбъекта="501" Курс="1" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="1000" Количество="72" />
    <ПланыНовыеЧасы КодОбъекта="501" Курс="1" Семестр="2" КодТипаЧасов="1" КодВидаРаботы="50" Количество="2" />
</dsMMISDB>
"""
        parsed = PLXParser.parse_plx_content(mmis_xml, "not_tripled.plx")
        discs = {d["code"]: d for d in parsed["disciplines"]}
        philo = discs["Б1.О.02"]

        self.assertEqual(philo["total_ze"], 2)
        self.assertEqual(philo["total_hours"], 72)
        self.assertEqual(philo["lectures"], 10)
        self.assertEqual(philo["seminars"], 22)
        self.assertEqual(philo["self_hours"], 36)
        self.assertEqual(philo["control_hours"], 4)

    def test_mmis_credits_from_attributes_and_hours_calculation(self):
        """Проверка чтения ЗЕТ из ЗЕТэкспертное, ЗЕТплан и расчета из часов по нормативу 36 ч = 1 ЗЕТ."""
        mmis_xml = """<?xml version="1.0" encoding="utf-8"?>
<dsMMISDB xmlns="http://tempuri.org/dsMMISDB.xsd">
    <Планы Код="1" КодООП="10" />
    <ООП Код="10" Шифр="40.03.01" Название="Юриспруденция" />
    <Кафедры Код="10" Название="Кафедра теории права" />

    <!-- Дисциплина с ЗЕТэкспертное -->
    <ПланыСтроки Код="601" Дисциплина="Римское право" ДисциплинаКод="Б1.В.01" ЗЕТэкспертное="4" ЧасовПоПлану="144" />
    <!-- Дисциплина с ЗЕТплан и дробным представлением через запятую -->
    <ПланыСтроки Код="602" Дисциплина="Логика" ДисциплинаКод="Б1.В.02" ЗЕТплан="1,5" ЧасовПоЗЕТ="54" />
    <!-- Дисциплина без ЗЕТ, но с часами 144 -> 4 ЗЕТ -->
    <ПланыСтроки Код="603" Дисциплина="Криминалистика" ДисциплинаКод="Б1.О.25" ЧасовПоПлану="144" />
    <!-- Дисциплина без ЗЕТ, но с часами 216 -> 6 ЗЕТ -->
    <ПланыСтроки Код="604" Дисциплина="Гражданское право" ДисциплинаКод="Б1.О.10" ВсегоЧасов="216" />
    <!-- Дисциплина с итогом курса Семестр=0 и семестровой строкой Семестр=1 (не должна удваиваться) -->
    <ПланыСтроки Код="605" Дисциплина="Социология" ДисциплинаКод="Б1.О.30" />
    <ПланыНовыеЧасы КодОбъекта="605" Курс="1" Семестр="0" КодТипаЧасов="1" КодВидаРаботы="50" Количество="2" />
    <ПланыНовыеЧасы КодОбъекта="605" Курс="1" Семестр="1" КодТипаЧасов="1" КодВидаРаботы="50" Количество="2" />
</dsMMISDB>
"""
        parsed = PLXParser.parse_plx_content(mmis_xml, "attrs_test.plx")
        discs = {d["code"]: d for d in parsed["disciplines"]}

        self.assertEqual(discs["Б1.В.01"]["total_ze"], 4)
        self.assertEqual(discs["Б1.В.01"]["total_hours"], 144)

        self.assertEqual(discs["Б1.В.02"]["total_ze"], 1.5)
        self.assertEqual(discs["Б1.В.02"]["total_hours"], 54)

        self.assertEqual(discs["Б1.О.25"]["total_ze"], 4)
        self.assertEqual(discs["Б1.О.25"]["total_hours"], 144)

        self.assertEqual(discs["Б1.О.10"]["total_ze"], 6)
        self.assertEqual(discs["Б1.О.10"]["total_hours"], 216)

        # Не должно удвоиться до 4
        self.assertEqual(discs["Б1.О.30"]["total_ze"], 2)

    def test_competency_code_normalization(self):
        """Проверка нормализации шифров компетенций с пробелами и длинными тире."""
        self.assertEqual(normalize_competency_code("ПК – 1"), "ПК-1")
        self.assertEqual(normalize_competency_code("ПК — 2"), "ПК-2")
        self.assertEqual(normalize_competency_code("УК - 1.1"), "УК-1.1")
        self.assertEqual(normalize_competency_code(" ОПК − 3 "), "ОПК-3")
        self.assertEqual(normalize_competency_code(None), "")

    def test_mmis_competencies_indicators_and_empty_names(self):
        """Проверка парсинга компетенций и индикаторов в Шахтинском плане с пустым наименованием."""
        mmis_xml = """<?xml version="1.0" encoding="utf-8"?>
<dsMMISDB xmlns="http://tempuri.org/dsMMISDB.xsd">
    <Планы Код="1" КодООП="10" />
    <ООП Код="10" Шифр="40.03.01" Название="Юриспруденция" />

    <!-- Компетенции и индикаторы -->
    <Компетенции Код="1001" ШифрКомпетенции="УК – 1" Наименование="Способен осуществлять поиск, критический анализ" />
    <Компетенции Код="1002" КодРодителя="1001" ШифрКомпетенции="УК – 1.1" Наименование="" />

    <Компетенции Код="2001" ШифрКомпетенции="ОПК - 2" Наименование="Способен применять нормы материального права" />
    <Компетенции Код="2002" ШифрКомпетенции="ОПК - 2.1" Наименование="Анализирует нормативные правовые акты" />

    <ПланыСтроки Код="10" Дисциплина="Теория государства и права" ДисциплинаКод="Б1.О.03" />
    <ПланыКомпетенцииДисциплины КодСтроки="10" КодКомпетенции="1002" />
    <ПланыКомпетенцииДисциплины КодСтроки="10" КодКомпетенции="2002" />

    <ПланыСтроки Код="20" Дисциплина="Римское право" ДисциплинаКод="Б1.В.01" Компетенции="УК – 1; ОПК - 2" />
</dsMMISDB>
"""
        parsed = PLXParser.parse_plx_content(mmis_xml, "comp_test.plx")
        discs = {d["code"]: d for d in parsed["disciplines"]}

        tgp = discs["Б1.О.03"]
        self.assertEqual(len(tgp["competencies"]), 2)

        c1 = tgp["competencies"][0]
        self.assertEqual(c1["code"], "УК-1")
        self.assertEqual(c1["indicator_code"], "УК-1.1")
        self.assertEqual(c1["name"], "Способен осуществлять поиск, критический анализ")
        self.assertTrue(len(c1["indicator_name"]) > 0)
        self.assertIn("УК-1.1", c1["indicator_name"])

        c2 = tgp["competencies"][1]
        self.assertEqual(c2["code"], "ОПК-2")
        self.assertEqual(c2["indicator_code"], "ОПК-2.1")
        self.assertEqual(c2["name"], "Способен применять нормы материального права")
        self.assertEqual(c2["indicator_name"], "Анализирует нормативные правовые акты")

        rim = discs["Б1.В.01"]
        self.assertEqual(len(rim["competencies"]), 2)
        self.assertEqual(rim["competencies"][0]["code"], "УК-1")
        self.assertEqual(rim["competencies"][1]["code"], "ОПК-2")

    def test_parse_iup_plan(self):
        """Проверка разбора индивидуального учебного плана (ИУП) и таблицы ПереаттестацияДетали."""
        # 1. Поиск реального файла в tmp/ИУП/ если доступен
        iup_files = glob.glob("tmp/ИУП/*.plx") + glob.glob("/Users/ezgard/DisciplinProgramm_Generator/tmp/ИУП/*.plx")
        if iup_files and os.path.exists(iup_files[0]):
            with open(iup_files[0], "rb") as f:
                data = f.read()
            filename = os.path.basename(iup_files[0])
        else:
            # Автономный синтетический ИУП XML для независимого прогона
            data = """<?xml version="1.0" encoding="utf-8"?>
<dsMMISDB xmlns="http://tempuri.org/dsMMISDB.xsd">
    <Планы Код="1" КодООП="10" Титул="ИУП Студента" />
    <ООП Код="10" Шифр="40.03.01" Название="Юриспруденция" />
    <Студенты Код="1" Фамилия="Боярчук" Имя="В." Отчество="А." НомерГруппы="ЮР-101" />
    <ПланыСтроки Код="101" Дисциплина="История государства и права" ДисциплинаКод="Б1.О.01" />
    <ПланыСтроки Код="102" Дисциплина="Философия" ДисциплинаКод="Б1.О.02" />
    <ПереаттестацияДетали Код="1" КодСтроки="101" КодВидаРаботы="50" КоличествоПерезачтено="3" Оценка="отлично" />
</dsMMISDB>
""".encode("utf-8")
            filename = "В.А.Боярчук.plx"

        parsed = PLXParser.parse_plx_content(data, filename)

        self.assertTrue(parsed.get("is_iup"))
        iup_prof = parsed.get("iup_profile", {})
        self.assertTrue(iup_prof.get("is_iup"))
        self.assertIn("Боярчук", iup_prof.get("student_fio", ""))

        reatts = iup_prof.get("reattestations", [])
        self.assertGreater(len(reatts), 0)

        closed_discs = parsed.get("iup_closed_disciplines", [])
        self.assertGreater(len(closed_discs), 0)
        closed_titles = {d["title"] for d in closed_discs}
        self.assertTrue(any("История" in t or "Философия" in t for t in closed_titles))


if __name__ == "__main__":
    unittest.main()
