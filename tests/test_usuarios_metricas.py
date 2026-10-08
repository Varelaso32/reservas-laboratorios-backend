"""Pruebas del conteo mensual incluido en GET /api/v1/usuarios/."""
from datetime import datetime, timedelta
from uuid import uuid4

from app.core.database import SessionLocal
from app.models.enums import EstadoReserva, EstadoSolicitud, TipoEspacio
from app.models.modelos import Espacio, Reserva, Solicitud
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera


URL = "/api/v1/usuarios/"


def _crear_espacio() -> int:
    with SessionLocal() as db:
        espacio = Espacio(
            nombre=f"Conteo mensual {uuid4().hex}",
            tipo=TipoEspacio.LABORATORIO,
            capacidad=10,
        )
        db.add(espacio)
        db.commit()
        return espacio.id


def _crear_reserva(espacio_id: int, usuario_id: int, inicio: datetime, estado: EstadoReserva) -> None:
    fin = inicio + timedelta(hours=1)
    with SessionLocal() as db:
        solicitud = Solicitud(
            solicitante_id=usuario_id,
            espacio_id=espacio_id,
            inicio=inicio,
            fin=fin,
            proposito="Prueba del conteo mensual",
            asistentes=1,
            estado=EstadoSolicitud.APROBADA,
            decidido_por=usuario_id,
            fecha_decision=datetime.now(ZONA_COLOMBIA),
        )
        db.add(solicitud)
        db.flush()
        db.add(
            Reserva(
                solicitud_id=solicitud.id,
                espacio_id=espacio_id,
                usuario_id=usuario_id,
                inicio=inicio,
                fin=fin,
                estado=estado,
            )
        )
        db.commit()


def test_lista_admin_incluye_reservas_activas_del_mes_y_omite_canceladas(
    client, admin, solicitante, crear_usuario
):
    otro_solicitante = crear_usuario("otro-conteo@reservas.test")
    espacio_id = _crear_espacio()
    ahora = datetime.now(ZONA_COLOMBIA)
    inicio_mes = datetime(ahora.year, ahora.month, 1, 10, tzinfo=ZONA_COLOMBIA)
    if ahora.month == 12:
        inicio_mes_siguiente = datetime(ahora.year + 1, 1, 1, tzinfo=ZONA_COLOMBIA)
    else:
        inicio_mes_siguiente = datetime(ahora.year, ahora.month + 1, 1, tzinfo=ZONA_COLOMBIA)

    _crear_reserva(espacio_id, solicitante.id, inicio_mes, EstadoReserva.ACTIVA)
    _crear_reserva(
        espacio_id,
        solicitante.id,
        inicio_mes + timedelta(days=1),
        EstadoReserva.CANCELADA,
    )
    _crear_reserva(
        espacio_id,
        solicitante.id,
        inicio_mes_siguiente,
        EstadoReserva.ACTIVA,
    )
    _crear_reserva(
        espacio_id,
        otro_solicitante.id,
        inicio_mes + timedelta(days=2),
        EstadoReserva.ACTIVA,
    )

    respuesta = client.get(
        URL,
        params={"rol": "SOLICITANTE", "activo": True},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    usuarios_por_id = {usuario["id"]: usuario for usuario in respuesta.json()["items"]}
    assert usuarios_por_id[solicitante.id]["reservas_mes"] == 1
    assert usuarios_por_id[otro_solicitante.id]["reservas_mes"] == 1


def test_usuario_sin_reservas_tiene_conteo_cero(client, admin, solicitante):
    respuesta = client.get(URL, headers=cabecera(admin))

    assert respuesta.status_code == 200
    usuario = next(item for item in respuesta.json()["items"] if item["id"] == solicitante.id)
    assert usuario["reservas_mes"] == 0
