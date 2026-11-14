"""Composition root for real mode (P3 fills this in at task T7)."""
from app.config import Settings
from app.ports.container import Container


def build_real_container(settings: Settings) -> Container:
    # Placeholder: returns an empty container until P3 wires the real services.
    return Container()
