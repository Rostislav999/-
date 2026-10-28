import tempfile
import unittest
import zipfile
from unittest.mock import patch, Mock
from datetime import date
from pathlib import Path

from lxml import etree as E

from protocol_excel import (
    FIELDS, NS, R, S, Record, cell_text, extract, extract_text,
    kg, read_document, validate, write_excel, xml,
)


TEXT = """№70-001-1001-1001-2
ПРОТОКОЛ ВИПРОБУВАНЬ №70-001-1001-1001-2

«26» вересня 2026 року
Номер за Каталогом продуктів харчування: 12022.
Ідентифікаційний номер та назва зразка: №70-001-1001-1001-2 – Філе куряче.
Виробник:
Постачальник:
Договір:
Дата виготовлення: 19.09.2026.
Розмір партії, від якої відібрано зразок: ____ кг.
Вага зразка: 1 пак. од. (0,600 кг).
№70-001-1001-1001-2 – Хек заморожений
Висновок: Представлений зразок відповідає На показники, які не наведені, зразок не досліджувався.
"""


def make_template(path, end=88, date1904=False):
    root = E.Element(f"{{{S}}}worksheet", nsmap={None: S, "r": R, "x14": "urn:test:x14"})
    E.SubElement(root, f"{{{S}}}dimension", ref="A1:Q56")
    data = E.SubElement(root, f"{{{S}}}sheetData")
    header = E.SubElement(data, f"{{{S}}}row", r="1")
    for col, label in [("A", "(Не змінювати) Протокол УБХП")] + FIELDS:
        cell = E.SubElement(header, f"{{{S}}}c", r=f"{col}1", t="inlineStr")
        E.SubElement(E.SubElement(cell, f"{{{S}}}is"), f"{{{S}}}t").text = label
    row = E.SubElement(data, f"{{{S}}}row", r="2")
    for col, text in [("A", "service-id"), ("B", "checksum"), ("C", "service-date"), ("D", "№old")]:
        cell = E.SubElement(row, f"{{{S}}}c", r=f"{col}2", t="inlineStr", s="0")
        E.SubElement(E.SubElement(cell, f"{{{S}}}is"), f"{{{S}}}t").text = text
    E.SubElement(row, f"{{{S}}}c", r="E2", s="1")
    # Styled empty row must be reused, not counted as an existing record.
    row = E.SubElement(data, f"{{{S}}}row", r="3", ht="25")
    E.SubElement(row, f"{{{S}}}c", r="G3", s="0")
    ext = E.SubElement(root, f"{{{S}}}extLst")
    E.SubElement(ext, "{urn:test:x14}dataValidation", sqref="O2:P1048576").text = "hiddenSheet!A2:B2"
    tp = E.SubElement(root, f"{{{S}}}tableParts", count="1")
    E.SubElement(tp, f"{{{S}}}tablePart", {f"{{{R}}}id": "rTable"})
    workbook = f'''<workbook xmlns="{S}" xmlns:r="{R}"><workbookPr date1904="{int(date1904)}"/><sheets><sheet name="Шаблон" sheetId="1" r:id="rSheet"/></sheets></workbook>'''
    parts = {
        "xl/workbook.xml": workbook.encode(),
        "xl/_rels/workbook.xml.rels": b'<Relationships><Relationship Id="rSheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": E.tostring(root),
        "xl/worksheets/_rels/sheet1.xml.rels": b'<Relationships><Relationship Id="rTable" Target="../tables/table1.xml"/></Relationships>',
        "xl/tables/table1.xml": f'<table xmlns="{S}" ref="A1:P{end}"><autoFilter ref="A1:P{end}"/></table>'.encode(),
        "xl/worksheets/sheet2.xml": b'<hidden>unchanged metadata</hidden>',
        "xl/styles.xml": b'<styles>unchanged styles</styles>',
        "customXml/item1.xml": b'<extra>unchanged application metadata</extra>',
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, value in parts.items():
            z.writestr(name, value)


class ExtractionTests(unittest.TestCase):
    def test_sample_mapping_and_conflict(self):
        r = extract_text(TEXT)
        self.assertEqual(r.values["D"], "№70-001-1001-1001-2")
        self.assertEqual(r.values["E"], "26.09.2026")
        self.assertEqual(r.values["F"], "12022")
        self.assertEqual(r.values["G"], "Філе куряче")
        self.assertEqual(r.values["I"], "19.09.2026")
        self.assertEqual(r.values["L"], "0.600")
        self.assertEqual(r.values["O"], "Відповідає")
        self.assertTrue(any("Хек заморожений" in w for w in r.warnings))
        self.assertFalse(any("другой номер" in w for w in r.warnings))
        self.assertEqual(len([w for w in r.warnings if "Разные названия" in w]), 1)
        self.assertEqual(r.values["H"], "19.09.2026")
        for c in ["J", "K", "M", "N", "P"]:
            self.assertEqual(r.values[c], "")

    def test_empty_field_does_not_consume_next_line(self):
        r = extract_text(TEXT.replace("Постачальник:", "Постачальник: ТОВ Приклад ЄДРПОУ 00123456"))
        self.assertEqual(r.values["M"], "00123456")
        self.assertEqual(r.values["N"], "")

    def test_explicit_batch_catalog_compliance_and_negative_result(self):
        r = extract_text(TEXT.replace("відповідає На", "не відповідає ДСТУ. На") +
                         '\nПартія (позначення): LOT-007\nВжити до: 30.09.2026\n'
                         'Відповідність описам Каталогу: Не відповідає\n')
        self.assertEqual(r.values["H"], "19.09.2026")
        self.assertTrue(any("Обозначение партии" in w for w in r.warnings))
        self.assertEqual(r.values["J"], "30.09.2026")
        self.assertEqual(r.values["O"], "Не відповідає")
        self.assertEqual(r.values["P"], "Не відповідає")

    def test_no_mass_inference_for_multiple_units(self):
        r = extract_text(TEXT.replace("1 пак. од.", "2 пак. од."))
        self.assertEqual(r.values["L"], "")
        self.assertEqual(kg("1 234,56 кг"), "1234.56")
        self.assertEqual(kg("600 г"), "0.6")
        self.assertEqual(kg("____ кг"), "")

    def test_missing_number_and_multiple_protocols_rejected(self):
        with self.assertRaises(ValueError):
            extract_text("Это произвольный документ")
        with self.assertRaises(ValueError):
            extract_text(TEXT + "\nПРОТОКОЛ ВИПРОБУВАНЬ №70-001-9999-9999-2")

    def test_validation(self):
        for col, value in [("E", "31.02.2026"), ("K", "nan"), ("L", "-1"), ("M", "ТОВ Приклад"), ("O", "да")]:
            r = extract_text(TEXT)
            r.values[col] = value
            with self.subTest(col=col), self.assertRaises(ValueError):
                validate(r)
        self.assertEqual(validate(extract_text(TEXT))["E"], date(2026, 9, 26))

    def test_docx_reader(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sample.docx"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
                           ''.join('<w:p><w:r><w:t>' + line + '</w:t></w:r></w:p>' for line in TEXT.splitlines()) +
                           '</w:body></w:document>')
            self.assertEqual(extract(p).values["G"], "Філе куряче")

    def test_wrapped_pdf_fields_ocr_number_marker_and_each_unit_weight(self):
        text = TEXT.replace("ПРОТОКОЛ ВИПРОБУВАНЬ №", "ПРОТОКОЛ ВИПРОБУВАНЬ Ме")
        text = text.replace("– Філе куряче.", "– Консерви м'ясні\nстерилізовані. «Свинина тушкована».")
        text = text.replace("Виробник:", "Виробник: ТОВ Приклад. Адреса:\nм. Полтава. Код ЄДРПОУ: 12345678.")
        text = text.replace("1 пак. од. (0,600 кг)", "9 ж/б по 525 г (4,725 кг)")
        r = extract_text(text)
        self.assertEqual(r.values["D"], "№70-001-1001-1001-2")
        self.assertEqual(r.values["G"], "Консерви м'ясні стерилізовані. «Свинина тушкована»")
        self.assertEqual(r.values["N"], "12345678")
        self.assertEqual(r.values["L"], "0.525")
        self.assertEqual(r.values["H"], r.values["I"])

    def test_scan_routes_through_ocr_and_reports_warning(self):
        page = Mock()
        page.extract_text.return_value = ""
        page.images = [Mock()]
        reader = Mock(pages=[page], is_encrypted=False)
        with patch("pypdf.PdfReader", return_value=reader), \
             patch("ocr_pdf.recognize_pages", return_value={0: TEXT}) as ocr:
            record = extract(Path("scan.pdf"))
        self.assertEqual(record.values["D"], "№70-001-1001-1001-2")
        self.assertIn("OCR", record.warnings[0])
        self.assertEqual(ocr.call_args.args[1], [0])

    def test_text_pdf_and_scanned_pdf(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "text.pdf"
            writer = PdfWriter()
            page = writer.add_blank_page(600, 800)
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})})})
            stream = DecodedStreamObject()
            stream.set_data(b'BT /F1 12 Tf 20 750 Td (Example protocol text layer long enough to validate extraction.) Tj ET')
            page[NameObject("/Contents")] = writer._add_object(stream)
            writer.write(p)
            self.assertIn("Example protocol", read_document(p))
            blank = PdfWriter()
            blank.add_blank_page(600, 800)
            blank.write(p)
            with self.assertRaisesRegex(ValueError, "OCR"):
                read_document(p)


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.template = Path(self.temp.name) / "template.xlsx"
        self.output = Path(self.temp.name) / "result.xlsx"
        make_template(self.template)

    def test_append_preserves_existing_rows_service_columns_and_parts(self):
        report = write_excel(self.template, self.output, [extract_text(TEXT, "sample.docx")])
        self.assertEqual(report["added"][0]["row"], 3)
        with zipfile.ZipFile(self.template) as before, zipfile.ZipFile(self.output) as after:
            self.assertEqual(before.namelist(), after.namelist())
            for name in before.namelist():
                if name != "xl/worksheets/sheet1.xml":
                    self.assertEqual(before.read(name), after.read(name), name)
            old = xml(before.read("xl/worksheets/sheet1.xml"))
            new = xml(after.read("xl/worksheets/sheet1.xml"))
            for xpath in ["s:sheetData/s:row[@r='1']", "s:sheetData/s:row[@r='2']", "s:extLst"]:
                self.assertEqual(E.tostring(old.find(xpath, NS)), E.tostring(new.find(xpath, NS)))
            row = new.find("s:sheetData/s:row[@r='3']", NS)
            self.assertIsNone(row.find("s:c[@r='A3']", NS))
            self.assertEqual(cell_text(row.find("s:c[@r='G3']", NS), []), "Філе куряче")
            self.assertEqual(cell_text(row.find("s:c[@r='L3']", NS), []), "0.6")
            self.assertEqual(row.find("s:c[@r='E3']", NS).get("t"), "n")
            self.assertEqual(row.find("s:c[@r='E3']", NS).get("s"), "1")

    def test_repeat_import_skips_duplicate_and_no_new_file(self):
        first = extract_text(TEXT)
        write_excel(self.template, self.output, [first])
        second = self.output.with_name("second.xlsx")
        with self.assertRaisesRegex(ValueError, "Все номера"):
            write_excel(self.output, second, [first])
        self.assertFalse(second.exists())
        other = Record("other.docx", {"D": "№new"})
        result = write_excel(self.output, second, [first, other])
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["added"][0]["row"], 4)

    def test_update_same_number_preserves_service_data_and_unsourced_values(self):
        r = extract_text(TEXT)
        r.values["P"] = "Відповідає"
        write_excel(self.template, self.output, [r])
        r.values["G"] = "Исправленное название"
        r.values["P"] = ""
        second = self.output.with_name("updated.xlsx")
        result = write_excel(self.output, second, [r], on_duplicate="update")
        self.assertEqual(len(result["added"]), 0)
        self.assertEqual(len(result["updated"]), 1)
        self.assertEqual(result["updated"][0]["row"], 3)
        self.assertEqual(result["updated"][0]["retained"], ["P"])
        with zipfile.ZipFile(self.output) as before, zipfile.ZipFile(second) as after:
            old = xml(before.read("xl/worksheets/sheet1.xml"))
            new = xml(after.read("xl/worksheets/sheet1.xml"))
            self.assertEqual(cell_text(new.find(".//s:c[@r='G3']", NS), []), "Исправленное название")
            self.assertEqual(cell_text(new.find(".//s:c[@r='P3']", NS), []), "Відповідає")
            self.assertEqual(E.tostring(old.find("s:sheetData/s:row[@r='2']", NS)),
                             E.tostring(new.find("s:sheetData/s:row[@r='2']", NS)))

    def test_update_matching_row_preserves_abc(self):
        r = Record("new.docx", {"D": "№old", "G": "Product", "H": "21.09.2026", "I": "21.09.2026"})
        result = write_excel(self.template, self.output, [r], on_duplicate="update")
        self.assertEqual(result["updated"][0]["row"], 2)
        with zipfile.ZipFile(self.template) as before, zipfile.ZipFile(self.output) as after:
            old = xml(before.read("xl/worksheets/sheet1.xml"))
            new = xml(after.read("xl/worksheets/sheet1.xml"))
            for col in "ABC":
                xpath = f".//s:c[@r='{col}2']"
                self.assertEqual(E.tostring(old.find(xpath, NS)), E.tostring(new.find(xpath, NS)))

    def test_duplicates_in_input_and_overwriting_rejected(self):
        r = extract_text(TEXT)
        with self.assertRaisesRegex(ValueError, "повторяются"):
            write_excel(self.template, self.output, [r, r])
        with self.assertRaises(ValueError):
            write_excel(self.template, self.template, [r])
        self.output.write_text("existing user file")
        with self.assertRaises(ValueError):
            write_excel(self.template, self.output, [r])
        self.assertEqual(self.output.read_text(), "existing user file")

    def test_table_expansion_and_dimension(self):
        make_template(self.template, end=3)
        records = [Record(f"{i}.docx", {"D": f"№{i}"}) for i in range(90)]
        write_excel(self.template, self.output, records)
        with zipfile.ZipFile(self.output) as z:
            table = xml(z.read("xl/tables/table1.xml"))
            self.assertEqual(table.get("ref"), "A1:P92")
            self.assertEqual(table.find("s:autoFilter", NS).get("ref"), "A1:P92")
            self.assertEqual(xml(z.read("xl/worksheets/sheet1.xml")).find("s:dimension", NS).get("ref"), "A1:Q92")

    def test_text_not_formula_and_codes_keep_leading_zero(self):
        r = Record("example.docx", {"D": "№new", "G": '=HYPERLINK("https://example.com")', "M": "00123456"})
        write_excel(self.template, self.output, [r])
        with zipfile.ZipFile(self.output) as z:
            root = xml(z.read("xl/worksheets/sheet1.xml"))
            self.assertEqual(len(root.findall(".//s:f", NS)), 0)
            self.assertEqual(cell_text(root.find(".//s:c[@r='M3']", NS), []), "00123456")
            self.assertEqual(root.find(".//s:c[@r='G3']", NS).get("t"), "inlineStr")

    def test_1904_epoch(self):
        make_template(self.template, date1904=True)
        write_excel(self.template, self.output, [extract_text(TEXT)])
        with zipfile.ZipFile(self.output) as z:
            root = xml(z.read("xl/worksheets/sheet1.xml"))
            serial = int(cell_text(root.find(".//s:c[@r='E3']", NS), []))
            self.assertEqual(serial, (date(2026, 9, 26) - date(1904, 1, 1)).days)

    def test_wrong_template_rejected(self):
        with zipfile.ZipFile(self.template) as z:
            parts = {name: z.read(name) for name in z.namelist()}
        root = xml(parts["xl/worksheets/sheet1.xml"])
        root.find(".//s:c[@r='D1']/s:is/s:t", NS).text = "wrong column"
        parts["xl/worksheets/sheet1.xml"] = E.tostring(root)
        with zipfile.ZipFile(self.template, "w") as z:
            for name, data in parts.items():
                z.writestr(name, data)
        with self.assertRaisesRegex(ValueError, "Не найден лист"):
            write_excel(self.template, self.output, [extract_text(TEXT)])
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
