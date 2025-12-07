import io
import re
from typing import List, Tuple

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from docx import Document
from docx.oxml import parse_xml
from xml.sax.saxutils import escape

app = FastAPI()

# Permitir peticiones desde el mismo origen (y pruebas locales)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Delimitadores de fórmulas LaTeX:
#   $ ... $
#   $$ ... $$
#   \[ ... \]
FORMULA_PATTERN = re.compile(
    r"(\\\[.*?\\\]|\$\$.*?\$\$|\$[^$].*?\$)",
    re.DOTALL,
)


def split_text_and_formulas(text: str) -> Tuple[str, List[str]]:
    """
    Dado un párrafo de texto, devuelve:
      - text_without_formulas: el texto original pero con las fórmulas eliminadas
        (sustituidas por un espacio).
      - formulas: lista con las cadenas LaTeX interiores de cada fórmula detectada.
    """
    formulas: List[str] = []

    def _replacer(match: re.Match) -> str:
        raw = match.group(0)
        inner = raw
        if raw.startswith("$$") and raw.endswith("$$"):
            inner = raw[2:-2]
        elif raw.startswith("$") and raw.endswith("$"):
            inner = raw[1:-1]
        elif raw.startswith(r"\[") and raw.endswith(r"\]"):
            inner = raw[2:-2]
        inner = inner.strip()
        if inner:
            formulas.append(inner)
        # Dejamos un espacio donde estaba la fórmula para no juntar palabras
        return " "

    text_without = FORMULA_PATTERN.sub(_replacer, text)
    return text_without, formulas


def add_equation_paragraph(doc: Document, latex: str) -> None:
    """
    Añade un párrafo de ecuación OMML al documento usando la cadena LaTeX
    como texto lineal dentro del objeto de ecuación.

    No intenta convertir toda la sintaxis LaTeX a estructura 2D perfecta,
    pero sí crea un objeto de ecuación de Word (OMML) que luego se puede
    editar en el propio Word.
    """
    latex = latex.strip()
    if not latex:
        return

    omml_str = f"""
    <m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
                 xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <m:oMath>
        <m:r>
          <w:rPr/>
          <m:t>{escape(latex)}</m:t>
        </m:r>
      </m:oMath>
    </m:oMathPara>
    """
    omml = parse_xml(omml_str)
    body = doc._element.body
    body.append(omml)


def build_converted_document_from_text_lines(lines: List[str]) -> Document:
    """
    Construye un nuevo documento Word a partir de una lista de líneas de texto,
    detectando fórmulas LaTeX y sustituyéndolas por ecuaciones OMML.
    """
    doc = Document()

    for raw_line in lines:
        line = raw_line.rstrip("\n\r")

        if not line.strip():
            # Conservamos líneas en blanco como separación de párrafos
            doc.add_paragraph("")
            continue

        text_without, formulas = split_text_and_formulas(line)

        # Párrafo con el texto (sin las fórmulas originales)
        if text_without.strip():
            doc.add_paragraph(text_without)

        # A continuación, una ecuación por cada fórmula detectada, en orden
        for f in formulas:
            add_equation_paragraph(doc, f)

    return doc


@app.get("/")
def read_root():
    """
    Sirve la página principal (index.html).
    """
    return FileResponse("index.html", media_type="text/html")


@app.get("/blog")
@app.get("/blog.html")
def read_blog():
    """
    Sirve el artículo del blog (blog.html).
    """
    return FileResponse("blog.html", media_type="text/html")


@app.post("/convert")
async def convert_document(file: UploadFile = File(...)):
    """
    Endpoint principal de conversión.

    - Acepta archivos .txt y .docx.
    - Extrae el texto.
    - Detecta fórmulas LaTeX delimitadas por:
        $...$, $$...$$ o \[...\]
    - Crea un nuevo .docx donde:
        - El texto se mantiene (sin las fórmulas originales).
        - Cada fórmula se inserta como ecuación OMML de Word
          en párrafos separados.
    """
    filename = file.filename or "documento"
    name_lower = filename.lower()

    if not (name_lower.endswith(".txt") or name_lower.endswith(".docx")):
        raise HTTPException(
            status_code=400,
            detail="Solo se admiten archivos .txt o .docx.",
        )

    # Leemos el archivo subido
    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error leyendo el archivo subido: {exc}",
        ) from exc

    lines: List[str] = []

    if name_lower.endswith(".txt"):
        # Interpretar como texto plano UTF-8 (ignorando caracteres raros)
        text = content.decode("utf-8", errors="ignore")
        lines = text.splitlines()
    else:
        # .docx: abrir con python-docx y extraer los párrafos como texto
        bio = io.BytesIO(content)
        try:
            original_doc = Document(bio)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"No se ha podido abrir el .docx: {exc}",
            ) from exc

        for para in original_doc.paragraphs:
            lines.append(para.text)

    # Construimos el nuevo documento con las ecuaciones insertadas
    new_doc = build_converted_document_from_text_lines(lines)

    # Guardamos el nuevo .docx en memoria
    output = io.BytesIO()
    new_doc.save(output)
    output.seek(0)

    out_name = filename.rsplit(".", 1)[0] + "_convertido.docx"
    headers = {
        "Content-Disposition": f'attachment; filename="{out_name}"'
    }

    return Response(
        content=output.getvalue(),
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        headers=headers,
    )
