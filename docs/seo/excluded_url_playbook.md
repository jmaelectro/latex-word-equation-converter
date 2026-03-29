# Playbook de URLs excluidas

## A. Pagina con redireccion
- Sacar la URL redirigida del sitemap.
- Sustituir por URL final 200 canonica.
- Corregir enlaces internos para apuntar a destino final.

## B. Bloqueado por otro 4xx
- Localizar URL y validar si debe existir.
- Si debe existir: reparar para devolver 200.
- Si no debe existir: eliminar del sitemap y del enlazado interno.

## C. Descubierta: actualmente sin indexar
- Aumentar enlaces internos contextuales desde cluster relevante.
- Enlazar desde home/blog/landing segun intencion.
- Mantener en sitemap solo si aporta valor unico.

## D. Rastreada: actualmente sin indexar
- Reescribir contenido con enfoque diferencial.
- Reducir solapamiento con URLs internas.
- Definir una sola keyword principal y una intencion por URL.

## Checklist tecnico por URL prioritaria
- 200 OK.
- Sin `noindex`.
- Sin bloqueo en `robots.txt`.
- Canonical autorreferente.
- Sin redireccion intermedia.
- En sitemap solo si indexable.
- Al menos 2-3 enlaces internos relevantes.
