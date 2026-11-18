"""Recursos tecnológicos asociados a una reserva (HU-43 a HU-46).

Cubre:
- HU-43: inventario, identificador único, estado con comentario y permisos.
- HU-44: solicitud ligada a una reserva, disponibilidad por horario y bloqueo.
- HU-45: aprobación por orden de llegada, stock y asignación atómica.
- HU-46: entrega, devolución y penalización doble por retraso.
"""
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.enums import (
    AccionTrazabilidad,
    Cargo,
    EstadoReserva,
    EstadoSolicitud,
    EstadoSolicitudRecurso,
    Rol,
    TipoEspacio,
    TipoNotificacion,
)
from app.models.modelos import (
    AsignacionRecurso,
    Espacio,
    Notificacion,
    Recurso,
    Reserva,
    Solicitud,
    SolicitudRecurso,
    Strike,
    Trazabilidad,
)
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera

RECURSOS = "/api/v1/recursos"
RESERVAS = "/api/v1/reservas"


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _crear_espacio() -> int:
    with SessionLocal() as db:
        espacio = Espacio(
            nombre=f"Espacio {uuid4().hex}",
            tipo=TipoEspacio.LABORATORIO,
            capacidad=20,
            ubicacion="Bloque A",
        )
        db.add(espacio)
        db.commit()
        return espacio.id


def _crear_reserva(usuario, inicio: datetime) -> tuple[int, int]:
    with SessionLocal() as db:
        espacio_id = _crear_espacio()
        solicitud = Solicitud(
            solicitante_id=usuario.id,
            espacio_id=espacio_id,
            inicio=inicio,
            fin=inicio + timedelta(hours=2),
            proposito="Prueba de recursos",
            asistentes=10,
            estado=EstadoSolicitud.APROBADA,
            decidido_por=usuario.id,
            fecha_decision=datetime.now(ZONA_COLOMBIA),
        )
        db.add(solicitud)
        db.flush()
        reserva = Reserva(
            solicitud_id=solicitud.id,
            espacio_id=espacio_id,
            usuario_id=usuario.id,
            inicio=solicitud.inicio,
            fin=solicitud.fin,
            estado=EstadoReserva.ACTIVA,
        )
        db.add(reserva)
        db.commit()
        return reserva.id, solicitud.id


def _tipo(client, admin, nombre: str = "Video beam") -> int:
    respuesta = client.post(
        f"{RECURSOS}/tipos",
        json={"nombre": f"{nombre} {uuid4().hex[:6]}"},
        headers=cabecera(admin),
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id"]


def _unidad(client, admin, tipo_id: int, codigo: str | None = None) -> dict:
    respuesta = client.post(
        f"{RECURSOS}/",
        json={
            "tipo_recurso_id": tipo_id,
            "codigo": codigo or f"VB-{uuid4().hex[:6].upper()}",
            "descripcion": "Unidad de prueba",
        },
        headers=cabecera(admin),
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _solicitar(client, usuario, reserva_id: int, tipo_id: int, cantidad: int):
    return client.post(
        f"{RECURSOS}/solicitudes",
        json={
            "reserva_id": reserva_id,
            "detalle": [{"tipo_recurso_id": tipo_id, "cantidad": cantidad}],
        },
        headers=cabecera(usuario),
    )


def _asignaciones(solicitud_id: int) -> list[AsignacionRecurso]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AsignacionRecurso).where(
                    AsignacionRecurso.solicitud_recurso_id == solicitud_id
                )
            )
        )


def _solicitud(solicitud_id: int) -> SolicitudRecurso:
    with SessionLocal() as db:
        return db.get(SolicitudRecurso, solicitud_id)


def _strikes(usuario_id: int) -> list[Strike]:
    with SessionLocal() as db:
        return list(
            db.scalars(select(Strike).where(Strike.usuario_id == usuario_id))
        )


# --------------------------------------------------------------------------- #
# HU-43: inventario
# --------------------------------------------------------------------------- #
def test_solo_el_admin_gestiona_el_inventario(client, admin, solicitante):
    respuesta = client.post(
        f"{RECURSOS}/tipos",
        json={"nombre": "Cámara"},
        headers=cabecera(solicitante),
    )
    assert respuesta.status_code == 403

    tipo_id = _tipo(client, admin)
    repetido = client.post(
        f"{RECURSOS}/tipos",
        json={"nombre": client.get(f"{RECURSOS}/tipos", headers=cabecera(admin)).json()[0]["nombre"]},
        headers=cabecera(admin),
    )
    assert repetido.status_code == 409

    unidad = _unidad(client, admin, tipo_id, "VB-UNICA")
    otra = client.post(
        f"{RECURSOS}/",
        json={"tipo_recurso_id": tipo_id, "codigo": "vb-unica"},
        headers=cabecera(admin),
    )
    assert otra.status_code == 409, "el identificador no distingue mayúsculas"

    inventario = client.get(f"{RECURSOS}/inventario", headers=cabecera(admin))
    assert inventario.status_code == 200
    assert inventario.json()[0]["codigo"] == unidad["codigo"]


def test_cambiar_estado_exige_comentario(client, admin):
    tipo_id = _tipo(client, admin)
    unidad = _unidad(client, admin, tipo_id)

    sin_comentario = client.patch(
        f"{RECURSOS}/{unidad['id']}/estado",
        json={"estado": "FALLIDO"},
        headers=cabecera(admin),
    )
    assert sin_comentario.status_code == 422

    cambio = client.patch(
        f"{RECURSOS}/{unidad['id']}/estado",
        json={"estado": "FALLIDO", "comentario": "No enciende"},
        headers=cabecera(admin),
    )
    assert cambio.status_code == 200
    assert cambio.json()["estado"] == "FALLIDO"
    assert cambio.json()["comentario_estado"] == "No enciende"


def test_una_unidad_fallida_no_se_asigna(client, admin, crear_usuario):
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    tipo_id = _tipo(client, admin)
    rota = _unidad(client, admin, tipo_id, "VB-ROTA")
    client.patch(
        f"{RECURSOS}/{rota['id']}/estado",
        json={"estado": "FALLIDO", "comentario": "Lente rayado"},
        headers=cabecera(admin),
    )
    sana = _unidad(client, admin, tipo_id, "VB-SANA")

    reserva_id, _ = _crear_reserva(docente, datetime.now(ZONA_COLOMBIA) + timedelta(days=1))
    respuesta = _solicitar(client, docente, reserva_id, tipo_id, 1)
    assert respuesta.status_code == 201
    solicitud_id = respuesta.json()["id"]

    decision = client.post(
        f"{RECURSOS}/solicitudes/{solicitud_id}/decision",
        json={"aprobar": True},
        headers=cabecera(admin),
    )
    assert decision.status_code == 200, decision.text
    asignadas = _asignaciones(solicitud_id)
    assert [asignacion.recurso_id for asignacion in asignadas] == [sana["id"]]


# --------------------------------------------------------------------------- #
# HU-44: solicitud
# --------------------------------------------------------------------------- #
def test_un_estudiante_no_puede_solicitar_recursos(client, admin, solicitante):
    tipo_id = _tipo(client, admin)
    _unidad(client, admin, tipo_id)
    reserva_id, _ = _crear_reserva(
        solicitante, datetime.now(ZONA_COLOMBIA) + timedelta(days=1)
    )

    assert client.get(f"{RECURSOS}/reservas-elegibles", headers=cabecera(solicitante)).json() == []
    respuesta = _solicitar(client, solicitante, reserva_id, tipo_id, 1)
    assert respuesta.status_code == 403


def test_solicitud_limita_la_cantidad_a_lo_disponible(client, admin, crear_usuario):
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    tipo_id = _tipo(client, admin)
    _unidad(client, admin, tipo_id, "VB-1")
    _unidad(client, admin, tipo_id, "VB-2")
    reserva_id, _ = _crear_reserva(
        docente, datetime.now(ZONA_COLOMBIA) + timedelta(days=1)
    )

    elegibles = client.get(f"{RECURSOS}/reservas-elegibles", headers=cabecera(docente))
    assert elegibles.status_code == 200
    assert elegibles.json()[0]["reserva_id"] == reserva_id

    disponibilidad = client.get(
        f"{RECURSOS}/disponibilidad",
        params={"reserva_id": reserva_id},
        headers=cabecera(docente),
    )
    assert disponibilidad.status_code == 200
    assert disponibilidad.json()["tipos"][0]["disponibles"] == 2

    excedida = _solicitar(client, docente, reserva_id, tipo_id, 3)
    assert excedida.status_code == 422
    assert "2 unidad" in excedida.json()["detail"]

    valida = _solicitar(client, docente, reserva_id, tipo_id, 2)
    assert valida.status_code == 201
    assert valida.json()["estado"] == "PENDIENTE"

    repetida = _solicitar(client, docente, reserva_id, tipo_id, 1)
    assert repetida.status_code == 409

    with SessionLocal() as db:
        avisos = list(
            db.scalars(
                select(Notificacion).where(
                    Notificacion.tipo == TipoNotificacion.RECURSO_SOLICITADO
                )
            )
        )
        assert len(avisos) == 1, "se avisa a los administradores"


def test_un_usuario_bloqueado_no_puede_solicitar(client, admin, crear_usuario):
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    tipo_id = _tipo(client, admin)
    _unidad(client, admin, tipo_id)
    reserva_id, reserva_solicitud_id = _crear_reserva(
        docente, datetime.now(ZONA_COLOMBIA) + timedelta(days=1)
    )
    with SessionLocal() as db:
        for _ in range(3):
            db.add(
                Strike(
                    usuario_id=docente.id,
                    reserva_id=reserva_id,
                    minutos_retraso=10,
                )
            )
        db.commit()

    respuesta = _solicitar(client, docente, reserva_id, tipo_id, 1)
    assert respuesta.status_code == 409
    assert "strikes" in respuesta.json()["detail"]


# --------------------------------------------------------------------------- #
# HU-45: aprobación
# --------------------------------------------------------------------------- #
def test_aprobar_asigna_unidades_y_descuenta_stock(client, admin, crear_usuario):
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    tipo_id = _tipo(client, admin)
    primera = _unidad(client, admin, tipo_id, "VB-1")
    _unidad(client, admin, tipo_id, "VB-2")
    reserva_id, _ = _crear_reserva(
        docente, datetime.now(ZONA_COLOMBIA) + timedelta(days=1)
    )

    solicitud_id = _solicitar(client, docente, reserva_id, tipo_id, 2).json()["id"]
    stock_antes = client.get(f"{RECURSOS}/stock", headers=cabecera(admin)).json()[0]
    assert stock_antes["disponibles"] == 2
    assert stock_antes["reservados"] == 0

    decision = client.post(
        f"{RECURSOS}/solicitudes/{solicitud_id}/decision",
        json={"aprobar": True},
        headers=cabecera(admin),
    )
    assert decision.status_code == 200, decision.text
    cuerpo = decision.json()
    assert cuerpo["estado"] == "APROBADA"
    assert len(cuerpo["asignaciones"]) == 2
    assert cuerpo["asignaciones"][0]["estado"] == "ASIGNADA"

    stock_despues = client.get(f"{RECURSOS}/stock", headers=cabecera(admin)).json()[0]
    assert stock_despues["disponibles"] == 0
    assert stock_despues["reservados"] == 2

    # Otra reserva en el mismo horario ya no tiene stock
    otra_reserva, _ = _crear_reserva(docente, datetime.now(ZONA_COLOMBIA) + timedelta(days=1))
    sin_stock = _solicitar(client, docente, otra_reserva, tipo_id, 1)
    assert sin_stock.status_code == 422

    # Entrega y devolución devuelven la unidad al inventario
    asignacion_id = cuerpo["asignaciones"][0]["id"]
    entrega = client.post(
        f"{RECURSOS}/asignaciones/{asignacion_id}/entrega", headers=cabecera(admin)
    )
    assert entrega.status_code == 200, entrega.text
    assert entrega.json()["asignaciones"][0]["entregada_en"] is not None

    devolucion = client.post(
        f"{RECURSOS}/asignaciones/{asignacion_id}/devolucion",
        json={"estado": "EN_FUNCIONAMIENTO", "comentario": "En buen estado"},
        headers=cabecera(admin),
    )
    assert devolucion.status_code == 200, devolucion.text
    assert devolucion.json()["asignaciones"][0]["estado"] == "DEVUELTA"

    stock_final = client.get(f"{RECURSOS}/stock", headers=cabecera(admin)).json()[0]
    assert stock_final["disponibles"] == 1
    assert stock_final["reservados"] == 1

    historial = client.get(
        f"{RECURSOS}/{primera['id']}/historial", headers=cabecera(admin)
    )
    assert historial.status_code == 200
    assert historial.json()[0]["estado"] == "DEVUELTA"


def test_rechazo_exige_motivo_y_avisa(client, admin, crear_usuario):
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    tipo_id = _tipo(client, admin)
    _unidad(client, admin, tipo_id)
    reserva_id, _ = _crear_reserva(
        docente, datetime.now(ZONA_COLOMBIA) + timedelta(days=1)
    )
    solicitud_id = _solicitar(client, docente, reserva_id, tipo_id, 1).json()["id"]

    sin_motivo = client.post(
        f"{RECURSOS}/solicitudes/{solicitud_id}/decision",
        json={"aprobar": False},
        headers=cabecera(admin),
    )
    assert sin_motivo.status_code == 422

    rechazo = client.post(
        f"{RECURSOS}/solicitudes/{solicitud_id}/decision",
        json={"aprobar": False, "motivo": "Sin disponibilidad para esa actividad"},
        headers=cabecera(admin),
    )
    assert rechazo.status_code == 200
    assert rechazo.json()["estado"] == "RECHAZADA"
    assert "Sin disponibilidad" in rechazo.json()["motivo_rechazo"]

    with SessionLocal() as db:
        aviso = db.scalar(
            select(Notificacion).where(
                Notificacion.tipo == TipoNotificacion.RECURSO_RECHAZADO
            )
        )
        assert aviso is not None


def test_no_se_puede_aprobar_si_la_reserva_ya_no_esta_activa(
    client, admin, crear_usuario
):
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    tipo_id = _tipo(client, admin)
    _unidad(client, admin, tipo_id)
    reserva_id, _ = _crear_reserva(
        docente, datetime.now(ZONA_COLOMBIA) + timedelta(days=1)
    )
    solicitud_id = _solicitar(client, docente, reserva_id, tipo_id, 1).json()["id"]

    with SessionLocal() as db:
        reserva = db.get(Reserva, reserva_id)
        reserva.estado = EstadoReserva.CANCELADA
        db.commit()

    decision = client.post(
        f"{RECURSOS}/solicitudes/{solicitud_id}/decision",
        json={"aprobar": True},
        headers=cabecera(admin),
    )
    assert decision.status_code == 409


# --------------------------------------------------------------------------- #
# HU-46: retraso
# --------------------------------------------------------------------------- #
def test_devolucion_tardia_genera_el_doble_de_strikes_sin_duplicar(
    client, admin, crear_usuario
):
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    tipo_id = _tipo(client, admin)
    _unidad(client, admin, tipo_id)
    reserva_id, _ = _crear_reserva(
        docente, datetime.now(ZONA_COLOMBIA) + timedelta(days=1)
    )
    solicitud_id = _solicitar(client, docente, reserva_id, tipo_id, 1).json()["id"]
    decision = client.post(
        f"{RECURSOS}/solicitudes/{solicitud_id}/decision",
        json={"aprobar": True},
        headers=cabecera(admin),
    )
    asignacion_id = decision.json()["asignaciones"][0]["id"]
    client.post(f"{RECURSOS}/asignaciones/{asignacion_id}/entrega", headers=cabecera(admin))

    # La reserva terminó hace 35 minutos: 3 bloques de 10 -> 6 strikes
    with SessionLocal() as db:
        asignacion = db.get(AsignacionRecurso, asignacion_id)
        asignacion.fin = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=35)
        asignacion.inicio = asignacion.fin - timedelta(hours=2)
        db.commit()

    primero = client.post(f"{RECURSOS}/procesar-retrasos", headers=cabecera(admin))
    assert primero.status_code == 200
    assert primero.json()["strikes"] == 6
    assert len(_strikes(docente.id)) == 6

    segundo = client.post(f"{RECURSOS}/procesar-retrasos", headers=cabecera(admin))
    assert segundo.json()["strikes"] == 0, "el barrido no duplica cargos"
    assert len(_strikes(docente.id)) == 6

    with SessionLocal() as db:
        aviso = db.scalar(
            select(Notificacion).where(
                Notificacion.tipo == TipoNotificacion.RECURSO_DEVOLUCION_TARDIA
            )
        )
        assert aviso is not None
        registro = db.scalar(
            select(Trazabilidad).where(
                Trazabilidad.accion == AccionTrazabilidad.RECURSO_PENALIZADO
            )
        )
        assert registro is not None

    # La devolución posterior no vuelve a penalizar
    devolucion = client.post(
        f"{RECURSOS}/asignaciones/{asignacion_id}/devolucion",
        json={"estado": "EN_FUNCIONAMIENTO"},
        headers=cabecera(admin),
    )
    assert devolucion.status_code == 200
    assert len(_strikes(docente.id)) == 6


# --------------------------------------------------------------------------- #
# HU-44, criterio 7: cancelación en cascada
# --------------------------------------------------------------------------- #
def test_cancelar_la_reserva_cancela_los_recursos_pendientes(
    client, admin, crear_usuario
):
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    tipo_id = _tipo(client, admin)
    _unidad(client, admin, tipo_id)
    reserva_id, _ = _crear_reserva(
        docente, datetime.now(ZONA_COLOMBIA) + timedelta(days=2)
    )
    solicitud_id = _solicitar(client, docente, reserva_id, tipo_id, 1).json()["id"]

    cancelacion = client.post(
        f"{RESERVAS}/{reserva_id}/cancelar",
        json={"motivo": "Cambio de actividad"},
        headers=cabecera(docente),
    )
    assert cancelacion.status_code == 200, cancelacion.text

    with SessionLocal() as db:
        solicitud = db.get(SolicitudRecurso, solicitud_id)
        assert solicitud.estado == EstadoSolicitudRecurso.CANCELADA
        aviso = db.scalar(
            select(Notificacion).where(
                Notificacion.tipo == TipoNotificacion.RECURSO_CANCELADO
            )
        )
        assert aviso is not None


def test_el_no_show_cancela_los_recursos_pendientes(client, admin, crear_usuario):
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=30)
    reserva_id, _ = _crear_reserva(docente, inicio)

    with SessionLocal() as db:
        solicitud = SolicitudRecurso(reserva_id=reserva_id, solicitante_id=docente.id)
        db.add(solicitud)
        db.commit()
        solicitud_id = solicitud.id

    from app.services import asistencia

    with SessionLocal() as db:
        asistencia.procesar_vencidas(db, datetime.now(ZONA_COLOMBIA))

    with SessionLocal() as db:
        assert db.get(SolicitudRecurso, solicitud_id).estado == (
            EstadoSolicitudRecurso.CANCELADA
        )
        assert db.get(Reserva, reserva_id).estado == EstadoReserva.NO_ASISTIO


# --------------------------------------------------------------------------- #
# Amenidades: el recurso es la amenidad y comparte stock (HU-19 / HU-43)
# --------------------------------------------------------------------------- #
ESPACIOS = "/api/v1/espacios"


def _tipo_con_stock(client, admin, cantidad: int = 4, nombre: str = "TV") -> dict:
    respuesta = client.post(
        f"{RECURSOS}/tipos",
        json={"nombre": f"{nombre} {uuid4().hex[:6]}", "cantidad": cantidad},
        headers=cabecera(admin),
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _espacio_api(client, admin, amenidades: list[int] | None = None):
    return client.post(
        f"{ESPACIOS}/",
        json={
            "nombre": f"Sala {uuid4().hex}",
            "tipo": "SALA",
            "capacidad": 10,
            "amenidades": amenidades or [],
        },
        headers=cabecera(admin),
    )


def test_crear_tipo_con_cantidad_genera_unidades_y_stock(client, admin):
    tipo = _tipo_con_stock(client, admin, cantidad=4)

    assert tipo["total"] == 4
    assert tipo["disponibles"] == 4
    assert tipo["instalados"] == 0

    with SessionLocal() as db:
        codigos = list(
            db.scalars(
                select(Recurso.codigo).where(Recurso.tipo_recurso_id == tipo["id"])
            )
        )
    assert len(codigos) == 4
    assert len(set(codigos)) == 4
    assert all(codigo.startswith("TV-") for codigo in codigos)


def test_crear_espacio_instala_la_amenidad_y_descuenta_el_stock(client, admin):
    tipo = _tipo_con_stock(client, admin, cantidad=2)

    respuesta = _espacio_api(client, admin, [tipo["id"]])
    assert respuesta.status_code == 201, respuesta.text
    espacio = respuesta.json()
    assert [amenidad["nombre"] for amenidad in espacio["amenidades"]] == [tipo["nombre"]]

    amenidades = client.get(
        f"{RECURSOS}/amenidades",
        params={"espacio_id": espacio["id"]},
        headers=cabecera(admin),
    )
    assert amenidades.status_code == 200, amenidades.text
    fila = next(a for a in amenidades.json() if a["tipo_recurso_id"] == tipo["id"])
    assert fila["instalado_aqui"] is True
    assert fila["instalados"] == 1
    assert fila["disponibles"] == 1


def test_no_se_puede_instalar_una_amenidad_sin_stock(client, admin):
    tipo = _tipo_con_stock(client, admin, cantidad=0)

    respuesta = _espacio_api(client, admin, [tipo["id"]])

    assert respuesta.status_code == 409, respuesta.text
    assert "No quedan unidades" in respuesta.json()["detail"]


def test_quitar_una_amenidad_devuelve_la_unidad_al_stock(client, admin):
    tipo = _tipo_con_stock(client, admin, cantidad=1)
    espacio = _espacio_api(client, admin, [tipo["id"]]).json()

    respuesta = client.patch(
        f"{ESPACIOS}/{espacio['id']}",
        json={"amenidades": []},
        headers=cabecera(admin),
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["amenidades"] == []

    tipos = client.get(
        f"{RECURSOS}/tipos", params={"solo_activos": True}, headers=cabecera(admin)
    ).json()
    fila = next(t for t in tipos if t["id"] == tipo["id"])
    assert fila["instalados"] == 0
    assert fila["disponibles"] == 1


def test_no_se_puede_reducir_la_cantidad_si_la_unidad_esta_instalada(client, admin):
    tipo = _tipo_con_stock(client, admin, cantidad=1)
    _espacio_api(client, admin, [tipo["id"]])

    respuesta = client.patch(
        f"{RECURSOS}/tipos/{tipo['id']}",
        json={"cantidad": 0},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 409, respuesta.text
    assert "instalado en espacios" in respuesta.json()["detail"]


def test_bajar_la_cantidad_retira_solo_las_unidades_libres(client, admin):
    tipo = _tipo_con_stock(client, admin, cantidad=3)
    _espacio_api(client, admin, [tipo["id"]])

    respuesta = client.patch(
        f"{RECURSOS}/tipos/{tipo['id']}",
        json={"cantidad": 1},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["total"] == 1
    assert respuesta.json()["instalados"] == 1
    assert respuesta.json()["disponibles"] == 0


def test_solo_admin_y_aprobador_ven_las_amenidades(client, solicitante):
    respuesta = client.get(f"{RECURSOS}/amenidades", headers=cabecera(solicitante))
    assert respuesta.status_code == 403
