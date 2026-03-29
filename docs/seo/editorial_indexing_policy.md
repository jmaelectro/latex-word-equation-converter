# Politica editorial de indexacion

## Reglas obligatorias antes de publicar
- No publicar una URL sin intencion principal unica.
- No publicar una URL si el contenido es insuficiente o thin.
- No crear dos URLs para la misma keyword + misma intencion.
- No incluir en sitemap paginas con redireccion, 4xx, noindex o valor SEO dudoso.

## Reglas de sitemap
- Solo URLs 200 finales (sin redireccion).
- Solo URLs indexables en idiomas primarios (es/en).
- Excluir posts marcados como noindex por canibalizacion.
- Revisar cada semana que `generate_sitemap_xml()` siga cumpliendo las reglas.

## Reglas de arquitectura interna
- Cada articulo debe enlazar:
  - 1 landing transaccional.
  - 2 articulos relacionados.
  - 1 pagina pilar.
- Cada landing debe enlazar:
  - home (pagina pilar).
  - guia principal del caso de uso.
  - al menos 2 guias relacionadas.

## Revision trimestral (cada 2-3 meses)
1. Exportar consultas por URL desde Search Console.
2. Detectar canibalizacion por query compartida.
3. Decidir fusion, noindex o reposicionamiento.
4. Actualizar `docs/seo/keyword_intent_matrix.csv` y `docs/seo/url_audit_sheet.csv`.
