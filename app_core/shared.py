from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "Missing dependency 'jinja2'. Install it with: pip install jinja2"
    ) from exc


APP_TITLE = "Ecuaciones a Word (LaTeX â†’ Word OMML)"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_NAME = "Ecuaciones a Word"

logger = logging.getLogger("ecuacionesaword")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

SITE_CANONICAL_ORIGIN = os.getenv("CANONICAL_SITE_ORIGIN", "").strip().rstrip("/")
if not SITE_CANONICAL_ORIGIN:
    _canonical_host_for_urls = os.getenv("CANONICAL_HOST", "").strip()
    _canonical_scheme_for_urls = os.getenv("CANONICAL_SCHEME", "https").strip()
    if _canonical_host_for_urls:
        SITE_CANONICAL_ORIGIN = f"{_canonical_scheme_for_urls}://{_canonical_host_for_urls}"
    else:
        SITE_CANONICAL_ORIGIN = "https://www.ecuacionesaword.com"

BLOG_DATA_PATH = os.path.join(BASE_DIR, "blog_content", "posts.json")
BLOG_POSTS_DIR = os.path.join(BASE_DIR, "blog_content", "posts")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
OG_IMAGE_PATH = (
    "/static/og-image.png"
    if os.path.exists(os.path.join(BASE_DIR, "static", "og-image.png"))
    else "/static/og-image.svg"
)
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID", "G-GS589S9BG4").strip()

JINJA_ENV = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)
JINJA_ENV.globals["GA_MEASUREMENT_ID"] = GA_MEASUREMENT_ID

SUPPORTED_LANGS: Tuple[str, ...] = ("es", "en", "de", "fr", "it", "pt")
PRIMARY_CONTENT_LANGS: Tuple[str, ...] = ("es", "en")
SECONDARY_LANGS: Tuple[str, ...] = tuple(
    lang for lang in SUPPORTED_LANGS if lang not in PRIMARY_CONTENT_LANGS
)
SITEMAP_LANGS: Tuple[str, ...] = PRIMARY_CONTENT_LANGS

LANG_PREFIX: Dict[str, str] = {
    "es": "",
    "en": "/en",
    "de": "/de",
    "fr": "/fr",
    "it": "/it",
    "pt": "/pt",
}


def _mojibake_score(value: str) -> int:
    if not value:
        return 0
    suspect_chars = {"\u00c2", "\u00c3", "\u00e2", "\ufffd"}
    score = sum(ch in suspect_chars for ch in value)
    score += value.count("Ã¢") * 2
    return score


def _decode_mojibake_once(value: str) -> str:
    candidates = [value]
    for source_encoding in ("latin-1", "cp1252"):
        try:
            candidates.append(value.encode(source_encoding).decode("utf-8"))
        except Exception:
            continue
    return min(candidates, key=lambda candidate: (_mojibake_score(candidate), len(candidate)))


def _fix_text_mojibake(text: str) -> str:
    if not text:
        return text

    fixed = text.lstrip("\ufeff")
    original_score = _mojibake_score(fixed)
    candidate = fixed
    for _ in range(4):
        new_candidate = _decode_mojibake_once(candidate)
        if new_candidate == candidate:
            break
        if _mojibake_score(new_candidate) <= _mojibake_score(candidate):
            candidate = new_candidate
            continue
        break
    fixed = candidate

    replacements = {
        "Ã¢â‚¬Â¦": "â€¦",
        "Ã¢â‚¬Å“": "â€œ",
        "Ã¢â‚¬Â": "â€",
        "Ã¢â‚¬Ëœ": "â€˜",
        "Ã¢â‚¬â„¢": "â€™",
        "Ã¢â‚¬â€œ": "â€“",
        "Ã¢â‚¬â€": "â€”",
        "Ã¢â‚¬Â¢": "â€¢",
        "Ã¢â€ â€™": "â†’",
        "Ã¢â€ Â": "â†",
        "Ã¢â€ â€": "â†”",
        "Ã¢â€¡â€™": "â‡’",
        "Ã¢â€¡â€": "â‡”",
        "Ã¢Ë†â€˜": "âˆ‘",
        "Ã¢Ë†Â": "âˆ",
        "Ã¢Ë†Å¡": "âˆš",
        "Ã¢Ë†Å¾": "âˆž",
        "Ã¢Ë†â€š": "âˆ‚",
        "Ã¢Ë†â€¡": "âˆ‡",
        "Ã¢â€°Â¤": "â‰¤",
        "Ã¢â€°Â¥": "â‰¥",
        "Ã¢â€° ": "â‰ ",
        "Ã¢â€°Ë†": "â‰ˆ",
        "Ã‚Â©": "Â©",
        "Ã‚Â·": "Â·",
        "Ã‚Â¿": "Â¿",
        "Ã‚Â¡": "Â¡",
        "Ã‚Âº": "Âº",
        "Ã‚Âª": "Âª",
        "\u00a0": " ",
    }
    for bad, good in replacements.items():
        fixed = fixed.replace(bad, good)

    if _mojibake_score(fixed) > original_score:
        return text
    return fixed


def _deep_fix_mojibake(value: Any) -> Any:
    if isinstance(value, str):
        return _fix_text_mojibake(value)
    if isinstance(value, list):
        return [_deep_fix_mojibake(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_deep_fix_mojibake(v) for v in value)
    if isinstance(value, dict):
        return {k: _deep_fix_mojibake(v) for k, v in value.items()}
    return value


def _read_text_file(path: str, default: Optional[str] = None) -> str:
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            return file_obj.read()
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def render_template(template_name: str, context: Dict[str, Any]) -> str:
    template = JINJA_ENV.get_template(template_name)
    return template.render(**_deep_fix_mojibake(context))


def tracked_site_files() -> List[Path]:
    return [
        Path(__file__),
        Path(BASE_DIR) / "index.html",
        Path(BASE_DIR) / "index-en.html",
        Path(BASE_DIR) / "templates" / "base.html",
        Path(BASE_DIR) / "templates" / "blog_index.html",
        Path(BASE_DIR) / "templates" / "blog_post.html",
        Path(BASE_DIR) / "templates" / "legal_page.html",
        Path(BASE_DIR) / "templates" / "solution_landing.html",
        Path(BASE_DIR) / "templates" / "solutions_hub.html",
        Path(BLOG_DATA_PATH),
    ]
