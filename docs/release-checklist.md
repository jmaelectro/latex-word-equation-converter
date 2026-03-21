# Release Checklist

1. Update `CHANGELOG.md`.
2. Run local checks:
   - `python -m py_compile main.py`
   - `python -m unittest discover -s tests -p "test_*.py"`
3. Verify key URLs:
   - `/`
   - `/en`
   - `/blog`
   - `/en/blog`
   - `/robots.txt`
   - `/sitemap.xml`
4. Confirm canonical and hreflang tags in ES/EN pages.
5. Create tag:
   - `git tag vX.Y.Z`
   - `git push origin vX.Y.Z`
