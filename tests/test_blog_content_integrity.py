from __future__ import annotations

import json
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


class BlogContentIntegrityTests(unittest.TestCase):
    def test_posts_json_is_valid_utf8_json(self):
        with (BASE_DIR / "blog_content" / "posts.json").open(encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIn("posts", data)
        self.assertIsInstance(data["posts"], list)

    def test_spanish_live_fragments_do_not_keep_known_broken_copy(self):
        cases = {
            "blog_content/posts/es/pasar-ecuaciones-chatgpt-word.html": [
                "Indice rapido",
                "extra?os",
                "Checklist minimo",
                "Antes y despues",
                "ChatGPT -> Word",
            ],
            "blog_content/posts/es/latex-a-word-omml-guia-definitiva.html": [
                "Indice rapido",
                "Cu?ndo",
                "\x0crac",
                "landing de solucion",
            ],
            "blog_content/posts/es/overleaf-latex-a-word-ecuaciones-editables.html": [
                "Indice rapido",
                "compa?ero",
                "Errores tipicos",
            ],
            "blog_content/posts/es/pandoc-ecuaciones-word-no-editables-soluciones.html": [
                "Indice rapido",
                "Checklist de solucion",
                "a?ade",
                "Antes y despues",
            ],
            "blog_content/posts/es/que-es-omml-ecuaciones-word.html": [
                "Indice rapido",
                "Que es OMML",
                "matematicos",
            ],
            "blog_content/posts/es/latex-a-word-online-gratis-ecuaciones-editables.html": [
                "?Empieza",
            ],
        }

        for rel_path, broken_tokens in cases.items():
            text = (BASE_DIR / rel_path).read_text(encoding="utf-8")
            for token in broken_tokens:
                self.assertNotIn(token, text, msg=f"{rel_path} still contains {token!r}")

    def test_en_live_fragments_do_not_keep_broken_question_spacing(self):
        cases = {
            "blog_content/posts/en/question-marks-chatgpt-equations-word.html": ("?Use", "? Use"),
            "blog_content/posts/en/latex-to-word-quick-guide-no-broken-equations.html": ("?Read", "? Read"),
        }

        for rel_path, (broken, fixed) in cases.items():
            text = (BASE_DIR / rel_path).read_text(encoding="utf-8")
            self.assertNotIn(broken, text, msg=f"{rel_path} still contains {broken!r}")
            self.assertIn(fixed, text, msg=f"{rel_path} should contain {fixed!r}")


if __name__ == "__main__":
    unittest.main()
