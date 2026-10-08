"""Pruebas de las operaciones de /api/v1/reservas."""
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.enums import AccionTrazabilidad, EstadoReserva, EstadoSolicitud, Rol, TipoEspacio
from app.models.modelos import Espacio, Reserva, Solicitud, Trazabilidad, espacio_aprobador
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera


URL = "/api/v1/reservas"


def _crear_reserva(usuario, inicio: datetime):
    with SessionLocal() as db:
        espacio = Espacio(
            nombre=f"Laboratorio de prueba {uuid4().hex}",
            tipo=TipoEspacio.LABORATORIO,
            capacidad=20,
            ubicacion="Bloque A",
        )
        db.add(espacio)
        db.flush()

        solicitud = Solicitud(
            solicitante_id=usuario.id,
            espacio_id=espacio.id,
            inicio=inicio,
            fin=inicio + timedelta(hours=1),
            proposito="Prueba",
            asistentes=2,
            estado=EstadoSolicitud.APROBADA,
            decidido_por=usuario.id,
            fecha_decision=datetime.now(ZONA_COLOMBIA),
        )
        db.add(solicitud)
        db.flush()

        reserva = Reserva(
            solicitud_id=solicitud.id,
            espacio_id=espacio.id,
            usuario_id=usuario.id,
            inicio=solicitud.inicio,
            fin=solicitud.fin,
            estado=EstadoReserva.ACTIVA,
        )
        db.add(reserva)
        db.commit()
        return reserva.id, solicitud.id


def test_solicitante_cancela_reserva_propia_y_registra_historial(client, solicitante):
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(hours=2)
    reserva_id, solicitud_id = _crear_reserva(solicitante, inicio)

    respuesta = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(solicitante))

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "CANCELADA"
    with SessionLocal() as db:
        assert db.get(Reserva, reserva_id).estado == EstadoReserva.CANCELADA
        assert db.get(Solicitud, solicitud_id).estado == EstadoSolicitud.CANCELADA
        acciones = db.scalars(
            select(Trazabilidad).where(Trazabilidad.reserva_id == reserva_id)
        ).all()
    assert len(acciones) == 1
    assert acciones[0].accion == AccionTrazabilidad.CANCELADA


def test_cancelar_reserva_ya_cancelada_es_idempotente(client, solicitante):
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(hours=2)
    reserva_id, _ = _crear_reserva(solicitante, inicio)
    primera = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(solicitante))
    segunda = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(solicitante))

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert segunda.json()["estado"] == "CANCELADA"
    with SessionLocal() as db:
        cantidad = len(db.scalars(
            select(Trazabilidad).where(
                Trazabilidad.reserva_id == reserva_id,
                Trazabilidad.accion == AccionTrazabilidad.CANCELADA,
            )
        ).all())
    assert cantidad == 1


def test_solicitante_no_puede_cancelar_reserva_ajena(client, solicitante, crear_usuario):
    otra_persona = crear_usuario("otra@reservas.test")
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(hours=2)
    reserva_id, _ = _crear_reserva(otra_persona, inicio)

    respuesta = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(solicitante))

    assert respuesta.status_code == 404
    with SessionLocal() as db:
        assert db.get(Reserva, reserva_id).estado == EstadoReserva.ACTIVA
        assert db.scalar(
            select(Trazabilidad.id).where(Trazabilidad.reserva_id == reserva_id)
        ) is None


def test_no_se_puede_cancelar_reserva_que_ya_inicio(client, solicitante):
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=30)
    reserva_id, _ = _crear_reserva(solicitante, inicio)

    respuesta = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(solicitante))

    assert respuesta.status_code == 409
    with SessionLocal() as db:
        assert db.get(Reserva, reserva_id).estado == EstadoReserva.ACTIVA
        assert db.scalar(
            select(Trazabilidad.id).where(Trazabilidad.reserva_id == reserva_id)
        ) is None


def test_solo_solicitante_puede_cancelar_reserva(client, crear_usuario):
    aprobador = crear_usuario("aprobador@reservas.test", Rol.APROBADOR)
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(hours=2)
    reserva_id, _ = _crear_reserva(aprobador, inicio)

    respuesta = client.post(f"{URL}/{reserva_id}/cancelar", headers=cabecera(aprobador))

    assert respuesta.status_code == 403


def test_mias_incluye_canceladas_solo_si_se_pide(client, solicitante):
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(hours=3)
    activa_id, _ = _crear_reserva(solicitante, inicio)
    cancelada_id, _ = _crear_reserva(solicitante, inicio + timedelta(days=1))
    client.post(f"{URL}/{cancelada_id}/cancelar", headers=cabecera(solicitante))

    por_defecto = client.get(f"{URL}/mias", headers=cabecera(solicitante))
    con_canceladas = client.get(f"{URL}/mias?incluir_canceladas=true", headers=cabecera(solicitante))

    assert [r["id"] for r in por_defecto.json()] == [activa_id]
    assert [(r["id"], r["estado"]) for r in con_canceladas.json()] == [
        (activa_id, "ACTIVA"),
        (cancelada_id, "CANCELADA"),
    ]


def _asignar(espacio_id: int, aprobador_id: int):
    with SessionLocal() as db:
        db.execute(espacio_aprobador.insert().values(espacio_id=espacio_id, usuario_id=aprobador_id))
        db.commit()


def _espacio_de(reserva_id: int) -> int:
    with SessionLocal() as db:
        return db.get(Reserva, reserva_id).espacio_id


def test_agenda_admin_ve_reservas_del_dia_de_todos(client, admin, solicitante):
    manana = (datetime.now(ZONA_COLOMBIA) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    primera, _ = _crear_reserva(solicitante, manana)
    segunda, _ = _crear_reserva(solicitante, manana + timedelta(hours=2))
    otro_dia, _ = _crear_reserva(solicitante, manana + timedelta(days=3))
    cancelada, _ = _crear_reserva(solicitante, manana + timedelta(hours=4))
    client.post(f"{URL}/{cancelada}/cancelar", headers=cabecera(solicitante))

    respuesta = client.get(f"{URL}/?fecha={manana.date().isoformat()}", headers=cabecera(admin))

    assert respuesta.status_code == 200
    reservas = respuesta.json()
    assert [r["id"] for r in reservas] == [primera, segunda]
    assert reservas[0]["titular"] == solicitante.nombre
    assert reservas[0]["proposito"] == "Prueba"


def test_agenda_por_rango_para_el_calendario(client, admin, solicitante):
    lunes = (datetime.now(ZONA_COLOMBIA) + timedelta(days=7)).replace(hour=10, minute=0, second=0, microsecond=0)
    dentro, _ = _crear_reserva(solicitante, lunes + timedelta(days=2))
    _crear_reserva(solicitante, lunes + timedelta(days=9))
    desde = lunes.date().isoformat()
    hasta = (lunes + timedelta(days=6)).date().isoformat()

    respuesta = client.get(f"{URL}/?fecha_inicio={desde}&fecha_fin={hasta}", headers=cabecera(admin))

    assert [r["id"] for r in respuesta.json()] == [dentro]


def test_agenda_aprobador_ve_solo_sus_espacios(client, solicitante, crear_usuario):
    aprobador = crear_usuario("coordinador-agenda@reservas.test", Rol.APROBADOR)
    manana = (datetime.now(ZONA_COLOMBIA) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    propia, _ = _crear_reserva(solicitante, manana)
    _crear_reserva(solicitante, manana)
    _asignar(_espacio_de(propia), aprobador.id)

    respuesta = client.get(f"{URL}/?fecha={manana.date().isoformat()}", headers=cabecera(aprobador))

    assert [r["id"] for r in respuesta.json()] == [propia]


def test_agenda_valida_parametros_y_rol(client, admin, solicitante):
    def consultar(parametros, usuario=admin):
        return client.get(f"{URL}/?{parametros}", headers=cabecera(usuario)).status_code

    assert consultar("") == 200
    assert consultar("fecha=2026-10-08&fecha_inicio=2026-10-08&fecha_fin=2026-10-09") == 422
    assert consultar("fecha_inicio=2026-10-08") == 422
    assert consultar("fecha_inicio=2026-10-09&fecha_fin=2026-10-08") == 422
    assert consultar("fecha_inicio=2026-01-01&fecha_fin=2026-12-31") == 422
    assert consultar("fecha=2026-10-08", solicitante) == 403
