from fastapi.testclient import TestClient
from app.main import app  # Importa la instancia principal de FastAPI

client = TestClient(app)

def test_health_check():
    """Prueba mínima para validar que la API responde."""
    response = client.get("/")  # O el endpoint inicial/salud que tengan configurado
    # Valida respuesta exitosa o al menos que no colapse el servidor
    assert response.status_code == 200

def test_placeholder():
    """Asegura que pytest detecte una aserción válida."""
    assert True