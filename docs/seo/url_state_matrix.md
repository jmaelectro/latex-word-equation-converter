# URL State Matrix (Post Cleanup)

Legacy root HTML copies are no longer part of the live source tree. Historical URLs are kept only as 301 redirects to their canonical 200 destinations.

## Indexable (index, follow, in sitemap)
- `https://www.ecuacionesaword.com/`
- `https://www.ecuacionesaword.com/en`
- `https://www.ecuacionesaword.com/blog`
- `https://www.ecuacionesaword.com/en/blog`
- `https://www.ecuacionesaword.com/soluciones`
- `https://www.ecuacionesaword.com/en/solutions`
- ES/EN transactional landings under:
  - `/soluciones/{slug}`
  - `/en/solutions/{slug}`
- ES/EN blog posts only when:
  - canonical path is valid (`/blog/...` or `/en/blog/...`)
  - post is primary-language and indexable by policy
  - not listed in `NON_INDEXABLE_BLOG_SLUGS`

## Noindex (public but intentionally non-indexable)
- `/healthz` (via `X-Robots-Tag`)

## Excluded from Sitemap
- All non-primary language URLs (`de`, `fr`, `it`, `pt`)
- Blog posts flagged as non-indexable strategy
- Blog posts marked `noindex` in metadata
- Blog URLs with invalid/mismatched canonical paths
- Broken ES/EN alternates without a valid indexable counterpart
- Legal pages and technical endpoints

## Redirected (301)
- Deprecated language versions now consolidated to EN:
  - `/de`, `/fr`, `/it`, `/pt` -> `/en`
  - `/{de|fr|it|pt}/blog` -> `/en/blog`
  - `/{de|fr|it|pt}/blog/{slug}` -> matching `/en/blog/{canonical-slug}` when equivalent exists
  - `/{de|fr|it|pt}/solutions` -> `/en/solutions`
  - `/{de|fr|it|pt}/solutions/{slug}` -> matching `/en/solutions/{slug}` when equivalent exists
  - `/{de|fr|it|pt}/{privacy|terms|contact}` -> `/en/{privacy|terms|contact}`
- Legacy short blog routes:
  - `/blog.html`
  - `/blog2` ... `/blog6`
  - `/blog2.html` ... `/blog6.html`
- Legacy static routes:
  - `/index.html`, `/index-en.html`
  - `/index-de.html`, `/index-fr.html`, `/index-it.html`, `/index-pt.html`
  - `/blog-index.html`, `/blog-index-en.html`
  - old blog html slugs (`/blog-en-*.html`, selected ES legacy html pages)
- Blog alias slugs (via `BLOG_ALIASES`) to canonical blog paths
- `/convert` (GET) -> `/` to avoid crawler 4xx/405 noise

## Kept as Real Error (404)
- Unknown routes with no semantic replacement
- Missing/nonexistent blog posts
- Unmapped legacy paths
