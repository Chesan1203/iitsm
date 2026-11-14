"""Enforces the layering rules (plan section 3.2) by scanning imports with `ast`.

domain       -> standard library only (no sqlite3, sockets, http, threads, ...)
ports        -> standard library + domain
persistence  -> domain, ports, bcrypt (+ stdlib incl. sqlite3)
services     -> domain, ports, bcrypt, apscheduler. Only services/wiring.py may import persistence
web          -> ports; from domain only enums, exceptions and models; fastapi stack
config       -> standard library only
sqlite3 appears only inside persistence. app/main.py is the composition entry point and is exempt.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
STDLIB = set(sys.stdlib_module_names)

DOMAIN_FORBIDDEN_STDLIB = {"sqlite3", "socket", "http", "urllib", "smtplib", "threading", "asyncio"}
WEB_DOMAIN_ALLOWED = ("app.domain.enums", "app.domain.exceptions", "app.domain.models")

RULES = {
    "domain": {"internal": ("app.domain",), "third_party": set()},
    "ports": {"internal": ("app.domain", "app.ports"), "third_party": set()},
    "persistence": {"internal": ("app.domain", "app.ports", "app.persistence", "app.config"),
                    "third_party": {"bcrypt"}},
    "services": {"internal": ("app.domain", "app.ports", "app.services", "app.config"),
                 "third_party": {"bcrypt", "apscheduler"}},
    "web": {"internal": ("app.ports", "app.web", "app.config") + WEB_DOMAIN_ALLOWED,
            "third_party": {"fastapi", "starlette", "jinja2", "pydantic", "itsdangerous"}},
    "config": {"internal": ("app.config",), "third_party": set()},
}
EXEMPT_FILES = {"app/main.py", "app/__init__.py"}
EXTRA_INTERNAL = {"app/services/wiring.py": ("app.persistence",)}
CLOCK_EXEMPT = {"app/domain/time_provider.py"}


def _matches(full: str, prefixes) -> bool:
    return any(full == p or full.startswith(p + ".") for p in prefixes)


def _layer(rel_path: str) -> str | None:
    parts = rel_path.split("/")
    if parts[0] != "app" or len(parts) < 2:
        return None
    if parts[1] in RULES:
        return parts[1]
    if parts[1] == "config.py":
        return "config"
    return None


def _package_of(rel_path: str) -> list[str]:
    parts = rel_path[:-3].split("/")           # strip .py
    return parts if parts[-1] == "__init__" and parts.pop() else parts[:-1]


def _imports(rel_path: str, tree: ast.AST):
    """Yield (lineno, top_level_module, full_dotted_name) for every import in the file."""
    package = _package_of(rel_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0], alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package[: len(package) - (node.level - 1)]
                base = ".".join(base_parts + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            for alias in node.names:
                yield node.lineno, base.split(".")[0], f"{base}.{alias.name}"


def check_source(rel_path: str, source: str) -> list[str]:
    if rel_path in EXEMPT_FILES:
        return []
    layer = _layer(rel_path)
    if layer is None:
        return [f"{rel_path}: file is outside every known layer"]
    rules = RULES[layer]
    internal = rules["internal"] + EXTRA_INTERNAL.get(rel_path, ())
    problems = []
    for lineno, top, full in _imports(rel_path, ast.parse(source)):
        where = f"{rel_path}:{lineno}: {layer} must not import {full}"
        if top == "app":
            if not _matches(full, internal):
                problems.append(where)
        elif top in STDLIB:
            if top == "sqlite3" and layer != "persistence":
                problems.append(where + " (SQL belongs in persistence)")
            elif layer == "domain" and top in DOMAIN_FORBIDDEN_STDLIB:
                problems.append(where + " (domain is pure business logic)")
        elif top not in rules["third_party"]:
            problems.append(where + " (third-party library not allowed here)")
    return problems


def check_domain_clock_and_setters(rel_path: str, source: str) -> list[str]:
    if not rel_path.startswith("app/domain/"):
        return []
    problems = []
    for node in ast.walk(ast.parse(source)):
        if (rel_path not in CLOCK_EXEMPT and isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"now", "today", "utcnow"}):
            problems.append(f"{rel_path}:{node.lineno}: domain code must not read the clock; "
                            f"take `at`/`now` as a parameter")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Attribute) and dec.attr == "setter":
                    problems.append(f"{rel_path}:{node.lineno}: setters are not allowed; "
                                    f"change state through behaviour methods")
    return problems


def _app_files():
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")


# ---- the real checks -------------------------------------------------------

def test_layer_import_rules_hold():
    problems = [p for rel, src in _app_files() for p in check_source(rel, src)]
    assert not problems, "\n" + "\n".join(problems)


def test_domain_never_reads_the_clock_and_has_no_setters():
    problems = [p for rel, src in _app_files() for p in check_domain_clock_and_setters(rel, src)]
    assert not problems, "\n" + "\n".join(problems)


def test_every_code_folder_is_a_package():
    missing = [str(d.relative_to(ROOT)) for base in (APP, ROOT / "tests")
               for d in [base, *base.rglob("*")]
               if d.is_dir() and "__pycache__" not in d.parts
               and any(f.suffix == ".py" for f in d.iterdir()) and not (d / "__init__.py").exists()]
    assert not missing, f"missing __init__.py in: {missing}"


# ---- the checker itself must catch violations ------------------------------

def test_checker_flags_domain_importing_framework_or_sql():
    assert check_source("app/domain/x.py", "import fastapi")
    assert check_source("app/domain/x.py", "import sqlite3")
    assert check_source("app/domain/x.py", "from app.ports import dto")
    assert not check_source("app/domain/x.py", "from datetime import datetime\nfrom app.domain.enums import Role")


def test_checker_flags_services_and_web_crossing_layers():
    assert check_source("app/services/impl/a.py", "from app.persistence.database import Database")
    assert not check_source("app/services/wiring.py", "from app.persistence.database import Database")
    assert check_source("app/web/routes/a.py", "from app.services.impl import auth_service")
    assert check_source("app/web/routes/a.py", "from app.domain.state import states")
    assert check_source("app/web/routes/a.py", "from app.domain import strategies")
    assert not check_source("app/web/routes/a.py", "from app.domain.enums import Role\nfrom app.domain.models.incident import Incident")
    assert check_source("app/ports/a.py", "from app.persistence import x")


def test_checker_resolves_relative_imports():
    assert check_source("app/services/impl/a.py", "from ...persistence import database")
    assert check_source("app/domain/models/a.py", "from ...web import errors")
    assert not check_source("app/domain/models/a.py", "from . import user\nfrom ..enums import Role")


def test_checker_flags_sqlite_outside_persistence_only():
    assert check_source("app/services/impl/a.py", "import sqlite3")
    assert not check_source("app/persistence/database.py", "import sqlite3")


def test_clock_and_setter_checker_catches_violations():
    bad_clock = "from datetime import datetime\ndef f():\n    return datetime.now()"
    assert check_domain_clock_and_setters("app/domain/x.py", bad_clock)
    assert not check_domain_clock_and_setters("app/domain/time_provider.py", bad_clock)
    bad_setter = "class A:\n    @property\n    def x(self): ...\n    @x.setter\n    def x(self, v): ..."
    assert check_domain_clock_and_setters("app/domain/x.py", bad_setter)
