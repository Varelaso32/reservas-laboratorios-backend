"""Pruebas de GET /api/v1/espacios/metricas."""
from datetime import date, datetime, time
from uuid import uuid4

from app.core.database import SessionLocal
from app.models.enums import EstadoReserva, EstadoSolicitud, TipoEspacio
from app.models.modelos import Espacio, Reserva, Solicitud
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera


URL = "/api/v1/espacios/metricas"


def _crear_espacio(nombre: str, activo: bool = True) -> Espacio:
    with SessionLocal() as db:
        espacio = Espacio(
            nombre=f"{nombre} {uuid4().hex}",
            tipo=TipoEspacio.LABORATORIO,
            capacidad=20,
            ubicacion="Bloque A",
            activo=activo,
        )
        db.add(espacio)
        db.flush()
        return_id = espacio.id
        db.commit()
        return db.get(Espacio, return_id)


def _crear_reserva(espacio_id: int, usuario_id: int, inicio: datetime, fin: datetime, estado: EstadoReserva):
    with SessionLocal() as db:
        solicitud = Solicitud(
            solicitante_id=usuario_id,
            espacio_id=espacio_id,
            inicio=inicio,
            fin=fin,
            proposito="Prueba de métricas",
            asistentes=2,
            estado=EstadoSolicitud.APROBADA,
            decidido_por=usuario_id,
            fecha_decision=datetime.now(ZONA_COLOMBIA),
        )
        db.add(solicitud)
        db.flush()
        reserva = Reserva(
            solicitud_id=solicitud.id,
            espacio_id=espacio_id,
            usuario_id=usuario_id,
            inicio=inicio,
            fin=fin,
            estado=estado,
        )
        db.add(reserva)
        db.commit()


def test_admin_consulta_metricas_agregadas_y_excluye_canceladas(client, admin, solicitante):
    fecha = date(2026, 10, 6)
    espacio = _crear_espacio("Metricas")
    _crear_reserva(
        espacio.id,
        solicitante.id,
        datetime.combine(fecha, time(6, 30), ZONA_COLOMBIA),
        datetime.combine(fecha, time(8), ZONA_COLOMBIA),
        EstadoReserva.ACTIVA,
    )
    _crear_reserva(
        espacio.id,
        solicitante.id,
        datetime.combine(fecha, time(9), ZONA_COLOMBIA),
        datetime.combine(fecha, time(10), ZONA_COLOMBIA),
        EstadoReserva.CANCELADA,
    )
    _crear_reserva(
        espacio.id,
        solicitante.id,
        datetime.combine(fecha, time(21, 30), ZONA_COLOMBIA),
        datetime.combine(fecha, time(22, 30), ZONA_COLOMBIA),
        EstadoReserva.ACTIVA,
    )

    respuesta = client.get(f"{URL}?fecha={fecha.isoformat()}", headers=cabecera(admin))

    assert respuesta.status_code == 200
    fila = next(item for item in respuesta.json() if item["id"] == espacio.id)
    assert fila["reservas_dia"] == 2
    assert fila["minutos_reservados"] == 90
    assert fila["minutos_disponibles"] == 900
    assert fila["porcentaje_ocupacion"] == 10
    assert fila["activo"] is True


def test_porcentaje_es_null_si_espacio_inactivo_o_dia_cerrado(client, admin):
    domingo = date(2026, 10, 11)
    espacio = _crear_espacio("Inactivo", activo=False)

    respuesta = client.get(f"{URL}?fecha={domingo.isoformat()}", headers=cabecera(admin))

    assert respuesta.status_code == 200
    fila = next(item for item in respuesta.json() if item["id"] == espacio.id)
    assert fila["reservas_dia"] == 0
    assert fila["minutos_disponibles"] == 0
    assert fila["porcentaje_ocupacion"] is None


def test_metricas_solo_disponibles_para_admin(client, solicitante):
    respuesta = client.get(
        f"{URL}?fecha={date(2026, 10, 6).isoformat()}",
        headers=cabecera(solicitante),
    )

    assert respuesta.status_code == 403
