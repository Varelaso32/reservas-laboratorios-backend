"""Pruebas del horario institucional al crear solicitudes (07:00 a 22:00, todos los días)."""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.core.database import SessionLocal
from app.models.enums import TipoEspacio
from app.models.modelos import Espacio
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera


URL = "/api/v1/solicitudes/"


def _crear_espacio() -> int:
    with SessionLocal() as db:
        espacio = Espacio(nombre=f"Horario {uuid4().hex}", tipo=TipoEspacio.SALA, capacidad=10)
        db.add(espacio)
        db.commit()
        return espacio.id


def _proximo_domingo() -> str:
    hoy = datetime.now(ZONA_COLOMBIA).date()
    return (hoy + timedelta(days=(6 - hoy.weekday()) or 7)).isoformat()


def _cuerpo(espacio_id: int, fecha: str, inicio: str, fin: str) -> dict:
    return {
        "espacio_id": espacio_id,
        "fecha": fecha,
        "hora_inicio": inicio,
        "hora_fin": fin,
        "proposito": "Prueba de horario",
        "asistentes": 2,
    }


@pytest.mark.parametrize("inicio, fin", [("06:30", "08:00"), ("21:00", "23:00"), ("06:00", "23:00")])
def test_no_se_puede_reservar_fuera_del_horario(client, solicitante, inicio, fin):
    espacio_id = _crear_espacio()

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _proximo_domingo(), inicio, fin), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 422
    assert "07:00" in respuesta.json()["detail"]


def test_se_puede_reservar_cualquier_dia_dentro_del_horario(client, solicitante):
    espacio_id = _crear_espacio()

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _proximo_domingo(), "07:00", "22:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201


def test_otro_usuario_no_puede_pedir_horario_con_solicitud_pendiente(client, solicitante, crear_usuario):
    espacio_id = _crear_espacio()
    otro = crear_usuario("otro-solicitante@reservas.test")
    fecha = _proximo_domingo()

    primera = client.post(URL, json=_cuerpo(espacio_id, fecha, "08:00", "10:00"), headers=cabecera(solicitante))
    cruzada = client.post(URL, json=_cuerpo(espacio_id, fecha, "09:00", "11:00"), headers=cabecera(otro))

    assert primera.status_code == 201
    assert cruzada.status_code == 409
    # No se revela el número de la solicitud de otra persona
    assert "#" not in cruzada.json()["detail"]


def test_mismo_usuario_recibe_el_numero_de_su_solicitud(client, solicitante):
    espacio_id = _crear_espacio()
    fecha = _proximo_domingo()

    primera = client.post(URL, json=_cuerpo(espacio_id, fecha, "08:00", "10:00"), headers=cabecera(solicitante))
    repetida = client.post(URL, json=_cuerpo(espacio_id, fecha, "08:00", "10:00"), headers=cabecera(solicitante))

    assert repetida.status_code == 409
    assert f"#{primera.json()['id']}" in repetida.json()["detail"]


def test_horarios_contiguos_u_otro_espacio_no_se_bloquean(client, solicitante, crear_usuario):
    espacio_id = _crear_espacio()
    otro_espacio = _crear_espacio()
    otro = crear_usuario("contiguo@reservas.test")
    fecha = _proximo_domingo()

    client.post(URL, json=_cuerpo(espacio_id, fecha, "08:00", "10:00"), headers=cabecera(solicitante))
    contigua = client.post(URL, json=_cuerpo(espacio_id, fecha, "10:00", "12:00"), headers=cabecera(otro))
    en_otro_espacio = client.post(URL, json=_cuerpo(otro_espacio, fecha, "08:00", "10:00"), headers=cabecera(otro))

    assert contigua.status_code == 201
    assert en_otro_espacio.status_code == 201
