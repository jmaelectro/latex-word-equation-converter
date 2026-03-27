# Ecuaciones a Word

Pequeña herramienta web (FastAPI + Python) para convertir documentos `.txt` o `.docx` con fórmulas en **LaTeX** en un nuevo `.docx` donde esas fórmulas pasan a ser **ecuaciones nativas de Word (OMML)**.

Flujo típico:

1. IA (ChatGPT, Gemini, Copilot, etc.) genera una solución con fórmulas en LaTeX.
2. Copias ese texto y lo pegas en un `.docx` o `.txt`.
3. Subes el archivo a la web.
4. Descargas un `.docx` con las ecuaciones convertidas a ecuaciones nativas de Word.

## Ejecutar localmente

```bash
pip install -r requirements.txt
uvicorn main:app --reload
