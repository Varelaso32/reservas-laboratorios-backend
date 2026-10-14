"""SCRUM-205: Swagger debe mostrar enmascarada la clave del login.

Swagger UI usa <input type="password"> cuando el esquema del campo tiene
format: password. Esta prueba evita que un cambio en el login lo rompa.
"""
from app.main import app


def test_password_del_login_tiene_formato_password(client):
    esquema = client.get(app.openapi_url).json()
    cuerpo = esquema["paths"]["/api/v1/auth/login"]["post"]["requestBody"]["content"]
    ref = cuerpo["application/x-www-form-urlencoded"]["schema"]["$ref"].split("/")[-1]
    campos = esquema["components"]["schemas"][ref]["properties"]

    assert campos["password"]["format"] == "password"
