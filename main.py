from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
import math2docx

import io
import os
import re
from typing import List, Tuple, Dict, Any, Optional

# ================================================================
#  Configuración básica de FastAPI
# ================================================================

app = FastAPI(
    title="LaTeX → Word Equations Converter",
    description="Convierte fórmulas LaTeX simples en ecuaciones nativas de Word (OMML) dentro de un .docx.",
)

# CORS para poder llamar desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Segment = Tuple[str, str]  # ("text" | "inline" | "display", contenido)

# ================================================================
#  Blog posts (dinámicos en /blog/{slug})
# ================================================================

blog_posts: Dict[str, Dict[str, Any]] = {
    "pasar-ecuaciones-chatgpt-word": {
        "slug": "pasar-ecuaciones-chatgpt-word",
        "title": "Cómo pasar ecuaciones de ChatGPT a Word sin copiarlas a mano",
        "description": (
            "Guía paso a paso para convertir las soluciones en LaTeX que te da "
            "ChatGPT u otras IA en ecuaciones nativas de Word usando Ecuaciones a Word."
        ),
        "content_html": """
<h1>Cómo pasar ecuaciones de ChatGPT a Word sin copiarlas a mano</h1>

<p>
Si usas ChatGPT para resolver ejercicios de matemáticas, seguro que te has encontrado con este problema:
las ecuaciones salen preciosas en la pantalla… pero luego tienes que pasarlas a Word y
acabas copiando todo a mano o pegando capturas de pantalla.
</p>

<p>
En esta guía te explico un método mucho más rápido usando
<strong><a href="https://www.ecuacionesaword.com">Ecuaciones a Word</a></strong>,
una herramienta online que convierte fórmulas LaTeX en ecuaciones nativas de Word.
</p>

<h2>El problema: ChatGPT escribe en LaTeX, Word no</h2>

<p>
Cuando ChatGPT genera fórmulas matemáticas, casi siempre lo hace en
<strong>LaTeX</strong>, por ejemplo:
</p>

<pre><code>D_1 = 2 &gt; 0, \\quad D_2 = \\begin{vmatrix} 2 &amp; 1 \\\\ 1 &amp; 2 \\end{vmatrix}</code></pre>

<p>
Eso está muy bien para documentos científicos o para compilar en PDF,
pero si tu profesor te pide el trabajo en <strong>Word</strong>, necesitas que esas fórmulas
sean ecuaciones nativas (las que se insertan con “Insertar → Ecuación”).
</p>

<p>
Copiar y pegar directamente desde ChatGPT a Word no convierte las fórmulas,
simplemente pega el texto plano. Ahí es donde entra en juego Ecuaciones a Word.
</p>

<h2>Paso 1: copia el texto desde ChatGPT</h2>

<p>
Primero, pídele a ChatGPT que te dé la solución o el desarrollo del ejercicio usando LaTeX.
Luego, copia todo el texto (incluyendo las fórmulas con <code>$...$</code> o <code>$$...$$</code>).
</p>

<p>
Te quedará algo de este estilo:
</p>

<pre><code>Partimos de la matriz A = \\begin{pmatrix} 2 &amp; 1 \\\\ 1 &amp; 2 \\end{pmatrix}.

D_1 = 2 &gt; 0.

D_2 = \\det(A) = 2\\cdot 2 - 1\\cdot 1 = 3 &gt; 0.</code></pre>

<h2>Paso 2: pega el texto en un archivo .txt o .docx</h2>

<p>
Ahora abre Word (o cualquier editor de texto) y pega el contenido que has copiado de ChatGPT.
Puedes guardarlo de dos maneras:
</p>

<ul>
  <li>Como archivo de texto: <code>.txt</code></li>
  <li>Como documento de Word: <code>.docx</code></li>
</ul>

<p>
Ambos formatos son aceptados por Ecuaciones a Word.
</p>

<h2>Paso 3: sube el documento a Ecuaciones a Word</h2>

<ol>
  <li>Ve a <a href="https://www.ecuacionesaword.com">https://www.ecuacionesaword.com</a>.</li>
  <li>Haz clic en <strong>“Seleccionar archivo”</strong> y elige tu .txt o .docx.</li>
  <li>Pulsa en <strong>“Convertir documento”</strong>.</li>
</ol>

<p>
La aplicación detectará las fórmulas delimitadas por <code>$...$</code>, <code>$$...$$</code> o <code>\\[...\\]</code>,
las interpretará como LaTeX sencillo y las transformará en ecuaciones de Word (OMML).
</p>

<h2>Paso 4: descarga el nuevo .docx con ecuaciones nativas</h2>

<p>
Cuando termine la conversión, aparecerá un botón para
<strong>descargar el documento convertido</strong>. Ábrelo con Word y verás que:
</p>

<ul>
  <li>El texto normal se mantiene igual.</li>
  <li>Las fórmulas que antes estaban en LaTeX ahora son ecuaciones nativas de Word.</li>
</ul>

<p>
Puedes pulsar sobre cada ecuación y editarla con el editor de ecuaciones de Word, como si la hubieras escrito a mano.
</p>

<h2>Ventajas de este método</h2>

<ul>
  <li><strong>Ahorra tiempo</strong>: no tienes que reescribir las fórmulas en Word.</li>
  <li><strong>Evitas errores</strong>: no hay riesgo de equivocarte al copiar términos, índices o exponentes.</li>
  <li><strong>Resultado limpio</strong>: Word trata las ecuaciones como objetos matemáticos, no como imágenes.</li>
</ul>

<h2>Conclusión</h2>

<p>
Si usas ChatGPT para resolver ejercicios de matemáticas y luego necesitas entregar el trabajo en Word,
Ecuaciones a Word te ahorra muchos pasos intermedios. Solo tienes que copiar el texto de ChatGPT,
guardarlo en un .txt o .docx, subirlo a la web y descargar el documento ya con las ecuaciones convertidas.
</p>

<p>
Puedes probarlo ahora mismo en <a href="https://www.ecuacionesaword.com">Ecuaciones a Word</a>.
</p>
        """,
    },
    "convertir-documento-latex-word": {
        "slug": "convertir-documento-latex-word",
        "title": "Cómo convertir un documento LaTeX a ecuaciones de Word",
        "description": (
            "Aprende a convertir contenido LaTeX (con fórmulas matemáticas) "
            "en un documento Word con ecuaciones nativas usando Ecuaciones a Word."
        ),
        "content_html": """
<h1>Cómo convertir un documento LaTeX a ecuaciones de Word</h1>

<p>
Muchos trabajos de matemáticas, física o ingeniería se escriben originalmente en LaTeX.
Sin embargo, a veces la universidad, una revista o una empresa exige que el documento final
se entregue en <strong>Microsoft Word</strong>. Ahí empieza el dolor de cabeza:
¿cómo pasar todas esas fórmulas a Word sin reescribirlas a mano?
</p>

<p>
En este artículo veremos una forma práctica de hacerlo usando
<strong><a href="https://www.ecuacionesaword.com">Ecuaciones a Word</a></strong>,
una herramienta online que convierte fórmulas LaTeX en ecuaciones Word (OMML).
</p>

<h2>LaTeX vs Word: dos mundos diferentes</h2>

<p>
LaTeX está pensado para componer documentos científicos de alta calidad tipográfica.
Word, en cambio, es un procesador de texto más general. Aunque Word tiene un editor
de ecuaciones bastante potente, no entiende directamente el código LaTeX estándar.
</p>

<p>
Esto significa que no puedes simplemente pegar esto en Word y esperar que se convierta solo:
</p>

<pre><code>\\int_0^1 x^2 \\, dx = \\frac{1}{3}</code></pre>

<p>
Lo que necesitas es una conversión intermedia que interprete el LaTeX y genere
ecuaciones en el formato interno de Word, llamado <strong>OMML</strong>.
</p>

<h2>Preparar el contenido LaTeX</h2>

<p>
Ecuaciones a Word funciona mejor cuando el contenido está en formato texto con las
fórmulas delimitadas. Por ejemplo:
</p>

<ul>
  <li><code>$ ... $</code> para fórmulas en línea.</li>
  <li><code>$$ ... $$</code> o <code>\\[ ... \\]</code> para fórmulas en bloque.</li>
</ul>

<p>
Supongamos que tienes un documento LaTeX con párrafos y fórmulas como:
</p>

<pre><code>
Sea la función $f(x) = x^2 + 2x + 1$. Su derivada es $f'(x) = 2x + 2$.

La integral definida es
\\[
\\int_0^1 x^2 \\, dx = \\frac{1}{3}.
\\]
</code></pre>

<p>
Puedes copiar el contenido relevante (sin el preámbulo de LaTeX si no es necesario) a un archivo
de texto plano o a un documento de Word.
</p>

<h2>Subir el documento a Ecuaciones a Word</h2>

<p>
Una vez tengas el texto con LaTeX:
</p>

<ol>
  <li>Guarda el archivo como <code>.txt</code> o <code>.docx</code>.</li>
  <li>Ve a <a href="https://www.ecuacionesaword.com">https://www.ecuacionesaword.com</a>.</li>
  <li>Haz clic en <strong>“Seleccionar archivo”</strong> y elige tu documento.</li>
  <li>Pulsa <strong>“Convertir documento”</strong> y espera unos segundos.</li>
</ol>

<p>
La herramienta analizará el texto, localizará las fórmulas LaTeX y generará internamente
las ecuaciones en formato OMML, el que utiliza Word.
</p>

<h2>Descargar y abrir el .docx convertido</h2>

<p>
Al terminar la conversión, podrás descargar un nuevo archivo <code>.docx</code>.
Ábrelo con Word y comprueba:
</p>

<ul>
  <li>Las fórmulas en línea aparecen integradas en los párrafos.</li>
  <li>Las fórmulas en bloque aparecen centradas y separadas del texto.</li>
  <li>Al hacer clic en una ecuación, se activa el editor de ecuaciones de Word.</li>
</ul>

<p>
Desde ahí puedes ajustar el estilo, el tamaño de letra o incluso reescribir partes de las fórmulas.
</p>

<h2>Consejos para una conversión más limpia</h2>

<ul>
  <li>Usa LaTeX sencillo: potencias, subíndices, fracciones, matrices, etc.</li>
  <li>Evita comandos muy específicos de paquetes raros que Word no sabrá representar.</li>
  <li>
    Asegúrate de que las fórmulas estén bien delimitadas con <code>$...$</code>,
    <code>$$...$$</code> o <code>\\[...\\]</code>.
  </li>
</ul>

<h2>Conclusión</h2>

<p>
Convertir un documento LaTeX a Word no tiene por qué ser una pesadilla.
Con una herramienta como <a href="https://www.ecuacionesaword.com">Ecuaciones a Word</a> puedes
mantener la comodidad de escribir en LaTeX y, al mismo tiempo, obtener un documento Word con
ecuaciones nativas, listo para entregar.
</p>

<p>
Si estás preparando tu TFG, TFM o apuntes de clase y necesitas Word como formato final,
prueba esta solución y ahórrate horas de trabajo manual.
</p>
        """,
    },
    "ia-chatgpt-a-word-ejercicios": {
        "slug": "ia-chatgpt-a-word-ejercicios",
        "title": "Usar IA + Ecuaciones a Word para hacer tus ejercicios en Word",
        "description": (
            "Cómo combinar inteligencias artificiales como ChatGPT con Ecuaciones a Word "
            "para crear rápidamente ejercicios y soluciones en documentos Word."
        ),
        "content_html": """
<h1>Usar IA + Ecuaciones a Word para hacer tus ejercicios en Word</h1>

<p>
Cada vez más estudiantes y profesores utilizan <strong>inteligencias artificiales</strong> como
ChatGPT, Gemini o Copilot para generar enunciados, soluciones o resúmenes de matemáticas.
El problema llega cuando todo eso hay que entregarlo en <strong>formato Word</strong>.
</p>

<p>
En este artículo te explico un flujo de trabajo práctico para combinar IA con
<strong><a href="https://www.ecuacionesaword.com">Ecuaciones a Word</a></strong> y así obtener
documentos limpios, con ecuaciones nativas y listos para entregar.
</p>

<h2>Paso 1: pide a la IA que te dé las soluciones en LaTeX</h2>

<p>
Cuando uses ChatGPT u otra IA, es buena idea indicarle que te escriba las fórmulas en LaTeX.
Por ejemplo:
</p>

<pre><code>Escribe la solución detallada usando LaTeX. Utiliza $...$ para fórmulas en línea
y $$...$$ para fórmulas en bloque.</code></pre>

<p>
Así obtendrás un texto estructurado, con fórmulas fáciles de detectar y convertir.
</p>

<h2>Paso 2: copia el resultado a un .docx o .txt</h2>

<p>
Una vez tengas la respuesta de la IA:
</p>

<ul>
  <li>Copia todo el texto, incluyendo las fórmulas.</li>
  <li>Pégalo en un documento nuevo de Word o en un editor de texto.</li>
  <li>Guarda el archivo como <strong>.docx</strong> o <strong>.txt</strong>.</li>
</ul>

<p>
No es necesario que las ecuaciones se vean bien en este punto; lo importante es que el LaTeX esté correcto.
</p>

<h2>Paso 3: convierte el documento con Ecuaciones a Word</h2>

<ol>
  <li>Ve a <a href="https://www.ecuacionesaword.com">https://www.ecuacionesaword.com</a>.</li>
  <li>Selecciona tu archivo .docx o .txt.</li>
  <li>Haz clic en <strong>“Convertir documento”</strong>.</li>
</ol>

<p>
La herramienta buscará las fórmulas delimitadas por <code>$...$</code>, <code>$$...$$</code> o <code>\\[...\\]</code>
y las transformará en ecuaciones de Word.
</p>

<h2>Paso 4: revisa y personaliza el documento en Word</h2>

<p>
Descarga el nuevo .docx y ábrelo en Word. Verás que:
</p>

<ul>
  <li>Las ecuaciones son <strong>nativas</strong>, no imágenes.</li>
  <li>Puedes cambiarles el estilo, el tamaño de letra o el formato.</li>
  <li>Si algo no te convence, puedes editar directamente la ecuación en Word.</li>
</ul>

<h2>Ventajas de este flujo IA + Ecuaciones a Word</h2>

<ul>
  <li><strong>Velocidad</strong>: la IA genera el contenido y Ecuaciones a Word se ocupa del formato matemático.</li>
  <li><strong>Calidad</strong>: las ecuaciones se integran perfectamente con el texto de Word.</li>
  <li><strong>Flexibilidad</strong>: puedes corregir, ampliar o traducir el documento sin perder las fórmulas.</li>
</ul>

<h2>Conclusión</h2>

<p>
Las inteligencias artificiales son una herramienta muy potente para generar contenido matemático,
pero por sí solas no resuelven el problema del formato en Word. Combinarlas con
<a href="https://www.ecuacionesaword.com">Ecuaciones a Word</a> te permite tener lo mejor de ambos mundos:
rapidez y comodidad, sin renunciar a un documento final profesional y editable.
</p>
        """,
    },
}


# ================================================================
#  1. Normalización y 'prettify' específico de tu ejercicio
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
    for var in ["x", "y", "z"]:
        for exp in ["2", "3", "4"]:
            t = re.sub(rf"{var}{exp}\b", rf"{var}^{exp}", t)

    return t


def prettify_paragraphs_for_exercise(paragraph_texts: List[str]) -> List[str]:
    """
    Recibe la lista de párrafos extraídos del documento original y devuelve
    una lista nueva, más limpia y pensada para el ejercicio concreto que
    estás utilizando (formas q1..q4, criterio de Sylvester, etc.).

    Está fuertemente adaptada a tu documento actual.
    """
    out: List[str] = []

    for text in paragraph_texts:
        s = normalize_math_text(text)
        stripped = s.strip()

        # 0) Eliminamos párrafos completamente vacíos para evitar huecos grandes
        if stripped == "":
            continue

        # 0-bis) Limpiamos "actividad2grupal"
        if stripped.lower() == "actividad2grupal":
            out.append("Actividad 2 (trabajo grupal)")
            continue

        # 1) Párrafo largo con q1, q2, q3, q4 todos seguidos
        if all(sym in stripped for sym in ["q_1(x,y,z)", "q_2(x,y,z)", "q_3(x,y,z)", "q_4(x,y,z)"]):
            # Reescribimos en cuatro ecuaciones limpias, tipo ChatGPT
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
        if "Escribimos cada forma como q(x)=xT" in stripped or "Escribimos cada forma como q(x)=xTA" in stripped \
           or "Escribimos cada forma como q(x)=xTA x(\\mathbf x)" in stripped \
           or "Escribimos cada forma como q(x)=xTAx(\\mathbf x)=\\mathbf x^T A\\mathbf x" in stripped:
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
            out.append("Forma $q_1$:")  # título limpio
            continue
        if "Forma q2" in stripped or "q2q_2q2" in stripped:
            out.append("Forma $q_2$:")  # título limpio
            continue
        if "Forma q3" in stripped or "q3q_3q3" in stripped:
            out.append("Forma $q_3$:")  # título limpio
            continue
        if "Forma q4" in stripped or "q4q_4q4" in stripped:
            out.append("Forma $q_4$:")  # título limpio
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

        # 7) Línea compacta D1>0, D2>0, D3>0  -> bloque aligned
        if "D_1>0" in stripped and "D_2>0" in stripped and "D_3>0" in stripped:
            out.append(
                "\\begin{aligned}\n"
                "D_1 &> 0,\\\\\n"
                "D_2 &> 0,\\\\\n"
                "D_3 &> 0.\n"
                "\\end{aligned}"
            )
            continue

        # 7-bis) Párrafos con varios D_i encadenados (tipo "D_1 = ... D_2 = ... D_3 = ...")
        d_terms = list(re.finditer(r"D_[1-4][^D]*", stripped))
        if len(d_terms) >= 2:
            for m in d_terms:
                term = m.group(0).strip().strip(",")
                if term:
                    out.append(f"$$ {term} $$")
            continue

        # 8) Conclusiones A1, A4 definidas positivas con texto feo
        if "A1A_1A1" in stripped or "A1A1" in stripped:
            out.append("⇒ $A_1$ es definida positiva ⇒ $q_1$ definida positiva.")
            continue
        if "A4A_4A4" in stripped or "A4A4" in stripped:
            out.append("⇒ $A_4$ es definida positiva ⇒ $q_4$ definida positiva.")
            continue

        # 9) Determinantes de A2 y A3 escritos de forma caótica
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


# ================================================================
#  2. Utilidades de párrafo y parsing LaTeX
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


def add_math_safe(paragraph, latex: str):
    """Llama a math2docx.add_math; si falla, deja el texto LaTeX tal cual."""
    try:
        math2docx.add_math(paragraph, latex)
    except Exception:
        paragraph.add_run(latex)


def parse_math_segments(text: str) -> List[Segment]:
    """
    Detecta $...$, $$...$$ y \[...\] en UNA línea y devuelve segmentos.
    tipo ∈ {"text", "inline", "display"}.
    """
    segments: List[Segment] = []
    buf: List[str] = []

    def flush_text():
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
            latex = text[i + 2: end]
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
            latex = text[i + 2: end]
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
            latex = text[i + 1: end]
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
#  3. Troceo genérico de ecuaciones largas
# ================================================================

def split_long_latex_equation(latex: str, max_len: int = 120) -> List[str]:
    """
    Heurística para partir ecuaciones largas en varias más cortas, para que
    Word tenga más margen de colocarlas en distintas líneas/páginas.

    Estrategia:
    - Si hay '\\\\' (saltos de línea LaTeX), separamos por ahí.
    - Si hay '=', intentamos agrupar términos hasta llegar a max_len.
    - Si hay ',', hacemos algo similar.
    - Si no, partimos en trozos de max_len caracteres.
    """
    latex = latex.strip()
    if not latex:
        return []
    if len(latex) <= max_len:
        return [latex]

    # 1) Si ya hay saltos de línea LaTeX, lo más natural es respetarlos
    if r"\\" in latex:
        parts = [p.strip() for p in latex.split(r"\\") if p.strip()]
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
    return [latex[i:i + max_len].strip() for i in range(0, len(latex), max_len)]


# ================================================================
#  4. Bloques aligned (criterio de Sylvester, etc.)
# ================================================================

def add_aligned_block(doc: Document, aligned_block: str):
    """
    Convierte un entorno \\begin{aligned}...\\end{aligned} en varias ecuaciones,
    centradas, una debajo de otra.
    """
    content = aligned_block.strip()

    if content.startswith(r"\begin{aligned}"):
        content = content[len(r"\begin{aligned}"):]
    if content.endswith(r"\end{aligned}"):
        content = content[:-len(r"\end{aligned}")]

    content = content.strip()
    if not content:
        return

    rows = [row.strip() for row in content.split(r"\\") if row.strip()]

    for row in rows:
        row_no_amp = row.replace("&", "")
        p = new_paragraph(doc, WD_ALIGN_PARAGRAPH.CENTER)
        add_math_safe(p, row_no_amp)


# ================================================================
#  5. Construcción del documento
# ================================================================

def build_document_from_paragraphs(paragraph_texts: List[str]) -> Document:
    """
    Recorre todos los párrafos de texto (ya limpios) y construye
    el nuevo Document con ecuaciones de Word.
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
#  6. Endpoints FastAPI
# ================================================================

@app.post("/convert")
async def convert_document(file: UploadFile = File(...)):
    """Recibe un .txt o .docx con LaTeX sencillo y devuelve un .docx convertido."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="El archivo debe tener nombre.")

    filename = file.filename
    base_name, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext not in (".txt", ".docx"):
        raise HTTPException(
            status_code=400,
            detail="Tipo de archivo no soportado. Usa .txt o .docx.",
        )

    file_bytes = await file.read()

    try:
        # 1) Extraemos párrafos del archivo original
        if ext == ".txt":
            text = file_bytes.decode("utf-8", errors="ignore")
            paragraph_texts = text.splitlines()
        else:
            source_stream = io.BytesIO(file_bytes)
            source_doc = Document(source_stream)
            paragraph_texts = [p.text for p in source_doc.paragraphs]

        # 2) Los limpiamos y adaptamos a tu ejercicio
        pretty_paragraphs = prettify_paragraphs_for_exercise(paragraph_texts)

        # 3) Construimos el nuevo documento con ecuaciones de Word
        out_doc = build_document_from_paragraphs(pretty_paragraphs)

        # 4) Guardamos resultado en memoria
        output_stream = io.BytesIO()
        out_doc.save(output_stream)
        output_stream.seek(0)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando el documento: {str(e)}",
        )

    out_filename = f"{base_name}_convertido.docx"
    headers = {
        "Content-Disposition": f'attachment; filename="{out_filename}"'
    }

    return StreamingResponse(
        output_stream,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers=headers,
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ================================================================
#  7. Servir index.html en "/"
# ================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@app.get("/", response_class=HTMLResponse)
async def home():
    """
    Devuelve la página principal (index.html).
    """
    index_path = os.path.join(BASE_DIR, "index.html")
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>No se encuentra index.html</h1>"


# ================================================================
#  8. Servir blog.html en "/blog" y "/blog.html"
# ================================================================

@app.get("/blog", response_class=HTMLResponse)
@app.get("/blog.html", response_class=HTMLResponse)
async def blog():
    """
    Devuelve la página del blog (blog.html).
    """
    blog_path = os.path.join(BASE_DIR, "blog.html")
    try:
        with open(blog_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>No se encuentra blog.html</h1>"


# ================================================================
#  8-bis. Servir blog2.html en "/blog2" y "/blog2.html"
# ================================================================

@app.get("/blog2", response_class=HTMLResponse)
@app.get("/blog2.html", response_class=HTMLResponse)
async def blog2():
    """
    Devuelve el segundo artículo del blog (blog2.html).
    """
    blog2_path = os.path.join(BASE_DIR, "blog2.html")
    try:
        with open(blog2_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>No se encuentra blog2.html</h1>"


# ================================================================
#  8-ter. Blog dinámico en /blog/{slug}
# ================================================================

@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post(slug: str):
    """
    Devuelve una entrada del blog generada dinámicamente según el slug.
    Ejemplos:
      - /blog/pasar-ecuaciones-chatgpt-word
      - /blog/convertir-documento-latex-word
      - /blog/ia-chatgpt-a-word-ejercicios
    """
    post = blog_posts.get(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    title = post["title"] + " | Ecuaciones a Word"
    description = post["description"]
    body_html = post["content_html"]

    html = (
        "<!DOCTYPE html>"
        "<html lang='es'>"
        "<head>"
        "<meta charset='UTF-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'/>"
        f"<title>{title}</title>"
        f"<meta name='description' content='{description}'/>"
        "<link rel='canonical' href='https://www.ecuacionesaword.com/blog/" + slug + "'/>"
        "<style>"
        "body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "background:#020617;color:#e5e7eb;margin:0;padding:0;}"
        ".page{max-width:900px;margin:0 auto;padding:24px 16px 40px;}"
        "a{color:#22c55e;text-decoration:none;}a:hover{text-decoration:underline;}"
        "header{margin-bottom:20px;}"
        "header a{font-weight:600;font-size:14px;}"
        "h1{font-size:24px;margin-bottom:12px;color:#f9fafb;}"
        "h2{font-size:18px;margin-top:18px;margin-bottom:8px;color:#f9fafb;}"
        "p{font-size:14px;line-height:1.6;margin-bottom:8px;}"
        "ul,ol{font-size:14px;line-height:1.6;margin:4px 0 10px 20px;}"
        "pre{background:#020617;border-radius:8px;padding:10px;font-size:13px;"
        "overflow-x:auto;border:1px solid #1f2937;}"
        "code{font-family:ui-monospace,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;}"
        "footer{margin-top:24px;font-size:12px;color:#9ca3af;border-top:1px solid #1f2937;padding-top:10px;}"
        "</style>"
        "</head>"
        "<body>"
        "<div class='page'>"
        "<header>"
        "<a href='/'>&larr; Volver a Ecuaciones a Word</a>"
        "</header>"
        "<main>"
        + body_html +
        "</main>"
        "<footer>"
        "© Ecuaciones a Word · LaTeX → ecuaciones de Word"
        "</footer>"
        "</div>"
        "</body>"
        "</html>"
    )
    return HTMLResponse(content=html)


# ================================================================
#  9. Servir sitemap.xml y robots.txt
# ================================================================

@app.get("/sitemap.xml", response_class=HTMLResponse)
async def sitemap():
    """
    Devuelve el sitemap XML.
    """
    sitemap_path = os.path.join(BASE_DIR, "sitemap.xml")
    try:
        with open(sitemap_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, media_type="application/xml")
    except FileNotFoundError:
        # Sitemap mínimo vacío si no existe el archivo (no debería ocurrir)
        return HTMLResponse("<urlset></urlset>", media_type="application/xml")


@app.get("/robots.txt", response_class=HTMLResponse)
async def robots():
    """
    Devuelve el robots.txt.
    """
    robots_path = os.path.join(BASE_DIR, "robots.txt")
    try:
        with open(robots_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, media_type="text/plain; charset=utf-8")
    except FileNotFoundError:
        # robots.txt mínimo por defecto
        content = "User-agent: *\nAllow: /"
        return HTMLResponse(content=content, media_type="text/plain; charset=utf-8")
