from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_responde_200():
    """El endpoint raiz responde con un mensaje de bienvenida."""
    response = client.get("/")
    assert response.status_code == 200


def test_root_devuelve_mensaje_de_bienvenida():
    """El cuerpo del endpoint raiz incluye el campo message con texto."""
    response = client.get("/")
    cuerpo = response.json()
    assert "message" in cuerpo
    assert isinstance(cuerpo["message"], str)
    assert cuerpo["message"]
