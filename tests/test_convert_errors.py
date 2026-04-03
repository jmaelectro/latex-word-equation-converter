import asyncio
import io
import json
import unittest

from fastapi import HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

import main


class ConvertErrorContractTests(unittest.TestCase):
    def setUp(self):
        main._RATE_LIMIT_BUCKETS.clear()

    def _request(self) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/convert",
                "headers": [],
                "scheme": "https",
                "server": ("testserver", 443),
                "client": ("127.0.0.1", 12345),
                "query_string": b"",
            }
        )

    def _upload(self, filename: str, content: bytes) -> UploadFile:
        return UploadFile(file=io.BytesIO(content), filename=filename, size=len(content))

    def _json_from_response(self, response) -> dict:
        return json.loads(response.body.decode("utf-8"))

    def _convert_response(self, upload: UploadFile, lang: str = "es"):
        try:
            return asyncio.run(main.convert(upload, lang))
        except HTTPException as exc:
            return asyncio.run(main.custom_http_exception_handler(self._request(), exc))

    def test_missing_file_returns_json_contract(self):
        exc = RequestValidationError(
            [{"loc": ("body", "file"), "msg": "Field required", "type": "missing"}]
        )
        response = asyncio.run(main.custom_validation_exception_handler(self._request(), exc))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("content-type"), "application/json")
        self.assertEqual(
            self._json_from_response(response),
            {
                "ok": False,
                "error": {
                    "code": "missing_file",
                    "message": "No file was uploaded.",
                    "status": 400,
                },
            },
        )

    def test_unsupported_file_type_returns_json_contract(self):
        response = self._convert_response(self._upload("notes.pdf", b"pdf-content"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self._json_from_response(response),
            {
                "ok": False,
                "error": {
                    "code": "unsupported_file_type",
                    "message": "Unsupported file type. Use .docx or .txt.",
                    "status": 400,
                },
            },
        )

    def test_file_too_large_returns_json_contract(self):
        oversized = b"a" * (main.MAX_FILE_SIZE_BYTES + 1)
        response = self._convert_response(self._upload("large.txt", oversized), lang="en")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(
            self._json_from_response(response),
            {
                "ok": False,
                "error": {
                    "code": "file_too_large",
                    "message": "File too large. Maximum size is 5 MB.",
                    "status": 413,
                },
            },
        )

    def test_invalid_docx_returns_json_contract(self):
        response = self._convert_response(
            self._upload("broken.docx", b"this-is-not-a-valid-docx"),
            lang="en",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self._json_from_response(response),
            {
                "ok": False,
                "error": {
                    "code": "invalid_document",
                    "message": "Invalid .docx file. Upload a valid Word document.",
                    "status": 400,
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
