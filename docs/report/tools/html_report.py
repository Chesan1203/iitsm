"""Renders the report content (Docx.items) to HTML and prints it to PDF with headless Microsoft Edge.

This is how the PDF is made: Word's own PDF export stalled on this large document, and Edge prints reliably.
The table of contents gets real page numbers from a two-pass print: pass 1 finds the page of every heading
(each heading carries an invisible marker that is found in the PDF text), pass 2 prints again with the numbers.

Needs the small `pypdf` package (not in the project's requirements) next to `websockets`:
    python -m venv %TEMP%\\pdfenv ; %TEMP%\\pdfenv\\Scripts\\python -m pip install pypdf websockets
"""
from __future__ import annotations

import base64
import html
import io
import pathlib
import re
import tempfile

from docx_writer import INLINE_RE, LINK_RE

NAVY = "#1F3864"


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def inline_html(text: str) -> str:
    text = LINK_RE.sub(lambda m: m.group(1), text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    out = []
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.lower().startswith("<br"):
            out.append("<br>")
        elif part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(f"<b>{inline_html(part[2:-2])}</b>")
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            out.append(f"<code>{esc(part[1:-1])}</code>")
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(f"<i>{inline_html(part[1:-1])}</i>")
        else:
            out.append(esc(part))
    return "".join(out)


CSS = f"""
@page {{ size: A4; margin: 20mm; }}
@page land {{ size: A4 landscape; margin: 20mm; }}
html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ font-family: Calibri, 'Segoe UI', Arial, sans-serif; font-size: 10.5pt; line-height: 1.38; color: #212529; margin: 0; }}
.land {{ page: land; }}
h1 {{ font-size: 19pt; color: {NAVY}; margin: 0 0 14px; padding-bottom: 6px; border-bottom: 2px solid {NAVY}; break-before: page; break-after: avoid; }}
h2 {{ font-size: 14.5pt; color: {NAVY}; margin: 20px 0 6px; break-after: avoid; }}
h3 {{ font-size: 12pt; color: #2F5496; margin: 14px 0 4px; break-after: avoid; }}
h4 {{ font-size: 11pt; color: #404040; margin: 10px 0 3px; break-after: avoid; }}
p {{ margin: 0 0 7px; }}
ul, ol {{ margin: 0 0 8px; padding-left: 22px; }}
li {{ margin-bottom: 3px; }}
li.l1 {{ margin-left: 18px; list-style-type: '– '; }}
code {{ font-family: Consolas, 'Courier New', monospace; font-size: 9pt; background: #EEF1F4; padding: 0 2px; border-radius: 2px; }}
pre {{ font-family: Consolas, 'Courier New', monospace; font-size: 7.8pt; line-height: 1.25; background: #F4F5F7; border: 1px solid #dde1e6;
      padding: 6px 8px; margin: 0 0 10px; white-space: pre-wrap; word-break: break-word; }}
table {{ border-collapse: collapse; width: 100%; table-layout: fixed; margin: 4px 0 12px; font-size: 8.8pt; line-height: 1.28; }}
table.small {{ font-size: 8pt; }}
th, td {{ border: 1px solid #B7BEC8; padding: 3px 5px; vertical-align: top; overflow-wrap: anywhere; }}
th {{ background: #DCE6F5; text-align: left; }}
tr {{ break-inside: avoid; }}
thead {{ display: table-header-group; }}
figure {{ margin: 8px 0 14px; text-align: center; break-inside: avoid; }}
figure img {{ display: block; margin: 0 auto; }}
figcaption {{ font-size: 9.2pt; font-style: italic; color: #404040; margin-top: 4px; }}
.mk {{ font-size: 1px; color: #ffffff; }}
.cover {{ break-after: page; padding-top: 70mm; }}
.cover .t1 {{ font-size: 30pt; font-weight: 700; color: {NAVY}; line-height: 1.15; }}
.cover .sub {{ font-size: 15pt; color: #595959; margin: 6px 0 30px; }}
.cover .course {{ font-size: 13pt; font-weight: 700; margin-bottom: 4px; }}
.cover .date {{ font-size: 12pt; margin-bottom: 10px; }}
.cover .group {{ font-size: 15pt; font-weight: 700; color: {NAVY}; margin-bottom: 14px; }}
.toctitle {{ font-size: 19pt; font-weight: 700; color: {NAVY}; margin-bottom: 12px; break-before: page; }}
.toc1, .toc2 {{ display: flex; align-items: baseline; }}
.toc1 {{ font-weight: 700; margin-top: 7px; }}
.toc2 {{ margin-left: 16px; font-size: 9.6pt; }}
.toc1 .dots, .toc2 .dots {{ flex: 1; border-bottom: 1px dotted #777; margin: 0 4px; transform: translateY(-3px); }}
"""


def render_html(items: list[tuple], pages: dict[str, int] | None = None) -> str:
    counter = 0
    toc_entries: list[tuple[str, int, str]] = []
    for item in items:
        if item[0] in ("h1", "h2"):
            counter += 1
            toc_entries.append((f"HM{counter}X", 1 if item[0] == "h1" else 2, item[1]))
    out: list[str] = []
    ids = iter(toc_entries)
    cur_land = False
    out.append('<div class="port">')
    for item in items:
        kind = item[0]
        if kind == "cover":
            c = item[1]
            out.append('<div class="cover">')
            out.append(f'<div class="t1">{esc(c["title"])}</div><div class="t1">{esc(c["short"])}</div>')
            out.append(f'<div class="sub">{esc(c["subtitle"])}</div><div class="course">{esc(c["course"])}</div>'
                       f'<div class="date">{esc(c["date_line"])}</div>')
            if c.get("group"):
                out.append(f'<div class="group">{esc(c["group"])}</div>')
            out.append('<table style="width:100%"><colgroup><col style="width:60%"><col style="width:40%"></colgroup>'
                       '<thead><tr><th>Team member</th><th>Student ID</th></tr></thead><tbody>')
            for name, student_id in c["team"]:
                out.append(f"<tr><td>{inline_html(name)}</td><td>{inline_html(student_id)}</td></tr>")
            out.append("</tbody></table>")
            out.append(f'<p style="margin-top:14px"><b>Source code:</b> {esc(c["repo"])}</p></div>')
        elif kind == "toc":
            out.append('<div class="toctitle">Contents</div>')
            for marker, level, label in toc_entries:
                page = (pages or {}).get(marker, 0)
                out.append(f'<div class="toc{level}"><span>{esc(label)}</span><span class="dots"></span><span>{page or ""}</span></div>')
        elif kind in ("h1", "h2"):
            marker = next(ids)[0]
            tag = "h1" if kind == "h1" else "h2"
            out.append(f'<{tag}>{esc(item[1])}<span class="mk">{marker}</span></{tag}>')
        elif kind == "hn":
            out.append(f"<h{item[2]}>{esc(item[1])}</h{item[2]}>")
        elif kind == "p":
            out.append(f"<p>{inline_html(item[1])}</p>")
        elif kind == "ul":
            out.append("<ul>" + "".join(f'<li class="l{lv}">{inline_html(t)}</li>' if lv else f"<li>{inline_html(t)}</li>"
                                         for lv, t in item[1]) + "</ul>")
        elif kind == "ol":
            out.append(f'<ol start="{item[2]}">' + "".join(f'<li class="l{lv}">{inline_html(t)}</li>' if lv else f"<li>{inline_html(t)}</li>"
                                                            for lv, t in item[1]) + "</ol>")
        elif kind == "code":
            out.append(f"<pre>{esc(item[1])}</pre>")
        elif kind == "table":
            header, rows, widths = item[1], item[2], item[3]
            cls = ' class="small"' if len(header) >= 6 else ""
            cols = "".join(f'<col style="width:{w * 100:.2f}%">' for w in widths)
            head = "".join(f"<th>{inline_html(h)}</th>" for h in header)
            body = "".join("<tr>" + "".join(f"<td>{inline_html(c)}</td>" for c in row) + "</tr>" for row in rows)
            out.append(f"<table{cls}><colgroup>{cols}</colgroup><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
        elif kind == "fig":
            _, path, caption, cx, cy, number = item
            uri = pathlib.Path(path).as_uri()
            out.append(f'<figure><img src="{uri}" style="width:{cx:.3f}in;height:{cy:.3f}in">'
                       f"<figcaption><b>Figure {number}.</b> {inline_html(caption)}</figcaption></figure>")
        elif kind == "pb":
            out.append('<div style="break-after:page"></div>')
        elif kind == "section":
            cur_land = item[1] == "landscape"
            out.append(f'</div><div class="{"land" if cur_land else "port"}">')
    out.append("</div>")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>I-ITSM project report</title><style>{CSS}</style></head><body>{''.join(out)}</body></html>"


FOOTER = ('<div style="width:100%;box-sizing:border-box;padding:0 20mm;font-size:8px;color:#777;text-align:center;'
          'font-family:Calibri,Arial,sans-serif">Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>')
HEADER = ('<div style="width:100%;box-sizing:border-box;padding:0 20mm;font-size:8px;color:#777;text-align:right;'
          'font-family:Calibri,Arial,sans-serif">Group 6 | I-ITSM project report</div>')


def print_pdf(edge, html_text: str) -> bytes:
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as handle:
        handle.write(html_text)
        url = pathlib.Path(handle.name).as_uri()
    edge.viewport(1000, 1400, 1.0)
    edge.goto(url, settle=0.5, timeout=120)
    edge.evaluate("Promise.all(Array.from(document.images).map(i => i.complete ? 1 : new Promise(r => {i.onload = i.onerror = r})))"
                  ".then(() => true)")
    result = edge.call("Page.printToPDF", printBackground=True, preferCSSPageSize=True, displayHeaderFooter=True,
                       headerTemplate=HEADER, footerTemplate=FOOTER, transferMode="ReturnAsBase64")
    return base64.b64decode(result["data"])


def heading_pages(pdf: bytes) -> dict[str, int]:
    from pypdf import PdfReader
    found: dict[str, int] = {}
    reader = PdfReader(io.BytesIO(pdf))
    for number, page in enumerate(reader.pages, start=1):
        for marker in re.findall(r"HM\d+X", page.extract_text() or ""):
            found.setdefault(marker, number)
    return found


def render_pdf(items: list[tuple], out_path: pathlib.Path):
    from cdp import Edge
    with Edge(width=1000, height=1400) as edge:
        first = print_pdf(edge, render_html(items))
        pages = heading_pages(first)
        final = print_pdf(edge, render_html(items, pages))
        check = heading_pages(final)
    wrong = [k for k in pages if check.get(k) != pages[k]]
    out_path.write_bytes(final)
    from pypdf import PdfReader
    count = len(PdfReader(io.BytesIO(final)).pages)
    print(f"PDF: {count} pages, {len(final) // 1024} KB -> {out_path}")
    if wrong:
        print("warning: the contents page numbers changed between passes for", len(wrong), "headings")
