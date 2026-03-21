import unittest

import main


class SeoAndTextTests(unittest.TestCase):
    def test_fix_text_mojibake(self):
        raw = "GuÃ­a rÃ¡pida â†’ Word con fÃ³rmulas"
        fixed = main._fix_text_mojibake(raw)
        self.assertIn("Guía rápida", fixed)
        self.assertIn("Word con fórmulas", fixed)
        self.assertNotIn("Ã", fixed)

    def test_sitemap_has_hreflang_namespace(self):
        xml = main.generate_sitemap_xml()
        self.assertIn('xmlns:xhtml="http://www.w3.org/1999/xhtml"', xml)
        self.assertIn('hreflang="x-default"', xml)
        self.assertIn("<loc>https://www.ecuacionesaword.com/blog</loc>", xml)


if __name__ == "__main__":
    unittest.main()
