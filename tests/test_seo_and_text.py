import asyncio
import io
import re
import unittest
import zipfile
from unittest.mock import patch

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

import main


class SeoAndTextTests(unittest.TestCase):
    def _doc_omml_count(self, doc) -> int:
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            document_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        return document_xml.count("<m:oMath") + document_xml.count("<m:oMathPara")

    async def _asgi_get(self, path: str):
        response_start = {}
        body_chunks = []
        receive_messages = iter([{"type": "http.request", "body": b"", "more_body": False}])

        async def receive():
            return next(receive_messages, {"type": "http.disconnect"})

        async def send(message):
            nonlocal response_start
            if message["type"] == "http.response.start":
                response_start = message
            elif message["type"] == "http.response.body":
                body_chunks.append(message.get("body", b""))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [(b"host", b"www.ecuacionesaword.com")],
            "client": ("127.0.0.1", 12345),
            "server": ("www.ecuacionesaword.com", 443),
            "root_path": "",
            "app": main.app,
        }

        await main.app(scope, receive, send)
        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in response_start.get("headers", [])
        }
        body = b"".join(body_chunks).decode("utf-8", errors="ignore")
        return response_start.get("status", 500), headers, body

    def test_fix_text_mojibake(self):
        raw = "GuÃƒÂ­a rÃƒÂ¡pida Ã¢â€ â€™ Word con fÃƒÂ³rmulas"
        fixed = main._fix_text_mojibake(raw)
        self.assertIn("Word con", fixed)
        self.assertNotIn("Ãƒ", fixed)

    def test_sitemap_has_hreflang_namespace(self):
        xml = main.generate_sitemap_xml()
        self.assertIn('xmlns:xhtml="http://www.w3.org/1999/xhtml"', xml)
        self.assertIn('hreflang="x-default"', xml)
        self.assertIn("<loc>https://www.ecuacionesaword.com/blog</loc>", xml)

    def test_sitemap_excludes_non_primary_legal_and_noindex_posts(self):
        xml = main.generate_sitemap_xml()
        self.assertNotIn("<loc>https://www.ecuacionesaword.com/de</loc>", xml)
        self.assertNotIn("<loc>https://www.ecuacionesaword.com/fr</loc>", xml)
        self.assertNotIn("/privacy</loc>", xml)
        self.assertNotIn("/en/privacy</loc>", xml)
        self.assertNotIn("/blog/convertidor-formulas-chatgpt-a-word</loc>", xml)
        self.assertNotIn("/en/blog/simbolos-raros-ecuaciones-word-cambria-math</loc>", xml)
        self.assertIn("/soluciones</loc>", xml)
        self.assertIn("/en/solutions</loc>", xml)

    def test_home_has_only_primary_hreflang(self):
        html = main.read_html_file("index.html")
        self.assertIn('hreflang="es"', html)
        self.assertIn('hreflang="en"', html)
        self.assertNotIn('hreflang="de"', html)
        self.assertNotIn('hreflang="fr"', html)
        self.assertNotIn('hreflang="it"', html)
        self.assertNotIn('hreflang="pt"', html)

    def test_solutions_hub_is_200_not_redirect(self):
        resp = asyncio.run(main.solutions_es())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Soluciones", resp.body.decode("utf-8", errors="ignore"))

    def test_non_primary_home_redirects_to_en(self):
        resp = asyncio.run(main.home_de())
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp.headers.get("location"), "/en")

    def test_non_primary_blog_redirects_to_en_blog(self):
        resp = asyncio.run(main.blog_index_de())
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp.headers.get("location"), "/en/blog")

    def test_non_primary_legal_redirects_to_en(self):
        resp = asyncio.run(main.privacy_fr())
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp.headers.get("location"), "/en/privacy")

    def test_non_primary_solutions_redirect_to_en(self):
        resp = asyncio.run(main.solutions_it())
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp.headers.get("location"), "/en/solutions")

    def test_non_primary_blog_post_redirects_to_en_equivalent(self):
        resp = asyncio.run(main.blog_post_de("gemini-equations-to-word-omml"))
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp.headers.get("location"), "/en/blog/gemini-equations-to-word-omml")

    def test_non_primary_solution_slug_redirects_to_en_equivalent(self):
        resp = asyncio.run(main.solution_landing_fr("gemini-equations-to-word"))
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp.headers.get("location"), "/en/solutions/gemini-equations-to-word")

    def test_mixed_language_solution_slug_redirects_to_en_equivalent(self):
        resp = asyncio.run(main.solution_landing_fr("gemini-ecuaciones-a-word"))
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp.headers.get("location"), "/en/solutions/gemini-equations-to-word")

    def test_mixed_language_blog_slug_redirects_to_canonical_language(self):
        resp = asyncio.run(main.blog_post_en("matrices-sistemas-latex-a-word"))
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp.headers.get("location"), "/blog/matrices-sistemas-latex-a-word")

    def test_legal_text_no_mojibake(self):
        ctx = main.site_module._legal_page_context("es", "privacy")
        self.assertIn("Política", ctx["title"])
        self.assertIn("Cómo", ctx["description"])
        self.assertIn("únicamente", ctx["body_html"])
        self.assertIn("Analítica", ctx["body_html"])
        self.assertNotIn("Pol?tica", ctx["title"])
        self.assertNotIn("C?mo", ctx["description"])
        self.assertNotIn("PolÃ", ctx["title"])
        self.assertNotIn("CÃ³mo", ctx["description"])

    def test_home_tracking_events_are_consistent(self):
        html = main.read_html_file("index.html")
        required_events = [
            "file_selected",
            "convert_clicked",
            "convert_started",
            "convert_success",
            "download_completed",
            "error_conversion",
            "language_selected",
            "landing_cta_clicked",
        ]
        for event_name in required_events:
            self.assertIn(event_name, html)
        self.assertNotIn("convert_error", html)

    def test_parse_math_segments_ignores_currency(self):
        segments = main.parse_math_segments("Price is $5 and $10.")
        self.assertEqual(segments, [("text", "Price is $5 and $10.")])

    def test_parse_math_segments_supports_parenthesis_delimiter(self):
        segments = main.parse_math_segments(r"Inline \(x+1\) should convert")
        self.assertEqual(
            segments,
            [("text", "Inline "), ("inline", "x+1"), ("text", " should convert")],
        )

    def test_txt_conversion_keeps_currency_as_text(self):
        doc = main.build_document_from_paragraphs(["Budget: $5-$10"])
        self.assertEqual(self._doc_omml_count(doc), 0)
        self.assertIn("Budget: $5-$10", doc.paragraphs[0].text)

    def test_keywords_are_normalized_to_lists(self):
        keywords = main.BLOG_POSTS["en"]["copy-chatgpt-equations-word"]["keywords"]
        self.assertIsInstance(keywords, list)
        self.assertGreater(len(keywords), 1)

    def test_untranslated_post_does_not_emit_missing_hreflang(self):
        resp = asyncio.run(main.blog_post_en("gemini-equations-to-word-omml"))
        html = resp.body.decode("utf-8", errors="ignore")
        self.assertNotIn(
            'hreflang="es" href="https://www.ecuacionesaword.com/blog/gemini-equations-to-word-omml"',
            html,
        )
        self.assertNotIn('hreflang="de"', html)

    def test_custom_404_is_noindex(self):
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/missing-page",
                "headers": [],
                "scheme": "https",
                "server": ("testserver", 443),
                "client": ("127.0.0.1", 12345),
                "query_string": b"",
            }
        )
        resp = asyncio.run(
            main.custom_http_exception_handler(
                request,
                StarletteHTTPException(status_code=404, detail="Not found"),
            )
        )
        self.assertEqual(resp.headers.get("X-Robots-Tag"), "noindex, nofollow")
        self.assertIn("noindex, nofollow", resp.body.decode("utf-8", errors="ignore"))

    def test_home_markup_has_accessibility_improvements(self):
        html = main.read_html_file("index.html")
        self.assertIn('role="status"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertNotIn('role="link"', html)

    def test_home_pages_use_single_upload_field_contract(self):
        for filename in [
            "index.html",
            "index-en.html",
            "index-de.html",
            "index-fr.html",
            "index-it.html",
            "index-pt.html",
        ]:
            html = main.read_html_file(filename)
            self.assertIn('fd.append("file", file);', html)
            self.assertNotIn('fd.append("document", file);', html)

    def test_home_guide_cards_use_matching_data_href_and_anchor(self):
        for filename in [
            "index.html",
            "index-en.html",
            "index-de.html",
            "index-fr.html",
            "index-it.html",
            "index-pt.html",
        ]:
            html = main.read_html_file(filename)
            for match in re.finditer(r'<article[^>]*data-href="([^"]+)"[^>]*>(.*?)</article>', html, re.S):
                anchor = re.search(r'<a href="([^"]+)"', match.group(2))
                if anchor:
                    self.assertEqual(match.group(1), anchor.group(1), filename)

    def test_localized_home_json_ld_uses_localized_urls(self):
        expected = {
            "index-en.html": "/en",
            "index-de.html": "/de",
            "index-fr.html": "/fr",
            "index-it.html": "/it",
            "index-pt.html": "/pt",
        }
        for filename, suffix in expected.items():
            html = main.read_html_file(filename)
            self.assertIn('"url": "https://www.ecuacionesaword.com/"', html)
            self.assertIn(f'"url": "https://www.ecuacionesaword.com{suffix}"', html)
            self.assertIn('"inLanguage": ["es", "en", "de", "fr", "it", "pt"]', html)

    def test_analytics_default_consent_is_granted_on_published_pages(self):
        for filename in [
            "index.html",
            "index-en.html",
            "index-de.html",
            "index-fr.html",
            "index-it.html",
            "index-pt.html",
        ]:
            html = main.read_html_file(filename)
            self.assertIn("analytics_storage: 'granted'", html, filename)
            self.assertNotIn("analytics_storage: 'denied'", html, filename)

        _, _, blog_body = asyncio.run(self._asgi_get("/en/blog/markdown-latex-to-word-docx"))
        self.assertIn("analytics_storage: 'granted'", blog_body)
        self.assertNotIn("analytics_storage: 'denied'", blog_body)

    def test_home_language_switcher_supports_all_published_languages(self):
        expected_langs = 'const supportedLangs = ["es", "en", "de", "fr", "it", "pt"];'
        for filename in ["index.html", "index-en.html", "index-de.html", "index-fr.html", "index-it.html", "index-pt.html"]:
            html = main.read_html_file(filename)
            self.assertIn(expected_langs, html, filename)

    def test_trusted_html_sanitizer_removes_active_content(self):
        raw = (
            '<p class="intro" onclick="alert(1)">Texto '
            '<a href="javascript:alert(1)" class="cta">enlace</a>'
            "<script>alert(1)</script></p>"
        )
        sanitized = main.site_module._sanitize_trusted_html(raw, "test")
        self.assertIn('<p class="intro">Texto <a class="cta">enlace</a></p>', sanitized)
        self.assertNotIn("onclick", sanitized)
        self.assertNotIn("javascript:", sanitized)
        self.assertNotIn("<script", sanitized)

    def test_home_csp_uses_nonce_for_raw_html_scripts(self):
        status_code, headers, body = asyncio.run(self._asgi_get("/"))
        self.assertEqual(status_code, 200)

        csp = headers.get("content-security-policy", "")
        self.assertIn("script-src 'self' 'nonce-", csp)
        self.assertNotRegex(csp, r"script-src[^;]*'unsafe-inline'")
        self.assertIn("script-src-attr 'none'", csp)

        nonces = re.findall(r'<script nonce="([^"]+)"', body)
        self.assertGreaterEqual(len(nonces), 3)
        self.assertEqual(len(set(nonces)), 1)
        self.assertIn(f"'nonce-{nonces[0]}'", csp)

    def test_blog_and_legal_pages_render_expected_content(self):
        blog_status, _, blog_body = asyncio.run(self._asgi_get("/en/blog/markdown-latex-to-word-docx"))
        self.assertEqual(blog_status, 200)
        self.assertIn("Markdown with LaTeX to Word", blog_body)
        self.assertIn("<h2>1) Common export paths</h2>", blog_body)
        self.assertNotIn("javascript:", blog_body)

        legal_status, _, legal_body = asyncio.run(self._asgi_get("/privacy"))
        self.assertEqual(legal_status, 200)
        self.assertIn("Política de privacidad", legal_body)
        self.assertIn("mailto:ecuacionesaword@gmail.com", legal_body)

    def test_rendered_pages_do_not_contain_known_text_corruption(self):
        pages = [
            asyncio.run(main.home()).body.decode("utf-8", errors="ignore"),
            asyncio.run(main.home_en()).body.decode("utf-8", errors="ignore"),
            asyncio.run(main.privacy_fr()).body.decode("utf-8", errors="ignore"),
            asyncio.run(main.solutions_it()).body.decode("utf-8", errors="ignore"),
        ]
        for body in pages:
            self.assertNotIn("ChatGPT?Word", body)
            self.assertNotIn("? Ecuaciones", body)
            self.assertNotIn("? No se vende", body)
            self.assertNotIn("? Flujo pensado", body)
            self.assertNotIn("Politique de confidentialit?", body)
            self.assertNotIn("Datenschutzerkl?rung", body)

    def test_json_ld_is_rendered_as_json_object_not_string(self):
        _, _, body = asyncio.run(self._asgi_get("/en/blog/markdown-latex-to-word-docx"))
        self.assertIn('type="application/ld+json">{"@context"', body)
        self.assertNotIn('type="application/ld+json">"{', body)

    def test_convert_upload_to_docx_bytes_txt_flow(self):
        out_bytes = main._convert_upload_to_docx_bytes("txt", b"Equation: $x+1$\n")
        doc = main.Document(io.BytesIO(out_bytes))
        self.assertGreater(self._doc_omml_count(doc), 0)
        self.assertIn("Equation:", doc.paragraphs[0].text)

    def test_convert_endpoint_offloads_blocking_work_to_threadpool(self):
        captured = {}

        async def fake_run_in_threadpool(func, *args, **kwargs):
            captured["func"] = func
            captured["args"] = args
            return main._convert_upload_to_docx_bytes(*args)

        with patch("main.run_in_threadpool", side_effect=fake_run_in_threadpool):
            upload = main.UploadFile(filename="sample.txt", file=io.BytesIO(b"Equation: $x+1$\n"))
            response = asyncio.run(main.convert(file=upload, lang="en"))
            response_bytes = asyncio.run(self._collect_streaming_response(response))

        self.assertIs(captured["func"], main._convert_upload_to_docx_bytes)
        self.assertEqual(captured["args"][0], "txt")
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        doc = main.Document(io.BytesIO(response_bytes))
        self.assertGreater(self._doc_omml_count(doc), 0)

    async def _collect_streaming_response(self, response) -> bytes:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return b"".join(chunks)


if __name__ == "__main__":
    unittest.main()
