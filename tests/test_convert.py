import asyncio
import io
import json
import unittest
import zipfile

from docx import Document
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

import main


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ConvertEndpointTests(unittest.TestCase):
    def setUp(self):
        main._RATE_LIMIT_BUCKETS.clear()
        main._RATE_LIMIT_LAST_SWEEP_AT = 0.0

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

    def _make_upload(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> UploadFile:
        return UploadFile(
            file=io.BytesIO(content),
            filename=filename,
            headers=Headers({"content-type": content_type}),
        )

    def _make_convert_request(self) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/convert",
                "headers": [],
                "scheme": "https",
                "server": ("testserver", 443),
                "client": ("198.51.100.10", 12345),
                "query_string": b"",
            }
        )

    async def _collect_streaming_body(self, response) -> bytes:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return b"".join(chunks)

    def _run_convert(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        lang: str = "es",
    ):
        upload = self._make_upload(filename, content, content_type)
        return asyncio.run(main.convert(file=upload, lang=lang))

    def _convert_error_response(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        lang: str = "es",
    ):
        try:
            self._run_convert(filename, content, content_type, lang)
        except HTTPException as exc:
            response = asyncio.run(
                main.custom_http_exception_handler(self._make_convert_request(), exc)
            )
            return response
        self.fail("Expected convert() to raise HTTPException")

    def test_convert_get_redirects_to_home(self):
        response = asyncio.run(main.convert_get())

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["location"], "/")

    def test_convert_txt_returns_docx_with_default_spanish_filename(self):
        response = self._run_convert("sample.txt", b"Equation: $x+1$\n", "text/plain")
        response_bytes = asyncio.run(self._collect_streaming_body(response))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], DOCX_MIME)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn('filename="ecuaciones-a-word.docx"', response.headers["content-disposition"])
        self.assertGreater(self._doc_omml_count(response_bytes), 0)

    def test_convert_docx_returns_docx_with_english_filename(self):
        source_bytes = self._make_docx_bytes("Equation: $x+1$")

        response = self._run_convert("sample.docx", source_bytes, DOCX_MIME, lang="en")
        response_bytes = asyncio.run(self._collect_streaming_body(response))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], DOCX_MIME)
        self.assertIn('filename="equations-to-word.docx"', response.headers["content-disposition"])
        self.assertGreater(self._doc_omml_count(response_bytes), 0)

    def test_convert_rejects_invalid_docx(self):
        response = self._convert_error_response(
            "broken.docx",
            b"this-is-not-a-docx",
            DOCX_MIME,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            json.loads(response.body.decode("utf-8")),
            {
                "ok": False,
                "error": {
                    "code": "invalid_document",
                    "message": "Invalid .docx file. Upload a valid Word document.",
                    "status": 400,
                },
            },
        )

    def test_convert_rejects_unsupported_extension(self):
        response = self._convert_error_response(
            "notes.md",
            b"$x+1$",
            "text/markdown",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            json.loads(response.body.decode("utf-8")),
            {
                "ok": False,
                "error": {
                    "code": "unsupported_file_type",
                    "message": "Unsupported file type. Use .docx or .txt.",
                    "status": 400,
                },
            },
        )

    def test_convert_rejects_oversized_payload(self):
        oversized_content = b"a" * (main.MAX_FILE_SIZE_BYTES + 1)
        response = self._convert_error_response(
            "too-big.txt",
            oversized_content,
            "text/plain",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            json.loads(response.body.decode("utf-8")),
            {
                "ok": False,
                "error": {
                    "code": "file_too_large",
                    "message": "File too large. Maximum size is 5 MB.",
                    "status": 413,
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
