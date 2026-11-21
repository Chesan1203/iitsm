"""Render every Mermaid file in docs/report/diagrams/*.mmd to a PNG next to it.

Run from the repository root (Windows):
    .venv\Scripts\python.exe docs\report\tools\render_diagrams.py [name ...]

Needs internet (the Mermaid library is loaded from a CDN) and Microsoft Edge.
"""
from __future__ import annotations

import html
import math
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from cdp import Edge  # noqa: E402

DIAGRAMS = pathlib.Path(__file__).resolve().parents[1] / "diagrams"

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>body{{margin:0;padding:24px;background:#fff;font-family:'Segoe UI',Arial,sans-serif}}</style></head>
<body><pre class="mermaid">{source}</pre>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>
mermaid.initialize({{startOnLoad:false, theme:'{theme}', securityLevel:'loose',
  flowchart:{{useMaxWidth:false, htmlLabels:true, curve:'basis'}}, sequence:{{useMaxWidth:false, mirrorActors:false, actorMargin:30, width:150, wrap:true, messageMargin:34}},
  er:{{useMaxWidth:false}}, state:{{useMaxWidth:false}}, themeVariables:{{fontSize:'{font}px'}}}});
mermaid.run().then(()=>{{window.__done=true}}).catch(e=>{{window.__err=String(e)}});
</script></body></html>"""


def render(edge: Edge, source_file: pathlib.Path) -> pathlib.Path:
    text = source_file.read_text(encoding="utf-8")
    theme, font = "default", "16"
    for line in text.splitlines():                       # optional first-line settings: %% theme=neutral font=18
        if line.startswith("%% "):
            for part in line[3:].split():
                key, _, value = part.partition("=")
                if key == "theme":
                    theme = value
                if key == "font":
                    font = value
    page = PAGE.format(source=html.escape(text), theme=theme, font=font)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as handle:
        handle.write(page)
        url = pathlib.Path(handle.name).as_uri()
    edge.viewport(3000, 2400, 1.0)
    edge.goto(url, settle=0.2)
    edge.wait_for("window.__done || window.__err", timeout=60)
    error = edge.evaluate("window.__err || ''")
    if error:
        raise RuntimeError(f"{source_file.name}: {error}")
    box = edge.evaluate("(()=>{const r=document.querySelector('pre.mermaid svg').getBoundingClientRect();"
                        "return {w:r.width,h:r.height}})()")
    width, height = math.ceil(box["w"]) + 48, math.ceil(box["h"]) + 48
    edge.viewport(width, height, 2.0)
    out = source_file.with_suffix(".png")
    edge.screenshot(str(out), clip={"x": 0, "y": 0, "width": width, "height": height})
    return out


def render_svg(edge: Edge, source_file: pathlib.Path) -> pathlib.Path:
    svg = source_file.read_text(encoding="utf-8")
    page = f'<!doctype html><html><head><meta charset="utf-8"><style>body{{margin:0;background:#fff}}</style></head><body>{svg}</body></html>'
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as handle:
        handle.write(page)
        url = pathlib.Path(handle.name).as_uri()
    box = None
    edge.viewport(2000, 2000, 1.0)
    edge.goto(url, settle=0.3)
    box = edge.evaluate("(()=>{const r=document.querySelector('svg').getBoundingClientRect();return {w:r.width,h:r.height}})()")
    width, height = math.ceil(box["w"]), math.ceil(box["h"])
    edge.viewport(width, height, 2.0)
    out = source_file.with_suffix(".png")
    edge.screenshot(str(out), clip={"x": 0, "y": 0, "width": width, "height": height})
    return out


def main(names: list[str]):
    files = sorted(list(DIAGRAMS.glob("*.mmd")) + list(DIAGRAMS.glob("*.svg")))
    if names:
        files = [f for f in files if f.stem in names]
    with Edge() as edge:
        for file in files:
            try:
                out = render_svg(edge, file) if file.suffix == ".svg" else render(edge, file)
                print(f"ok    {file.name} -> {out.name} ({out.stat().st_size // 1024} KB)")
            except Exception as exc:                      # keep going so one bad file does not hide the others
                print(f"FAIL  {file.name}: {exc}")


if __name__ == "__main__":
    main(sys.argv[1:])
