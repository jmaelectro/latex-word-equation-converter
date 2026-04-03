import asyncio
import io
import unittest
import zipfile

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

    def _request_for_path(self, path: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [],
                "scheme": "https",
                "server": ("testserver", 443),
                "client": ("127.0.0.1", 12345),
                "query_string": b"",
            }
        )

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

    def test_sitemap_excludes_non_primary_and_noindex_posts(self):
        xml = main.generate_sitemap_xml()
        self.assertNotIn("<loc>https://www.ecuacionesaword.com/de</loc>", xml)
        self.assertNotIn("<loc>https://www.ecuacionesaword.com/fr</loc>", xml)
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

    def test_live_public_routes_still_return_200(self):
        live_routes = {
            "/": main.home,
            "/en": main.home_en,
            "/blog": main.blog_index_es,
            "/en/blog": main.blog_index_en,
            "/robots.txt": main.robots_txt,
            "/sitemap.xml": main.sitemap_xml,
        }
        for path, handler in live_routes.items():
            with self.subTest(path=path):
                resp = asyncio.run(handler())
                self.assertEqual(resp.status_code, 200)

    def test_removed_legacy_root_html_routes_redirect_to_canonical_urls(self):
        cases = {
            "/blog.html": "/blog/pasar-ecuaciones-chatgpt-word",
            "/blog2": "/blog/convertir-documento-latex-word",
            "/blog2.html": "/blog/convertir-documento-latex-word",
            "/blog6.html": "/blog/markdown-con-latex-a-word-docx",
            "/blog-index.html": "/blog",
            "/blog-en-1.html": "/en/blog/copy-chatgpt-equations-word",
            "/index-de.html": "/en",
            "/index-fr.html": "/en",
            "/index-it.html": "/en",
            "/index-pt.html": "/en",
        }
        for path, target in cases.items():
            with self.subTest(path=path):
                resp = asyncio.run(main.legacy_redirects(self._request_for_path(path)))
                self.assertEqual(resp.status_code, 301)
                self.assertEqual(resp.headers.get("location"), target)

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
        self.assertTrue(resp.headers.get("location", "").startswith("/en/blog/"))

    def test_non_primary_solution_slug_redirects_to_en_equivalent(self):
        resp = asyncio.run(main.solution_landing_fr("gemini-equations-to-word"))
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp.headers.get("location"), "/en/solutions/gemini-equations-to-word")

    def test_legal_text_no_mojibake(self):
        ctx = main._legal_page_context("es", "privacy")
        self.assertIn("Política", ctx["title"])
        self.assertIn("Cómo", ctx["description"])
        self.assertIn("únicamente", ctx["body_html"])
        self.assertIn("Analítica", ctx["body_html"])
        self.assertNotIn("Pol?tica", ctx["title"])
        self.assertNotIn("C?mo", ctx["description"])

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


if __name__ == "__main__":
    unittest.main()
