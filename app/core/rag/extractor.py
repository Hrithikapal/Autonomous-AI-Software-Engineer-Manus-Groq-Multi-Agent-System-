"""
Text extractor — pulls raw text from files and URLs.
Supports: .txt .md .py .js .ts .json .yaml .toml .html .pdf
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx",
    ".json", ".yaml", ".yml", ".toml", ".html", ".css",
    ".sh", ".bash", ".sql", ".csv", ".xml", ".pdf",
}


async def extract_from_bytes(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return _extract_pdf(data)
    try:
        return data.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("extract_from_bytes failed for %s: %s", filename, exc)
        return ""


def _extract_pdf(data: bytes) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    except ImportError:
        return "[PDF extraction requires pypdf — install it in requirements.txt]"
    except Exception as exc:
        logger.warning("PDF extraction failed: %s", exc)
        return ""


async def extract_from_url(url: str) -> tuple[str, str]:
    """Fetch URL and return (title, text). Strips HTML tags for web pages."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 Manus-RAG/1.0"})
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            raw = resp.text

        if "html" in content_type:
            title, text = _strip_html(raw)
        else:
            title = url
            text = raw

        return title, text[:20_000]   # cap at 20k chars
    except Exception as exc:
        logger.warning("extract_from_url failed %s: %s", url, exc)
        return url, f"[Failed to fetch URL: {exc}]"


def _strip_html(html: str) -> tuple[str, str]:
    """Very lightweight HTML → text. No external deps."""
    import re

    # Title
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else "Web page"

    # Remove scripts, styles, head
    html = re.sub(r"<(script|style|head)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"\s{2,}", "\n", text).strip()
    return title, text
