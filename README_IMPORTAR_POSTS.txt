Incluye 8 posts nuevos (4 ES + 4 EN) + blog-index y sitemap actualizados.

Archivos nuevos:
- blog-<slug>.html (ES)
- blog-en-<slug>.html (EN)

Slugs ES:
- /blog/signos-interrogacion-ecuaciones-chatgpt-word
- /blog/overleaf-latex-a-word-ecuaciones-editables
- /blog/omml-vs-mathtype-vs-latex-word-tfg
- /blog/pandoc-ecuaciones-word-no-editables-soluciones

Slugs EN:
- /en/blog/question-marks-chatgpt-equations-word
- /en/blog/overleaf-latex-to-word-editable-equations
- /en/blog/omml-vs-mathtype-vs-latex-word-thesis
- /en/blog/pandoc-math-to-word-omml-troubleshooting

Si tu main.py usa una lista/mapping de slugs -> archivos HTML, añade estos slugs.

Consejo: crea un fallback que sirva automáticamente 'blog-<slug>.html' y 'blog-en-<slug>.html' si existen,
así añadir posts es solo subir el HTML + sitemap.
