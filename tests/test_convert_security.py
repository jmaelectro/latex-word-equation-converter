import asyncio
import io
import unittest
import zipfile

from docx import Document
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request
from starlette.responses import PlainTextResponse

import main


class ConvertSecurityTests(unittest.TestCase):
    def setUp(self):
        main._RATE_LIMIT_BUCKETS.clear()
        main._RATE_LIMIT_LAST_SWEEP_AT = 0.0

    def _build_docx_bytes(self, text: str = "Equation $x+1$") -> bytes:
        doc = Document()
        doc.add_paragraph(text)
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

    def _build_request(self, client_host: str, x_forwarded_for: str | None = None) -> Request:
        headers = []
        if x_forwarded_for is not None:
            headers.append((b"x-forwarded-for", x_forwarded_for.encode("ascii")))
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/convert",
                "headers": headers,
                "scheme": "https",
                "server": ("testserver", 443),
                "client": (client_host, 12345),
                "query_string": b"",
            }
        )

    def _build_oversized_docx_member(self) -> bytes:
        large_text = "A" * (main.MAX_DOCX_ENTRY_UNCOMPRESSED_BYTES + 1024)
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>"
            f"{large_text}"
            "</w:t></w:r></w:p></w:body></w:document>"
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        )
        relationships = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            "</Relationships>"
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", relationships)
            zf.writestr("word/document.xml", document_xml)
        return buf.getvalue()

    def _run_convert(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ):
        upload = self._make_upload(filename, content, content_type)
        return asyncio.run(main.convert(file=upload, lang="en"))

    def test_convert_accepts_valid_txt(self):
        resp = self._run_convert("math.txt", b"$x+1$\nSecond line", "text/plain")

        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            resp.headers.get("content-type", ""),
        )

    def test_convert_accepts_valid_docx(self):
        resp = self._run_convert(
            "math.docx",
            self._build_docx_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment;", resp.headers.get("content-disposition", ""))

    def test_convert_rejects_docx_extension_spoof(self):
        with self.assertRaises(HTTPException) as ctx:
            self._run_convert("not-really.docx", b"plain text", "text/plain")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(
            ctx.exception.detail,
            {
                "code": "invalid_document",
                "message": "Invalid .docx file. Upload a valid Word document.",
            },
        )

    def test_convert_rejects_binary_txt_payload(self):
        with self.assertRaises(HTTPException) as ctx:
            self._run_convert("payload.txt", b"\x00\x01\x02not-text", "text/plain")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Invalid .txt file. Upload plain text.")

    def test_convert_rejects_short_binary_txt_payload(self):
        with self.assertRaises(HTTPException) as ctx:
            self._run_convert("short.txt", b"\x00\x01\x02bad", "text/plain")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Invalid .txt file. Upload plain text.")

    def test_convert_rejects_oversized_upload(self):
        with self.assertRaises(HTTPException) as ctx:
            self._run_convert(
                "huge.txt",
                b"a" * (main.MAX_FILE_SIZE_BYTES + 1),
                "text/plain",
            )

        self.assertEqual(ctx.exception.status_code, 413)
        self.assertEqual(
            ctx.exception.detail,
            {
                "code": "file_too_large",
                "message": "File too large. Maximum size is 5 MB.",
            },
        )

    def test_convert_rejects_docx_with_oversized_member(self):
        with self.assertRaises(HTTPException) as ctx:
            self._run_convert(
                "compressed.docx",
                self._build_oversized_docx_member(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        self.assertEqual(ctx.exception.status_code, 413)
        self.assertEqual(
            ctx.exception.detail,
            {
                "code": "file_too_large",
                "message": "The .docx file exceeds safe size limits.",
            },
        )

    def test_client_ip_ignores_spoofed_forwarded_header_from_public_client(self):
        request = self._build_request("198.51.100.10", "203.0.113.77")
        self.assertEqual(main._client_ip(request), "198.51.100.10")

    def test_client_ip_accepts_forwarded_header_from_trusted_proxy(self):
        request = self._build_request("10.1.2.3", "203.0.113.77, 10.1.2.3")
        self.assertEqual(main._client_ip(request), "203.0.113.77")

    def test_rate_limit_cannot_be_sharded_with_spoofed_forwarded_for(self):
        original_limit = main.RATE_LIMIT_MAX_REQUESTS
        try:
            main.RATE_LIMIT_MAX_REQUESTS = 1
            first = self._build_request("198.51.100.20", "203.0.113.1")
            second = self._build_request("198.51.100.20", "203.0.113.2")

            self.assertTrue(main._check_convert_rate_limit(first))
            self.assertFalse(main._check_convert_rate_limit(second))
        finally:
            main.RATE_LIMIT_MAX_REQUESTS = original_limit
            main._RATE_LIMIT_BUCKETS.clear()

    def test_convert_middleware_rejects_oversized_content_length(self):
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/convert",
                "headers": [
                    (
                        b"content-length",
                        str(main.MAX_UPLOAD_CONTENT_LENGTH_BYTES + 1).encode("ascii"),
                    )
                ],
                "scheme": "https",
                "server": ("testserver", 443),
                "client": ("198.51.100.10", 12345),
                "query_string": b"",
            }
        )

        async def call_next(_request):
            return PlainTextResponse("ok")

        resp = asyncio.run(
            main.add_common_headers_mw(
                request,
                call_next,
            )
        )

        self.assertEqual(resp.status_code, 413)
        self.assertEqual(resp.headers.get("Cache-Control"), "no-store")


if __name__ == "__main__":
    unittest.main()
