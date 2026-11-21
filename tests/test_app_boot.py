from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.ports.container import Container


def test_app_boots_in_both_modes_and_exposes_a_container(tmp_path):
    for mode in ("real", "stub"):
        settings = Settings(ITSM_MODE=mode, DATABASE_PATH=str(tmp_path / f"{mode}.db"),
                            EMAIL_LOG_PATH=str(tmp_path / f"{mode}.log"),
                            ENABLE_SCHEDULER=False, SEED_DEMO_DATA=False)
        app = create_app(settings)
        assert isinstance(app.state.container, Container)
        response = TestClient(app).get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "mode": mode}
