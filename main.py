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
from fastapi.responses import HTMLResponse, StreamingResponse

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

ALLOWED_ORIGINS = [
    "https://www.ecuacionesaword.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

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
    Versión con reglas específicas que usabas para tu ejercicio de q1..q4,
    D1..D4, criterio de Sylvester, etc.

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
        if all(sym in stripped for sym in ["q_1(x,y,z)", "q_2(x,y,z)", "q_3(x,y,z)", "q_4(x,y,z)"]):
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
            or "Escribimos cada forma como q(x)=xTAx(\\mathbf x)=\\mathbf x^T A\\mathbf x" in stripped
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

    # Comportamiento antiguo conservado
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
    Heurística para partir ecuaciones largas en varias más cortas, para que
    Word tenga más margen de colocarlas en distintas líneas/páginas.
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
        eqs = []
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
# 6. Endpoints FastAPI: /convert, /api/v1/convert y /health
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
        # Re-lanzamos tal cual (errores de usuario controlados)
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
# 7. Servir HTML estático: "/", "/blog" y "/blog2"
# ================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def read_html_file(filename: str) -> str:
    path = os.path.join(BASE_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("No se encuentra el archivo HTML: %s", filename)
        raise


@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    """Devuelve la página principal (index.html)."""
    try:
        return HTMLResponse(read_html_file("index.html"))
    except FileNotFoundError:
        return HTMLResponse("<h1>No se encuentra index.html</h1>", status_code=404)


@app.get("/blog", response_class=HTMLResponse)
async def blog() -> HTMLResponse:
    """Devuelve la página de blog principal (blog.html)."""
    try:
        return HTMLResponse(read_html_file("blog.html"))
    except FileNotFoundError:
        return HTMLResponse("<h1>No se encuentra blog.html</h1>", status_code=404)


@app.get("/blog2", response_class=HTMLResponse)
async def blog2() -> HTMLResponse:
    """Devuelve la segunda página de blog (blog2.html)."""
    try:
        return HTMLResponse(read_html_file("blog2.html"))
    except FileNotFoundError:
        return HTMLResponse("<h1>No se encuentra blog2.html</h1>", status_code=404)
