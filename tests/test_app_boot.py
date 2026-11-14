from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.ports.container import Container


def test_app_boots_in_both_modes_and_exposes_a_container():
    for mode in ("real", "stub"):
        app = create_app(Settings(ITSM_MODE=mode, ENABLE_SCHEDULER=False))
        assert isinstance(app.state.container, Container)
        response = TestClient(app).get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "mode": mode}
