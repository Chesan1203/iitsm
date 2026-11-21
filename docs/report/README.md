# The project report: how it is made

The report is generated from the project's own documents, so it never disagrees with the repository.

| File | What it is |
| --- | --- |
| `I-ITSM_Project_Report.pdf` | The report as a PDF (the file to submit). |
| `I-ITSM_Project_Report.docx` | The same report in Word format, to edit names or wording. |
| `diagrams/*.png` | The rendered diagrams (architecture, use case, ER, state, two sequence diagrams). |
| `diagrams/*.svg`, `diagrams/*.mmd` | Their sources: SVG drawn by `tools/draw_diagrams.py`, Mermaid text for the sequence diagrams. |
| `../screenshots/*.png` | The user-interface screenshots, taken by `tools/take_screenshots.py`. |
| `tools/` | The scripts that make all of the above. |

## Rebuilding everything

Run these from the repository root (Windows, PowerShell). They need internet access and Microsoft Edge. The first
three need nothing beyond the project's own `requirements.txt`.

```bash
.venv\Scripts\python.exe docs\report\tools\draw_diagrams.py
.venv\Scripts\python.exe docs\report\tools\render_diagrams.py
.venv\Scripts\python.exe docs\report\tools\take_screenshots.py
.venv\Scripts\python.exe docs\report\tools\build_report.py
```

1. `draw_diagrams.py` writes the SVG diagrams (architecture, use case, state, ER).
2. `render_diagrams.py` turns the SVG and Mermaid files into PNG pictures using headless Edge.
3. `take_screenshots.py` starts a throw-away copy of the app on port 8123 with a temporary database, signs in as the demo
   users, walks one incident through its life and saves the screenshots. Your real `data/` folder is not touched.
4. `build_report.py` assembles the Word file from the Markdown files in `docs/`, the diagrams and the screenshots.

### The PDF

`build_report.py --pdf` also prints the PDF with headless Edge, with a table of contents that carries real page
numbers. That step needs two small packages that are **not** in `requirements.txt`, so install them in a scratch
environment instead of the project's `.venv`:

```bash
python -m venv %TEMP%\pdfenv
%TEMP%\pdfenv\Scripts\python -m pip install pypdf websockets
%TEMP%\pdfenv\Scripts\python docs\report\tools\build_report.py --pdf
```

(Word's own "Save as PDF" can also be used on the `.docx`. It stalled for many minutes on this 90-page document on
the machine the report was made on, which is why the PDF is printed with Edge.)

### The Word contents page

The `.docx` is written with an empty table of contents field. `tools/update_toc.ps1` opens it in Word, fills in the
contents and page numbers and saves it. In Word you can do the same by right-clicking the contents page and
choosing Update Field.

To change the wording of a chapter, edit the Markdown file it comes from (see `build_report.py`) or the text written in
`build_report.py` itself (introduction, picture captions, conclusion), then rebuild. Edits made directly in the Word
file are lost the next time the report is rebuilt, so do the rebuild first and the hand edits last.
