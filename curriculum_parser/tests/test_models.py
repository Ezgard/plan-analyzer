"""
Тесты типизированных моделей и обратной совместимости (dict-like интерфейс)
для curriculum_parser.
"""
import json
import unittest

try:
    from modules.curriculum_parser import (
        CurriculumPlanData,
        DisciplineItem,
        CompetencyItem,
        IUPProfile,
        CurriculumModule,
        ReattestationItem,
        parse_curriculum_plan,
        PLXParser,
    )
except ImportError:
    from curriculum_parser import (  # type: ignore
        CurriculumPlanData,
        DisciplineItem,
        CompetencyItem,
        IUPProfile,
        CurriculumModule,
        ReattestationItem,
        parse_curriculum_plan,
        PLXParser,
    )


class TestModelsAndDictCompatibility(unittest.TestCase):

    def test_competency_item_fields_and_dict_access(self):
        c = CompetencyItem(
            code="УК-5",
            name="Межкультурное взаимодействие",
            indicator_code="УК-5.1",
            indicator_name="Понимает разнообразие культур"
        )
        # 1. Атрибутный доступ
        self.assertEqual(c.code, "УК-5")
        self.assertEqual(c.indicator_code, "УК-5.1")

        # 2. Словарный доступ
        self.assertEqual(c["code"], "УК-5")
        self.assertEqual(c["indicator_code"], "УК-5.1")
        self.assertEqual(c.get("name"), "Межкультурное взаимодействие")
        self.assertEqual(c.get("missing", "default"), "default")
        self.assertIn("code", c)
        self.assertNotIn("non_existent", c)

        # 3. Методы словаря и сериализация
        self.assertIn("code", list(c.keys()))
        d = c.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["code"], "УК-5")

        with self.assertRaises(KeyError):
            _ = c["unknown_field"]

    def test_discipline_item_fields_and_dict_access(self):
        comp = CompetencyItem(
            code="ОПК-1",
            name="Естественнонаучные знания",
            indicator_code="ОПК-1.1",
            indicator_name="Применяет физико-математический аппарат"
        )
        d = DisciplineItem(
            code="Б1.О.01",
            title="История России",
            block="Блок 1",
            dept_name="Кафедра истории",
            dept_code="12",
            semester=1,
            semesters=[1],
            total_ze=3,
            total_hours=108,
            lectures=16,
            seminars=32,
            contact_hours=48,
            self_hours=60,
            control_hours=0,
            exam_type="экзамен",
            competencies=[comp],
            item_type="discipline"
        )

        # Атрибуты
        self.assertEqual(d.code, "Б1.О.01")
        self.assertEqual(d.title, "История России")
        self.assertEqual(d.total_ze, 3)
        self.assertEqual(len(d.competencies), 1)

        # Словарный доступ
        self.assertEqual(d["code"], "Б1.О.01")
        self.assertEqual(d["title"], "История России")
        self.assertEqual(d.get("semester"), 1)
        self.assertEqual(d.get("absent_key", 42), 42)
        self.assertIn("total_ze", d)

        # Сериализация to_dict
        as_dict = d.to_dict()
        self.assertIsInstance(as_dict, dict)
        self.assertEqual(as_dict["competencies"][0]["code"], "ОПК-1")

    def test_curriculum_plan_data_features(self):
        demo_xml = PLXParser.generate_demo_plx_xml()
        plan = parse_curriculum_plan(demo_xml, "demo.plx")

        # 1. Проверка типа модели
        self.assertIsInstance(plan, CurriculumPlanData)

        # 2. Атрибутный доступ
        self.assertEqual(plan.filename, "demo.plx")
        self.assertEqual(plan.direction_code, "09.03.03")
        self.assertEqual(plan.direction_title, "Прикладная информатика")
        self.assertEqual(plan.profile_title, "Искусственный интеллект и анализ данных")
        self.assertEqual(plan.start_year, 2025)
        self.assertEqual(len(plan.disciplines), 6)
        self.assertEqual(len(plan.pure_disciplines), 4)
        self.assertEqual(len(plan.practices), 1)
        self.assertEqual(len(plan.gia), 1)

        # 3. Словарный доступ к плану
        self.assertEqual(plan["direction_code"], "09.03.03")
        self.assertEqual(plan.get("start_year"), 2025)
        self.assertEqual(plan.get("unknown_key", "fallback"), "fallback")
        self.assertIn("disciplines", plan)
        self.assertIn("modules", plan)
        self.assertTrue(len(list(plan.keys())) > 5)

        # 4. Методы поиска и фильтрации
        disc = plan.find_discipline("История России")
        self.assertIsNotNone(disc)
        self.assertEqual(disc.code, "Б1.О.01")

        by_code = plan.find_discipline("Б1.О.05")
        self.assertIsNotNone(by_code)
        self.assertEqual(by_code.title, "Высшая математика и линейная алгебра")

        sem1 = plan.filter_by_semester(1)
        self.assertEqual(len(sem1), 2)  # История и Высшая математика

        base_b1 = plan.filter_by_block("Б1.О")
        self.assertEqual(len(base_b1), 3)

        # 5. Сериализация в чистый dict и JSON
        plan_dict = plan.to_dict()
        self.assertIsInstance(plan_dict, dict)
        self.assertEqual(plan_dict["direction_code"], "09.03.03")
        self.assertIsInstance(plan_dict["disciplines"], list)
        self.assertIsInstance(plan_dict["disciplines"][0], dict)

        plan_json = plan.to_json()
        self.assertIsInstance(plan_json, str)
        parsed_json = json.loads(plan_json)
        self.assertEqual(parsed_json["direction_code"], "09.03.03")

    def test_parse_curriculum_plan_as_dict(self):
        demo_xml = PLXParser.generate_demo_plx_xml()
        raw_dict = parse_curriculum_plan(demo_xml, "demo.plx", as_dict=True)

        self.assertIsInstance(raw_dict, dict)
        self.assertEqual(raw_dict["direction_code"], "09.03.03")
        self.assertIsInstance(raw_dict["disciplines"], list)

    def test_iup_profile_and_reattestation_models(self):
        r = ReattestationItem(
            id="1",
            row_id="101",
            work_type_code=50,
            original_course=1,
            original_semester=1,
            amount_was=3.0,
            amount_studied=3.0,
            attestation_type="экзамен",
            attestation_type_code=1,
            grade="отлично"
        )
        self.assertEqual(r.work_type_code, 50)
        self.assertEqual(r["work_type_code"], 50)
        self.assertEqual(r.get("grade"), "отлично")

        prof = IUPProfile(
            is_iup=True,
            student_fio="Иванов И.И.",
            group_name="ИТ-21",
            base_plan_filename="base.plx",
            start_course=2,
            start_semester=3,
            total_reattestations=1,
            reattestations=[r]
        )
        self.assertTrue(prof.is_iup)
        self.assertEqual(prof["student_fio"], "Иванов И.И.")
        d_prof = prof.to_dict()
        self.assertIsInstance(d_prof, dict)
        self.assertEqual(d_prof["student_fio"], "Иванов И.И.")


if __name__ == "__main__":
    unittest.main()
