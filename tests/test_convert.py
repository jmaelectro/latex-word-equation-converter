import io
import unittest
import zipfile

from docx import Document
from fastapi.testclient import TestClient

import main


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ConvertEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def _doc_omml_count(self, doc_bytes: bytes) -> int:
        with zipfile.ZipFile(io.BytesIO(doc_bytes)) as zf:
            document_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        return document_xml.count("<m:oMath") + document_xml.count("<m:oMathPara")

    def _make_docx_bytes(self, *paragraphs: str) -> bytes:
        doc = Document()
        for paragraph in paragraphs:
            doc.add_paragraph(paragraph)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue()

    def test_convert_get_redirects_to_home(self):
        response = self.client.get("/convert", follow_redirects=False)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["location"], "/")

    def test_convert_txt_returns_docx_with_default_spanish_filename(self):
        response = self.client.post(
            "/convert",
            files={"file": ("sample.txt", b"Equation: $x+1$\n", "text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], DOCX_MIME)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn('filename="ecuaciones-a-word.docx"', response.headers["content-disposition"])
        self.assertGreater(self._doc_omml_count(response.content), 0)

    def test_convert_docx_returns_docx_with_english_filename(self):
        source_bytes = self._make_docx_bytes("Equation: $x+1$")

        response = self.client.post(
            "/convert",
            data={"lang": "en"},
            files={"file": ("sample.docx", source_bytes, DOCX_MIME)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], DOCX_MIME)
        self.assertIn('filename="equations-to-word.docx"', response.headers["content-disposition"])
        self.assertGreater(self._doc_omml_count(response.content), 0)

    def test_convert_rejects_invalid_docx(self):
        response = self.client.post(
            "/convert",
            files={"file": ("broken.docx", b"this-is-not-a-docx", DOCX_MIME)},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.text, "Invalid .docx file. Upload a valid Word document.")

    def test_convert_rejects_unsupported_extension(self):
        response = self.client.post(
            "/convert",
            files={"file": ("notes.md", b"$x+1$", "text/markdown")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.text, "Unsupported file type. Use .docx or .txt")

    def test_convert_rejects_oversized_payload(self):
        oversized_content = b"a" * (main.MAX_FILE_SIZE_BYTES + 1)

        response = self.client.post(
            "/convert",
            files={"file": ("too-big.txt", oversized_content, "text/plain")},
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.text, "File too large (max 5MB)")


if __name__ == "__main__":
    unittest.main()
