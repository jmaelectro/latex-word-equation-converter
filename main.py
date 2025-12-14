from __future__ import annotations

import io
import logging
import os
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request

import math2docx


# ================================================================
# Config
# ================================================================
APP_TITLE = "Ecuaciones a Word (LaTeX → Word OMML)"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logger = logging.getLogger("ecuacionesaword")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
Segment = Tuple[str, str]  # ("text" | "inline" | "display", contenido)

# Puedes desactivar reglas específicas del "ejercicio" si no las quieres:
USE_EXERCISE_TWEAKS = True


def _parse_allowed_origins(value: str) -> List[str]:
    return [o.strip() for o in value.split(",") if o.strip()]


def get_allowed_origins() -> List[str]:
    env_val = os.getenv("ALLOWED_ORIGINS", "").strip()
    if env_val:
        return _parse_allowed_origins(env_val)
    return [
        "https://www.ecuacionesaword.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


app = FastAPI(title=APP_TITLE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=800)

# Static
_static_dir = os.path.join(BASE_DIR, "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ================================================================
# Blog (data-driven): metadata + aliases + templates
# ================================================================
SITE_NAME = "Ecuaciones a Word"
CANONICAL_HOST = "https://www.ecuacionesaword.com"

BLOG_DATA_PATH = os.path.join(BASE_DIR, "blog_content", "posts.json")
BLOG_POSTS_DIR = os.path.join(BASE_DIR, "blog_content", "posts")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "Missing dependency 'jinja2'. Install it with: pip install jinja2"
    ) from e

JINJA_ENV = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)

BLOG_POSTS: Dict[str, Dict[str, Dict[str, Any]]] = {"es": {}, "en": {}}
BLOG_LIST: Dict[str, List[Dict[str, Any]]] = {"es": [], "en": []}
BLOG_ALIASES: Dict[str, Dict[str, str]] = {"es": {}, "en": {}}


def _load_blog_data() -> Dict[str, Any]:
    """Load blog metadata from blog_content/posts.json.

    This is the single source of truth for:
    - canonical slugs
    - SEO metadata
    - translation pairing
    - alias slugs (legacy URLs) -> canonical
    """
    try:
        with open(BLOG_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("posts.json root is not a JSON object")
        data.setdefault("posts", [])
        data.setdefault("aliases", {})
        return data
    except Exception as exc:
        logger.exception("Failed to load blog data from %s", BLOG_DATA_PATH)
        # Keep the app running (converter is critical). Blog will 404 gracefully.
        return {"posts": [], "aliases": {}}


def _init_blog_cache() -> None:
    data = _load_blog_data()
    posts = data.get("posts", [])
    aliases = data.get("aliases", {})

    BLOG_POSTS["es"].clear()
    BLOG_POSTS["en"].clear()
    BLOG_LIST["es"].clear()
    BLOG_LIST["en"].clear()
    BLOG_ALIASES["es"].clear()
    BLOG_ALIASES["en"].clear()

    # Aliases
    if isinstance(aliases, dict):
        BLOG_ALIASES["es"].update((aliases.get("es") or {}))
        BLOG_ALIASES["en"].update((aliases.get("en") or {}))

    # Posts
    for p in posts:
        if not isinstance(p, dict):
            continue
        lang = (p.get("lang") or "").strip()
        slug = (p.get("slug") or "").strip()
        canonical_path = (p.get("canonical_path") or "").strip()
        if lang not in ("es", "en") or not slug or not canonical_path:
            continue
        BLOG_POSTS[lang][slug] = p

    # Lists (sorted)
    for lang in ("es", "en"):
        lst = list(BLOG_POSTS[lang].values())
        lst.sort(key=lambda d: (d.get("date_published") or "", d.get("slug") or ""), reverse=True)
        BLOG_LIST[lang] = lst


_init_blog_cache()


def _render_template(template_name: str, context: Dict[str, Any]) -> str:
    template = JINJA_ENV.get_template(template_name)
    return template.render(**context)


def _read_blog_body(lang: str, slug: str) -> str:
    path = os.path.join(BLOG_POSTS_DIR, lang, f"{slug}.html")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _month_name_es(month: int) -> str:
    names = [
        "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return names[month] if 1 <= month <= 12 else ""


def _format_date(lang: str, iso_date: str) -> str:
    """Format YYYY-MM-DD into a human-readable date."""
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d").date()
    except Exception:
        return iso_date

    if lang == "es":
        return f"{dt.day} de {_month_name_es(dt.month)} de {dt.year}"
    # en
    return dt.strftime("%b %d, %Y")


def _build_schema_article(post: Dict[str, Any], canonical_url: str) -> str:
    slug = post.get("slug") or ""
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url},
        "headline": post.get("title") or "",
        "description": post.get("description") or "",
        "datePublished": post.get("date_published") or "",
        "dateModified": post.get("date_modified") or post.get("date_published") or "",
        "author": {"@type": "Organization", "name": SITE_NAME},
        "publisher": {"@type": "Organization", "name": SITE_NAME},
        "inLanguage": post.get("lang") or "",
        "url": canonical_url,
        "keywords": post.get("keywords") or [],
        "about": post.get("tags") or [],
        "identifier": slug,
    }
    return json.dumps(schema, ensure_ascii=False)


def _build_schema_index(lang: str, canonical_url: str) -> str:
    items = []
    for idx, p in enumerate(BLOG_LIST.get(lang, []), start=1):
        items.append({
            "@type": "ListItem",
            "position": idx,
            "url": f"{CANONICAL_HOST}{p.get('canonical_path')}",
            "name": p.get("title") or "",
        })
    schema = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "Blog",
        "url": canonical_url,
        "inLanguage": lang,
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": items[:50],  # keep size bounded
        },
    }
    return json.dumps(schema, ensure_ascii=False)


# ================================================================
# Helpers
# ================================================================
def _read_text_file(path: str, default: Optional[str] = None) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def read_html_file(filename: str) -> str:
    path = os.path.join(BASE_DIR, filename)
    return _read_text_file(path)


def _now_lastmod_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _abs_url(path: str) -> str:
    # Canonical host (ajusta si cambias dominio)
    return f"https://www.ecuacionesaword.com{path}"


def _sitemap_url_entry(loc: str, lastmod: str, changefreq: str, priority: str) -> str:
    return (
        "  <url>\n"
        f"    <loc>{loc}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        "  </url>\n"
    )


def generate_sitemap_xml() -> str:
    """
    Sitemap XML (válido) generado desde las rutas reales.
    """
    lastmod = _now_lastmod_iso()
    urls: List[str] = []

    # Home
    urls.append(_sitemap_url_entry(_abs_url("/"), lastmod, "weekly", "1.0"))
    urls.append(_sitemap_url_entry(_abs_url("/en"), lastmod, "weekly", "0.8"))

    # Blog index
    urls.append(_sitemap_url_entry(_abs_url("/blog"), lastmod, "weekly", "0.8"))
    urls.append(_sitemap_url_entry(_abs_url("/en/blog"), lastmod, "weekly", "0.7"))

    # Blog posts ES
    for slug in BLOG_SLUGS_ES.keys():
        urls.append(_sitemap_url_entry(_abs_url(f"/blog/{slug}"), lastmod, "monthly", "0.6"))

    # Blog posts EN
    for slug in BLOG_SLUGS_EN.keys():
        urls.append(_sitemap_url_entry(_abs_url(f"/en/blog/{slug}"), lastmod, "monthly", "0.5"))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(urls)
        + "</urlset>\n"
    )


# ================================================================
# 1) Normalización / prettify (tu lógica existente)
# ================================================================
def normalize_math_text(text: str) -> str:
    t = text
    t = re.sub(r"q([1-4])\s*\(", r"q_\1(", t)          # q1( -> q_1(
    t = re.sub(r"\bD([1-4])\b", r"D_\1", t)            # D1 -> D_1
    for var in ("x", "y", "z"):
        for exp in ("2", "3", "4"):
            t = re.sub(rf"{var}{exp}\b", rf"{var}^{exp}", t)  # x2 -> x^2
    return t


def _prettify_paragraphs_for_exercise(paragraph_texts: List[str]) -> List[str]:
    out: List[str] = []
    for text in paragraph_texts:
        s = normalize_math_text(text)
        stripped = s.strip()
        if stripped == "":
            continue

        if stripped.lower() == "actividad2grupal":
            out.append("Actividad 2 (trabajo grupal)")
            continue

        if all(sym in stripped for sym in ["q_1(x,y,z)", "q_2(x,y,z)", "q_3(x,y,z)", "q_4(x,y,z)"]):
            out.append("$$ q_1(x,y,z) = 2x^2 + 2y^2 + 2z^2 + 2xy + 2xz $$")
            out.append("$$ q_2(x,y,z) = x^2 - y^2 + z^2 + 2xy $$")
            out.append("$$ q_3(x,y,z) = 2x^2 - y^2 + 2z^2 + 4xy - 4yz $$")
            out.append("$$ q_4(x,y,z) = 4x^2 + 2y^2 + z^2 + 2yz $$")
            continue

        if stripped.startswith("Interpretamos que") and "garantizar beneficios" in stripped:
            out.append(
                "Interpretamos que “garantizar beneficios” significa que el beneficio "
                "$q(x,y,z)$ sea positivo para todo $(x,y,z)\\neq(0,0,0)$, es decir, "
                "que la forma cuadrática sea definida positiva."
            )
            continue

        if (
            "Escribimos cada forma como q(x)=xT" in stripped
            or "Escribimos cada forma como q(x)=xTA" in stripped
            or "Escribimos cada forma como q(x)=xTA x(\\mathbf x)" in stripped
            or ("Escribimos cada forma como q(x)=xTAx(\\mathbf x)=\\mathbf x^T A\\mathbf x" in stripped)
        ):
            out.append("Escribimos cada forma como $q(\\mathbf x) = \\mathbf x^T A\\, \\mathbf x$, con $\\mathbf x = (x,y,z)^T$.")
            continue

        if "coeficiente del término cruzado" in stripped:
            out.append("Recordando que el coeficiente del término cruzado $2x_i y_j$ se reparte como $a_{ij}=a_{ji}=1$:")
            continue

        if "Forma q1" in stripped or "q1q_1q1" in stripped:
            out.append("Forma $q_1$:")
            continue
        if "Forma q2" in stripped or "q2q_2q2" in stripped:
            out.append("Forma $q_2$:")
            continue
        if "Forma q3" in stripped or "q3q_3q3" in stripped:
            out.append("Forma $q_3$:")
            continue
        if "Forma q4" in stripped or "q4q_4q4" in stripped:
            out.append("Forma $q_4$:")
            continue

        if "Criterio de Sylvester" in stripped:
            out.append("2. Criterio de Sylvester")
            continue
        if "Una matriz simétrica" in stripped and "definida positiva" in stripped:
            out.append("Una matriz simétrica $A$ es definida positiva si todos sus menores principales líderes son positivos:")
            continue

        if "D_1>0" in stripped and "D_2>0" in stripped and "D_3>0" in stripped:
            out.append("\\begin{aligned}\nD_1 &> 0,\\\\\nD_2 &> 0,\\\\\nD_3 &> 0.\n\\end{aligned}")
            continue

        d_terms = list(re.finditer(r"D_[1-4][^D]*", stripped))
        if len(d_terms) >= 2:
            for m in d_terms:
                term = m.group(0).strip().strip(",")
                if term:
                    out.append(f"$$ {term} $$")
            continue

        if "A1A_1A1" in stripped or "A1A1" in stripped:
            out.append("⇒ $A_1$ es definida positiva ⇒ $q_1$ definida positiva.")
            continue
        if "A4A_4A4" in stripped or "A4A4" in stripped:
            out.append("⇒ $A_4$ es definida positiva ⇒ $q_4$ definida positiva.")
            continue

        if "detA2" in stripped or "det A_2" in stripped:
            out.append("$$ \\det A_2 = -2 < 0 $$")
            continue
        if "detA3" in stripped or "det A_3" in stripped:
            out.append("$$ \\det A_3 = -20 < 0 $$")
            continue

        if "q3q_3q3" in stripped and "indefinida" in stripped:
            out.append("⇒ $q_3$ también es indefinida.")
            continue

        out.append(stripped)

    return out


def prettify_paragraphs(paragraph_texts: List[str]) -> List[str]:
    generic: List[str] = []
    for text in paragraph_texts:
        s = normalize_math_text(text)
        if s.strip():
            generic.append(s.strip())
    if not USE_EXERCISE_TWEAKS:
        return generic
    return _prettify_paragraphs_for_exercise(generic)


# ================================================================
# 2) Parsing LaTeX
# ================================================================
def new_paragraph(doc: Document, align: Optional[Any] = None):
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    fmt.line_spacing = 1.0
    if align is not None:
        p.alignment = align
    return p


def add_math_safe(paragraph, latex: str) -> None:
    try:
        math2docx.add_math(paragraph, latex)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallo convirtiendo LaTeX a OMML: %s", exc)
        paragraph.add_run(latex)


def parse_math_segments(text: str) -> List[Segment]:
    segments: List[Segment] = []
    buf: List[str] = []

    def flush_text() -> None:
        if buf:
            segments.append(("text", "".join(buf)))
            buf.clear()

    i = 0
    n = len(text)
    while i < n:
        if text.startswith("$$", i):
            flush_text()
            end = text.find("$$", i + 2)
            if end == -1:
                buf.append(text[i:])
                break
            latex = text[i + 2 : end]
            segments.append(("display", latex.strip()))
            i = end + 2
            continue

        if text.startswith(r"\[", i):
            flush_text()
            end = text.find(r"\]", i + 2)
            if end == -1:
                buf.append(text[i:])
                break
            latex = text[i + 2 : end]
            segments.append(("display", latex.strip()))
            i = end + 2
            continue

        if text[i] == "$":
            flush_text()
            end = text.find("$", i + 1)
            if end == -1:
                buf.append(text[i:])
                break
            latex = text[i + 1 : end]
            segments.append(("inline", latex.strip()))
            i = end + 1
            continue

        buf.append(text[i])
        i += 1

    flush_text()
    return segments


def split_into_paragraph_descriptors(text: str) -> List[Dict[str, Any]]:
    segments = parse_math_segments(text)
    paragraphs: List[Dict[str, Any]] = []
    current_chunks: List[Segment] = []

    for kind, value in segments:
        if kind in ("text", "inline"):
            if value:
                current_chunks.append((kind, value))
        elif kind == "display":
            if current_chunks:
                paragraphs.append({"type": "inline", "chunks": current_chunks})
                current_chunks = []
            paragraphs.append({"type": "display", "latex": value})

    if current_chunks:
        paragraphs.append({"type": "inline", "chunks": current_chunks})

    return paragraphs


def split_long_latex_equation(latex: str, max_len: int = 120) -> List[str]:
    latex = latex.strip()
    if not latex:
        return []
    if len(latex) <= max_len:
        return [latex]

    if "\\\\" in latex:
        return [p.strip() for p in latex.split("\\\\") if p.strip()]

    if "=" in latex:
        tokens = [t.strip() for t in latex.split("=")]
        eqs: List[str] = []
        current = tokens[0]
        for tok in tokens[1:]:
            candidate = current + " = " + tok
            if len(candidate) > max_len and current:
                eqs.append(current)
                current = tok
            else:
                current = candidate
        if current:
            eqs.append(current)
        return eqs

    if "," in latex:
        tokens = [t.strip() for t in latex.split(",")]
        eqs2: List[str] = []
        current2 = ""
        for tok in tokens:
            candidate = (current2 + ", " if current2 else "") + tok
            if len(candidate) > max_len and current2:
                eqs2.append(current2)
                current2 = tok
            else:
                current2 = candidate
        if current2:
            eqs2.append(current2)
        return eqs2

    return [latex[i : i + max_len].strip() for i in range(0, len(latex), max_len)]


def add_aligned_block(doc: Document, aligned_block: str) -> None:
    content = aligned_block.strip()
    if content.startswith(r"\begin{aligned}"):
        content = content[len(r"\begin{aligned}") :]
    if content.endswith(r"\end{aligned}"):
        content = content[: -len(r"\end{aligned}")]
    content = content.strip()
    if not content:
        return
    rows = [row.strip() for row in content.split(r"\\") if row.strip()]
    for row in rows:
        row_no_amp = row.replace("&", "")
        p = new_paragraph(doc, WD_ALIGN_PARAGRAPH.CENTER)
        add_math_safe(p, row_no_amp)


def build_document_from_paragraphs(paragraph_texts: List[str]) -> Document:
    out_doc = Document()
    if not paragraph_texts:
        new_paragraph(out_doc)
        return out_doc

    in_display_block = False
    display_block_delim: Optional[str] = None  # "$$" o "\["
    display_lines: List[str] = []

    in_aligned_block = False
    aligned_lines: List[str] = []

    matrix_envs = ["vmatrix", "bmatrix", "pmatrix", "matrix"]

    for raw_text in paragraph_texts:
        text = normalize_math_text(raw_text)
        stripped = text.strip()

        # aligned multi-línea
        if in_aligned_block:
            aligned_lines.append(text)
            if r"\end{aligned}" in text:
                add_aligned_block(out_doc, "\n".join(aligned_lines))
                in_aligned_block = False
                aligned_lines = []
            continue

        if r"\begin{aligned}" in stripped:
            if r"\end{aligned}" in stripped:
                add_aligned_block(out_doc, stripped)
            else:
                in_aligned_block = True
                aligned_lines = [stripped]
            continue

        # display multi-línea $$ ... $$  o \[ ... \]
        if in_display_block:
            if (
                (display_block_delim == "$$" and stripped == "$$")
                or (display_block_delim == r"\[" and stripped == r"\]")
            ):
                latex = "\n".join(display_lines).strip()
                for part in split_long_latex_equation(latex):
                    p = new_paragraph(out_doc, WD_ALIGN_PARAGRAPH.CENTER)
                    add_math_safe(p, part)
                in_display_block = False
                display_block_delim = None
                display_lines = []
            else:
                display_lines.append(text)
            continue

        if stripped == "$$":
            in_display_block = True
            display_block_delim = "$$"
            display_lines = []
            continue

        if stripped == r"\[":
            in_display_block = True
            display_block_delim = r"\["
            display_lines = []
            continue

        # matrices en una línea
        handled_matrix = False
        for env in matrix_envs:
            begin = rf"\begin{{{env}}}"
            end = rf"\end{{{env}}}"
            if begin in stripped and end in stripped and "$" not in stripped:
                p = new_paragraph(out_doc, WD_ALIGN_PARAGRAPH.CENTER)
                add_math_safe(p, stripped)
                handled_matrix = True
                break
        if handled_matrix:
            continue

        # normal
        descriptors = split_into_paragraph_descriptors(text)
        if not descriptors:
            new_paragraph(out_doc)
            continue

        for desc in descriptors:
            if desc["type"] == "inline":
                p = new_paragraph(out_doc)
                for kind, value in desc["chunks"]:
                    if kind == "text":
                        p.add_run(value)
                    elif kind == "inline":
                        add_math_safe(p, value)
            elif desc["type"] == "display":
                for part in split_long_latex_equation(desc["latex"].strip()):
                    p = new_paragraph(out_doc, WD_ALIGN_PARAGRAPH.CENTER)
                    add_math_safe(p, part)

    # cierre si termina dentro de display/aligned
    if in_display_block and display_lines:
        latex = "\n".join(display_lines).strip()
        for part in split_long_latex_equation(latex):
            p = new_paragraph(out_doc, WD_ALIGN_PARAGRAPH.CENTER)
            add_math_safe(p, part)

    if in_aligned_block and aligned_lines:
        add_aligned_block(out_doc, "\n".join(aligned_lines))

    return out_doc


# ================================================================
# Routes: páginas
# ================================================================
@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    try:
        return HTMLResponse(read_html_file("index.html"))
    except FileNotFoundError:
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)


@app.get("/en", response_class=HTMLResponse)
async def home_en() -> HTMLResponse:
    try:
        return HTMLResponse(read_html_file("index-en.html"))
    except FileNotFoundError:
        return HTMLResponse("<h1>index-en.html not found</h1>", status_code=404)


@app.get("/blog", response_class=HTMLResponse)
async def blog_index_es() -> HTMLResponse:
    lang = "es"
    canonical_url = _abs_url("/blog")
    other_url = _abs_url("/en/blog")

    posts_view: List[Dict[str, Any]] = []
    tag_counts: Dict[str, int] = {}
    for p in BLOG_LIST.get(lang, []):
        for t in (p.get("tags") or []):
            if not isinstance(t, str) or not t.strip():
                continue
            tag_counts[t] = tag_counts.get(t, 0) + 1
        posts_view.append({
            "url": p.get("canonical_path") or f"/blog/{p.get('slug')}",
            "title": p.get("title") or "",
            "description": p.get("description") or "",
            "kicker": p.get("kicker") or "",
            "tags": p.get("tags") or [],
            "meta": f"{_format_date(lang, p.get('date_published') or '')} · {p.get('reading_time') or ''}".strip(" ·"),
        })

    top_tags = [k for k, _ in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))][:8]

    ctx = {
        "lang": lang,
        "site_name": SITE_NAME,
        "seo_title": "Blog | Ecuaciones a Word",
        "description": "Guías para convertir LaTeX e IA a Word con ecuaciones nativas (OMML), sin imágenes ni fórmulas rotas.",
        "keywords": ["LaTeX a Word", "OMML", "Word ecuaciones", "ChatGPT", "Pandoc"],
        "canonical_url": canonical_url,
        "alternates": [
            {"hreflang": "es", "href": canonical_url},
            {"hreflang": "en", "href": other_url},
            {"hreflang": "x-default", "href": canonical_url},
        ],
        "og_type": "website",
        "og_title": "Blog | Ecuaciones a Word",
        "og_description": "Guías prácticas para llevar ecuaciones LaTeX a Word (OMML) de forma limpia y editable.",
        "og_image": _abs_url("/static/og-image.svg"),
        "schema_json": _build_schema_index(lang, canonical_url),
        "converter_href": "/",
        "blog_index_href": "/blog",
        "nav_converter": "Conversor",
        "nav_blog": "Blog",
        "lang_switch_href": "/en/blog",
        "lang_switch_label": "EN",
        "h1": "Blog",
        "intro": "Guías prácticas para pasar ecuaciones de LaTeX e IA a Word con ecuaciones nativas (OMML).",
        "index_cta_primary": "Abrir conversor",
        "search_label": "Buscar artículos",
        "search_placeholder": "Buscar por tema, herramienta o problema (ej. pandoc, overleaf, OMML, ChatGPT)…",
        "filter_label": "Filtrar por etiqueta",
        "filter_all": "Todos",
        "top_tags": top_tags,
        "featured_title": "Artículos",
        "posts": posts_view,
        "year": datetime.now().year,
    }
    return HTMLResponse(_render_template("blog_index.html", ctx))


@app.get("/en/blog", response_class=HTMLResponse)
async def blog_index_en() -> HTMLResponse:
    lang = "en"
    canonical_url = _abs_url("/en/blog")
    other_url = _abs_url("/blog")

    posts_view: List[Dict[str, Any]] = []
    tag_counts: Dict[str, int] = {}
    for p in BLOG_LIST.get(lang, []):
        for t in (p.get("tags") or []):
            if not isinstance(t, str) or not t.strip():
                continue
            tag_counts[t] = tag_counts.get(t, 0) + 1
        posts_view.append({
            "url": p.get("canonical_path") or f"/en/blog/{p.get('slug')}",
            "title": p.get("title") or "",
            "description": p.get("description") or "",
            "kicker": p.get("kicker") or "",
            "tags": p.get("tags") or [],
            "meta": f"{_format_date(lang, p.get('date_published') or '')} · {p.get('reading_time') or ''}".strip(" ·"),
        })

    top_tags = [k for k, _ in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))][:8]

    ctx = {
        "lang": lang,
        "site_name": SITE_NAME,
        "seo_title": "Blog | Ecuaciones a Word",
        "description": "Practical guides to convert LaTeX/AI content to Word with native (OMML) editable equations.",
        "keywords": ["LaTeX to Word", "OMML", "Word equations", "ChatGPT", "Pandoc"],
        "canonical_url": canonical_url,
        "alternates": [
            {"hreflang": "en", "href": canonical_url},
            {"hreflang": "es", "href": other_url},
            {"hreflang": "x-default", "href": other_url},
        ],
        "og_type": "website",
        "og_title": "Blog | Ecuaciones a Word",
        "og_description": "Practical guides for converting LaTeX equations to native Word (OMML) cleanly and reliably.",
        "og_image": _abs_url("/static/og-image.svg"),
        "schema_json": _build_schema_index(lang, canonical_url),
        "converter_href": "/en",
        "blog_index_href": "/en/blog",
        "nav_converter": "Converter",
        "nav_blog": "Blog",
        "lang_switch_href": "/blog",
        "lang_switch_label": "ES",
        "h1": "Blog",
        "intro": "Practical guides to export LaTeX/AI equations to Word as native editable OMML equations.",
        "index_cta_primary": "Open converter",
        "search_label": "Search articles",
        "search_placeholder": "Search by topic, tool or issue (e.g., pandoc, overleaf, OMML, ChatGPT)…",
        "filter_label": "Filter by tag",
        "filter_all": "All",
        "top_tags": top_tags,
        "featured_title": "Articles",
        "posts": posts_view,
        "year": datetime.now().year,
    }
    return HTMLResponse(_render_template("blog_index.html", ctx))


# Redirects legacy numeric
@app.get("/blog2")
async def blog2_redirect() -> RedirectResponse:
    return RedirectResponse(url="/blog/convertir-documento-latex-word", status_code=301)


@app.get("/blog3")
async def blog3_redirect() -> RedirectResponse:
    return RedirectResponse(url="/blog/ia-chatgpt-a-word-ejercicios", status_code=301)


@app.get("/blog4")
async def blog4_redirect() -> RedirectResponse:
    return RedirectResponse(url="/blog/pegar-latex-en-word-alt-eq", status_code=301)


@app.get("/blog5")
async def blog5_redirect() -> RedirectResponse:
    return RedirectResponse(url="/blog/que-es-omml-ecuaciones-word", status_code=301)


@app.get("/blog6")
async def blog6_redirect() -> RedirectResponse:
    return RedirectResponse(url="/blog/markdown-con-latex-a-word-docx", status_code=301)


def _resolve_blog_slug(lang: str, slug: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Return (redirect_url, post). redirect_url is set for alias slugs."""
    alias_map = BLOG_ALIASES.get(lang, {})
    if slug in alias_map:
        canonical_slug = alias_map[slug]
        post = BLOG_POSTS.get(lang, {}).get(canonical_slug)
        if post and post.get("canonical_path"):
            return post["canonical_path"], None
        # fallback
        prefix = "/blog/" if lang == "es" else "/en/blog/"
        return f"{prefix}{canonical_slug}", None

    post = BLOG_POSTS.get(lang, {}).get(slug)
    return None, post


@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post_es(slug: str) -> HTMLResponse:
    lang = "es"
    redirect_url, post = _resolve_blog_slug(lang, slug)
    if redirect_url:
        return RedirectResponse(url=redirect_url, status_code=301)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")

    body_html = _read_blog_body(lang, post["slug"])
    if not body_html.strip():
        raise HTTPException(status_code=404, detail="Blog post body not found")

    canonical_url = _abs_url(post.get("canonical_path") or f"/blog/{post['slug']}")
    translation_slug = (post.get("translation_slug") or "").strip()
    has_translation = bool(translation_slug and translation_slug in BLOG_POSTS.get("en", {}))

    alternates = [{"hreflang": "es", "href": canonical_url}]
    lang_switch_href = "/en/blog"
    if has_translation:
        other = BLOG_POSTS["en"][translation_slug]
        other_url = _abs_url(other.get("canonical_path") or f"/en/blog/{translation_slug}")
        alternates.append({"hreflang": "en", "href": other_url})
        alternates.append({"hreflang": "x-default", "href": canonical_url})
        lang_switch_href = other.get("canonical_path") or f"/en/blog/{translation_slug}"
    else:
        alternates.append({"hreflang": "en", "href": _abs_url("/en/blog")})
        alternates.append({"hreflang": "x-default", "href": canonical_url})

    date_pub = post.get("date_published") or ""
    date_mod = post.get("date_modified") or ""
    meta_line = f"Publicado {_format_date(lang, date_pub)}"
    if post.get("reading_time"):
        meta_line += f" · {post['reading_time']}"
    if date_mod and date_mod != date_pub:
        meta_line += f" · Actualizado {_format_date(lang, date_mod)}"

    ctx = {
        "lang": lang,
        "site_name": SITE_NAME,
        "seo_title": post.get("seo_title") or (post.get("title") or ""),
        "description": post.get("description") or "",
        "keywords": post.get("keywords") or [],
        "canonical_url": canonical_url,
        "alternates": alternates,
        "og_type": "article",
        "og_title": post.get("title") or "",
        "og_description": post.get("description") or "",
        "og_image": _abs_url("/static/og-image.svg"),
        "schema_json": _build_schema_article(post, canonical_url),
        "converter_href": "/",
        "blog_index_href": "/blog",
        "nav_converter": "Conversor",
        "nav_blog": "Blog",
        "lang_switch_href": lang_switch_href,
        "lang_switch_label": "EN",
        "kicker": post.get("kicker") or "",
        "title": post.get("title") or "",
        "meta_line": meta_line,
        "tags": post.get("tags") or [],
        "intro_html": post.get("intro_html") or [],
        "body_html": body_html,
        "cta_strong": "¿Necesitas convertir un .docx o .txt con fórmulas LaTeX?",
        "cta_text": "Usa el conversor y descarga un Word con ecuaciones nativas (OMML).",
        "cta_primary": "Abrir conversor",
        "cta_secondary": "Ver más artículos",
        "year": datetime.now().year,
    }
    return HTMLResponse(_render_template("blog_post.html", ctx))


@app.get("/en/blog/{slug}", response_class=HTMLResponse)
async def blog_post_en(slug: str) -> HTMLResponse:
    lang = "en"
    redirect_url, post = _resolve_blog_slug(lang, slug)
    if redirect_url:
        return RedirectResponse(url=redirect_url, status_code=301)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")

    body_html = _read_blog_body(lang, post["slug"])
    if not body_html.strip():
        raise HTTPException(status_code=404, detail="Blog post body not found")

    canonical_url = _abs_url(post.get("canonical_path") or f"/en/blog/{post['slug']}")
    translation_slug = (post.get("translation_slug") or "").strip()
    has_translation = bool(translation_slug and translation_slug in BLOG_POSTS.get("es", {}))

    alternates = [{"hreflang": "en", "href": canonical_url}]
    lang_switch_href = "/blog"
    if has_translation:
        other = BLOG_POSTS["es"][translation_slug]
        other_url = _abs_url(other.get("canonical_path") or f"/blog/{translation_slug}")
        alternates.append({"hreflang": "es", "href": other_url})
        alternates.append({"hreflang": "x-default", "href": other_url})
        lang_switch_href = other.get("canonical_path") or f"/blog/{translation_slug}"
    else:
        alternates.append({"hreflang": "es", "href": _abs_url("/blog")})
        alternates.append({"hreflang": "x-default", "href": _abs_url("/blog")})

    date_pub = post.get("date_published") or ""
    date_mod = post.get("date_modified") or ""
    meta_line = f"Published {_format_date(lang, date_pub)}"
    if post.get("reading_time"):
        meta_line += f" · {post['reading_time']}"
    if date_mod and date_mod != date_pub:
        meta_line += f" · Updated {_format_date(lang, date_mod)}"

    ctx = {
        "lang": lang,
        "site_name": SITE_NAME,
        "seo_title": post.get("seo_title") or (post.get("title") or ""),
        "description": post.get("description") or "",
        "keywords": post.get("keywords") or [],
        "canonical_url": canonical_url,
        "alternates": alternates,
        "og_type": "article",
        "og_title": post.get("title") or "",
        "og_description": post.get("description") or "",
        "og_image": _abs_url("/static/og-image.svg"),
        "schema_json": _build_schema_article(post, canonical_url),
        "converter_href": "/en",
        "blog_index_href": "/en/blog",
        "nav_converter": "Converter",
        "nav_blog": "Blog",
        "lang_switch_href": lang_switch_href,
        "lang_switch_label": "ES",
        "kicker": post.get("kicker") or "",
        "title": post.get("title") or "",
        "meta_line": meta_line,
        "tags": post.get("tags") or [],
        "intro_html": post.get("intro_html") or [],
        "body_html": body_html,
        "cta_strong": "Need to convert a .docx or .txt containing LaTeX?",
        "cta_text": "Use the converter and download a Word file with native editable OMML equations.",
        "cta_primary": "Open converter",
        "cta_secondary": "More articles",
        "year": datetime.now().year,
    }
    return HTMLResponse(_render_template("blog_post.html", ctx))


@app.get("/robots.txt")
async def robots_txt() -> Response:
    default = "User-agent: *\nAllow: /\nSitemap: https://www.ecuacionesaword.com/sitemap.xml\n"
    path = os.path.join(BASE_DIR, "robots.txt")
    content = _read_text_file(path, default=default)
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml")
async def sitemap_xml() -> Response:
    # Generado siempre en XML válido (no dependes del fichero)
    content = generate_sitemap_xml()
    return Response(content=content, media_type="application/xml")


@app.get("/healthz")
async def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok")


# ================================================================
# Convert endpoint
# ================================================================
def _extract_text_lines_from_docx(file_bytes: bytes) -> List[str]:
    doc = Document(io.BytesIO(file_bytes))
    lines: List[str] = []
    for p in doc.paragraphs:
        # Mantener líneas aunque sean vacías para separar bloques
        lines.append(p.text if p.text is not None else "")
    return lines


def _extract_text_lines_from_txt(file_bytes: bytes) -> List[str]:
    text = file_bytes.decode("utf-8", errors="replace")
    return text.splitlines()


@app.post("/convert")
async def convert(file: UploadFile = File(...)) -> StreamingResponse:
    filename = (file.filename or "").lower().strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")

    if filename.endswith(".docx"):
        paragraph_texts = _extract_text_lines_from_docx(content)
    elif filename.endswith(".txt"):
        paragraph_texts = _extract_text_lines_from_txt(content)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use .docx or .txt")

    cleaned = prettify_paragraphs(paragraph_texts)
    out_doc = build_document_from_paragraphs(cleaned)

    out = io.BytesIO()
    out_doc.save(out)
    out.seek(0)

    download_name = "ecuaciones-a-word.docx"
    headers = {
        "Content-Disposition": f'attachment; filename="{download_name}"',
        "Cache-Control": "no-store",
    }

    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


# ================================================================
# 404 handler (HTML en vez de JSON)
# ================================================================
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        is_en = str(request.url.path).startswith("/en")
        if is_en:
            html = f"""
            <h1>404 · Page not found</h1>
            <p>The URL <code>{request.url.path}</code> does not exist.</p>
            <p><a href="/en">Go to the converter</a> · <a href="/en/blog">Read the guides</a></p>
            """
        else:
            html = f"""
            <h1>404 · Página no encontrada</h1>
            <p>No existe la URL <code>{request.url.path}</code>.</p>
            <p><a href="/">Ir al conversor</a> · <a href="/blog">Ver las guías</a></p>
            """
        return HTMLResponse(html, status_code=404)

    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)

