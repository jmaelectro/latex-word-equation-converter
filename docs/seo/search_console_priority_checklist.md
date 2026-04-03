# Checklist final para solicitud de indexación (Search Console)

## Alcance
Solicitar indexación **solo de URLs prioritarias** ya corregidas (200, canónica autorreferente, indexables, enlazadas internamente y presentes en sitemap).

## Pre-check técnico (obligatorio antes de pedir indexación)
- [ ] URL devuelve `200 OK` en inspección en vivo.
- [ ] No tiene `noindex` (meta robots ni cabecera `X-Robots-Tag`).
- [ ] No está bloqueada por `robots.txt`.
- [ ] Canonical autorreferente (sin apuntar a otra URL).
- [ ] No redirige (sin 3xx intermedios).
- [ ] Está incluida en `sitemap.xml` si es indexable.
- [ ] Tiene al menos 2-3 enlaces internos contextuales desde páginas relevantes.
- [ ] Title y H1 únicos para su intención principal.
- [ ] No compite con otra URL interna por la misma query principal.

## Lote 1 (prioridad máxima)
1. `/`
2. `/soluciones/`
3. `/soluciones/chatgpt-a-word/`
4. `/soluciones/gemini-a-word/`
5. `/soluciones/overleaf-a-word/`
6. `/soluciones/pandoc-a-word-omml/`
7. `/soluciones/conversor-omml/`

## Lote 2 (pilares del blog)
1. `/blog/latex-a-word-omml-guia-definitiva/`
2. `/blog/pasar-ecuaciones-chatgpt-word/`
3. `/blog/overleaf-latex-a-word-ecuaciones-editables/`
4. `/blog/pandoc-ecuaciones-word-no-editables-soluciones/`
5. `/blog/que-es-omml-ecuaciones-word/`

## Protocolo de envío en Search Console
1. Inspeccionar cada URL del **Lote 1** y pedir indexación.
2. Esperar 48-72h y revisar cobertura/rastreo.
3. Si no hay incidencias, inspeccionar y pedir indexación del **Lote 2**.
4. No pedir indexación de URLs fusionadas/retiradas (deben quedar en 301 o fuera de sitemap).

## Verificación posterior (7-14 días)
- [ ] Cobertura: sin nuevos estados de “Página con redirección” para URLs en sitemap.
- [ ] Cobertura: sin “Bloqueado por otro 4xx” en URLs prioritarias.
- [ ] Tendencia de “Descubierta: actualmente sin indexar” a la baja en lotes enviados.
- [ ] Tendencia de “Rastreada: actualmente sin indexar” a la baja tras reescritura.
- [ ] Impresiones/clics en URLs prioritarias creciendo en rendimiento.

## No enviar a indexación (por ahora)
- URLs antiguas fusionadas y redirigidas por alias.
- Páginas noindex de idiomas no primarios.
- URLs utilitarias o de baja calidad editorial.
