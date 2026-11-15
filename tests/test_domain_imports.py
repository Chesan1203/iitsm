"""Every domain module must import on its own, in a fresh interpreter. Catches circular imports
that only show up for one particular import order."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _modules():
    for path in sorted((ROOT / "app" / "domain").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        parts = path.relative_to(ROOT).with_suffix("").parts
        yield ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def test_every_domain_module_imports_standalone():
    failures = []
    for module in _modules():
        result = subprocess.run([sys.executable, "-W", "error", "-c", f"import {module}"],
                                cwd=ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            failures.append(f"{module}: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else '?'}")
    assert not failures, "\n" + "\n".join(failures)
