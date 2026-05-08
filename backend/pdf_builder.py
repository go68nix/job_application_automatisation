from __future__ import annotations

from datetime import datetime, timezone
import html
import re
from pathlib import Path

from weasyprint import HTML

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_BASE = BASE_DIR / "data" / "outputs"


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "unknown"


def _markdownish_to_html(text: str) -> str:
    lines = (text or "").splitlines()
    blocks: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            blocks.append(f"<h2>{html.escape(s.lstrip('# ').strip())}</h2>")
        elif s.startswith("- "):
            blocks.append(f"<li>{html.escape(s[2:].strip())}</li>")
        else:
            blocks.append(f"<p>{html.escape(s)}</p>")

    wrapped: list[str] = []
    in_list = False
    for block in blocks:
        if block.startswith("<li>") and not in_list:
            wrapped.append("<ul>")
            in_list = True
        if not block.startswith("<li>") and in_list:
            wrapped.append("</ul>")
            in_list = False
        wrapped.append(block)
    if in_list:
        wrapped.append("</ul>")
    return "\n".join(wrapped)


def _base_css() -> str:
    return """
    body { font-family: Arial, sans-serif; color:#1a1a1a; margin: 36px; }
    h1,h2 { margin: 0 0 8px 0; }
    h2 { font-size: 18px; margin-top: 18px; }
    p { line-height: 1.5; margin: 0 0 10px 0; }
    ul { margin: 8px 0 12px 20px; }
    li { margin-bottom: 6px; }
    .muted { color:#666; font-size: 13px; }
    """


def build_pdfs(company: str, role: str, cv_text: str, cover_letter_text: str) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date().isoformat()
    folder_name = f"{_sanitize_filename(company)}_{_sanitize_filename(role)}_{today}"
    output_dir = OUTPUT_BASE / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    cv_html = f"""
    <html><head><style>{_base_css()}</style></head>
    <body>
      <h1>Tailored CV Summary</h1>
      <p class="muted">Generated for {html.escape(company)} — {html.escape(role)}</p>
      {_markdownish_to_html(cv_text)}
    </body></html>
    """

    cl_html = f"""
    <html><head><style>{_base_css()}</style></head>
    <body>
      <h1>Cover Letter</h1>
      <p class="muted">Date: {today}</p>
      {_markdownish_to_html(cover_letter_text)}
    </body></html>
    """

    cv_path = output_dir / "cv.pdf"
    cl_path = output_dir / "cover_letter.pdf"
    HTML(string=cv_html).write_pdf(str(cv_path))
    HTML(string=cl_html).write_pdf(str(cl_path))

    rel_cv = cv_path.relative_to(OUTPUT_BASE).as_posix()
    rel_cl = cl_path.relative_to(OUTPUT_BASE).as_posix()
    return rel_cv, rel_cl
