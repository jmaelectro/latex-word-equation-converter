# Contributing

Thanks for contributing to `latex-word-equation-converter`.

## Development setup
1. Create a virtual environment.
2. Install dependencies:
   - `python -m pip install -r requirements.txt`
3. Run locally:
   - `uvicorn main:app --reload`

## Branch and commit style
- Create focused branches from `main`.
- Use clear commit messages:
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `chore: ...`

## Pull request checklist
- Keep scope focused.
- Explain problem, solution, and validation.
- Ensure CI is green.
- Update docs if behavior changed.

## Coding guidelines
- Prefer small, testable helper functions.
- Keep user-facing copy clear in ES and EN.
- Preserve canonical/hreflang consistency on SEO routes.
