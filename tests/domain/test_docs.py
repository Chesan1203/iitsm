"""Keeps the documents honest: they must keep up with the code."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NOT_DIAGRAMMED = {"enums.py", "exceptions.py", "business_rules.py"}


def public_classes():
    for path in sorted((ROOT / "app" / "domain").rglob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                yield path.name, node.name


def test_required_documents_exist_and_have_content():
    for name in ("DOMAIN_README.md", "oop_and_patterns.md", "business_rules.md", "domain_decisions.md",
                 "video_script_p1.md", "class_diagram.puml", "class_diagram_1_entities.png",
                 "class_diagram_2_incident.png", "class_diagram_3_lifecycle.png",
                 "class_diagram_4_strategies.png", "class_diagram_5_engines.png"):
        path = ROOT / "docs" / name
        assert path.exists() and path.stat().st_size > 500, name


def test_domain_readme_describes_every_public_class():
    text = (ROOT / "docs" / "DOMAIN_README.md").read_text(encoding="utf-8")
    missing = [name for _, name in public_classes() if f"`{name}`" not in text]
    assert not missing, f"add these classes to docs/DOMAIN_README.md: {missing}"


def test_class_diagrams_show_every_modelled_class():
    puml = (ROOT / "docs" / "class_diagram.puml").read_text(encoding="utf-8")
    missing = [name for file, name in public_classes()
               if file not in NOT_DIAGRAMMED and not re.search(rf"\b{name}\b", puml)]
    assert not missing, f"add these classes to scripts/generate_class_diagrams.py and regenerate: {missing}"


def test_patterns_document_names_the_patterns_and_concepts_it_must_cover():
    text = (ROOT / "docs" / "oop_and_patterns.md").read_text(encoding="utf-8")
    for word in ("Encapsulation", "Abstraction", "Inheritance", "Polymorphism", "Interfaces", "Composition",
                 "Association", "Exception handling", "Collections", "State", "Strategy", "Observer"):
        assert word in text, word
