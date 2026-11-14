"""Composition root for stub mode (P4 fills this in at task T1)."""
from app.ports.container import Container


def build_stub_container() -> Container:
    # Placeholder: returns an empty container until P4 writes the stub services.
    return Container()
