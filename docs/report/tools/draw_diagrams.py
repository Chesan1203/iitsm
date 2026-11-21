"""Draws the architecture diagram and the use case diagram as SVG with a fixed, hand-chosen layout.

Mermaid's automatic layout made these two unreadable, so they are drawn here directly.
Run from the repository root, then render with render_diagrams.py:
    python docs/report/tools/draw_diagrams.py
"""
from __future__ import annotations

import pathlib
from xml.sax.saxutils import escape

OUT = pathlib.Path(__file__).resolve().parents[1] / "diagrams"
FONT = "font-family=\"'Segoe UI', Arial, sans-serif\""


class Svg:
    def __init__(self, width: int, height: int):
        self.w, self.h, self.parts = width, height, []

    def add(self, markup: str):
        self.parts.append(markup)

    def text(self, x, y, text, size=14, bold=False, anchor="middle", fill="#212529", italic=False, line=None):
        lines = str(text).split("\n")
        step = line or size + 3
        top = y - (len(lines) - 1) * step / 2
        weight = ' font-weight="700"' if bold else ""
        style = ' font-style="italic"' if italic else ""
        spans = "".join(f'<tspan x="{x}" y="{top + i * step + size * 0.35:.1f}">{escape(part)}</tspan>'
                        for i, part in enumerate(lines))
        self.add(f'<text {FONT} font-size="{size}" text-anchor="{anchor}" fill="{fill}"{weight}{style}>{spans}</text>')

    def rect(self, x, y, w, h, fill, stroke, rx=8, sw=1.5, dash=None):
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="{sw}"{extra}/>')

    def box(self, x, y, w, h, text, fill="#ffffff", stroke="#495057", size=13, bold=False):
        self.rect(x, y, w, h, fill, stroke)
        self.text(x + w / 2, y + h / 2, text, size=size, bold=bold)

    def oval(self, cx, cy, w, h, text, fill="#ffffff", stroke="#495057", size=13):
        self.add(f'<ellipse cx="{cx}" cy="{cy}" rx="{w / 2}" ry="{h / 2}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        self.text(cx, cy, text, size=size, line=size + 2)

    def arrow(self, x1, y1, x2, y2, label=None, dashed=False, marker="arrow", lx=None, ly=None,
              anchor="start", color="#343a40"):
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.5"{dash} '
                 f'marker-end="url(#{marker})"/>')
        if label:
            lx = (x1 + x2) / 2 + 6 if lx is None else lx
            ly = (y1 + y2) / 2 if ly is None else ly
            self.text(lx, ly, label, size=12, anchor=anchor, fill="#495057", italic=True)

    def polyline(self, points, marker="open", color="#343a40"):
        pts = " ".join(f"{x},{y}" for x, y in points)
        self.add(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5" marker-end="url(#{marker})"/>')

    def line(self, x1, y1, x2, y2, color="#343a40"):
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.4"/>')

    def actor(self, cx, cy, name):
        top = cy - 34
        self.add(f'<circle cx="{cx}" cy="{top + 8}" r="8" fill="#fff" stroke="#212529" stroke-width="1.6"/>')
        self.line(cx, top + 16, cx, top + 42, "#212529")
        self.line(cx - 14, top + 25, cx + 14, top + 25, "#212529")
        self.line(cx, top + 42, cx - 12, top + 58, "#212529")
        self.line(cx, top + 42, cx + 12, top + 58, "#212529")
        self.text(cx, top + 74 + (7 if "\n" in name else 0), name, size=13, bold=True)

    def save(self, path: pathlib.Path):
        defs = ('<defs>'
                '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
                '<path d="M0,0 L10,5 L0,10 z" fill="#343a40"/></marker>'
                '<marker id="open" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" orient="auto">'
                '<path d="M1,1 L11,6 L1,11 z" fill="#fff" stroke="#343a40" stroke-width="1.3"/></marker></defs>')
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">'
               f'{defs}<rect width="100%" height="100%" fill="#ffffff"/>' + "".join(self.parts) + "</svg>")
        path.write_text(svg, encoding="utf-8")


def architecture():
    s = Svg(840, 880)
    colours = {"web": ("#eaf2ff", "#0d6efd"), "ports": ("#f1f3f5", "#6c757d"), "svc": ("#e8f5ec", "#198754"),
               "dom": ("#fff4e5", "#e8590c"), "per": ("#f3ebff", "#6f42c1"), "store": ("#fff3cd", "#997404")}

    def band(x, y, w, h, title, key):
        fill, stroke = colours[key]
        s.rect(x, y, w, h, fill, stroke, rx=10, sw=2)
        s.text(x + 12, y + 17, title, size=13, bold=True, anchor="start", fill=stroke)

    def inner(x, y, w, h, text, key):
        s.box(x, y, w, h, text, "#ffffff", colours[key][1])

    s.box(260, 10, 320, 52, "Users: Employee, Technician, Administrator\n(web browser)", "#ffffff", "#212529", size=14, bold=False)
    s.arrow(420, 62, 420, 96, "HTML pages and form posts")

    band(15, 96, 810, 110, "WEB LAYER   app/web   (FastAPI, Jinja2, Bootstrap)", "web")
    for i, text in enumerate(["Routers by role\nauth, employee, technician,\nadmin, incident", "Role guards and\nsigned-cookie session",
                              "Jinja2 templates\nand static CSS", "Error handlers\n(400, 403, 404, 500)"]):
        inner(28 + i * 200, 128, 190, 64, text, "web")
    s.arrow(123, 206, 123, 246, "calls one service method")

    band(15, 246, 810, 100, "CONTRACT   app/ports   (interfaces and data carriers only)", "ports")
    inner(28, 276, 250, 56, "Six service interfaces\nAuth, Incident, Admin,\nLookup, Report, Notification", "ports")
    inner(295, 276, 250, 56, "Data carriers\n(requests, reports) and\nthe Container", "ports")
    inner(562, 276, 250, 56, "Repository interfaces\n(one for each kind of record)", "ports")

    cols = [(15, "SERVICES   app/services", "svc"), (300, "DOMAIN   app/domain", "dom"), (585, "PERSISTENCE   app/persistence", "per")]
    for x, title, key in cols:
        band(x, 396, 240, 366, title, key)
    s.text(135, 428 - 0, "", size=1)
    services = ["Service implementations\nworkflow, access checks", "Access policy, password\nhasher, input rules",
                "Observers\naudit and notification", "Channels\nin-app, simulated email",
                "Background jobs (every 30 s)\nSLA monitor, escalation", "wiring.py\ncomposition root"]
    domain = ["Incident and its\neight State classes", "Priority and assignment\nstrategies", "SLA calculator",
              "Duplicate and correlation\ndetectors, escalation policy", "Entities: User, ITService,\nCategory, SLA policy ..."]
    persistence = ["Ten SQLite repositories", "Database, codec,\nschema.sql", "Demo data seeder"]
    for items, (x, _, key) in zip((services, domain, persistence), cols):
        for i, text in enumerate(items):
            inner(x + 15, 424 + i * 56, 210, 48, text, key)

    s.arrow(135, 346, 135, 396, "implemented by")
    s.arrow(705, 346, 705, 396, "implemented by")
    s.arrow(255, 520, 300, 520, "uses", lx=277, ly=508, anchor="middle")
    s.arrow(585, 520, 540, 520, "builds", lx=562, ly=508, anchor="middle")

    s.box(40, 806, 190, 50, "logs/emails.log\n(simulated email)", colours["store"][0], colours["store"][1])
    s.arrow(135, 762, 135, 806, "written by the channel")
    s.box(615, 806, 180, 50, "SQLite file\ndata/iitsm.db", colours["store"][0], colours["store"][1])
    s.arrow(705, 762, 705, 806, "SQL")
    s.save(OUT / "architecture.svg")


def usecase():
    s = Svg(860, 1170)
    s.rect(125, 10, 620, 1130, "#fcfcfd", "#495057", rx=6, sw=2)
    s.text(140, 28, "I-ITSM", size=15, bold=True, anchor="start")
    LX, LW, RX, RW, H = 275, 270, 590, 250, 40
    ovals = {}

    def group(title, y_title, items, cx=LX, w=LW, top=None, step=50):
        s.text(cx - w / 2, y_title, title, size=12, anchor="start", fill="#6c757d", italic=True)
        y = top if top is not None else y_title + 28
        for key, text in items:
            ovals[key] = (cx, y, w)
            s.oval(cx, y, w, H, text)
            y += step

    group("Common (every signed-in user)", 56, [("login", "Register / sign in"), ("notif", "View notifications"),
                                                 ("search", "Search incidents"), ("view", "View incident and timeline")])
    group("Technician", 262, [("ack", "Acknowledge incident"), ("invest", "Investigate and add notes"),
                              ("request", "Request information"), ("resolve", "Resolve incident")])
    group("Employee", 472, [("report", "Report an incident"), ("info", "Answer a question /\nadd information"),
                            ("verify", "Verify or reject the fix"), ("close", "Close incident and\ngive feedback")])
    group("Administrator", 682, [("demo", "Use demo controls\n(clock, run checks now)"), ("assign", "Assign / reassign technician"),
                                 ("recommend", "Recommend technician"), ("override", "Override priority\n(recalculates SLA deadlines)"),
                                 ("users", "Manage users"), ("config", "Manage services, categories\nand SLA policies"),
                                 ("strategy", "Choose assignment and\npriority strategy"), ("reports", "View reports and\nSLA violations"),
                                 ("audit", "View audit log")])
    # right column: work the system does by itself
    s.text(RX - RW / 2, 440, "Done automatically for every report", size=12, anchor="start", fill="#6c757d", italic=True)
    for key, y, text in [("dup", 470, "Flag possible duplicate"), ("prio", 520, "Calculate priority"),
                         ("sla", 570, "Determine SLA deadlines"), ("auto", 620, "Assign technician\nautomatically"),
                         ("send", 670, "Notify people"), ("record", 720, "Record audit trail")]:
        ovals[key] = (RX, y, RW)
        s.oval(RX, y, RW, H, text, fill="#eef7ee", stroke="#2f9e44")
    s.text(RX - RW / 2, 772, "Scheduled work", size=12, anchor="start", fill="#6c757d", italic=True)
    for key, y, text in [("monitor", 805, "Monitor SLA deadlines\n(warning, violation)"), ("escalate", 865, "Escalate unacknowledged\ncritical incident")]:
        ovals[key] = (RX, y, RW)
        s.oval(RX, y, RW, 46, text, fill="#eef7ee", stroke="#2f9e44")
    s.text(RX - RW / 2, 905, "Monitoring and escalation also notify people and\nrecord the audit trail.", size=11,
           anchor="start", fill="#6c757d", italic=True, line=14)

    def left(key):
        cx, y, w = ovals[key]
        return cx - w / 2, y

    def right(key):
        cx, y, w = ovals[key]
        return cx + w / 2, y

    actors = {"all": (62, 155, "Signed-in\nuser"), "tech": (62, 365, "Technician"), "emp": (62, 575, "Employee"), "adm": (62, 905, "Administrator")}
    for name, (cx, cy, label) in actors.items():
        s.actor(cx, cy, label)
    # actor to use case lines: a short bar next to the actor, then one stub to each use case
    def connect(actor_y, keys, spine_x):
        hand_y = actor_y - 9
        ys = [left(k)[1] for k in keys] + [hand_y]
        s.line(76, hand_y, spine_x, hand_y)
        s.line(spine_x, min(ys), spine_x, max(ys))
        for k in keys:
            x, y = left(k)
            s.line(spine_x, y, x, y)

    connect(155, ("login", "notif", "search", "view"), 100)
    connect(365, ("ack", "invest", "request", "resolve"), 100)
    connect(575, ("report", "info", "verify", "close"), 100)
    connect(905, ("demo", "assign", "recommend", "override", "users", "config", "strategy", "reports", "audit",
                  "verify", "close"), 114)
    # generalisation: Technician, Employee and Administrator are kinds of signed-in user
    for cy in (365, 575, 905):
        s.polyline([(36, cy - 6), (14, cy - 6), (14, 150), (38, 150)])

    # include / extend
    rx, ry = right("report")
    for key in ("prio", "sla", "auto", "send", "record"):
        s.arrow(rx, ry, ovals[key][0] - RW / 2, ovals[key][1], dashed=True)
    s.arrow(ovals["dup"][0] - RW / 2, ovals["dup"][1], rx, ry, dashed=True)
    # demo controls run the checks now
    dx, dy = right("demo")
    s.arrow(dx, dy, ovals["monitor"][0] - RW / 2, ovals["monitor"][1], dashed=True)
    s.arrow(dx, dy, ovals["escalate"][0] - RW / 2, ovals["escalate"][1], dashed=True)
    legend = ["Dashed arrows", "«include»: every report always triggers these five.",
              "«extend»: flagging a duplicate happens only when one", "is found.",
              "Demo controls: can run both scheduled checks now."]
    s.text(RX - RW / 2, 960, "\n".join(legend), size=11, anchor="start", fill="#495057", italic=True, line=15)
    # scheduler actor
    s.actor(802, 835, "Scheduler")
    s.text(802, 889, "(system)", size=12, fill="#6c757d")
    s.line(780, 835, ovals["monitor"][0] + RW / 2, ovals["monitor"][1])
    s.line(780, 835, ovals["escalate"][0] + RW / 2, ovals["escalate"][1])
    s.save(OUT / "usecase.svg")


def state():
    s = Svg(860, 470)
    fills = {"NEW": "#e7f1ff", "CLASSIFIED": "#dbe9ff", "ASSIGNED": "#cfe2ff", "ACKNOWLEDGED": "#c3dbff",
             "IN_PROGRESS": "#fff3cd", "RESOLVED": "#d8f0df", "VERIFIED": "#c5e8d0", "CLOSED": "#b1dfc0"}
    W, H, GAP = 124, 56, 96
    xs = [40 + i * (W + GAP) for i in range(4)]
    row1, row2 = 70, 235
    box = {}

    def state_box(name, x, y):
        box[name] = (x, y)
        s.rect(x, y, W, H, fills[name], "#495057", rx=14, sw=1.8)
        s.text(x + W / 2, y + H / 2, name, size=13, bold=True)

    for name, x in zip(["NEW", "CLASSIFIED", "ASSIGNED", "ACKNOWLEDGED"], xs):
        state_box(name, x, row1)
    for name, x in zip(["CLOSED", "VERIFIED", "RESOLVED", "IN_PROGRESS"], xs):
        state_box(name, x, row2)

    def label(x, y, text):
        s.text(x, y, text, size=11.5, fill="#343a40", line=14)

    # start marker
    s.add('<circle cx="22" cy="98" r="7" fill="#212529"/>')
    s.arrow(29, 98, 40, 98)
    label(76, 40, "employee reports")
    # top row, left to right
    for (a, b), text in zip([("NEW", "CLASSIFIED"), ("CLASSIFIED", "ASSIGNED"), ("ASSIGNED", "ACKNOWLEDGED")],
                            ["classify\n(system)", "assign\n(automatic or\nadministrator)", "acknowledge\n(technician)"]):
        x1, x2 = box[a][0] + W, box[b][0]
        s.arrow(x1, row1 + H / 2, x2, row1 + H / 2)
        label((x1 + x2) / 2, row1 + H / 2 - (31 if text.count("\n") == 2 else 24), text)
    # down from ACKNOWLEDGED to IN_PROGRESS
    ax = xs[3] + W / 2
    s.arrow(ax, row1 + H, ax, row2, "start investigation (technician)", lx=ax - 8, ly=(row1 + H + row2) / 2, anchor="end")
    # bottom row, right to left
    x1, x2 = xs[3], xs[2] + W
    s.arrow(x1, row2 + 20, x2, row2 + 20)
    label((x1 + x2) / 2, row2 + 20 - 24, "resolve\n(technician)")
    s.arrow(x2, row2 + 42, x1, row2 + 42)
    label((x1 + x2) / 2, row2 + 42 + 22, "reject resolution\n(reporter)")
    for (a, b), text in zip([("RESOLVED", "VERIFIED"), ("VERIFIED", "CLOSED")],
                            ["verify\n(reporter or\nadministrator)", "close\n(reporter or\nadministrator)"]):
        x1, x2 = box[a][0], box[b][0] + W
        s.arrow(x1, row2 + H / 2, x2, row2 + H / 2)
        label((x1 + x2) / 2, row2 + H / 2 - 33, text)
    # end marker
    cx = xs[0] + W / 2
    s.arrow(cx, row2 + H, cx, row2 + H + 40)
    s.add(f'<circle cx="{cx}" cy="{row2 + H + 50}" r="9" fill="#fff" stroke="#212529" stroke-width="1.8"/>'
          f'<circle cx="{cx}" cy="{row2 + H + 50}" r="5" fill="#212529"/>')
    # notes
    s.rect(430, 345, 400, 46, "#fffbe6", "#997404", rx=4, dash="5 3")
    s.text(630, 368, "Requesting information and the reporter's reply keep the\nstatus IN_PROGRESS.", size=12.5, line=16)
    s.rect(30, 400, 800, 52, "#fffbe6", "#997404", rx=4, dash="5 3")
    s.text(430, 426, "In every open status, with no change of status: add a note, escalate (P1 only), change the priority,\nflag a possible duplicate, reassign the technician. CLOSED accepts only feedback.",
           size=12.5, line=16)
    s.save(OUT / "state.svg")


def er():
    s = Svg(890, 900)
    RH, HEAD = 18, 28
    pos = {}
    VIOLET = "#6f42c1"

    def table(name, x, y, w, attrs):
        h = HEAD + RH * len(attrs) + 6
        s.rect(x, y, w, h, "#ffffff", VIOLET, rx=6, sw=1.6)
        s.add(f'<path d="M{x},{y + HEAD} L{x},{y + 6} Q{x},{y} {x + 6},{y} L{x + w - 6},{y} Q{x + w},{y} {x + w},{y + 6} '
              f'L{x + w},{y + HEAD} Z" fill="#ece4ff" stroke="{VIOLET}" stroke-width="1.6"/>')
        s.text(x + w / 2, y + HEAD / 2, name, size=14, bold=True)
        rows = {}
        for i, (key, attr, typ) in enumerate(attrs):
            cy = y + HEAD + RH * i + RH / 2
            if key:
                s.text(x + 8, cy, key, size=10, bold=True, anchor="start", fill=VIOLET)
            s.text(x + 44, cy, attr, size=12.5, anchor="start", italic=(attr.startswith("…")))
            rows[attr] = cy                       # column types are listed in the schema tables, not drawn here
        pos[name] = (x, y, w, h, rows)

    C1, C2, C3, CW = 40, 335, 630, 210
    table("users", C1, 10, CW, [("PK", "id", "int"), ("UK", "username", "text"), ("", "full_name", "text"), ("", "email", "text"),
                                ("", "password_hash", "text"), ("", "role", "text"), ("", "active", "int"), ("", "department", "text"),
                                ("", "admin_level", "text"), ("", "experience_years", "int"), ("", "available", "int"),
                                ("", "max_workload", "int")])
    table("technician_skills", C1, 290, CW, [("PK FK", "user_id", "int"), ("PK", "skill", "text")])
    table("notifications", C1, 390, CW, [("PK", "id", "int"), ("FK", "recipient_id", "int"), ("", "incident_id", "int"),
                                         ("", "event_type", "text"), ("", "channel", "text"), ("", "message", "text"),
                                         ("", "is_read", "int"), ("", "created_at", "text")])
    table("incident_notes", C1, 598, CW, [("PK", "id", "int"), ("FK", "incident_id", "int"), ("FK", "author_id", "int"),
                                           ("", "note_type", "text"), ("", "text", "text"), ("", "created_at", "text")])
    table("incidents", C2, 10, CW, [("PK", "id", "int"), ("UK", "ticket_number", "text"), ("", "title", "text"), ("", "description", "text"),
                                    ("FK", "reporter_id", "int"), ("FK", "category_id", "int"), ("FK", "service_id", "int"),
                                    ("FK", "assigned_technician_id", "int"), ("", "impact", "int"), ("", "urgency", "int"),
                                    ("", "affected_users", "int"), ("", "priority", "text"), ("", "priority_score", "int"),
                                    ("", "status", "text"), ("", "escalation_level", "text"), ("", "sla_status", "text"),
                                    ("", "sla_response_deadline", "text"), ("", "sla_resolution_deadline", "text"),
                                    ("", "created_at", "text"), ("", "resolution_summary", "text"), ("", "feedback_rating", "int"),
                                    ("", "… 15 more columns", "")])
    table("sla_events", C2, 480, CW, [("PK", "id", "int"), ("FK", "incident_id", "int"), ("", "event_type", "text"),
                                      ("", "recorded_at", "text")])
    table("categories", C3, 10, CW, [("PK", "id", "int"), ("UK", "name", "text"), ("", "description", "text"),
                                     ("", "required_skill", "text"), ("", "active", "int")])
    table("it_services", C3, 164, CW, [("PK", "id", "int"), ("UK", "name", "text"), ("", "description", "text"),
                                       ("", "business_criticality", "int"), ("FK", "sla_policy_id", "int"), ("", "active", "int")])
    table("sla_policies", C3, 336, CW, [("PK", "id", "int"), ("", "name", "text"), ("", "is_default", "int")])
    table("sla_targets", C3, 454, CW, [("PK FK", "policy_id", "int"), ("PK", "priority", "text"), ("", "response_minutes", "int"),
                                       ("", "resolution_minutes", "int")])
    table("audit_records", C3, 590, CW, [("PK", "id", "int"), ("", "incident_id", "int"), ("", "timestamp", "text"),
                                         ("", "actor_id", "int"), ("", "action", "text"), ("", "previous_status", "text"),
                                         ("", "new_status", "text"), ("", "description", "text")])
    table("settings", C3, 798, CW, [("PK", "key", "text"), ("", "value", "text")])

    GREY = "#495057"

    def mark(x, y, dx, dy, kind):
        px, py = -dy, dx

        def seg(ax, ay, bx, by):
            s.line(ax, ay, bx, by, GREY)
        if kind in ("one", "zero_one"):
            for d in ((8,) if kind == "zero_one" else (8, 13)):
                seg(x + dx * d + px * 6, y + dy * d + py * 6, x + dx * d - px * 6, y + dy * d - py * 6)
        if kind in ("many", "zero_many"):
            tip = 13
            for k in (-7, 0, 7):
                seg(x + dx * tip, y + dy * tip, x + px * k, y + py * k)
        if kind in ("zero_one", "zero_many"):
            d = 19 if kind == "zero_many" else 14
            s.add(f'<circle cx="{x + dx * d}" cy="{y + dy * d}" r="4.5" fill="#fff" stroke="{GREY}" stroke-width="1.4"/>')

    def anchor(table_name, side, row=None, y=None, xoff=0):
        x, ty, w, h, rows = pos[table_name]
        if side == "R":
            return x + w, (rows[row] if row else y), 1, 0
        if side == "L":
            return x, (rows[row] if row else y), -1, 0
        if side == "B":
            return x + w / 2 + xoff, ty + h, 0, 1
        return x + w / 2 + xoff, ty, 0, -1                                  # "T"

    def label(x, y, text, rotate=False):
        width = 6.3 * len(text) + 8
        if rotate:
            s.add(f'<g transform="translate({x},{y}) rotate(-90)"><rect x="{-width / 2}" y="-8" width="{width}" height="16" fill="#fff"/>'
                  f'<text {FONT} font-size="11.5" font-style="italic" fill="#495057" text-anchor="middle" y="4">{escape(text)}</text></g>')
        else:
            s.add(f'<rect x="{x - width / 2}" y="{y - 8}" width="{width}" height="16" fill="#fff"/>')
            s.text(x, y, text, size=11.5, fill="#495057", italic=True)

    def relation(parent, p_end, child, c_end, parent_kind, child_kind, text, path=None, dashed=False, rotate=False, label_at=None):
        px_, py_, pdx, pdy = p_end
        cx_, cy_, cdx, cdy = c_end
        points = [(px_, py_)] + (path or []) + [(cx_, cy_)]
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        s.add('<polyline points="' + " ".join(f"{a},{b}" for a, b in points) + f'" fill="none" stroke="{GREY}" stroke-width="1.4"{dash}/>')
        mark(px_, py_, pdx, pdy, parent_kind)
        mark(cx_, cy_, cdx, cdy, child_kind)
        if label_at is None:
            mx, my = (points[0][0] + points[-1][0]) / 2, (points[0][1] + points[-1][1]) / 2
        else:
            mx, my = label_at
        label(mx, my, text, rotate)

    inc, usr = pos["incidents"], pos["users"]
    relation("users", anchor("users", "R", y=36), "incidents", anchor("incidents", "L", row="reporter_id"), "one", "many", "reports")
    relation("users", anchor("users", "R", y=64), "incidents", anchor("incidents", "L", row="assigned_technician_id"), "zero_one", "many",
             "is assigned")
    relation("categories", anchor("categories", "L", y=44), "incidents", anchor("incidents", "R", row="category_id"), "one", "many", "classifies")
    relation("it_services", anchor("it_services", "L", y=210), "incidents", anchor("incidents", "R", row="service_id"), "one", "many", "is affected")
    relation("sla_policies", anchor("sla_policies", "T"), "it_services", anchor("it_services", "B"), "zero_one", "many", "governs")
    relation("sla_policies", anchor("sla_policies", "B"), "sla_targets", anchor("sla_targets", "T"), "one", "many", "defines")
    relation("users", anchor("users", "B"), "technician_skills", anchor("technician_skills", "T"), "one", "many", "has")
    nrow = pos["notifications"][4]["recipient_id"]
    relation("users", (C1, 80, -1, 0), "incident_notes", anchor("incident_notes", "L", row="author_id"), "one", "many", "writes",
             path=[(12, 80), (12, pos["incident_notes"][4]["author_id"])], rotate=True, label_at=(12, 330))
    relation("users", (C1, 110, -1, 0), "notifications", anchor("notifications", "L", row="recipient_id"), "one", "many", "receives",
             path=[(26, 110), (26, nrow)], rotate=True, label_at=(26, 250))
    relation("incidents", anchor("incidents", "L", y=330), "incident_notes", anchor("incident_notes", "R", row="incident_id"), "one", "many", "has")
    relation("incidents", anchor("incidents", "B"), "sla_events", anchor("sla_events", "T"), "one", "many", "records")
    relation("incidents", anchor("incidents", "R", y=400), "audit_records", anchor("audit_records", "L", row="incident_id"), "one", "many",
             "is traced by", dashed=True, label_at=(572, 470))
    s.text(C3 + CW / 2, 884, "settings has no relationships. Dashed line: no foreign key (the audit trail must survive deletions).",
           size=11, fill="#6c757d", italic=True) if False else None
    s.save(OUT / "er.svg")


if __name__ == "__main__":
    architecture()
    usecase()
    state()
    er()
    print("wrote architecture.svg, usecase.svg, state.svg, er.svg")
