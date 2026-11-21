"""A tiny .docx writer (standard library only) plus a Markdown reader, used to build the project report.

Why not a library: nothing extra has to be installed. The writer supports exactly what the report needs:
headings, paragraphs with bold / italic / code, bullet and numbered lists, tables, code blocks, pictures with
captions, portrait and landscape sections, a table of contents field and page numbers.
"""
from __future__ import annotations

import re
import struct
import zipfile
from xml.sax.saxutils import escape

# ----------------------------------------------------------------------------------------------------------
# Markdown reader
# ----------------------------------------------------------------------------------------------------------
LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells, current, in_code, i = [], "", False, 0
    while i < len(line):
        ch = line[i]
        if ch == "`":
            in_code = not in_code
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            current += "|"
            i += 2
            continue
        if ch == "|" and not in_code:
            cells.append(current.strip())
            current = ""
        else:
            current += ch
        i += 1
    cells.append(current.strip())
    return cells


def parse_markdown(text: str) -> list[tuple]:
    """Blocks: ('h', level, text) ('p', text) ('list', ordered, [(level, text)]) ('table', header, rows) ('code', text)."""
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[tuple] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.lstrip().startswith("```"):
            indent = len(line) - len(line.lstrip())
            i += 1
            body = []
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                body.append(lines[i][indent:] if lines[i][:indent].strip() == "" else lines[i])
                i += 1
            i += 1
            blocks.append(("code", "\n".join(body)))
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            blocks.append(("h", len(m.group(1)), m.group(2).strip()))
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1]):
            header = split_row(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                row = split_row(lines[i])
                row += [""] * (len(header) - len(row))
                rows.append(row[:len(header)])
                i += 1
            blocks.append(("table", header, rows))
            continue
        m = LIST_RE.match(line)
        if m:
            ordered = m.group(2)[0].isdigit()
            start = int(m.group(2)[:-1]) if ordered else 1
            items: list[tuple[int, str]] = []
            while i < len(lines):
                m = LIST_RE.match(lines[i])
                if m and (m.group(2)[0].isdigit() == ordered or len(m.group(1)) >= 2):
                    level = 0 if len(m.group(1)) < 2 else 1
                    items.append((level, m.group(3).strip()))
                    i += 1
                    continue
                if not lines[i].strip():
                    j = i
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and (LIST_RE.match(lines[j]) or lines[j].startswith("   ")):
                        # blank line inside a list: continue if the next thing is an item or an indented block
                        if LIST_RE.match(lines[j]):
                            i = j
                            continue
                        if lines[j].lstrip().startswith("```"):
                            # an indented code block belongs to the item; keep it as a separate block afterwards
                            break
                    break
                if lines[i].startswith("  ") and items:                      # continuation of the last item
                    items[-1] = (items[-1][0], items[-1][1] + " " + lines[i].strip())
                    i += 1
                    continue
                break
            blocks.append(("list", ordered, items, start))
            continue
        if line.lstrip().startswith(">"):
            body = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                body.append(lines[i].lstrip()[1:].strip())
                i += 1
            blocks.append(("p", " ".join(body)))
            continue
        body = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|\s*```|\s*\|)", lines[i]) \
                and not LIST_RE.match(lines[i]):
            body.append(lines[i].strip())
            i += 1
        blocks.append(("p", " ".join(body)))
    return blocks


# ----------------------------------------------------------------------------------------------------------
# DOCX writer
# ----------------------------------------------------------------------------------------------------------
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')

INLINE_RE = re.compile(r"(\*\*[^*]+?\*\*|`[^`]+`|\*[^*\s][^*]*?\*|<br\s*/?>)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
NAVY = "1F3864"


def png_size(path) -> tuple[int, int]:
    with open(path, "rb") as handle:
        header = handle.read(24)
    return struct.unpack(">II", header[16:24])


def run(text: str, bold=False, italic=False, code=False, color=None, size=None) -> str:
    props = ""
    if code:
        props += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'
    if bold:
        props += "<w:b/>"
    if italic:
        props += "<w:i/>"
    if color:
        props += f'<w:color w:val="{color}"/>'
    if size or code:
        props += f'<w:sz w:val="{size or 19}"/>'
    if code:
        props += '<w:shd w:val="clear" w:color="auto" w:fill="EEF1F4"/>'
    props = f"<w:rPr>{props}</w:rPr>" if props else ""
    return f'<w:r>{props}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def inline(text: str, base_bold=False, base_italic=False, color=None, size=None) -> str:
    text = LINK_RE.sub(lambda m: m.group(1), text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    out = []
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.lower().startswith("<br"):
            out.append("<w:r><w:br/></w:r>")
        elif part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(inline(part[2:-2], base_bold=True, base_italic=base_italic, color=color, size=size))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            out.append(run(part[1:-1], code=True, bold=base_bold, size=(size - 1) if size else None))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(inline(part[1:-1], base_bold=base_bold, base_italic=True, color=color, size=size))
        else:
            out.append(run(part, bold=base_bold, italic=base_italic, color=color, size=size))
    return "".join(out)


def para(content: str, style: str | None = None, align: str | None = None, keep_next=False, num=None,
         page_break_before=False, extra_ppr: str = "", spacing: tuple[int, int] | None = None) -> str:
    ppr = ""
    if style:
        ppr += f'<w:pStyle w:val="{style}"/>'
    if keep_next:
        ppr += "<w:keepNext/>"
    if page_break_before:
        ppr += "<w:pageBreakBefore/>"
    if num:
        ppr += f'<w:numPr><w:ilvl w:val="{num[1]}"/><w:numId w:val="{num[0]}"/></w:numPr>'
    if spacing:
        ppr += f'<w:spacing w:before="{spacing[0]}" w:after="{spacing[1]}"/>'
    if align:
        ppr += f'<w:jc w:val="{align}"/>'
    ppr += extra_ppr
    return f"<w:p><w:pPr>{ppr}</w:pPr>{content}</w:p>"


class Docx:
    PAGE = {"portrait": (11906, 16838), "landscape": (16838, 11906)}
    MARGIN = 1134                                                    # 2 cm

    def __init__(self, title: str, header_text: str):
        self.title, self.header_text = title, header_text
        self.body: list[str] = []
        self.media: list[tuple[str, bytes]] = []
        self.orientation = "portrait"
        self.first_section = True
        self._num_count = 1                                           # numId 1 is the bullet list
        self._ordered_ids: list[int] = []
        self._figure = 0
        self._doc_pr = 0
        self.h = [0, 0]                                               # chapter and section counters
        self.items: list[tuple] = []                                  # the same content, for the HTML/PDF renderer

    # -- sizes -------------------------------------------------------------------------------------------
    @property
    def text_width(self) -> int:
        return self.PAGE[self.orientation][0] - 2 * self.MARGIN

    @property
    def text_height(self) -> int:
        return self.PAGE[self.orientation][1] - 2 * self.MARGIN - 700

    # -- structure ---------------------------------------------------------------------------------------
    def chapter(self, title: str, numbered=True) -> str:
        if numbered:
            self.h[0] += 1
            self.h[1] = 0
            label = f"{self.h[0]}. {title}"
        else:
            label = title
        self.body.append(para(run(label), style="Heading1", page_break_before=True))
        self.items.append(("h1", label))
        return label

    def section(self, title: str, level: int = 2):
        if level == 2:
            self.h[1] += 1
            label = f"{self.h[0]}.{self.h[1]} {title}"
        else:
            label = title
        self.body.append(para(run(label), style=f"Heading{level}", keep_next=True))
        self.items.append(("h2", label) if level == 2 else ("hn", label, level))

    def heading_plain(self, title: str, level: int):
        self.body.append(para(run(title), style=f"Heading{level}", keep_next=True))
        self.items.append(("hn", title, level))

    def text(self, md: str, **kw):
        self.body.append(para(inline(md), **kw))
        self.items.append(("p", md))

    def bullets(self, items: list[str]):
        for item in items:
            self.body.append(para(inline(item), style="ListParagraph", num=(1, 0)))
        self.items.append(("ul", [(0, i) for i in items]))

    def numbered(self, items: list[tuple[int, str]], start: int = 1):
        self._num_count += 1
        self._ordered_ids.append((self._num_count, start))
        for level, item in items:
            self.body.append(para(inline(item), style="ListParagraph", num=(self._num_count, level)))
        self.items.append(("ol", list(items), start))

    def bullet_items(self, items: list[tuple[int, str]]):
        for level, item in items:
            self.body.append(para(inline(item), style="ListParagraph", num=(1, level)))
        self.items.append(("ul", list(items)))

    def cover(self, title: str, short: str, subtitle: str, course: str, date_line: str,
              team: list[tuple[str, str]], repo: str, group: str = ""):
        """The cover page. The table of contents follows on its own page (see contents())."""
        self.body.append(para("", spacing=(2400, 0)))
        self.body.append(para(run(title), style="Title"))
        self.body.append(para(run(short), style="Title"))
        self.body.append(para(run(subtitle), style="Subtitle", spacing=(120, 600)))
        self.body.append(para(run(course, bold=True, size=26), spacing=(0, 80)))
        self.body.append(para(run(date_line, size=24), spacing=(0, 160)))
        if group:
            self.body.append(para(run(group, bold=True, size=30, color=NAVY), spacing=(0, 200)))
        self.table(["Team member", "Student ID"], [list(t) for t in team], widths=[0.6, 0.4], record=False)
        self.body.append(para(run("Source code: ", bold=True, size=22) + run(repo, size=22), spacing=(240, 0)))
        self.items.append(("cover", dict(title=title, short=short, subtitle=subtitle, course=course, date_line=date_line,
                                         team=team, repo=repo, group=group)))

    def contents(self):
        self.body.append(para(run("Contents", bold=True, size=36, color=NAVY), page_break_before=True, spacing=(0, 200)))
        self.toc()
        self.items.append(("toc",))

    def code(self, text: str):
        self.items.append(("code", text))
        lines = text.split("\n")
        for idx, line in enumerate(lines):
            self.body.append(para(run(line if line else " ", code=True, size=17), style="Code",
                                  extra_ppr="<w:keepNext/>" if idx < len(lines) - 1 and len(lines) <= 40 else ""))

    def page_break(self):
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        self.items.append(("pb",))

    def toc(self):
        self.body.append('<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
                         '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-2" \\z \\u </w:instrText></w:r>'
                         '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
                         + run("Right-click here and choose Update Field to build the table of contents.") +
                         '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')

    # -- tables ------------------------------------------------------------------------------------------
    @staticmethod
    def column_fractions(header: list[str], rows: list[list[str]], widths: list[float] | None = None) -> list[float]:
        if widths is not None:
            return widths
        weights = []
        for c in range(len(header)):
            longest = max([len(re.sub(r"[`*]", "", header[c]))] + [len(re.sub(r"[`*]", "", r[c])) for r in rows] + [3])
            longest = min(longest, 70)
            weights.append(max(6.0, longest ** 0.85 + 3))
        s = sum(weights)
        return [w / s for w in weights]

    def table(self, header: list[str], rows: list[list[str]], widths: list[float] | None = None, small=False,
              record=True):
        n = len(header)
        total = self.text_width
        widths = self.column_fractions(header, rows, widths)
        if record:
            self.items.append(("table", header, rows, widths))
        grid = [int(total * w) for w in widths]
        size = 17 if (small or n >= 6) else 18
        xml = ['<w:tbl><w:tblPr><w:tblW w:w="%d" w:type="dxa"/>' % sum(grid),
               '<w:tblBorders>' + "".join(f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="B7BEC8"/>'
                                          for e in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>',
               '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
               '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr>',
               "<w:tblGrid>" + "".join(f'<w:gridCol w:w="{g}"/>' for g in grid) + "</w:tblGrid>"]

        def cell(text, width, head=False):
            parts = re.split(r"<br\s*/?>", text) if text else [""]
            paras = "".join(para(inline(p, base_bold=head, size=size), style="TableText") for p in parts)
            shade = '<w:shd w:val="clear" w:color="auto" w:fill="DCE6F5"/>' if head else ""
            return f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shade}</w:tcPr>{paras}</w:tc>'

        xml.append('<w:tr><w:trPr><w:cantSplit/><w:tblHeader/></w:trPr>' +
                   "".join(cell(h, g, True) for h, g in zip(header, grid)) + "</w:tr>")
        for row in rows:
            xml.append('<w:tr><w:trPr><w:cantSplit/></w:trPr>' + "".join(cell(c, g) for c, g in zip(row, grid)) + "</w:tr>")
        xml.append("</w:tbl>")
        self.body.append("".join(xml))
        self.body.append(para("", spacing=(0, 80)))

    # -- pictures ----------------------------------------------------------------------------------------
    def figure(self, path, caption: str, max_width_in: float | None = None, max_height_in: float | None = None):
        width_px, height_px = png_size(path)
        max_w = self.text_width / 1440 if max_width_in is None else min(max_width_in, self.text_width / 1440)
        max_h = (self.text_height / 1440 - 0.6) if max_height_in is None else max_height_in
        scale = min(max_w / width_px, max_h / height_px)
        cx, cy = int(width_px * scale * 914400), int(height_px * scale * 914400)
        self.media.append((f"image{len(self.media) + 1}.png", open(path, "rb").read()))
        rid, name = f"rIdImg{len(self.media)}", self.media[-1][0]
        self._doc_pr += 1
        drawing = (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
                   f'<wp:docPr id="{self._doc_pr}" name="Picture {self._doc_pr}" descr="{escape(caption, {chr(34): "&quot;"})}"/>'
                   '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
                   '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
                   f'<pic:nvPicPr><pic:cNvPr id="{self._doc_pr}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
                   f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                   f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"/></pic:spPr>'
                   '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
        self._figure += 1
        self.items.append(("fig", str(path), caption, cx / 914400, cy / 914400, self._figure))
        self.body.append(para(drawing, align="center", keep_next=True, spacing=(120, 40)))
        self.body.append(para(run(f"Figure {self._figure}. ", bold=True) + inline(caption), style="Caption"))

    # -- sections ----------------------------------------------------------------------------------------
    def _sect(self, orientation: str, title_page=False) -> str:
        w, h = self.PAGE[orientation]
        orient = ' w:orient="landscape"' if orientation == "landscape" else ""
        return ('<w:sectPr><w:headerReference w:type="default" r:id="rIdHdr"/><w:footerReference w:type="default" r:id="rIdFtr"/>'
                f'<w:pgSz w:w="{w}" w:h="{h}"{orient}/>'
                f'<w:pgMar w:top="{self.MARGIN}" w:right="{self.MARGIN}" w:bottom="{self.MARGIN}" w:left="{self.MARGIN}" '
                'w:header="567" w:footer="567" w:gutter="0"/>' + ("<w:titlePg/>" if title_page else "") + "</w:sectPr>")

    def new_section(self, orientation: str):
        """Ends the current section (with its own orientation) and starts one with `orientation`."""
        self.body.append(f"<w:p><w:pPr>{self._sect(self.orientation, self.first_section)}</w:pPr></w:p>")
        self.first_section = False
        self.orientation = orientation
        self.items.append(("section", orientation))

    # -- output ------------------------------------------------------------------------------------------
    def save(self, path):
        body = "".join(self.body) + self._sect(self.orientation)
        document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{body}</w:body></w:document>'
        ordered = "".join(f'<w:num w:numId="{n}"><w:abstractNumId w:val="1"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="{s}"/>'
                          f'</w:lvlOverride></w:num>' for n, s in self._ordered_ids)
        numbering = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering {NS}>'
                     '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>'
                     '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/>'
                     '<w:pPr><w:ind w:left="500" w:hanging="260"/></w:pPr></w:lvl>'
                     '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="–"/><w:lvlJc w:val="left"/>'
                     '<w:pPr><w:ind w:left="900" w:hanging="260"/></w:pPr></w:lvl></w:abstractNum>'
                     '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>'
                     '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:lvlJc w:val="left"/>'
                     '<w:pPr><w:ind w:left="500" w:hanging="320"/></w:pPr></w:lvl>'
                     '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%2)"/><w:lvlJc w:val="left"/>'
                     '<w:pPr><w:ind w:left="900" w:hanging="320"/></w:pPr></w:lvl></w:abstractNum>'
                     '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>' + ordered + "</w:numbering>")

        def style(sid, name, based="Normal", ppr="", rpr="", nxt=None, kind="paragraph", outline=None):
            outline_xml = f'<w:outlineLvl w:val="{outline}"/>' if outline is not None else ""
            nxt_xml = f'<w:next w:val="{nxt}"/>' if nxt else ""
            return (f'<w:style w:type="{kind}" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="{based}"/>{nxt_xml}'
                    f'<w:qFormat/><w:pPr>{ppr}{outline_xml}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')

        styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {NS}>'
                  '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" w:eastAsia="Calibri"/>'
                  '<w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault>'
                  '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
                  '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
                  + style("Heading1", "heading 1", ppr='<w:keepNext/><w:spacing w:before="240" w:after="200"/>',
                          rpr=f'<w:b/><w:color w:val="{NAVY}"/><w:sz w:val="36"/>', nxt="Normal", outline=0)
                  + style("Heading2", "heading 2", ppr='<w:keepNext/><w:spacing w:before="280" w:after="100"/>',
                          rpr=f'<w:b/><w:color w:val="{NAVY}"/><w:sz w:val="28"/>', nxt="Normal", outline=1)
                  + style("Heading3", "heading 3", ppr='<w:keepNext/><w:spacing w:before="200" w:after="80"/>',
                          rpr='<w:b/><w:color w:val="2F5496"/><w:sz w:val="24"/>', nxt="Normal", outline=2)
                  + style("Heading4", "heading 4", ppr='<w:keepNext/><w:spacing w:before="160" w:after="60"/>',
                          rpr='<w:b/><w:color w:val="404040"/><w:sz w:val="22"/>', nxt="Normal", outline=3)
                  + style("Title", "Title", ppr='<w:spacing w:before="0" w:after="120"/>',
                          rpr=f'<w:b/><w:color w:val="{NAVY}"/><w:sz w:val="64"/>')
                  + style("Subtitle", "Subtitle", rpr='<w:color w:val="595959"/><w:sz w:val="30"/>')
                  + style("Caption", "caption", ppr='<w:spacing w:before="40" w:after="200"/><w:jc w:val="center"/>',
                          rpr='<w:i/><w:color w:val="404040"/><w:sz w:val="19"/>')
                  + style("Code", "Code", ppr='<w:shd w:val="clear" w:color="auto" w:fill="F4F5F7"/><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/><w:ind w:left="120"/>',
                          rpr='<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:sz w:val="17"/>')
                  + style("TableText", "Table Text", ppr='<w:spacing w:before="0" w:after="20" w:line="240" w:lineRule="auto"/>',
                          rpr='<w:sz w:val="18"/>')
                  + style("ListParagraph", "List Paragraph", ppr='<w:spacing w:before="0" w:after="60"/>')
                  + style("TOC1", "toc 1", ppr='<w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9630"/></w:tabs><w:spacing w:before="80" w:after="40"/>',
                          rpr='<w:b/>')
                  + style("TOC2", "toc 2", ppr='<w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9630"/></w:tabs><w:spacing w:before="0" w:after="20"/><w:ind w:left="260"/>',
                          rpr='<w:sz w:val="20"/>')
                  + style("Header", "header", rpr='<w:color w:val="7F7F7F"/><w:sz w:val="17"/>')
                  + style("Footer", "footer", rpr='<w:color w:val="7F7F7F"/><w:sz w:val="17"/>')
                  + style("Hyperlink", "Hyperlink", kind="character", rpr='<w:color w:val="0563C1"/><w:u w:val="single"/>')
                  + "</w:styles>")
        header = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr {NS}>'
                  + para(run(self.header_text), style="Header", align="right") + "</w:hdr>")
        footer = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}>'
                  + para('<w:r><w:t xml:space="preserve">Page </w:t></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
                         '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>'
                         '<w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>', style="Footer", align="center")
                  + "</w:ftr>")
        settings = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings {NS}><w:defaultTabStop w:val="720"/>'
                    '<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat>'
                    '</w:settings>')
        rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdSty" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rIdNum" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
                '<Relationship Id="rIdSet" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
                '<Relationship Id="rIdHdr" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
                '<Relationship Id="rIdFtr" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
                + "".join(f'<Relationship Id="rIdImg{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{n}"/>'
                          for i, (n, _) in enumerate(self.media)) + "</Relationships>")
        content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
                         '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                         '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                         '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
                         '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
                         '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
                         '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
                         '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                         '</Types>')
        root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                     '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                     '</Relationships>')
        core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                f'<dc:title>{escape(self.title)}</dc:title><dc:creator>I-ITSM project team</dc:creator></cp:coreProperties>')
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", content_types)
            z.writestr("_rels/.rels", root_rels)
            z.writestr("docProps/core.xml", core)
            z.writestr("word/document.xml", document)
            z.writestr("word/styles.xml", styles)
            z.writestr("word/numbering.xml", numbering)
            z.writestr("word/settings.xml", settings)
            z.writestr("word/header1.xml", header)
            z.writestr("word/footer1.xml", footer)
            z.writestr("word/_rels/document.xml.rels", rels)
            for name, data in self.media:
                z.writestr(f"word/media/{name}", data)

