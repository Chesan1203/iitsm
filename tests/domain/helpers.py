from datetime import datetime

from app.domain.enums import Level
from app.domain.models.category import Category
from app.domain.models.incident import Incident
from app.domain.models.it_service import ITService
from app.domain.models.user import Employee, Technician

T0 = datetime(2026, 11, 14, 10, 5)


def make_incident() -> Incident:
    emp = Employee("emp1", "Asha Rao", "asha@x.com", "hash", "Finance", id=1)
    cat = Category("Database", "DB issues", "Database", id=1)
    svc = ITService("Payment", "Payments", Level.HIGH, id=1)
    return Incident("Payment down", "Cannot pay", emp, cat, svc, Level.HIGH, Level.HIGH, 120, T0)


def make_technician() -> Technician:
    return Technician("tech1", "Ravi K", "ravi@x.com", "hash", {"Database"}, 4, id=2)
