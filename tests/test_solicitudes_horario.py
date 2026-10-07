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
