"""Generates docs/class_diagram.puml (PlantUML source) and one PNG per diagram (Graphviz)
from a single specification, so the two always agree.

    python scripts/generate_class_diagrams.py        (needs the `dot` program from Graphviz)
"""
import html
import subprocess
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"

# kind: abstract | interface | class | value | record | stub | module
# edge kinds: inherit (a=child, b=parent) | realize | compose (a=whole, b=part) | aggregate
#             | assoc (a -> b) | depend (a ..> b)


def N(name, kind="class", attrs=(), methods=(), note=None, ordering=None):
    return dict(name=name, kind=kind, attrs=list(attrs), methods=list(methods), note=note, ordering=ordering)


def E(kind, a, b, label="", mult=""):
    return dict(kind=kind, a=a, b=b, label=label, mult=mult)


DIAGRAMS = []

# ---------------------------------------------------------------------------------- 1
DIAGRAMS.append(dict(
    key="1_entities", title="Diagram 1 - Users and reference data (app/domain/models)", rankdir="BT",
    nodes=[
        N("Entity", "abstract", ["-_id: int | None"], ["+id: int | None", "+assign_id(new_id)  {write-once}"]),
        N("User", "abstract",
          ["-username: str", "-full_name: str", "-email: str", "-password_hash: str", "-role: Role", "-active: bool"],
          ["+is_system: bool", "+activate()", "+deactivate()", "+describe(): str  {abstract}", "+system(): User  {static}"]),
        N("Employee", "class", ["-department: str"], ["+describe(): str"]),
        N("Technician", "class",
          ["-skills: frozenset[str]", "-experience_years: int", "-available: bool", "-max_workload: int"],
          ["+set_available(available)", "+describe(): str"]),
        N("Administrator", "class", ["-admin_level: AdminLevel"], ["+describe(): str"]),
        N("SystemUser", "class", ["id = 0, role = ADMINISTRATOR"], ["+activate() / deactivate(): raise", "+describe(): str"]),
        N("ITService", "class",
          ["-name: str", "-description: str", "-business_criticality: Level", "-sla_policy_id: int | None", "-active: bool"], []),
        N("Category", "class", ["-name: str", "-description: str", "-required_skill: str", "-active: bool"], []),
        N("SlaPolicy", "class", ["-name: str", "-is_default: bool", "-targets: dict[Priority, SlaTarget]"],
          ["+target_for(priority): SlaTarget"]),
        N("SlaTarget", "value", ["+response_minutes: int", "+resolution_minutes: int"], []),
    ],
    edges=[
        E("inherit", "User", "Entity"), E("inherit", "ITService", "Entity"), E("inherit", "Category", "Entity"),
        E("inherit", "SlaPolicy", "Entity"),
        E("inherit", "Employee", "User"), E("inherit", "Technician", "User"),
        E("inherit", "Administrator", "User"), E("inherit", "SystemUser", "User"),
        E("compose", "SlaPolicy", "SlaTarget", "targets", "0..4"),
        E("depend", "ITService", "SlaPolicy", "refers by sla_policy_id"),
    ]))

# ---------------------------------------------------------------------------------- 2
DIAGRAMS.append(dict(
    key="2_incident", title="Diagram 2 - The Incident and the objects it owns (app/domain/models)", rankdir="TB",
    nodes=[
        N("Incident", "class",
          ["-ticket_number: str", "-title: str", "-description: str", "-impact: Level", "-urgency: Level",
           "-affected_users: int", "-priority: Priority", "-priority_score: int", "-status: IncidentStatus",
           "-created_at, assigned_at, acknowledged_at,", "  resolved_at, verified_at, closed_at: datetime",
           "-escalation_level: EscalationLevel", "-possible_duplicate_of: str"],
          ["+is_open, is_active, has_pending_info_request, notes", "+add_observer(observer)", "+snapshot(): IncidentSnapshot",
           "+restore(snapshot): Incident  {static}", "+18 behaviour methods (see diagram 3)"]),
        N("SlaTracker", "class",
          ["-response_deadline, resolution_deadline: datetime", "-response_warned, resolution_warned: bool",
           "-response_violated, resolution_violated: bool", "-status: SlaStatus"], ["+copy(): SlaTracker"]),
        N("InvestigationNote", "value", ["+id", "+author: User", "+note_type: NoteType", "+text: str", "+created_at"], []),
        N("Resolution", "value", ["+summary: str", "+details: str", "+resolved_by: User", "+resolved_at"], []),
        N("Feedback", "value", ["+rating: int (1-5)", "+comment: str", "+submitted_at"], []),
        N("IncidentSnapshot", "value", ["one field per Incident field", "notes: tuple[InvestigationNote]"], []),
        N("AuditRecord", "record",
          ["+id, incident_id, ticket_number", "+timestamp, actor_id, actor_name", "+action", "+previous_status, new_status", "+description"], []),
        N("Notification", "record",
          ["+id, recipient_id, incident_id", "+event_type: IncidentEventType", "+channel: ChannelType", "+message, created_at", "+is_read: bool"], []),
        N("SlaEvent", "record", ["+id, incident_id", "+event_type: SlaEventType", "+recorded_at"], []),
        N("User", "stub", note="diagram 1"), N("Technician", "stub", note="diagram 1"),
        N("ITService", "stub", note="diagram 1"), N("Category", "stub", note="diagram 1"),
    ],
    edges=[
        E("compose", "Incident", "SlaTracker", "sla_tracker", "0..1"),
        E("compose", "Incident", "InvestigationNote", "notes", "0..*"),
        E("compose", "Incident", "Resolution", "resolution", "0..1"),
        E("compose", "Incident", "Feedback", "feedback", "0..1"),
        E("assoc", "Incident", "User", "reporter", "1"),
        E("assoc", "Incident", "Technician", "assigned_technician", "0..1"),
        E("assoc", "Incident", "ITService", "affected_service", "1"),
        E("assoc", "Incident", "Category", "category", "1"),
        E("assoc", "InvestigationNote", "User", "author", "1"),
        E("assoc", "Resolution", "User", "resolved_by", "1"),
        E("depend", "Incident", "IncidentSnapshot", "snapshot() / restore()"),
        E("depend", "AuditRecord", "Incident", "refers by incident_id"),
        E("depend", "Notification", "Incident", "refers by incident_id"),
        E("depend", "SlaEvent", "Incident", "refers by incident_id"),
    ]))

# ---------------------------------------------------------------------------------- 3
STATE_CLASSES = [
    ("NewState", ["+record_creation()", "+classify()"]),
    ("ClassifiedState", ["+assign_to()"]),
    ("AssignedState", ["+reassign()", "+acknowledge()"]),
    ("AcknowledgedState", ["+start_investigation()"]),
    ("InProgressState", ["+request_info()", "+respond_to_info()", "+resolve()"]),
    ("ResolvedState", ["+verify()", "+reject_resolution()"]),
    ("VerifiedState", ["+close()", "+submit_feedback()"]),
]
DIAGRAMS.append(dict(
    key="3_lifecycle", title="Diagram 3 - Incident lifecycle: State pattern and Observer pattern (app/domain/state, observer, events)",
    rankdir="BT",
    nodes=[
        N("Incident", "class", ["-status: IncidentStatus", "-observers: list[IncidentObserver]"],
          ["+record_creation, classify, assign_to, reassign,", "  acknowledge, start_investigation, add_note,", "  request_info, respond_to_info, resolve,",
           "  verify, reject_resolution, close, submit_feedback,", "  escalate, change_priority, mark_possible_duplicate,",
           "  apply_sla_result   (each delegates to the state)", "+add_observer(observer)", "-_state: IncidentState  {derived}",
           "-_set(**changes), _add_note(note)", "-_fire(event_type, actor, previous, description, at)"]),
        N("IncidentState", "abstract", [],
          ["+status: IncidentStatus  {abstract}", "+18 action methods: every one raises", "  InvalidStateTransitionError by default"]),
        N("OpenState", "abstract", ["-_technician_may_note: bool"],
          ["+add_note()", "+escalate()", "+change_priority()", "+mark_possible_duplicate()", "+apply_sla_result()"],
          ordering="in"),
        *[N(name, "class", [], methods) for name, methods in STATE_CLASSES],
        N("ClosedState", "class", [], ["+submit_feedback()  {the only action left}"]),
        N("IncidentStateFactory", "class", [], ["+for_status(status): IncidentState  {static}"]),
        N("IncidentObserver", "interface", [], ["+on_event(event: IncidentEvent)"]),
        N("IncidentEvent", "value", ["+incident", "+event_type: IncidentEventType", "+actor: User", "+previous_status", "+new_status", "+description", "+timestamp"], []),
        N("permissions", "module", [], ["require_system()", "require_admin()", "require_admin_or_system()", "require_assigned_technician()",
                                       "require_reporter()", "require_reporter_or_system()", "require_reporter_or_admin()"]),
    ],
    edges=[
        E("inherit", "OpenState", "IncidentState"), E("inherit", "ClosedState", "IncidentState"),
        *[E("inherit", name, "OpenState") for name, _ in STATE_CLASSES],
        E("depend", "Incident", "IncidentStateFactory", "asks for its state"),
        E("depend", "IncidentStateFactory", "IncidentState", "returns a shared instance"),
        E("aggregate", "Incident", "IncidentObserver", "observers", "0..*"),
        E("depend", "Incident", "IncidentEvent", "fires"),
        E("depend", "IncidentObserver", "IncidentEvent", "receives"),
        E("depend", "OpenState", "permissions", "checks the actor"),
    ]))

# ---------------------------------------------------------------------------------- 4
DIAGRAMS.append(dict(
    key="4_strategies", title="Diagram 4 - Strategy pattern: priority and technician assignment (app/domain/strategies)", rankdir="BT",
    nodes=[
        N("PriorityStrategy", "interface", [], ["+calculate(data: PriorityInput): PriorityResult", "+name: str"]),
        N("WeightedScorePriorityStrategy", "class", [], ["+calculate()", "+name = 'weighted_score'"]),
        N("RuleBasedPriorityStrategy", "class", ["-_fallback: WeightedScorePriorityStrategy"], ["+calculate()", "+name = 'rule_based'"]),
        N("PriorityInput", "value", ["+impact, urgency, criticality: Level", "+affected_users: int"], []),
        N("PriorityResult", "value", ["+score: int", "+priority: Priority", "+explanation: str"], []),
        N("AssignmentStrategy", "abstract", [],
          ["+rank(incident, candidates): list[RankedTechnician]  {abstract}", "+name: str  {abstract}",
           "+select(incident, candidates): Technician | None"]),
        N("SkillBasedAssignment", "class", [], ["+rank()", "+name = 'skill_based'"]),
        N("LoadBasedAssignment", "class", [], ["+rank()", "+name = 'load_based'"]),
        N("WeightedRecommendationStrategy", "class", [], ["+rank()", "+name = 'weighted_recommendation'"]),
        N("TechnicianCandidate", "value", ["+technician: Technician", "+active_incident_count: int", "+resolved_on_this_service_count: int"], []),
        N("RankedTechnician", "value", ["+technician: Technician", "+score: float", "+reasons: list[str]"], []),
        N("Incident", "stub", note="diagram 2"),
    ],
    edges=[
        E("realize", "WeightedScorePriorityStrategy", "PriorityStrategy"),
        E("realize", "RuleBasedPriorityStrategy", "PriorityStrategy"),
        E("compose", "RuleBasedPriorityStrategy", "WeightedScorePriorityStrategy", "falls back to", "1"),
        E("depend", "PriorityStrategy", "PriorityInput", "reads"), E("depend", "PriorityStrategy", "PriorityResult", "returns"),
        E("inherit", "SkillBasedAssignment", "AssignmentStrategy"),
        E("inherit", "LoadBasedAssignment", "AssignmentStrategy"),
        E("inherit", "WeightedRecommendationStrategy", "AssignmentStrategy"),
        E("depend", "AssignmentStrategy", "TechnicianCandidate", "reads"), E("depend", "AssignmentStrategy", "RankedTechnician", "returns"),
        E("depend", "AssignmentStrategy", "Incident", "ranks for"),
    ]))

# ---------------------------------------------------------------------------------- 5
DIAGRAMS.append(dict(
    key="5_engines", title="Diagram 5 - SLA engine, intelligent features and time (app/domain/sla, intelligence, time_provider)", rankdir="LR",
    nodes=[
        N("Incident", "stub", note="diagram 2"),
        N("SlaCalculator", "class", [], ["+create_tracker(priority, policy, start): SlaTracker", "+evaluate(incident, now): SlaCheckResult"]),
        N("SlaCheckResult", "value", ["+status: SlaStatus", "+new_events: list[SlaEventType]"], []),
        N("DuplicateDetector", "class", [], ["+find_similar(incident, recent): list[DuplicateMatch]"]),
        N("DuplicateMatch", "value", ["+other_ticket_number: str", "+score: float"], []),
        N("EscalationPolicy", "class", [], ["+evaluate(incident, now): EscalationDecision | None"]),
        N("EscalationDecision", "value", ["+new_level: EscalationLevel", "+target_admin_level: AdminLevel", "+reason: str"], []),
        N("CorrelationDetector", "class", [], ["+find_groups(open_incidents, now): list[CorrelationGroup]"]),
        N("CorrelationGroup", "value", ["+service: ITService", "+incidents: list[Incident]", "+is_probable_service_problem: bool"], []),
        N("TimeProvider", "interface", [], ["+now(): datetime"]),
        N("SystemTimeProvider", "class", [], ["+now(): datetime"]),
        N("SimulatedTimeProvider", "class", ["-_offset: timedelta"], ["+now(): datetime", "+advance(delta)", "+reset()", "+offset: timedelta"]),
    ],
    edges=[
        E("depend", "SlaCalculator", "Incident", "evaluates"), E("depend", "EscalationPolicy", "Incident", "evaluates"),
        E("depend", "DuplicateDetector", "Incident", "compares"), E("depend", "CorrelationDetector", "Incident", "groups"),
        E("depend", "SlaCalculator", "SlaCheckResult", "returns"),
        E("depend", "DuplicateDetector", "DuplicateMatch", "returns"),
        E("depend", "EscalationPolicy", "EscalationDecision", "returns"),
        E("depend", "CorrelationDetector", "CorrelationGroup", "returns"),
        E("realize", "SystemTimeProvider", "TimeProvider"), E("realize", "SimulatedTimeProvider", "TimeProvider"),
    ]))

# =================================================================== PlantUML
def puml(d):
    out = ["@startuml", f"title {d['title']}", "skinparam classAttributeIconSize 0", "skinparam linetype ortho"]
    for n in d["nodes"]:
        kw = {"abstract": "abstract class", "interface": "interface"}.get(n["kind"], "class")
        stereo = {"value": " <<value>>", "record": " <<record>>", "module": " <<module>>",
                  "stub": f" <<see {n['note']}>>"}.get(n["kind"], "")
        out.append(f"{kw} {n['name']}{stereo} {{")
        out += [f"  {a}" for a in n["attrs"]]
        if n["attrs"] and n["methods"]:
            out.append("  --")
        out += [f"  {m}" for m in n["methods"]]
        out.append("}")
    for e in d["edges"]:
        a, b, k, lab, mult = e["a"], e["b"], e["kind"], e["label"], e["mult"]
        text = f" : {lab}" if lab else ""
        if k == "inherit":
            out.append(f"{b} <|-- {a}")
        elif k == "realize":
            out.append(f"{b} <|.. {a}")
        elif k == "compose":
            out.append(f'{a} *-- "{mult}" {b}{text}')
        elif k == "aggregate":
            out.append(f'{a} o-- "{mult}" {b}{text}')
        elif k == "assoc":
            out.append(f'{a} --> "{mult}" {b}{text}')
        else:
            out.append(f"{a} ..> {b}{text}")
    out.append("@enduml")
    return "\n".join(out)


# =================================================================== Graphviz
COLORS = {"abstract": "#EEF2FF", "interface": "#EEF2FF", "class": "#FFFFFF", "value": "#F3FBF4",
          "record": "#FFF8EC", "stub": "#EDEDED", "module": "#F6F0FF"}


def cell(lines):
    if not lines:
        return ""
    body = "".join(f"{html.escape(l)}<BR ALIGN=\"LEFT\"/>" for l in lines)
    return f'<HR/><TR><TD ALIGN="LEFT" BALIGN="LEFT" CELLPADDING="3">{body}</TD></TR>'


def node_dot(n):
    stereo = {"abstract": "«abstract»", "interface": "«interface»", "value": "«value»",
              "record": "«record»", "module": "«module»"}.get(n["kind"], "")
    if n["kind"] == "stub":
        stereo = f"see {n['note']}"
    name = html.escape(n["name"])
    name = f"<I>{name}</I>" if n["kind"] in ("abstract", "interface") else name
    head = (f'<TR><TD CELLPADDING="4">{"<FONT POINT-SIZE=\"9\">" + html.escape(stereo) + "</FONT><BR/>" if stereo else ""}'
            f"<B>{name}</B></TD></TR>")
    attrs = cell(n["attrs"]) if n["kind"] != "stub" else ""
    methods = cell(n["methods"]) if n["kind"] != "stub" else ""
    if n["kind"] != "stub" and not n["attrs"] and n["methods"]:
        attrs = ""
    return (f'"{n["name"]}" [label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" '
            f'BGCOLOR="{COLORS[n["kind"]]}">{head}{attrs}{methods}</TABLE>>' + (f' ordering={n["ordering"]}' if n.get("ordering") else "") + '];')


def edge_dot(e):
    a, b, k = e["a"], e["b"], e["kind"]
    style = {
        "inherit": 'arrowhead=empty',
        "realize": 'arrowhead=empty style=dashed',
        "compose": 'dir=back arrowtail=diamond arrowhead=none',
        "aggregate": 'dir=back arrowtail=odiamond arrowhead=none',
        "assoc": 'arrowhead=vee',
        "depend": 'arrowhead=vee style=dashed',
    }[k]
    extra = ""
    if e["label"]:
        extra += f' label="{e["label"]}" fontsize=9 fontname="Helvetica"'
    if e["mult"]:
        extra += f' headlabel="{e["mult"]}" labeldistance=1.8 labelfontsize=9' if k in ("assoc",) else f' headlabel="{e["mult"]}" labeldistance=1.8 labelfontsize=9'
    return f'"{a}" -> "{b}" [{style}{extra}];'


def dot(d):
    lines = ['digraph G {', f'  rankdir={d["rankdir"]}; nodesep=0.45; ranksep=0.7; splines=true; pad=0.3;',
             f'  labelloc=t; fontname="Helvetica-Bold"; fontsize=15; label="{d["title"]}";',
             '  node [shape=plain fontname="Helvetica" fontsize=10];', '  edge [fontname="Helvetica" fontsize=9];']
    lines += ["  " + node_dot(n) for n in d["nodes"]]
    lines += ["  " + edge_dot(e) for e in d["edges"]]
    lines.append("}")
    return "\n".join(lines)


if __name__ == "__main__":
    (DOCS / "class_diagram.puml").write_text("\n\n".join(puml(d) for d in DIAGRAMS) + "\n", encoding="utf-8")
    for d in DIAGRAMS:
        src = DOCS / f"class_diagram_{d['key']}.dot"
        src.write_text(dot(d), encoding="utf-8")
        subprocess.run(["dot", "-Tpng", "-Gdpi=140", str(src), "-o", str(DOCS / f"class_diagram_{d['key']}.png")], check=True)
        src.unlink()
    print("written:", sorted(p.name for p in DOCS.glob("class_diagram*")))
