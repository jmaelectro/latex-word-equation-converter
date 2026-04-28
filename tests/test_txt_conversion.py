import io
import unittest
import zipfile

import main


class TxtConversionDecodingTests(unittest.TestCase):
    def _document_xml(self, doc) -> str:
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            return zf.read("word/document.xml").decode("utf-8")

    def _doc_omml_count(self, doc) -> int:
        document_xml = self._document_xml(doc)
        return document_xml.count("<m:oMath") + document_xml.count("<m:oMathPara")

    def test_utf8_txt_is_decoded_without_changes(self):
        lines = main._extract_text_lines_from_txt("Título\n$x^2$".encode("utf-8"))
        self.assertEqual(lines, ["Título", "$x^2$"])

    def test_utf8_bom_txt_is_supported(self):
        lines = main._extract_text_lines_from_txt("Encabezado\n$x+1$".encode("utf-8-sig"))
        self.assertEqual(lines, ["Encabezado", "$x+1$"])

    def test_utf16_txt_with_bom_is_supported(self):
        lines = main._extract_text_lines_from_txt("Sistema\n$$x+1$$".encode("utf-16"))
        self.assertEqual(lines, ["Sistema", "$$x+1$$"])

    def test_cp1252_txt_preserves_symbols_and_formula(self):
        payload = "Área – coste €10 y fórmula $x^2 + 1$".encode("cp1252")

        lines = main._extract_text_lines_from_txt(payload)
        doc = main.build_document_from_paragraphs(lines)
        document_xml = self._document_xml(doc)

        self.assertEqual(lines, ["Área – coste €10 y fórmula $x^2 + 1$"])
        self.assertEqual(self._doc_omml_count(doc), 1)
        self.assertIn("Área", document_xml)
        self.assertIn("coste €10", document_xml)
        self.assertNotIn("�", document_xml)

    def test_latin1_txt_keeps_accents_without_replacement(self):
        payload = "España y función $x^2$".encode("latin-1")

        lines = main._extract_text_lines_from_txt(payload)
        doc = main.build_document_from_paragraphs(lines)
        document_xml = self._document_xml(doc)

        self.assertEqual(lines, ["España y función $x^2$"])
        self.assertEqual(self._doc_omml_count(doc), 1)
        self.assertIn("España y función", document_xml)
        self.assertNotIn("�", document_xml)


if __name__ == "__main__":
    unittest.main()
