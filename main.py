from __future__ import annotations

import io
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
    RedirectResponse,
)
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request

import math2docx


# ================================================================
# Configuración básica de FastAPI
# ================================================================

app = FastAPI(
    title="LaTeX → Word Equations Converter",
    description=(
        "Convierte fórmulas LaTeX simples en ecuaciones nativas de Word (OMML) "
        "dentro de un .docx."
    ),
)


# Orígenes CORS
# - En producción, puedes sobreescribirlos con la variable de entorno ALLOWED_ORIGINS
#   (lista separada por comas). Ejemplo:
#     ALLOWED_ORIGINS="https://www.ecuacionesaword.com,https://tu-staging.onrender.com"

def _parse_allowed_origins(value: str):
    return [o.strip() for o in value.split(',') if o.strip()]


def get_allowed_origins():
    env_val = os.getenv('ALLOWED_ORIGINS', '').strip()
    if env_val:
        return _parse_allowed_origins(env_val)

    # Valores por defecto (dev + dominio principal)
    return [
        'https://www.ecuacionesaword.com',
        'http://localhost:8000',
        'http://127.0.0.1:8000',
    ]


ALLOWED_ORIGINS = get_allowed_origins()


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=800)

logger = logging.getLogger("ecuacionesaword")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

Segment = Tuple[str, str]  # ("text" | "inline" | "display", contenido)
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
USE_EXERCISE_TWEAKS = True  # activa/desactiva reglas específicas q1..q4, etc.

# ================================================================
# 1. Normalización y "prettify"
# ================================================================


def normalize_math_text(text: str) -> str:
    """
    Pequeñas correcciones de notación:
    - q1(x,y,z) -> q_1(x,y,z)
    - D1 -> D_1, ..., D4 -> D_4
    - x2 -> x^2, y3 -> y^3, z4 -> z^4 (solo exponentes 2,3,4)
    """
    t = text

    # q1(x,y,z) -> q_1(x,y,z)
    t = re.sub(r"q([1-4])\s*\(", r"q_\1(", t)

    # D1 -> D_1, etc.
    t = re.sub(r"\bD([1-4])\b", r"D_\1", t)

    # x2 -> x^2, etc.
    for var in ("x", "y", "z"):
        for exp in ("2", "3", "4"):
            t = re.sub(rf"{var}{exp}\b", rf"{var}^{exp}", t)

    return t


def _prettify_paragraphs_for_exercise(paragraph_texts: List[str]) -> List[str]:
    """
    Versión con reglas específicas de tu ejercicio q1..q4, D1..D4, Sylvester, etc.
    Si el texto no coincide con ningún patrón especial, se deja tal cual
    (salvo la normalización de notación).
    """
    out: List[str] = []

    for text in paragraph_texts:
        s = normalize_math_text(text)
        stripped = s.strip()

        # 0) Eliminamos párrafos completamente vacíos
        if stripped == "":
            continue

        # 0-bis) Limpiamos "actividad2grupal"
        if stripped.lower() == "actividad2grupal":
            out.append("Actividad 2 (trabajo grupal)")
            continue

        # 1) Párrafo largo con q1, q2, q3, q4 todos seguidos
        if all(
            sym in stripped
            for sym in ["q_1(x,y,z)", "q_2(x,y,z)", "q_3(x,y,z)", "q_4(x,y,z)"]
        ):
            out.append("$$ q_1(x,y,z) = 2x^2 + 2y^2 + 2z^2 + 2xy + 2xz $$")
            out.append("$$ q_2(x,y,z) = x^2 - y^2 + z^2 + 2xy $$")
            out.append("$$ q_3(x,y,z) = 2x^2 - y^2 + 2z^2 + 4xy - 4yz $$")
            out.append("$$ q_4(x,y,z) = 4x^2 + 2y^2 + z^2 + 2yz $$")
            continue

        # 2) Frase de "garantizar beneficios"
        if stripped.startswith("Interpretamos que") and "garantizar beneficios" in stripped:
            out.append(
                "Interpretamos que “garantizar beneficios” significa que el beneficio "
                "$q(x,y,z)$ sea positivo para todo $(x,y,z)\\neq(0,0,0)$, es decir, "
                "que la forma cuadrática sea definida positiva."
            )
            continue

        # 3) q(x) = x^T A x, con x=(x,y,z)^T
        if (
            "Escribimos cada forma como q(x)=xT" in stripped
            or "Escribimos cada forma como q(x)=xTA" in stripped
            or "Escribimos cada forma como q(x)=xTA x(\\mathbf x)" in stripped
            or (
                "Escribimos cada forma como q(x)=xTAx(\\mathbf x)=\\mathbf x^T A\\mathbf x"
                in stripped
            )
        ):
            out.append(
                "Escribimos cada forma como $q(\\mathbf x) = \\mathbf x^T A\\, \\mathbf x$, "
                "con $\\mathbf x = (x,y,z)^T$."
            )
            continue

        # 4) Término cruzado 2x_i y_j, a_ij = a_ji = 1
        if "coeficiente del término cruzado" in stripped:
            out.append(
                "Recordando que el coeficiente del término cruzado $2x_i y_j$ se reparte como "
                "$a_{ij}=a_{ji}=1$:"
            )
            continue

        # 5) Formas q1..q4 con texto raro (q1q_1q1, etc.)
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

        # 6) Texto del criterio de Sylvester
        if "Criterio de Sylvester" in stripped:
            out.append("2. Criterio de Sylvester")
            continue
        if "Una matriz simétrica" in stripped and "definida positiva" in stripped:
            out.append(
                "Una matriz simétrica $A$ es definida positiva si todos sus "
                "menores principales líderes son positivos:"
            )
            continue

        # 7) Línea compacta D1>0, D2>0, D3>0 -> bloque aligned
        if "D_1>0" in stripped and "D_2>0" in stripped and "D_3>0" in stripped:
            out.append(
                "\\begin{aligned}\n"
                "D_1 &> 0,\\\\\n"
                "D_2 &> 0,\\\\\n"
                "D_3 &> 0.\n"
                "\\end{aligned}"
            )
            continue

        # 7-bis) Párrafos con varios D_i encadenados
        d_terms = list(re.finditer(r"D_[1-4][^D]*", stripped))
        if len(d_terms) >= 2:
            for m in d_terms:
                term = m.group(0).strip().strip(",")
                if term:
                    out.append(f"$$ {term} $$")
            continue

        # 8) Conclusiones A1, A4 definidas positivas
        if "A1A_1A1" in stripped or "A1A1" in stripped:
            out.append("⇒ $A_1$ es definida positiva ⇒ $q_1$ definida positiva.")
            continue
        if "A4A_4A4" in stripped or "A4A4" in stripped:
            out.append("⇒ $A_4$ es definida positiva ⇒ $q_4$ definida positiva.")
            continue

        # 9) Determinantes de A2 y A3
        if "detA2" in stripped or "det A_2" in stripped:
            out.append("$$ \\det A_2 = -2 < 0 $$")
            continue
        if "detA3" in stripped or "det A_3" in stripped:
            out.append("$$ \\det A_3 = -20 < 0 $$")
            continue

        # 10) Conclusión sobre q3 indefinida
        if "q3q_3q3" in stripped and "indefinida" in stripped:
            out.append("⇒ $q_3$ también es indefinida.")
            continue

        # 11) Por defecto: dejamos el párrafo tal cual (ya normalizado)
        out.append(stripped)

    return out


def prettify_paragraphs(paragraph_texts: List[str]) -> List[str]:
    """
    Punto de entrada único para limpiar / normalizar texto antes de construir
    el documento final.

    - Siempre hace normalización genérica (notación, espacios, vacíos).
    - Opcionalmente aplica las reglas específicas del ejercicio.
    """
    # Limpieza genérica
    generic: List[str] = []
    for text in paragraph_texts:
        s = normalize_math_text(text)
        if s.strip():
            generic.append(s.strip())

    if not USE_EXERCISE_TWEAKS:
        return generic

    # Comportamiento específico de tu ejercicio q1..q4
    return _prettify_paragraphs_for_exercise(generic)


# ================================================================
# 2. Utilidades de párrafo y parsing LaTeX
# ================================================================


def new_paragraph(doc: Document, align: Optional[Any] = None):
    """
    Crea un párrafo con formato compacto:
    - espacio antes = 0
    - espacio después = 0
    - interlineado sencillo
    """
    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    fmt.line_spacing = 1.0
    if align is not None:
        p.alignment = align
    return p


def add_math_safe(paragraph, latex: str) -> None:
    """Llama a math2docx.add_math; si falla, deja el texto LaTeX tal cual."""
    try:
        math2docx.add_math(paragraph, latex)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallo convirtiendo LaTeX a ecuación Word: %s", exc)
        paragraph.add_run(latex)


def parse_math_segments(text: str) -> List[Segment]:
    """
    Detecta $...$, $$...$$ y \\[...\\] en UNA línea y devuelve segmentos.
    tipo ∈ {"text", "inline", "display"}.
    """
    segments: List[Segment] = []
    buf: List[str] = []

    def flush_text() -> None:
        if buf:
            segments.append(("text", "".join(buf)))
            buf.clear()

    i = 0
    n = len(text)

    while i < n:
        # Display $$ ... $$ en la MISMA línea
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

        # Display \[ ... \] en la MISMA línea
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

        # Inline $ ... $
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
    """
    Divide una línea en descriptores:
    - {"type": "inline", "chunks": [("text", ...), ("inline", ...), ...]}
    - {"type": "display", "latex": "..."}
    """
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


# ================================================================
# 3. Troceo genérico de ecuaciones largas
# ================================================================


def split_long_latex_equation(latex: str, max_len: int = 120) -> List[str]:
    """
    Heurística para partir ecuaciones largas en varias más cortas,
    para que Word tenga más margen de colocarlas en distintas líneas/páginas.
    """
    latex = latex.strip()
    if not latex:
        return []

    if len(latex) <= max_len:
        return [latex]

    # 1) Si ya hay saltos de línea LaTeX, lo más natural es respetarlos
    if "\\\\" in latex:
        parts = [p.strip() for p in latex.split("\\\\") if p.strip()]
        return parts

    # 2) Intentar partir por '='
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

    # 3) Intentar partir por comas
    if "," in latex:
        tokens = [t.strip() for t in latex.split(",")]
        eqs: List[str] = []
        current = ""
        for tok in tokens:
            candidate = (current + ", " if current else "") + tok
            if len(candidate) > max_len and current:
                eqs.append(current)
                current = tok
            else:
                current = candidate
        if current:
            eqs.append(current)
        return eqs

    # 4) Último recurso: trocear por longitud fija
    return [latex[i : i + max_len].strip() for i in range(0, len(latex), max_len)]


# ================================================================
# 4. Bloques aligned (criterio de Sylvester, etc.)
# ================================================================


def add_aligned_block(doc: Document, aligned_block: str) -> None:
    """
    Convierte un entorno \\begin{aligned}...\\end{aligned} en varias ecuaciones,
    centradas, una debajo de otra.
    """
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


# ================================================================
# 5. Construcción del documento
# ================================================================


def build_document_from_paragraphs(paragraph_texts: List[str]) -> Document:
    """
    Recorre todos los párrafos de texto (ya limpios) y construye el nuevo
    Document con ecuaciones de Word.
    """
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

        # ------------------ Bloque aligned multi-línea ------------------
        if in_aligned_block:
            aligned_lines.append(text)
            if r"\end{aligned}" in text:
                aligned_block = "\n".join(aligned_lines)
                add_aligned_block(out_doc, aligned_block)
                in_aligned_block = False
                aligned_lines = []
            continue

        if r"\begin{aligned}" in stripped:
            # Si begin y end están en la misma línea:
            if r"\end{aligned}" in stripped:
                add_aligned_block(out_doc, stripped)
            else:
                in_aligned_block = True
                aligned_lines = [stripped]
            continue

        # --------------- Bloques display multi-línea $$ / \[ -----------
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

        # --------------- Caso especial: párrafo con matriz --------------
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

        # ---------------------- Procesado normal -------------------------
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

    # Cierre de bloque display si el doc termina dentro de uno
    if in_display_block and display_lines:
        latex = "\n".join(display_lines).strip()
        for part in split_long_latex_equation(latex):
            p = new_paragraph(out_doc, WD_ALIGN_PARAGRAPH.CENTER)
            add_math_safe(p, part)

    # Cierre de bloque aligned si, por error, no se cerró
    if in_aligned_block and aligned_lines:
        aligned_block = "\n".join(aligned_lines)
        add_aligned_block(out_doc, aligned_block)

    return out_doc


# ================================================================
# 6. Lógica de conversión compartida (/convert y /api/v1/convert)
# ================================================================


async def _convert_document_impl(uploaded_file: UploadFile) -> StreamingResponse:
    """
    Lógica principal de conversión: compartida por /convert y /api/v1/convert.
    """
    if not uploaded_file.filename:
        raise HTTPException(status_code=400, detail="El archivo debe tener nombre.")

    filename = uploaded_file.filename
    base_name, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext not in (".txt", ".docx"):
        raise HTTPException(
            status_code=400,
            detail="Tipo de archivo no soportado. Usa un .txt o .docx.",
        )

    file_bytes = await uploaded_file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                "El archivo es demasiado grande. "
                "Prueba a dividir el documento en partes más pequeñas."
            ),
        )

    try:
        # 1) Extraemos párrafos del archivo original
        if ext == ".txt":
            text = file_bytes.decode("utf-8", errors="ignore")
            paragraph_texts = text.splitlines()
        else:
            source_stream = io.BytesIO(file_bytes)
            source_doc = Document(source_stream)
            paragraph_texts = [p.text for p in source_doc.paragraphs]

        # 2) Los limpiamos / normalizamos
        pretty_paragraphs = prettify_paragraphs(paragraph_texts)

        # 3) Construimos el nuevo documento con ecuaciones de Word
        out_doc = build_document_from_paragraphs(pretty_paragraphs)

        # 4) Guardamos resultado en memoria
        output_stream = io.BytesIO()
        out_doc.save(output_stream)
        output_stream.seek(0)

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error procesando el documento: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=(
                "Ha ocurrido un error procesando el documento. "
                "Prueba con un archivo más sencillo o contacta conmigo."
            ),
        ) from exc

    out_filename = f"{base_name}_ecuaciones.docx"
    headers = {
        "Content-Disposition": f'attachment; filename="{out_filename}"',
    }

    return StreamingResponse(
        output_stream,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers=headers,
    )


@app.post("/convert")
async def convert_document(file: UploadFile = File(...)) -> StreamingResponse:
    """
    Endpoint principal usado por la web. Mantiene la ruta /convert existente.
    """
    return await _convert_document_impl(file)


@app.post("/api/v1/convert")
async def convert_document_v1(file: UploadFile = File(...)) -> StreamingResponse:
    """
    Versión versionada del endpoint de conversión, para uso futuro o integraciones.
    """
    return await _convert_document_impl(file)


@app.get("/health")
@app.get("/healthz")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


# ================================================================
# 7. Servir HTML estático y ficheros auxiliares
#    "/", "/blog", "/blog2", "/blog/{slug}", robots.txt, sitemap.xml
# ================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Servir ficheros estáticos (favicon, OpenGraph, manifest, etc.)
_static_dir = os.path.join(BASE_DIR, "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


BLOG_SLUGS_ES: Dict[str, str] = {
    # URL "bonitas" para las entradas del blog (ES)
    "pasar-ecuaciones-chatgpt-word": "blog.html",
    "convertir-documento-latex-word": "blog2.html",
    "ia-chatgpt-a-word-ejercicios": "blog3.html",
    "pegar-latex-editor-ecuaciones-word": "blog4.html",
    "que-es-omml-ecuaciones-word": "blog5.html",
    "markdown-con-latex-a-word-docx": "blog6.html",
}

BLOG_SLUGS_EN: Dict[str, str] = {
    # Pretty URLs for the blog (EN)
    "copy-chatgpt-equations-to-word": "blog-en-1.html",
    "convert-latex-document-to-word": "blog-en-2.html",
    "use-ai-to-solve-exercises-and-export-to-word": "blog-en-3.html",
    "paste-latex-into-word-equation-editor": "blog-en-4.html",
    "what-is-omml-word-equations": "blog-en-5.html",
    "markdown-latex-to-word-docx": "blog-en-6.html",
}


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


@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    """Devuelve la página principal (index.html)."""
    try:
        return HTMLResponse(read_html_file("index.html"))
    except FileNotFoundError:
        return HTMLResponse("<h1>No se encuentra index.html</h1>", status_code=404)



@app.get("/en", response_class=HTMLResponse)
async def home_en() -> HTMLResponse:
    """Serve the English homepage (index-en.html)."""
    try:
        return HTMLResponse(read_html_file("index-en.html"))
    except FileNotFoundError:
        return HTMLResponse("<h1>index-en.html not found</h1>", status_code=404)


@app.get("/en/blog", response_class=HTMLResponse)
async def blog_en() -> HTMLResponse:
    """Serve the English blog index (blog-index-en.html)."""
    try:
        return HTMLResponse(read_html_file("blog-index-en.html"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="English blog index not found.")


@app.get("/en/blog/{slug}", response_class=HTMLResponse)
async def blog_entry_en(slug: str) -> HTMLResponse:
    """Serve an English blog post by slug."""
    filename = BLOG_SLUGS_EN.get(slug)
    if not filename:
        raise HTTPException(status_code=404, detail="Blog post not found.")
    try:
        return HTMLResponse(read_html_file(filename))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Blog post file not found.")

@app.get("/blog", response_class=HTMLResponse)
async def blog() -> HTMLResponse:
    """Devuelve el índice del blog (blog-index.html)."""
    try:
        return HTMLResponse(read_html_file("blog-index.html"))
    except FileNotFoundError:
        return HTMLResponse("<h1>No se encuentra blog.html</h1>", status_code=404)


@app.get("/blog2")
async def blog2_redirect() -> RedirectResponse:
    """Redirige a la URL canónica del artículo (SEO: evitar contenido duplicado)."""
    return RedirectResponse(url="/blog/convertir-documento-latex-word", status_code=301)


@app.get("/blog3")
async def blog3_redirect() -> RedirectResponse:
    """Redirige a la URL canónica del artículo (SEO: evitar enlaces rotos/antiguos)."""
    return RedirectResponse(url="/blog/ia-chatgpt-a-word-ejercicios", status_code=301)



@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_with_slug(slug: str) -> HTMLResponse:
    """
    Rutas tipo /blog/<slug> para las entradas del blog.

    Ejemplos:
      - /blog/pasar-ecuaciones-chatgpt-word
      - /blog/convertir-documento-latex-word
      - /blog/ia-chatgpt-a-word-ejercicios
    """
    filename = BLOG_SLUGS_ES.get(slug)
    if not filename:
        # Devolvemos 404 "normal", que será gestionado por el handler custom.
        raise HTTPException(status_code=404, detail="Entrada de blog no encontrada.")

    try:
        return HTMLResponse(read_html_file(filename))
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Plantilla de blog no encontrada.",
        )


ROBOTS_FALLBACK = """User-agent: *
Allow: /
# No tiene sentido que los bots prueben estos endpoints de API
Disallow: /convert
Disallow: /api/v1/convert
Disallow: /health
Disallow: /healthz

Sitemap: https://www.ecuacionesaword.com/sitemap.xml
"""

SITEMAP_FALLBACK = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.ecuacionesaword.com/</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/blog</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/en</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/en/blog</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.75</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/en/blog/copy-chatgpt-equations-to-word</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.65</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/en/blog/convert-latex-document-to-word</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.65</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/en/blog/use-ai-to-solve-exercises-and-export-to-word</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/en/blog/paste-latex-into-word-equation-editor</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/en/blog/what-is-omml-word-equations</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.55</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/en/blog/markdown-latex-to-word-docx</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.55</priority>
  </url>

  <url>
    <loc>https://www.ecuacionesaword.com/blog/pasar-ecuaciones-chatgpt-word</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/blog/convertir-documento-latex-word</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.75</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/blog/ia-chatgpt-a-word-ejercicios</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/blog/pegar-latex-editor-ecuaciones-word</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.65</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/blog/que-es-omml-ecuaciones-word</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
  <url>
    <loc>https://www.ecuacionesaword.com/blog/markdown-con-latex-a-word-docx</loc>
    <lastmod>2025-12-13</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
</urlset>
"""


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt() -> PlainTextResponse:
    """
    Sirve robots.txt desde archivo si existe; si no, usa un contenido por defecto.
    """
    path = os.path.join(BASE_DIR, "robots.txt")
    content = _read_text_file(path, default=ROBOTS_FALLBACK)
    return PlainTextResponse(content, media_type="text/plain")


@app.get("/sitemap.xml")
async def sitemap_xml() -> Response:
    """
    Sirve sitemap.xml desde archivo si existe; si no, usa un contenido por defecto.
    """
    path = os.path.join(BASE_DIR, "sitemap.xml")
    content = _read_text_file(path, default=SITEMAP_FALLBACK)
    return Response(content=content, media_type="application/xml")


# ================================================================
# 8. Manejador de errores 404 con HTML (en vez de JSON)
# ================================================================


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(
    request: Request, exc: StarletteHTTPException
):
    """
    Devuelve una página HTML amigable para los 404 en lugar de JSON.
    Para otros códigos, devuelve un texto plano sencillo.
    """
    if exc.status_code == 404:
        is_en = str(request.url.path).startswith("/en")
        if is_en:
            html = f"""
            <html>
              <head>
                <title>Page not found</title>
                <meta charset="utf-8" />
              </head>
              <body style="font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 3rem;">
                <h1>404 · Page not found</h1>
                <p>The URL <code>{request.url.path}</code> does not exist.</p>
                <p>
                  Go back to the <a href="/en">equation converter</a>
                  or read the <a href="/en/blog">blog guides</a>.
                </p>
              </body>
            </html>
            """
        else:
            html = f"""
            <html>
              <head>
                <title>Página no encontrada</title>
                <meta charset="utf-8" />
              </head>
              <body style="font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 3rem;">
                <h1>404 · Página no encontrada</h1>
                <p>No existe la URL <code>{request.url.path}</code>.</p>
                <p>
                  Puedes volver al <a href="/">conversor de ecuaciones</a>
                  o leer las <a href="/blog">guías del blog</a>.
                </p>
              </body>
            </html>
            """
        return HTMLResponse(html, status_code=404)

    # Para otros códigos mantenemos una respuesta sencilla
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)
