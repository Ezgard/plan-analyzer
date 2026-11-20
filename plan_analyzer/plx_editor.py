"""
Модуль безопасного чтения, модификации и сохранения файлов учебных планов (PLX / XML).
Поддерживает форматы Шахты (MMIS dsMMISDB DiffGram в zip или plain XML, а также упрощенный XML).
"""
import io
import os
import shutil
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple, Any

from plan_analyzer.models import PlannedFileChange


def get_local_tag(elem: ET.Element) -> str:
    """Извлекает локальный тег без XML-namespace."""
    t = elem.tag
    if "}" in t:
        return t.split("}", 1)[1]
    if ":" in t:
        return t.split(":", 1)[1]
    return t


class PLXFileContainer:
    """Контейнер для работы с файлом плана (zip или чистый xml)."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.is_zip = False
        self.inner_xml_name = "plan.xml"
        self.encoding = "utf-8"
        self.xml_tree: Optional[ET.ElementTree] = None
        self.root: Optional[ET.Element] = None
        self.has_xml_declaration = True
        self._load()

    def _load(self):
        with open(self.file_path, "rb") as f:
            raw_data = f.read()

        if raw_data.startswith(b"PK\x03\x04"):
            self.is_zip = True
            with zipfile.ZipFile(io.BytesIO(raw_data)) as z:
                xml_names = [n for n in z.namelist() if n.lower().endswith((".xml", ".plx"))]
                if xml_names:
                    self.inner_xml_name = xml_names[0]
                elif z.namelist():
                    self.inner_xml_name = z.namelist()[0]
                xml_bytes = z.read(self.inner_xml_name)
        else:
            self.is_zip = False
            xml_bytes = raw_data

        # Определение кодировки
        xml_text, encoding = self._decode_bytes(xml_bytes)
        self.encoding = encoding
        self.root = ET.fromstring(xml_text)
        self.xml_tree = ET.ElementTree(self.root)

    @staticmethod
    def _decode_bytes(b: bytes) -> Tuple[str, str]:
        if b.startswith(b"\xff\xfe"):
            return b.decode("utf-16le", errors="replace"), "utf-16"
        if b.startswith(b"\xfe\xff"):
            return b.decode("utf-16be", errors="replace"), "utf-16"
        if b.startswith(b"\xef\xbb\xbf"):
            return b[3:].decode("utf-8", errors="replace"), "utf-8"

        # Поиск декларации кодировки в начале
        head = b[:200]
        if b"encoding=\"utf-16\"" in head.lower() or b"encoding='utf-16'" in head.lower():
            try:
                return b.decode("utf-16le"), "utf-16"
            except Exception:
                pass
        if b"windows-1251" in head.lower() or b"cp1251" in head.lower():
            try:
                return b.decode("cp1251"), "cp1251"
            except Exception:
                pass

        try:
            return b.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            try:
                return b.decode("cp1251"), "cp1251"
            except UnicodeDecodeError:
                return b.decode("latin-1", errors="replace"), "utf-8"

    def modify_discipline(
        self,
        discipline_title: str,
        new_dept_code: Optional[str] = None,
        new_dept_name: Optional[str] = None,
        new_discipline_title: Optional[str] = None,
        target_row_code: Optional[str] = None,
    ) -> List[PlannedFileChange]:
        """
        Модифицирует дисциплину в XML.
        Возвращает список примененных изменений.
        """
        if self.root is None:
            return []

        changes: List[PlannedFileChange] = []
        norm_title = " ".join(discipline_title.strip().lower().split())

        # Ищем все элементы строк дисциплин
        for elem in self.root.iter():
            tag = get_local_tag(elem)
            if tag not in ("ПланыСтроки", "Строка"):
                continue

            row_code = elem.get("Код") or ""
            if target_row_code and row_code != target_row_code:
                continue

            current_disc = elem.get("Дисциплина") or ""
            current_norm = " ".join(current_disc.strip().lower().split())

            # Если row_code не задан, сверяем по названию дисциплины
            if not target_row_code and current_norm != norm_title:
                continue

            # Определяем текущие параметры
            orig_dept_code = elem.get("КодКафедры") or elem.get("Кафедра") or ""
            orig_dept_name = elem.get("КафедраНазвание") or ""

            change_types = []
            applied_new_title = None
            applied_dept_code = None
            applied_dept_name = None

            # 1. Изменение кафедры
            if new_dept_code is not None and str(new_dept_code) != orig_dept_code:
                if tag == "ПланыСтроки":
                    elem.set("КодКафедры", str(new_dept_code))
                elif tag == "Строка":
                    elem.set("Кафедра", str(new_dept_code))
                    if new_dept_name:
                        elem.set("КафедраНазвание", str(new_dept_name))
                applied_dept_code = str(new_dept_code)
                applied_dept_name = new_dept_name or ""
                change_types.append("Кафедра")

                # Также обновляем или синхронизируем справочник кафедр в плане MMIS
                if new_dept_name:
                    self._ensure_department_in_catalog(str(new_dept_code), str(new_dept_name))

            # 2. Переименование / унификация названия дисциплины
            if new_discipline_title and new_discipline_title.strip() != current_disc.strip():
                elem.set("Дисциплина", new_discipline_title.strip())
                applied_new_title = new_discipline_title.strip()
                change_types.append("Название")

            if change_types:
                changes.append(
                    PlannedFileChange(
                        file_path=self.file_path,
                        file_name=os.path.basename(self.file_path),
                        row_code=row_code,
                        original_title=current_disc,
                        new_title=applied_new_title,
                        original_dept_code=orig_dept_code,
                        original_dept_name=orig_dept_name,
                        new_dept_code=applied_dept_code,
                        new_dept_name=applied_dept_name,
                        change_type=" и ".join(change_types),
                    )
                )

        return changes

    def _ensure_department_in_catalog(self, dept_code: str, dept_name: str):
        """Обеспечивает наличие записи о кафедре в справочнике MMIS."""
        if self.root is None:
            return

        dept_elements = []
        for elem in self.root.iter():
            tag = get_local_tag(elem)
            if tag in ("Кафедры", "ПланыКафедры"):
                dept_elements.append(elem)
                if elem.get("Код") == dept_code:
                    elem.set("Название", dept_name)
                    return

        # Если записи с таким кодом нет, но есть родительские элементы справочника
        if dept_elements:
            parent_elem = None
            # Ищем родителя первой найденной кафедры
            for parent in self.root.iter():
                for child in list(parent):
                    if child in dept_elements:
                        parent_elem = parent
                        break
                if parent_elem is not None:
                    break

            if parent_elem is not None:
                tag_name = dept_elements[0].tag
                new_elem = ET.SubElement(parent_elem, tag_name)
                new_elem.set("Код", dept_code)
                new_elem.set("Название", dept_name)

    def save(
        self,
        backup: bool = True,
        output_dir: Optional[str] = None,
    ) -> str:
        """
        Сохраняет модифицированный документ.
        Возвращает итоговый путь к сохраненному файлу.
        """
        if self.xml_tree is None or self.root is None:
            raise ValueError("Документ не загружен")

        # Сериализация XML в байты
        xml_buf = io.BytesIO()
        self.xml_tree.write(
            xml_buf,
            encoding="utf-8",
            xml_declaration=True,
        )
        xml_bytes = xml_buf.getvalue()

        # Определение целевого пути
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            target_path = os.path.join(output_dir, os.path.basename(self.file_path))
        else:
            target_path = self.file_path
            if backup:
                backup_path = self.file_path + ".bak"
                shutil.copy2(self.file_path, backup_path)

        # Сохранение в zip или plain xml
        if self.is_zip:
            out_zip_buf = io.BytesIO()
            with zipfile.ZipFile(out_zip_buf, "w", zipfile.ZIP_DEFLATED) as z_out:
                # Читаем исходный zip, чтобы сохранить другие файлы если они были
                try:
                    with open(self.file_path, "rb") as f_orig:
                        with zipfile.ZipFile(f_orig, "r") as z_in:
                            for item in z_in.infolist():
                                if item.filename != self.inner_xml_name:
                                    z_out.writestr(item, z_in.read(item.filename))
                except Exception:
                    pass
                # Записываем обновленный XML
                z_out.writestr(self.inner_xml_name, xml_bytes)

            with open(target_path, "wb") as f_target:
                f_target.write(out_zip_buf.getvalue())
        else:
            with open(target_path, "wb") as f_target:
                f_target.write(xml_bytes)

        return target_path
