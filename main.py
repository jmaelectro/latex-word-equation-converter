from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, PlainTextResponse
from docx import Document
import math2docx
import io
import os
import re
from typing import List, Tuple

# ================================================================
# Configuración básica de FastAPI
# ================================================================

app = FastAPI(
    title="Ecuaciones a Word",
    description=(
        "Convierte documentos .txt/.docx con fórmulas en LaTeX "
        "en ecuaciones nativas de Word (OMML) dentro de un .docx."
    ),
)

# CORS para poder llamar desde cualquier origen (útil si sirves frontend aparte)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Segment = Tuple[str, str]  # (tipo, contenido) tipo ∈ {"text", "inline", "display"}

# ================================================================
# Utilidades de parsing LaTeX
# ================================================================

LATEX_PATTERN = re.compile(
    r"(\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\])",
    re.DOTALL,
)


def split_latex_segments(text: str) -> List[Segment]:
    """
    Divide un texto en segmentos:
    - ("text", texto normal)
    - ("inline", contenido LaTeX entre $...$)
    - ("display", contenido LaTeX entre $$...$$ o \[...\]
    """
    segments: List[Segment] = []
    pos = 0

    for match in LATEX_PATTERN.finditer(text):
        start, end = match.span()
        if start > pos:
            segments.append(("text", text[pos:start]))

        raw = match.group(0)
        if raw.startswith("$$"):
            latex = raw[2:-2].strip()
            segments.append(("display", latex))
        elif raw.startswith("\\["):
            latex = raw[2:-2].strip()
            segments.append(("display", latex))
        else:
            # $...$
            latex = raw[1:-1].strip()
            segments.append(("inline", latex))

        pos = end

    if pos < len(text):
        segments.append(("text", text[pos:]))

    return segments


# ================================================================
# Funciones de conversión a DOCX
# ================================================================


def build_docx_from_text(text: str) -> Document:
    """
    Crea un Document de python-docx a partir de texto plano
    con LaTeX delimitado por $...$, $$...$$ o \[...\].
    """
    document = Document()

    lines = text.splitlines() or [text]
    for line in lines:
        segments = split_latex_segments(line)
        paragraph = document.add_paragraph()
        for kind, content in segments:
            if not content:
                continue
            if kind == "text":
                paragraph.add_run(content)
            else:
                # Para fórmulas de bloque, podemos forzar un párrafo nuevo
                if kind == "display" and paragraph.text.strip():
                    paragraph = document.add_paragraph()
                math2docx.add_math(paragraph, content)

    return document


def build_docx_from_docx_bytes(data: bytes) -> Document:
    """
    Lee un .docx de entrada, detecta LaTeX en el texto y crea
    un nuevo Document con ecuaciones nativas.
    """
    source = Document(io.BytesIO(data))
    document = Document()

    if not source.paragraphs:
        # Documento vacío: devolvemos documento vacío
        return document

    for para in source.paragraphs:
        text = para.text or ""
        # Si no hay patrones LaTeX, copiamos el párrafo tal cual
        if not LATEX_PATTERN.search(text):
            document.add_paragraph(text)
            continue

        segments = split_latex_segments(text)
        paragraph = document.add_paragraph()
        for kind, content in segments:
            if not content:
                continue
            if kind == "text":
                paragraph.add_run(content)
            else:
                if kind == "display" and paragraph.text.strip():
                    paragraph = document.add_paragraph()
                math2docx.add_math(paragraph, content)

    return document


# ================================================================
# Rutas auxiliares (HTML, robots, sitemap, health)
# ================================================================


def _read_text_file(path: str) -> str:
    if not os.path.exists(path):
        raise HTTPException(status_code=500, detail=f"Fichero {path} no encontrado en el servidor.")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Página principal con el formulario de subida."""
    html = _read_text_file("index.html")
    return HTMLResponse(html)


@app.get("/blog", response_class=HTMLResponse)
async def blog() -> HTMLResponse:
    """Primer artículo del blog."""
    html = _read_text_file("blog.html")
    return HTMLResponse(html)


@app.get("/blog2", response_class=HTMLResponse)
async def blog2() -> HTMLResponse:
    """Segundo artículo del blog."""
    html = _read_text_file("blog2.html")
    return HTMLResponse(html)


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt() -> PlainTextResponse:
    text = _read_text_file("robots.txt")
    return PlainTextResponse(text)


@app.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap_xml() -> PlainTextResponse:
    xml = _read_text_file("sitemap.xml")
    return PlainTextResponse(xml, media_type="application/xml")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ================================================================
# Endpoint principal de conversión
# ================================================================


@app.post("/convert")
async def convert_document(file: UploadFile = File(...)) -> StreamingResponse:
    """
    Recibe un .txt o .docx con fórmulas LaTeX y devuelve
    un .docx con ecuaciones nativas de Word.
    """
    filename = file.filename or "documento"
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext not in {".txt", ".docx"}:
        raise HTTPException(
            status_code=400,
            detail="Solo se aceptan archivos .txt o .docx.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    try:
        if ext == ".txt":
            text = data.decode("utf-8", errors="ignore")
            output_doc = build_docx_from_text(text)
        else:
            output_doc = build_docx_from_docx_bytes(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Error al convertir el documento: {exc}",
        ) from exc

    buffer = io.BytesIO()
    output_doc.save(buffer)
    buffer.seek(0)

    base_name = re.sub(r"\.(txt|docx)$", "", filename, flags=re.IGNORECASE)
    output_filename = f"{base_name or 'documento'}_ecuaciones.docx"

    headers = {
        "Content-Disposition": f'attachment; filename="{output_filename}"'
    }

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )
