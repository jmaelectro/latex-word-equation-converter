# URL State Matrix (Post Cleanup)

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
- Non-primary language homes:
  - `/de`, `/fr`, `/it`, `/pt`
- Non-primary blog indexes/posts:
  - `/de/blog...`, `/fr/blog...`, `/it/blog...`, `/pt/blog...`
- Non-primary solutions hubs/landings:
  - `/de/solutions...`, `/fr/solutions...`, `/it/solutions...`, `/pt/solutions...`
- Legal pages in all languages (`/privacy`, `/terms`, `/contact`, and localized variants)
- `/healthz` (via `X-Robots-Tag`)

## Excluded from Sitemap
- All non-primary language URLs (`de`, `fr`, `it`, `pt`)
- Blog posts flagged as non-indexable strategy
- Blog posts marked `noindex` in metadata
- Blog URLs with invalid/mismatched canonical paths
- Broken ES/EN alternates without a valid indexable counterpart
- Legal pages and technical endpoints

## Redirected (301)
- Legacy short blog routes:
  - `/blog2` ... `/blog6`
- Legacy static routes:
  - `/index.html`, `/index-en.html`
  - `/blog-index.html`, `/blog-index-en.html`
  - old blog html slugs (`/blog-en-*.html`, selected ES legacy html pages)
- Blog alias slugs (via `BLOG_ALIASES`) to canonical blog paths
- `/convert` (GET) -> `/` to avoid crawler 4xx/405 noise

## Kept as Real Error (404)
- Unknown routes with no semantic replacement
- Missing/nonexistent blog posts
- Unmapped legacy paths
