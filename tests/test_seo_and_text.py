import unittest
import asyncio

import main


class SeoAndTextTests(unittest.TestCase):
    def test_sitemap_has_hreflang_namespace(self):
        xml = main.generate_sitemap_xml()
        self.assertIn('xmlns:xhtml="http://www.w3.org/1999/xhtml"', xml)
        self.assertIn('hreflang="x-default"', xml)
        self.assertIn("<loc>https://www.ecuacionesaword.com/blog</loc>", xml)

    def test_sitemap_excludes_non_primary_and_noindex_posts(self):
        xml = main.generate_sitemap_xml()
        self.assertNotIn("<loc>https://www.ecuacionesaword.com/de</loc>", xml)
        self.assertNotIn("/blog/convertidor-formulas-chatgpt-a-word</loc>", xml)
        self.assertIn("/soluciones</loc>", xml)
        self.assertIn("/en/solutions</loc>", xml)

    def test_solutions_hub_is_200_not_redirect(self):
        resp = asyncio.run(main.solutions_es())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Soluciones", resp.body.decode("utf-8", errors="ignore"))

    def test_non_primary_home_has_noindex_header(self):
        resp = asyncio.run(main.home_de())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("noindex", resp.headers.get("x-robots-tag", "").lower())

    def test_non_primary_blog_has_noindex_meta(self):
        resp = asyncio.run(main.blog_index_de())
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            'name="robots" content="noindex,follow,max-image-preview:large"',
            resp.body.decode("utf-8", errors="ignore"),
        )


if __name__ == "__main__":
    unittest.main()
