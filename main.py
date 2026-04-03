from __future__ import annotations

import codecs
import io
import ipaddress
import json
import os
import zipfile
from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from urllib.parse import quote

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request

from app_core.shared import APP_TITLE, BASE_DIR
from app_core.converter import (
    CANONICAL_HOST,
    CANONICAL_SCHEME,
    MAX_FILE_SIZE_BYTES,
    MAX_UPLOAD_CONTENT_LENGTH_BYTES,
    CanonicalHostRedirectMiddleware,
    _add_common_headers,
    _fix_text_mojibake,
    _extract_text_lines_from_txt,
    _request_is_https,
    _convert_docx_in_place,
    add_math_safe,
    build_document_from_paragraphs,
    get_allowed_origins,
    normalize_math_text,
    parse_math_segments,
    prettify_paragraphs,
)
import app_core.site as site_module
from app_core.site import (
    BLOG_POSTS,
    blog2_redirect,
    blog3_redirect,
    blog4_redirect,
    blog5_redirect,
    blog6_redirect,
    blog_index_de,
    blog_index_en,
    blog_index_es,
    blog_index_fr,
    blog_index_it,
    blog_index_pt,
    blog_post_de,
    blog_post_en,
    blog_post_es,
    blog_post_fr,
    blog_post_it,
    blog_post_pt,
    contact_de,
    contact_en,
    contact_es,
    contact_fr,
    contact_it,
    contact_pt,
    generate_sitemap_xml,
    healthz,
    home,
    home_de,
    home_en,
    home_fr,
    home_it,
    home_pt,
    legacy_redirects,
    privacy_de,
    privacy_en,
    privacy_es,
    privacy_fr,
    privacy_it,
    privacy_pt,
    read_html_file,
    robots_txt,
    sitemap_xml,
    solution_landing_de,
    solution_landing_en,
    solution_landing_es,
    solution_landing_fr,
    solution_landing_it,
    solution_landing_pt,
    solutions_de,
    solutions_en,
    solutions_es,
    solutions_fr,
    solutions_it,
    solutions_pt,
    terms_de,
    terms_en,
    terms_es,
    terms_fr,
    terms_it,
    terms_pt,
    _render_template,
    _secondary_blog_redirect_target,
    _solution_landing_context,
    _solutions_hub_context,
    _legal_page_context,
)


MAX_DOCX_ENTRY_UNCOMPRESSED_BYTES = 4 * 1024 * 1024
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("CONVERT_RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("CONVERT_RATE_LIMIT_MAX_REQUESTS", "20"))
_RATE_LIMIT_BUCKETS = defaultdict(deque)
_RATE_LIMIT_LOCK = Lock()
_RATE_LIMIT_LAST_SWEEP_AT = 0.0


app = FastAPI(title=APP_TITLE)
site_module.SITEMAP_LANGS = site_module.SUPPORTED_LANGS
site_module.BLOG_TRANSLATION_TO_ES = {
    (post.get("translation_slug") or ""): slug
    for slug, post in BLOG_POSTS.get("es", {}).items()
    if (post.get("translation_slug") or "")
}
site_module._published_home_langs = lambda: site_module.SUPPORTED_LANGS
_original_blog_alternate_paths = site_module._blog_alternate_paths
_original_all_alternates = site_module._all_alternates


def _patched_blog_alternate_paths(lang: str, post: dict):
    paths = _original_blog_alternate_paths(lang, post)
    slug = (post.get("slug") or "").strip()
    if lang == "en" and slug:
        for code in ("de", "fr", "it", "pt"):
            paths.setdefault(code, f"/{code}/blog/{slug}")
    return paths


site_module._blog_alternate_paths = _patched_blog_alternate_paths


def _patched_all_alternates(path_by_lang, default_lang="es", langs=site_module.PRIMARY_CONTENT_LANGS):
    effective_langs = langs
    if langs == site_module.PRIMARY_CONTENT_LANGS and any(
        code in path_by_lang for code in ("de", "fr", "it", "pt")
    ):
        effective_langs = site_module.SUPPORTED_LANGS
    return _original_all_alternates(path_by_lang, default_lang=default_lang, langs=effective_langs)


site_module._all_alternates = _patched_all_alternates

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=800)

if CANONICAL_HOST:
    app.add_middleware(
        CanonicalHostRedirectMiddleware,
        canonical_host=CANONICAL_HOST,
        canonical_scheme=CANONICAL_SCHEME,
    )


@app.middleware("http")
async def add_common_headers_mw(request: Request, call_next):
    if request.url.path == "/convert" and request.method == "POST":
        content_length = request.headers.get("content-length", "").strip()
        if content_length.isdigit() and int(content_length) > MAX_UPLOAD_CONTENT_LENGTH_BYTES:
            return _convert_error_response(413, "file_too_large", "File too large. Maximum size is 5 MB.")
        if not _check_convert_rate_limit(request):
            resp = _convert_error_response(429, "rate_limited", "Too many conversion requests. Please try again shortly.")
            resp.headers["Retry-After"] = str(RATE_LIMIT_WINDOW_SECONDS)
            return resp

    resp = await call_next(request)
    if _request_is_https(request):
        resp.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return _add_common_headers(resp)


_static_dir = os.path.join(BASE_DIR, "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


def _is_private_proxy(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    trusted_ranges = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
    ]
    return any(ip in network for network in trusted_ranges)


def _client_ip(request: Request) -> str:
    client_host = request.client.host if request.client and request.client.host else "unknown"
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and _is_private_proxy(client_host):
        return forwarded.split(",")[0].strip() or client_host
    return client_host


def _check_convert_rate_limit(request: Request) -> bool:
    global _RATE_LIMIT_LAST_SWEEP_AT
    now = monotonic()
    key = f"{_client_ip(request)}:convert"
    with _RATE_LIMIT_LOCK:
        if now - _RATE_LIMIT_LAST_SWEEP_AT > RATE_LIMIT_WINDOW_SECONDS:
            for bucket_key in list(_RATE_LIMIT_BUCKETS):
                bucket = _RATE_LIMIT_BUCKETS[bucket_key]
                while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
                    bucket.popleft()
                if not bucket:
                    _RATE_LIMIT_BUCKETS.pop(bucket_key, None)
            _RATE_LIMIT_LAST_SWEEP_AT = now

        bucket = _RATE_LIMIT_BUCKETS[key]
        while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
            return False
        bucket.append(now)
    return True


def _convert_error_payload(status: int, code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "status": status}}


def _convert_error_response(status: int, code: str, message: str) -> Response:
    response = Response(
        content=json.dumps(_convert_error_payload(status, code, message)),
        status_code=status,
        media_type="application/json",
    )
    response.headers["Cache-Control"] = "no-store"
    return _add_common_headers(response)


def _raise_convert_error(status: int, code: str, message: str):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def _normalize_upload_filename(file: UploadFile) -> str:
    filename = (file.filename or "").strip().lower()
    if not filename:
        _raise_convert_error(400, "missing_file", "No file was uploaded.")
    return filename


def _detect_upload_kind(filename: str) -> str:
    if filename.endswith(".docx"):
        return "docx"
    if filename.endswith(".txt"):
        return "txt"
    _raise_convert_error(400, "unsupported_file_type", "Unsupported file type. Use .docx or .txt.")


def _looks_like_binary_payload(data: bytes) -> bool:
    if not data:
        return False
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return False
    if b"\x00" in data:
        return True
    return False


def _guess_utf16_txt_encoding(data: bytes) -> str | None:
    if len(data) < 2:
        return None
    even_zeros = sum(1 for idx in range(0, len(data), 2) if data[idx] == 0)
    odd_zeros = sum(1 for idx in range(1, len(data), 2) if data[idx] == 0)
    pairs = max(1, len(data) // 2)
    if odd_zeros / pairs > 0.3:
        return "utf-16-le"
    if even_zeros / pairs > 0.3:
        return "utf-16-be"
    return None


def _extract_text_lines_from_txt(file_bytes: bytes):
    if _looks_like_binary_payload(file_bytes):
        raise HTTPException(status_code=400, detail="Invalid .txt file. Upload plain text.")

    encodings = []
    if file_bytes.startswith(codecs.BOM_UTF8):
        encodings.append("utf-8-sig")
    elif file_bytes.startswith(codecs.BOM_UTF16_LE) or file_bytes.startswith(codecs.BOM_UTF16_BE):
        encodings.append("utf-16")
    guessed_utf16 = _guess_utf16_txt_encoding(file_bytes)
    if guessed_utf16:
        encodings.append(guessed_utf16)
    encodings.extend(["utf-8", "cp1252", "latin-1"])

    for encoding in encodings:
        try:
            return file_bytes.decode(encoding).splitlines()
        except UnicodeDecodeError:
            continue

    raise HTTPException(status_code=400, detail="Invalid .txt file. Upload plain text.")


def _validate_docx_file_bytes(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            if "[Content_Types].xml" not in zf.namelist():
                _raise_convert_error(400, "invalid_document", "Invalid .docx file. Upload a valid Word document.")
            for info in zf.infolist():
                if info.file_size > MAX_DOCX_ENTRY_UNCOMPRESSED_BYTES:
                    _raise_convert_error(413, "file_too_large", "The .docx file exceeds safe size limits.")
    except zipfile.BadZipFile:
        _raise_convert_error(400, "invalid_document", "Invalid .docx file. Upload a valid Word document.")


async def convert_get():
    return site_module.RedirectResponse(url="/", status_code=301)


def _download_filename(lang: str) -> str:
    return "equations-to-word.docx" if lang == "en" else "ecuaciones-a-word.docx"


def _convert_upload_to_docx_bytes(upload_kind: str, content: bytes) -> bytes:
    if upload_kind == "docx":
        _validate_docx_file_bytes(content)
        try:
            out_doc = _convert_docx_in_place(content)
        except (zipfile.BadZipFile, PackageNotFoundError):
            _raise_convert_error(400, "invalid_document", "Invalid .docx file. Upload a valid Word document.")
    else:
        lines = _extract_text_lines_from_txt(content)
        out_doc = build_document_from_paragraphs(prettify_paragraphs(lines))

    out = io.BytesIO()
    out_doc.save(out)
    return out.getvalue()


async def convert(file: UploadFile, lang: str = Form("es")):
    lang = "en" if (lang or "").strip().lower() == "en" else "es"
    filename = _normalize_upload_filename(file)
    upload_kind = _detect_upload_kind(filename)
    content = await file.read()
    await file.close()

    if len(content) > MAX_FILE_SIZE_BYTES:
        _raise_convert_error(413, "file_too_large", "File too large. Maximum size is 5 MB.")

    out_bytes = await run_in_threadpool(_convert_upload_to_docx_bytes, upload_kind, content)
    out = io.BytesIO(out_bytes)
    download_name = _download_filename(lang)
    headers = {
        "Content-Disposition": f'attachment; filename="{download_name}"; filename*=UTF-8\'\'{quote(download_name)}',
        "Cache-Control": "no-store",
    }
    return site_module.StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path == "/convert":
        detail = exc.detail
        if isinstance(detail, dict):
            return _convert_error_response(exc.status_code, detail["code"], detail["message"])
        message = str(detail)
        return _convert_error_response(exc.status_code, "conversion_failed", message)
    return await site_module.custom_http_exception_handler(request, exc)


async def custom_validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path == "/convert":
        errors = exc.errors()
        missing_file = any("file" in [str(part) for part in error.get("loc", ())] for error in errors)
        if missing_file:
            return _convert_error_response(400, "missing_file", "No file was uploaded.")
        return _convert_error_response(400, "invalid_request", "Invalid conversion request.")
    return _convert_error_response(400, "invalid_request", "Invalid conversion request.")


async def home_de():
    return HTMLResponse(read_html_file("index-de.html"))


async def home_fr():
    return HTMLResponse(read_html_file("index-fr.html"))


async def home_it():
    return HTMLResponse(read_html_file("index-it.html"))


async def home_pt():
    return HTMLResponse(read_html_file("index-pt.html"))


async def blog_index_de():
    return await site_module.blog_index_de()


async def blog_index_fr():
    return await site_module.blog_index_fr()


async def blog_index_it():
    return await site_module.blog_index_it()


async def blog_index_pt():
    return await site_module.blog_index_pt()


async def privacy_de():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("de", "privacy")))


async def terms_de():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("de", "terms")))


async def contact_de():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("de", "contact")))


async def privacy_fr():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("fr", "privacy")))


async def terms_fr():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("fr", "terms")))


async def contact_fr():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("fr", "contact")))


async def privacy_it():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("it", "privacy")))


async def terms_it():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("it", "terms")))


async def contact_it():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("it", "contact")))


async def privacy_pt():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("pt", "privacy")))


async def terms_pt():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("pt", "terms")))


async def contact_pt():
    return HTMLResponse(_render_template("legal_page.html", _legal_page_context("pt", "contact")))


async def solutions_de():
    return await site_module.solutions_de()


async def solutions_fr():
    return await site_module.solutions_fr()


async def solutions_it():
    return await site_module.solutions_it()


async def solutions_pt():
    return await site_module.solutions_pt()


async def solution_landing_de(slug: str):
    return await site_module.solution_landing_de(slug)


async def solution_landing_fr(slug: str):
    return await site_module.solution_landing_fr(slug)


async def solution_landing_it(slug: str):
    return await site_module.solution_landing_it(slug)


async def solution_landing_pt(slug: str):
    return await site_module.solution_landing_pt(slug)


async def blog_post_de(slug: str):
    return await site_module.blog_post_de(slug)


async def blog_post_fr(slug: str):
    return await site_module.blog_post_fr(slug)


async def blog_post_it(slug: str):
    return await site_module.blog_post_it(slug)


async def blog_post_pt(slug: str):
    return await site_module.blog_post_pt(slug)


def _register_get(path: str, endpoint, response_class=None) -> None:
    kwargs = {"methods": ["GET"]}
    if response_class is not None:
        kwargs["response_class"] = response_class
    app.add_api_route(path, endpoint, **kwargs)


_GET_ROUTES = [
    ("/", home, HTMLResponse),
    ("/en", home_en, HTMLResponse),
    ("/de", home_de, HTMLResponse),
    ("/fr", home_fr, HTMLResponse),
    ("/it", home_it, HTMLResponse),
    ("/pt", home_pt, HTMLResponse),
    ("/soluciones/{slug}", solution_landing_es, HTMLResponse),
    ("/en/solutions/{slug}", solution_landing_en, HTMLResponse),
    ("/de/solutions/{slug}", solution_landing_de, HTMLResponse),
    ("/fr/solutions/{slug}", solution_landing_fr, HTMLResponse),
    ("/it/solutions/{slug}", solution_landing_it, HTMLResponse),
    ("/pt/solutions/{slug}", solution_landing_pt, HTMLResponse),
    ("/soluciones", solutions_es, HTMLResponse),
    ("/en/solutions", solutions_en, HTMLResponse),
    ("/de/solutions", solutions_de, HTMLResponse),
    ("/fr/solutions", solutions_fr, HTMLResponse),
    ("/it/solutions", solutions_it, HTMLResponse),
    ("/pt/solutions", solutions_pt, HTMLResponse),
    ("/privacy", privacy_es, HTMLResponse),
    ("/terms", terms_es, HTMLResponse),
    ("/contact", contact_es, HTMLResponse),
    ("/en/privacy", privacy_en, HTMLResponse),
    ("/en/terms", terms_en, HTMLResponse),
    ("/en/contact", contact_en, HTMLResponse),
    ("/de/privacy", privacy_de, HTMLResponse),
    ("/de/terms", terms_de, HTMLResponse),
    ("/de/contact", contact_de, HTMLResponse),
    ("/fr/privacy", privacy_fr, HTMLResponse),
    ("/fr/terms", terms_fr, HTMLResponse),
    ("/fr/contact", contact_fr, HTMLResponse),
    ("/it/privacy", privacy_it, HTMLResponse),
    ("/it/terms", terms_it, HTMLResponse),
    ("/it/contact", contact_it, HTMLResponse),
    ("/pt/privacy", privacy_pt, HTMLResponse),
    ("/pt/terms", terms_pt, HTMLResponse),
    ("/pt/contact", contact_pt, HTMLResponse),
    ("/blog", blog_index_es, HTMLResponse),
    ("/en/blog", blog_index_en, HTMLResponse),
    ("/de/blog", blog_index_de, HTMLResponse),
    ("/fr/blog", blog_index_fr, HTMLResponse),
    ("/it/blog", blog_index_it, HTMLResponse),
    ("/pt/blog", blog_index_pt, HTMLResponse),
    ("/blog2", blog2_redirect, None),
    ("/blog3", blog3_redirect, None),
    ("/blog4", blog4_redirect, None),
    ("/blog5", blog5_redirect, None),
    ("/blog6", blog6_redirect, None),
    ("/blog/{slug}", blog_post_es, HTMLResponse),
    ("/en/blog/{slug}", blog_post_en, HTMLResponse),
    ("/de/blog/{slug}", blog_post_de, HTMLResponse),
    ("/fr/blog/{slug}", blog_post_fr, HTMLResponse),
    ("/it/blog/{slug}", blog_post_it, HTMLResponse),
    ("/pt/blog/{slug}", blog_post_pt, HTMLResponse),
    ("/index.html", legacy_redirects, None),
    ("/index-en.html", legacy_redirects, None),
    ("/blog-index.html", legacy_redirects, None),
    ("/blog-index-en.html", legacy_redirects, None),
    ("/blog-en-1.html", legacy_redirects, None),
    ("/blog-en-2.html", legacy_redirects, None),
    ("/blog-en-3.html", legacy_redirects, None),
    ("/blog-en-4.html", legacy_redirects, None),
    ("/blog-en-5.html", legacy_redirects, None),
    ("/blog-en-6.html", legacy_redirects, None),
    ("/blog-en-question-marks-chatgpt-equations-word.html", legacy_redirects, None),
    ("/blog-en-overleaf-latex-to-word-editable-equations.html", legacy_redirects, None),
    ("/blog-en-pandoc-math-to-word-omml-troubleshooting.html", legacy_redirects, None),
    ("/blog-en-omml-vs-mathtype-vs-latex-word-thesis.html", legacy_redirects, None),
    ("/blog-signos-interrogacion-ecuaciones-chatgpt-word.html", legacy_redirects, None),
    ("/blog-overleaf-latex-a-word-ecuaciones-editables.html", legacy_redirects, None),
    ("/blog-pandoc-ecuaciones-word-no-editables-soluciones.html", legacy_redirects, None),
    ("/blog-omml-vs-mathtype-vs-latex-word-tfg.html", legacy_redirects, None),
    ("/robots.txt", robots_txt, Response),
    ("/sitemap.xml", sitemap_xml, Response),
    ("/healthz", healthz, PlainTextResponse),
    ("/convert", convert_get, None),
]

for route_path, route_handler, route_response_class in _GET_ROUTES:
    _register_get(route_path, route_handler, route_response_class)

app.add_api_route("/convert", convert, methods=["POST"])
app.add_exception_handler(StarletteHTTPException, custom_http_exception_handler)
app.add_exception_handler(RequestValidationError, custom_validation_exception_handler)
