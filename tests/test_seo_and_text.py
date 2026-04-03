import asyncio
import unittest

import main


class SeoAndTextTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
